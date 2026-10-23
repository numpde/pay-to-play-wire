"""Acceptance binds its signing key, one complete voucher and signing time."""

import json

from wire._json import MAX_SAFE_INTEGER, UNSIGNED, NumberToken, load_json
from wire._jws import MAX_PAYLOAD_BYTES
from wire._keys import require_public_key
from wire.voucher import SignedVoucher

MAX_ACCEPTED_AT = MAX_SAFE_INTEGER


class AcceptanceError(ValueError):
    """An acceptance payload, protected profile or signature is invalid."""

    canonical_json_hint: str | None = None


def _document(value):
    if type(value) is not dict or value.keys() != {"signer", "voucher", "acceptedAt"}:
        raise AcceptanceError("Cannot parse acceptance: payload must contain exactly signer, voucher and acceptedAt.")
    try:
        signer = require_public_key(value["signer"], "acceptance signer", error=AcceptanceError)
    except TypeError as exc:
        raise AcceptanceError("Cannot parse acceptance: signer must be an encoded Ed25519 public key string.") from exc
    accepted_at = value["acceptedAt"]
    if type(accepted_at) is not int or not 0 <= accepted_at <= MAX_ACCEPTED_AT:
        raise AcceptanceError("Cannot parse acceptance: acceptedAt must be integer Unix seconds in 0..2^53-1.")
    try:
        voucher = SignedVoucher.from_dict(value["voucher"])
    except (TypeError, ValueError) as exc:
        raise AcceptanceError("Cannot parse acceptance: voucher must be a complete strict PayToPlay/2 signed voucher.") from exc
    return {"signer": signer, "voucher": voucher.to_dict(), "acceptedAt": accepted_at}


def decode_acceptance(raw: bytes) -> dict:
    """Parse exact bounded JSON, retaining the original voucher signature value."""
    if type(raw) is not bytes:
        raise TypeError("Acceptance payload must be supplied as exact UTF-8 bytes.")
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise AcceptanceError("Cannot parse acceptance: payload exceeds 16384 bytes.")
    value = load_json(raw, error=AcceptanceError, name="acceptance")
    if type(value) is dict and "acceptedAt" in value:
        number = value["acceptedAt"]
        if (
            type(number) is not NumberToken
            or UNSIGNED.fullmatch(number.token) is None
            or len(number.token) > len(str(MAX_ACCEPTED_AT))
        ):
            raise AcceptanceError("Cannot parse acceptance: acceptedAt must be a canonical nonnegative JSON integer token.")
        value["acceptedAt"] = int(number.token)
    return _document(value)


def encode_acceptance(document: dict) -> bytes:
    """Serialize the acceptance fields once and validate their wire representation."""
    if type(document) is not dict:
        raise TypeError("Acceptance encoding requires a dictionary of payload fields.")
    raw = json.dumps(_document(document), separators=(",", ":")).encode("ascii")
    decode_acceptance(raw)
    return raw
