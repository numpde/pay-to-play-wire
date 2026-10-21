"""Five-field invoice wire grammar and exact-byte cryptography.

Verification takes an explicitly trusted provider key. Neither a parsed
invoice nor its beneficiary key supplies that trust. Keep original bytes for
storage and retransmission; parsing does not authenticate an offer or admit it.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .errors import InvoiceError
from .fields import (
    MAX_TIMESTAMP,
    UNSIGNED,
    require_amount,
    require_asset,
    require_best_before,
    require_public_key,
)

# Fixed wire grammar and bounds, independent of payment admission policy.
MAX_BYTES = 16384
MAX_DEPTH = 16
FIELDS = frozenset({"provider", "payment", "bestBefore", "beneficiary", "service"})
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


@dataclass(frozen=True)
class JsonNumber:
    """A product-owned JSON number, preserving its lexical value without rounding.

    Use this for fractions, exponents or very large nested integers. Generic
    decoding leaves these numbers opaque; merchants own their interpretation.
    """

    token: str

    def __post_init__(self):
        if type(self.token) is not str or NUMBER.fullmatch(self.token) is None:
            raise InvoiceError("Cannot encode JSON number: expected a finite JSON number token.")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvoiceError("Cannot decode invoice JSON: duplicate object member.")
        result[key] = value
    return result


def _constant(_token):
    raise InvoiceError("Cannot decode invoice JSON: NaN and Infinity are not JSON numbers.")


def _check_tree(value, depth):
    if isinstance(value, (dict, list)):
        depth += 1
        if depth > MAX_DEPTH:
            raise InvoiceError("Cannot decode invoice JSON: container depth exceeds 16.")
        if isinstance(value, dict):
            for key in value:
                _check_tree(key, depth)
            children = value.values()
        else:
            children = value
        for child in children:
            _check_tree(child, depth)
    elif isinstance(value, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise InvoiceError("Cannot decode invoice JSON: unpaired Unicode surrogate.")


def _load(raw):
    if type(raw) is not bytes:
        raise TypeError("Invoice JSON must be supplied as exact UTF-8 bytes.")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_object,
            parse_int=JsonNumber,
            parse_float=JsonNumber,
            parse_constant=_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InvoiceError("Cannot decode invoice JSON: expected strict UTF-8 JSON without a BOM.") from exc
    _check_tree(value, 0)
    return value


def decode_invoice(raw: bytes) -> dict:
    """Validate original bytes and return fresh fields, with lossless nested numbers.

    bestBefore becomes a Python integer after lexical validation.
    Product numbers remain JsonNumber instances. Keep raw for hashing/signatures.
    """
    if type(raw) is not bytes:
        raise TypeError("Invoice must be supplied as exact UTF-8 bytes.")
    if len(raw) > MAX_BYTES:
        raise InvoiceError("Cannot decode invoice: document exceeds 16384 bytes.")
    fields = _load(raw)
    if type(fields) is not dict or fields.keys() != FIELDS:
        raise InvoiceError(
            "Cannot decode invoice: document must contain exactly provider, payment, bestBefore, beneficiary and service."
        )
    payment = fields["payment"]
    if type(payment) is not dict or payment.keys() != {"asset", "amount"}:
        raise InvoiceError("Cannot decode invoice: payment must contain exactly asset and amount.")
    field = "provider"
    try:
        require_public_key(fields[field], field)
        field = "beneficiary"
        require_public_key(fields[field], field)
        field = "payment.asset"
        require_asset(payment["asset"], field)
        field = "payment.amount"
        require_amount(payment["amount"], field)
    except TypeError as exc:
        raise InvoiceError(f"Cannot decode invoice: {field} has the wrong JSON type.") from exc
    number = fields["bestBefore"]
    if type(number) is not JsonNumber:
        raise InvoiceError("Cannot decode invoice: bestBefore must be a JSON integer token.")
    # Lexical checks precede bounded conversion; the scalar owner checks range.
    if UNSIGNED.fullmatch(number.token) is None or len(number.token) > len(str(MAX_TIMESTAMP)):
        raise InvoiceError("Cannot decode invoice: bestBefore must be a canonical JSON integer within range.")
    fields["bestBefore"] = require_best_before(int(number.token))
    return fields


def _encode(value, depth):
    # Explicit number tokens keep foreign product numbers exact on re-encoding.
    if type(value) is JsonNumber:
        return value.token
    if type(value) in (dict, list):
        if depth >= MAX_DEPTH:
            raise InvoiceError("Cannot encode invoice: container depth exceeds 16.")
        if type(value) is list:
            return "[" + ",".join(_encode(item, depth + 1) for item in value) + "]"
        if any(type(key) is not str for key in value):
            raise InvoiceError("Cannot encode invoice: object member names must be strings.")
        return "{" + ",".join(_encode(key, 0) + ":" + _encode(item, depth + 1) for key, item in value.items()) + "}"
    if value is None or type(value) in (str, bool, int):
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    raise InvoiceError("Cannot encode invoice: use JSON values and JsonNumber for fractional or exponent numbers.")


def encode_invoice(fields: dict) -> bytes:
    """Serialize fields once in insertion order, then validate the wire document.

    Persist the returned bytes before signing. Retry from that stored intent;
    calling this again does not recover an earlier issuance or its deadlines.
    """
    if type(fields) is not dict:
        raise TypeError("Invoice encoding requires a dictionary of document fields.")
    try:
        raw = _encode(fields, 0).encode("utf-8", errors="strict")
    except (UnicodeEncodeError, ValueError) as exc:
        if isinstance(exc, InvoiceError):
            raise
        raise InvoiceError("Cannot encode invoice: fields cannot be represented as strict UTF-8 JSON.") from exc
    decode_invoice(raw)
    return raw


def invoice_signing_message(raw: bytes, *, domain: bytes) -> bytes:
    """Prepend the caller's trusted domain exactly, without adding delimiters."""
    if type(domain) is not bytes:
        raise TypeError("Invoice signing domain must be supplied as exact bytes.")
    if not domain:
        raise ValueError("Cannot construct invoice signing message: the signing domain must not be empty.")
    decode_invoice(raw)
    return domain + raw


