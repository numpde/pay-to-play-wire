"""Canonical UTF-8 JSON bytes, without schema, signature or trust claims."""

import math
from dataclasses import dataclass

import rfc8785

from ._json import MAX_DEPTH, MAX_DOCUMENT_BYTES, MAX_SAFE_INTEGER, load_json


class CanonicalJSONError(ValueError):
    """JSON cannot be represented or admitted under the canonical wire rules."""


def _number(token):
    if "." not in token and "e" not in token.lower() and len(token) <= 17:
        value = int(token)
        if abs(value) <= MAX_SAFE_INTEGER:
            return value
    return float(token)


def _validate(value, maximum):
    remaining = maximum

    def visit(item, depth):
        nonlocal remaining
        # Bound traversal and allocation before serialization; encoded size is checked below.
        remaining -= 1 + (len(item) if type(item) is str else 0)
        if remaining < 0:
            raise CanonicalJSONError("Cannot encode canonical JSON: value exceeds the supplied byte limit.")
        if type(item) is str:
            if any(
                0xD800 <= ord(char) <= 0xDFFF or 0xFDD0 <= ord(char) <= 0xFDEF or ord(char) & 0xFFFF in (0xFFFE, 0xFFFF)
                for char in item
            ):
                raise CanonicalJSONError("Cannot encode canonical JSON: strings must contain valid I-JSON Unicode characters.")
        elif type(item) in (list, dict):
            if depth >= MAX_DEPTH:
                raise CanonicalJSONError("Cannot encode canonical JSON: container depth exceeds 16.")
            if type(item) is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise CanonicalJSONError("Cannot encode canonical JSON: object member names must be strings.")
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
        elif type(item) is int:
            if abs(item) > MAX_SAFE_INTEGER:
                raise CanonicalJSONError("Cannot encode canonical JSON: exact integers outside the safe range must use strings.")
        elif type(item) is float:
            if not math.isfinite(item):
                raise CanonicalJSONError("Cannot encode canonical JSON: numbers must be finite binary64 values.")
        elif item is not None and type(item) is not bool:
            raise CanonicalJSONError("Cannot encode canonical JSON: use JSON values; exact decimal values must use strings.")

    visit(value, 0)


def _maximum(value):
    if type(value) is not int:
        raise TypeError("Canonical JSON byte limit must be an integer.")
    if value < 1:
        raise ValueError("Canonical JSON byte limit must be positive.")
    return value


def _encode(value, maximum):
    _validate(value, maximum)
    raw = rfc8785.dumps(value)
    if len(raw) > maximum:
        raise CanonicalJSONError("Cannot encode canonical JSON: encoded bytes exceed the supplied byte limit.")
    return raw


def _read(raw):
    return load_json(raw, error=CanonicalJSONError, name="canonical", number_type=_number)


@dataclass(frozen=True, slots=True, init=False)
class CanonicalJSON:
    """An immutable admitted byte value; .value returns a fresh JSON projection.

    Numbers follow JCS binary64 semantics. Exact large integers and decimal
    quantities belong in schema-defined strings. Admission never rewrites bytes.
    """

    _raw: bytes

    def __init__(self, raw: bytes, *, max_bytes: int = MAX_DOCUMENT_BYTES):
        maximum = _maximum(max_bytes)
        if type(raw) is not bytes:
            raise TypeError("Canonical JSON must be supplied as exact UTF-8 bytes.")
        if len(raw) > maximum:
            raise CanonicalJSONError("Cannot admit canonical JSON: bytes exceed the supplied byte limit.")
        value = _read(raw)
        if _encode(value, maximum) != raw:
            raise CanonicalJSONError("Cannot admit canonical JSON: received bytes must already use the canonical encoding.")
        object.__setattr__(self, "_raw", raw)

    @classmethod
    def encode(cls, value, *, max_bytes: int = MAX_DOCUMENT_BYTES):
        """Canonicalize unsigned JSON values; never coerce exact-number wrappers."""
        raw = _encode(value, _maximum(max_bytes))
        # The encoder establishes canonicality; received-byte admission is separate.
        result = object.__new__(cls)
        object.__setattr__(result, "_raw", raw)
        return result

    @classmethod
    def from_bytes(cls, raw: bytes, *, max_bytes: int = MAX_DOCUMENT_BYTES):
        """Admit only already-canonical bytes; this does not authenticate them."""
        return cls(raw, max_bytes=max_bytes)

    @property
    def bytes(self) -> bytes:
        return self._raw

    @property
    def value(self):
        return _read(self._raw)

    def __bytes__(self):
        return self._raw
