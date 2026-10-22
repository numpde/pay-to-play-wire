"""Strict five-field payload grammar, preserving original UTF-8 and JSON numbers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

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
        if type(self.token) is not str:
            raise TypeError("JSON number tokens must be strings.")
        if NUMBER.fullmatch(self.token) is None:
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