def invoice_hash(raw: bytes, *, domain: bytes) -> str:
    """Return the voucher/API hash of a well-formed invoice, without authenticating it."""
    return "0x" + hashlib.sha256(invoice_signing_message(raw, domain=domain)).hexdigest()


def sign_invoice_detached(raw: bytes, private_key: Ed25519PrivateKey, *, domain: bytes) -> bytes:
    """Sign a validated original document; return its detached 64-byte signature.

    The private key must match provider. The issuer owns that key's authority.
    This function performs no I/O, persistence, enrollment or key lookup.
    """
    message = invoice_signing_message(raw, domain=domain)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("Invoice signing requires an Ed25519 private key.")
    _require_provider(raw, private_key.public_key())
    return private_key.sign(message)


def encode_envelope(raw: bytes, signature: bytes) -> bytes:
    """Encode validated invoice/signature bytes; this does not authenticate them."""
    decode_invoice(raw)
    if type(signature) is not bytes:
        raise TypeError("Invoice envelope signature must be supplied as bytes.")
    if len(signature) != 64:
        raise InvoiceError("Cannot encode invoice envelope: Ed25519 signature must contain exactly 64 bytes.")
    envelope = {
        "bytes": base64.b64encode(raw).decode("ascii"),
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    return json.dumps(envelope, separators=(",", ":")).encode("ascii")


def sign_invoice(raw: bytes, private_key: Ed25519PrivateKey, *, domain: bytes) -> bytes:
    """Sign unchanged invoice bytes and return the compact JSON envelope."""
    signature = sign_invoice_detached(raw, private_key, domain=domain)
    return encode_envelope(raw, signature)


def _base64(value, limit, field):
    if type(value) is not str or len(value) > 4 * ((limit + 2) // 3):
        raise InvoiceError(f"Cannot decode invoice envelope: {field} must be bounded standard base64.")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InvoiceError(f"Cannot decode invoice envelope: {field} is not standard base64.") from exc
    if len(decoded) > limit or base64.b64encode(decoded).decode("ascii") != value:
        raise InvoiceError(f"Cannot decode invoice envelope: {field} is not canonical padded base64 within its limit.")
    return decoded


def decode_envelope(envelope: bytes) -> tuple[bytes, bytes]:
    """Return validated (invoice, signature) bytes without authenticating them.

    Supply original JSON bytes to retain duplicate-member rejection. The
    transport boundary owns the overall body limit, including whitespace.
    """
    envelope = _load(envelope)
    if type(envelope) is not dict or envelope.keys() != {"bytes", "signature"}:
        raise InvoiceError("Cannot decode invoice envelope: envelope must contain exactly bytes and signature.")
    raw = _base64(envelope["bytes"], MAX_BYTES, "bytes")
    signature = _base64(envelope["signature"], 64, "signature")
    if len(signature) != 64:
        raise InvoiceError("Cannot decode invoice envelope: Ed25519 signature must contain exactly 64 bytes.")
    decode_invoice(raw)
    return raw, signature


def _require_provider(raw: bytes, public_key: Ed25519PublicKey) -> None:
    provider = decode_invoice(raw)["provider"]
    encoded = base64.urlsafe_b64encode(public_key.public_bytes_raw()).rstrip(b"=").decode("ascii")
    if provider != encoded:
        raise InvoiceError("Cannot authenticate invoice: provider differs from the signature key.")


def verify_invoice(
    envelope: bytes,
    *,
    domain: bytes,
    public_key: Ed25519PublicKey,
) -> bytes:
    """Bind provider to the caller-trusted Ed25519 key; return authenticated bytes.

    Pass the original envelope JSON bytes so duplicate members cannot be lost.
    The HTTP boundary owns the overall body limit. Enrollment, retirement/
    compromise policy and payment admission are the caller's responsibilities.
    """
    raw, signature = decode_envelope(envelope)
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("Invoice verification requires a trusted Ed25519 public key.")
    _require_provider(raw, public_key)
    try:
        public_key.verify(signature, invoice_signing_message(raw, domain=domain))
    except InvalidSignature as exc:
        raise InvoiceError("Cannot verify invoice: signature does not match the trusted provider key and exact bytes.") from exc
    return raw
