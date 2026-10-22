"""The fixed Ed25519 invoice JWS profile and full signed-artifact identity.

Parsing establishes wire validity. Only verification with an application-trusted
provider key authenticates the offer; enrollment and admission stay outside.
"""

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .codec import MAX_BYTES, _load, decode_invoice
from .errors import InvoiceError

INVOICE_TYPE = "application/vnd.signed-invoice.v1+json"
MAX_PROTECTED_BYTES = 256
MAX_JSON_BYTES = 32768
MAX_PROTECTED_LENGTH = (4 * MAX_PROTECTED_BYTES + 2) // 3
MAX_PAYLOAD_LENGTH = (4 * MAX_BYTES + 2) // 3
SIGNATURE_LENGTH = 86
MAX_COMPACT_LENGTH = MAX_PROTECTED_LENGTH + MAX_PAYLOAD_LENGTH + SIGNATURE_LENGTH + 2
BASE64URL = re.compile(r"[A-Za-z0-9_-]+")
PROTECTED_BYTES = json.dumps({"alg": "Ed25519", "typ": INVOICE_TYPE}, separators=(",", ":")).encode("ascii")


def _encode_segment(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_segment(value, maximum, name):
    if type(value) is not str:
        raise TypeError(f"Invoice JWS {name} must be a string.")
    if len(value) > (4 * maximum + 2) // 3 or BASE64URL.fullmatch(value) is None:
        raise InvoiceError(f"Cannot parse invoice JWS: {name} must be bounded unpadded base64url.")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except binascii.Error as exc:
        raise InvoiceError(f"Cannot parse invoice JWS: {name} is not unpadded base64url.") from exc
    if len(raw) > maximum or _encode_segment(raw) != value:
        raise InvoiceError(f"Cannot parse invoice JWS: {name} must use canonical unpadded base64url within its limit.")
    return raw


@dataclass(frozen=True, slots=True)
class SignedInvoice:
    """Exact JWS segments with validated syntax/profile, without a trust claim.

    Header whitespace and ordering are significant signed bytes. Outer JSON
    ordering and whitespace are not part of this artifact's identity.
    """

    protected: str = field(metadata={"min_length": 1, "max_length": MAX_PROTECTED_LENGTH})
    payload: str = field(metadata={"min_length": 1, "max_length": MAX_PAYLOAD_LENGTH})
    signature: str = field(metadata={"min_length": SIGNATURE_LENGTH, "max_length": SIGNATURE_LENGTH})

    def __post_init__(self):
        header = _load(_decode_segment(self.protected, MAX_PROTECTED_BYTES, "protected"))
        if type(header) is not dict or header.keys() != {"alg", "typ"} or header["alg"] != "Ed25519":
            raise InvoiceError(
                "Cannot parse invoice JWS: protected header must contain only alg Ed25519 and the invoice profile typ."
            )
        typ = header["typ"]
        if type(typ) is not str or not typ.isascii():
            raise InvoiceError("Cannot parse invoice JWS: typ must identify the invoice media type.")
        # RFC 7515 section 4.1.9: media types ignore case and may omit application/.
        media_type = typ if "/" in typ else "application/" + typ
        if media_type.lower() != INVOICE_TYPE:
            raise InvoiceError("Cannot parse invoice JWS: typ does not identify the invoice profile.")
        decode_invoice(self.payload_bytes)
        if len(_decode_segment(self.signature, 64, "signature")) != 64:
            raise InvoiceError("Cannot parse invoice JWS: Ed25519 signature must contain exactly 64 bytes.")

    @classmethod
    def from_json(cls, raw: bytes):
        """Parse duplicate-aware flattened JWS JSON within the 32768-byte bound."""
        if type(raw) is not bytes:
            raise TypeError("Invoice JWS JSON must be supplied as exact UTF-8 bytes.")
        if len(raw) > MAX_JSON_BYTES:
            raise InvoiceError("Cannot parse invoice JWS: flattened JSON exceeds 32768 bytes.")
        fields = _load(raw)
        if type(fields) is not dict or fields.keys() != {"protected", "payload", "signature"}:
            raise InvoiceError("Cannot parse invoice JWS: flattened JSON must contain exactly protected, payload and signature.")
        if any(type(value) is not str for value in fields.values()):
            raise InvoiceError("Cannot parse invoice JWS: all three flattened members must be strings.")
        return cls(**fields)

    @classmethod
    def from_compact(cls, compact: str):
        """Read the exact bounded three-segment compact artifact, without normalization."""
        if type(compact) is not str:
            raise TypeError("Compact invoice JWS must be a string.")
        if len(compact) > MAX_COMPACT_LENGTH or compact.count(".") != 2:
            raise InvoiceError("Cannot parse invoice JWS: compact form must contain three bounded base64url segments.")
        return cls(*compact.split("."))

    @property
    def compact(self) -> str:
        return self.protected + "." + self.payload + "." + self.signature

    @property
    def signing_input(self) -> bytes:
        return (self.protected + "." + self.payload).encode("ascii")

    @property
    def payload_bytes(self) -> bytes:
        return _decode_segment(self.payload, MAX_BYTES, "payload")

    @property
    def document(self) -> dict:
        """Return a fresh validated projection, without authenticating it."""
        return decode_invoice(self.payload_bytes)

    @property
    def invoice_hash(self) -> str:
        return invoice_hash(self)

    def to_dict(self) -> dict[str, str]:
        return {"protected": self.protected, "payload": self.payload, "signature": self.signature}

    def to_json(self) -> bytes:
        return json.dumps(self.to_dict(), separators=(",", ":")).encode("ascii")


def invoice_hash(artifact: SignedInvoice) -> str:
    """Hash the entire signed compact artifact, without authenticating its signature."""
    if type(artifact) is not SignedInvoice:
        raise TypeError("Invoice hashing requires a SignedInvoice artifact.")
    return "0x" + hashlib.sha256(artifact.compact.encode("ascii")).hexdigest()


def _require_provider(document, public_key):
    if document["provider"] != _encode_segment(public_key.public_bytes_raw()):
        raise InvoiceError("Cannot authenticate invoice: provider differs from the signature key.")


def sign_invoice(raw: bytes, private_key: Ed25519PrivateKey) -> SignedInvoice:
    """Sign exact payload bytes under the fixed protected profile; require provider equality."""
    document = decode_invoice(raw)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("Invoice signing requires an Ed25519 private key.")
    _require_provider(document, private_key.public_key())
    protected, payload = _encode_segment(PROTECTED_BYTES), _encode_segment(raw)
    signature = private_key.sign((protected + "." + payload).encode("ascii"))
    return SignedInvoice(protected, payload, _encode_segment(signature))


def verify_invoice(artifact: SignedInvoice, *, public_key: Ed25519PublicKey) -> dict:
    """Authenticate the carried segments and provider against an application-trusted key."""
    if type(artifact) is not SignedInvoice:
        raise TypeError("Invoice verification requires a SignedInvoice artifact.")
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("Invoice verification requires a trusted Ed25519 public key.")
    document = artifact.document
    _require_provider(document, public_key)
    try:
        public_key.verify(_decode_segment(artifact.signature, 64, "signature"), artifact.signing_input)
    except InvalidSignature as exc:
        raise InvoiceError(
            "Cannot verify invoice JWS: signature does not match the trusted provider key and exact segments."
        ) from exc
    return document
