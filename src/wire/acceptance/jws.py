"""Authenticate original acceptance JWS segments with an explicitly trusted Ed25519 key."""

from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from wire._jws import Profile, SignedJWS, encode_segment, sign_segments, verify_signature
from wire.voucher import SignedVoucher

from .codec import AcceptanceError, decode_acceptance

ACCEPTANCE_TYPE = "application/vnd.signed-purchase-acceptance.v2+json"


@dataclass(frozen=True, slots=True)
class SignedAcceptance(SignedJWS):
    """A structurally valid acceptance; only explicit verification authenticates its signer."""

    _profile = Profile(
        name="acceptance",
        media_type=ACCEPTANCE_TYPE,
        error=AcceptanceError,
        decode_payload=decode_acceptance,
        key_role="acceptance",
        description="Fixed-profile Ed25519 purchase acceptance JWS. Parsing does not authenticate the acceptance or voucher signer.",
    )

    @property
    def signer(self) -> str:
        return self.document["signer"]

    @property
    def voucher(self) -> SignedVoucher:
        return SignedVoucher.from_dict(self.document["voucher"])

    @property
    def accepted_at(self) -> int:
        return self.document["acceptedAt"]


def _require_signer(document, public_key):
    if document["signer"] != encode_segment(public_key.public_bytes_raw()):
        raise AcceptanceError("Cannot authenticate acceptance: signer differs from the signature key.")


def sign_acceptance(raw: bytes, private_key: Ed25519PrivateKey) -> SignedAcceptance:
    """Sign exact payload bytes only when signer identifies the supplied private key."""
    document = decode_acceptance(raw)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("Acceptance signing requires an Ed25519 private key.")
    _require_signer(document, private_key.public_key())
    return sign_segments(raw, private_key, SignedAcceptance)


def verify_acceptance(artifact: SignedAcceptance, *, public_key: Ed25519PublicKey) -> dict:
    """Verify the receipt signature; voucher authority and purchase effects remain external."""
    if type(artifact) is not SignedAcceptance:
        raise TypeError("Acceptance verification requires a SignedAcceptance artifact.")
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError("Acceptance verification requires a trusted Ed25519 public key.")
    document = artifact.document
    _require_signer(document, public_key)
    verify_signature(artifact, public_key)
    return document
