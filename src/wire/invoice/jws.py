"""Invoice provider binding and full signed-artifact identity over the fixed JWS owner."""

import hashlib
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from wire._jws import MAX_JSON_BYTES as MAX_JSON_BYTES
from wire._jws import Profile, SignedJWS, encode_segment, sign_segments, verify_signature

from .codec import decode_invoice
from .errors import InvoiceError

INVOICE_TYPE = "application/vnd.signed-invoice.v1+json"


@dataclass(frozen=True, slots=True)
class SignedInvoice(SignedJWS):
    """Exact invoice JWS segments with validated syntax/profile, without a trust claim."""

    _profile = Profile(
        name="invoice",
        media_type=INVOICE_TYPE,
        error=InvoiceError,
        decode_payload=decode_invoice,
        key_role="provider",
        description="Fixed-profile Ed25519 invoice JWS. Structural validity does not authenticate or authorize the provider.",
    )

    @property
    def invoice_hash(self) -> str:
        return invoice_hash(self)


PROTECTED_BYTES = SignedInvoice._profile.protected_bytes


def invoice_hash(artifact: SignedInvoice) -> str:
    """Hash the entire signed compact artifact, without authenticating its signature."""
    if type(artifact) is not SignedInvoice:
        raise TypeError("Invoice hashing requires a SignedInvoice artifact.")
    return "0x" + hashlib.sha256(artifact.compact.encode("ascii")).hexdigest()


def _require_provider(document, public_key):
    if document["provider"] != encode_segment(public_key.public_bytes_raw()):
        raise InvoiceError("Cannot authenticate invoice: provider differs from the signature key.")


def sign_invoice(raw: bytes, private_key: Ed25519PrivateKey) -> SignedInvoice:
    """Sign exact payload bytes under the fixed protected profile; require provider equality."""
    document = decode_invoice(raw)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("Invoice signing requires an Ed25519 private key.")
    _require_provider(document, private_key.public_key())
    return sign_segments(raw, private_key, SignedInvoice)


def verify_invoice(artifact: SignedInvoice, *, public_key: Ed25519PublicKey) -> dict:
    """Authenticate the carried segments and provider against an application-trusted key."""
    if type(artifact) is not SignedInvoice:
        raise TypeError("Invoice verification requires a SignedInvoice artifact.")
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("Invoice verification requires a trusted Ed25519 public key.")
    document = artifact.document
    _require_provider(document, public_key)
    verify_signature(artifact, public_key)
    return document
