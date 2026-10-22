"""Invoice scalar representations; applications own trust and payment policy."""

import base64
import re

from wire._json import MAX_SAFE_INTEGER
from wire._json import UNSIGNED as UNSIGNED

from .errors import InvoiceError

MAX_TIMESTAMP = MAX_SAFE_INTEGER
MAX_AMOUNT_DIGITS = 16384
POSITIVE = re.compile(r"[1-9][0-9]*")
PUBLIC_KEY = re.compile(r"[A-Za-z0-9_-]{43}")
ASSET = re.compile(r"[-a-z0-9]{3,8}:[-_a-zA-Z0-9]{1,32}/[-a-z0-9]{3,8}:[-.%a-zA-Z0-9]{1,128}(?:/[-.%a-zA-Z0-9]{1,78})?")


def require_public_key(value: str, name: str = "public key") -> str:
    """Require canonical unpadded base64url of 32 Ed25519 public bytes."""
    if type(value) is not str:
        raise TypeError(f"Cannot validate {name}: the public key must be a string.")
    if PUBLIC_KEY.fullmatch(value) is None:
        raise InvoiceError(f"Cannot validate {name}: use 43 unpadded base64url characters for an Ed25519 public key.")
    # Adapted from Mail's public JWK x decoder; re-encoding rejects unused pad bits.
    decoded = base64.urlsafe_b64decode(value + "=")
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
        raise InvoiceError(f"Cannot validate {name}: the Ed25519 public key must use canonical base64url.")
    return value


def require_asset(value: str, name: str = "asset") -> str:
    """Require CAIP-19 asset type or asset ID syntax, preserving case and spelling."""
    if type(value) is not str:
        raise TypeError(f"Cannot validate {name}: the asset identifier must be a string.")
    if ASSET.fullmatch(value) is None:
        raise InvoiceError(f"Cannot validate {name}: use a CAIP-19 asset type or asset ID within its component bounds.")
    return value


def require_amount(value: str, name: str = "amount") -> str:
    """Require positive decimal base units; the adapter owns narrower numeric bounds."""
    if type(value) is not str:
        raise TypeError(f"Cannot validate {name}: the amount must be a decimal string.")
    if len(value) > MAX_AMOUNT_DIGITS or POSITIVE.fullmatch(value) is None:
        raise InvoiceError(f"Cannot validate {name}: use a positive decimal string without leading zeros, at most 16384 digits.")
    return value


def require_best_before(value: int, name: str = "bestBefore") -> int:
    """Require Unix seconds in 0..2^53-1 without consulting a clock."""
    if type(value) is not int:
        raise TypeError(f"Cannot validate {name}: Unix seconds must be an integer.")
    if not 0 <= value <= MAX_TIMESTAMP:
        raise InvoiceError(f"Cannot validate {name}: Unix seconds must be between 0 and 2^53-1.")
    return value
