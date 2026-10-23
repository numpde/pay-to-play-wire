"""Canonical Ed25519 public-key text shared by signed payload profiles."""

import base64
import re

PUBLIC_KEY = re.compile(r"[A-Za-z0-9_-]{43}")


def require_public_key(value, name, *, error):
    """Validate canonical public-key text with the caller's protocol error."""
    if type(value) is not str:
        raise TypeError(f"Cannot validate {name}: the public key must be a string.")
    if PUBLIC_KEY.fullmatch(value) is None:
        raise error(f"Cannot validate {name}: use 43 unpadded base64url characters for an Ed25519 public key.")
    # Copied from invoice.fields, adapted from Mail's JWK x decoder.
    # Re-encoding rejects unused pad bits.
    decoded = base64.urlsafe_b64decode(value + "=")
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
        raise error(f"Cannot validate {name}: the Ed25519 public key must use canonical base64url.")
    return value
