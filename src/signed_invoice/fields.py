"""Shared scalar wire facts for offers and complete invoice documents.

These validators return the original value without normalization or conversion.
They impose no enrollment, expiry, price, consent or deployment policy.
"""

import re

from .errors import InvoiceError

NATIVE_ASSET = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
EVM_ADDRESS_PATTERN = r"^0x[0-9a-f]{40}$"
EVM_ADDRESS_LENGTH = 42
UINT256_MAX = (1 << 256) - 1
MAX_TIMESTAMP = (1 << 53) - 1
UNSIGNED = re.compile(r"0|[1-9][0-9]*")
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}")
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
ADDRESS = re.compile(EVM_ADDRESS_PATTERN)


def require_merchant_id(value: str, name: str = "merchant id") -> str:
    """Require the lowercase hyphenated UUID representation, without UUID-version policy."""
    if type(value) is not str:
        raise TypeError(f"Cannot validate {name}: the value must be a string.")
    if UUID.fullmatch(value) is None:
        raise InvoiceError(f"Cannot validate {name}: the value must be a lowercase hyphenated UUID.")
    return value


def require_identifier(value: str, name: str = "identifier") -> str:
    """Require 1..128 case-sensitive ASCII letters, digits, underscores or hyphens."""
    if type(value) is not str:
        raise TypeError(f"Cannot validate {name}: the value must be a string.")
    if IDENTIFIER.fullmatch(value) is None:
        raise InvoiceError(f"Cannot validate {name}: use 1 to 128 ASCII letters, digits, underscores or hyphens.")
    return value


def require_evm_address(value: str, name: str = "address") -> str:
    """Require a lowercase 20-byte EVM address, without proving account or code identity."""
    if type(value) is not str:
        raise TypeError(f"Cannot validate {name}: the value must be a string.")
    if ADDRESS.fullmatch(value) is None:
        raise InvoiceError(f"Cannot validate {name}: the value must be a lowercase 20-byte EVM address.")
    return value


def require_asset(value: str, name: str = "asset") -> str:
    """Require the explicit nonzero asset identifier; denomination remains chain-scoped."""
    require_evm_address(value, name)
    if value == "0x" + "0" * 40:
        raise InvoiceError(f"Cannot validate {name}: zero is not an asset identifier; native assets use ERC-7528.")
    return value


def require_uint256(value: str, name: str = "integer", *, positive: bool = False) -> str:
    """Require a canonical uint256 decimal string; positive excludes zero."""
    if type(value) is not str:
        raise TypeError(f"Cannot validate {name}: the value must be a decimal string.")
    if type(positive) is not bool:
        raise TypeError("Unsigned integer validation requires a boolean positive constraint.")
    maximum = str(UINT256_MAX)
    if len(value) > len(maximum) or UNSIGNED.fullmatch(value) is None or (len(value) == len(maximum) and value > maximum):
        raise InvoiceError(f"Cannot validate {name}: the value must be a canonical unsigned integer within uint256 range.")
    if positive and value == "0":
        raise InvoiceError(f"Cannot validate {name}: the value must be greater than zero.")
    return value


def require_deadline(value: int, name: str = "deadline") -> int:
    """Require an exact integer in 0..2^53-1; this does not check time or ordering."""
    if type(value) is not int:
        raise TypeError(f"Cannot validate {name}: the value must be an integer.")
    if not 0 <= value <= MAX_TIMESTAMP:
        raise InvoiceError(f"Cannot validate {name}: the value must be between 0 and 2^53-1.")
    return value
