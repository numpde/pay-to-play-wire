"""The shared fixed-Ed25519 three-segment JWS mechanics; callers own payload meaning."""

import base64
import binascii
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from typing import ClassVar

from cryptography.exceptions import InvalidSignature

from ._json import MAX_DOCUMENT_BYTES, load_json
from ._schema import object_schema

MAX_PROTECTED_BYTES = 256
MAX_PAYLOAD_BYTES = MAX_DOCUMENT_BYTES
MAX_JSON_BYTES = 32768
MAX_PROTECTED_LENGTH = (4 * MAX_PROTECTED_BYTES + 2) // 3
MAX_PAYLOAD_LENGTH = (4 * MAX_PAYLOAD_BYTES + 2) // 3
SIGNATURE_LENGTH = 86
MAX_COMPACT_LENGTH = MAX_PROTECTED_LENGTH + MAX_PAYLOAD_LENGTH + SIGNATURE_LENGTH + 2
BASE64URL = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class Profile:
    name: str
    media_type: str
    error: type[ValueError]
    decode_payload: Callable[[bytes], dict]
    key_role: str
    description: str

    @property
    def protected_bytes(self):
        return json.dumps({"alg": "Ed25519", "typ": self.media_type}, separators=(",", ":")).encode("ascii")


def encode_segment(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_segment(value, maximum, name, profile):
    if type(value) is not str:
        raise TypeError(f"{profile.name.capitalize()} JWS {name} must be a string.")
    if len(value) > (4 * maximum + 2) // 3 or BASE64URL.fullmatch(value) is None:
        raise profile.error(f"Cannot parse {profile.name} JWS: {name} must be bounded unpadded base64url.")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except binascii.Error as exc:
        raise profile.error(f"Cannot parse {profile.name} JWS: {name} is not unpadded base64url.") from exc
    if len(raw) > maximum or encode_segment(raw) != value:
        raise profile.error(f"Cannot parse {profile.name} JWS: {name} must use canonical unpadded base64url within its limit.")
    return raw


@dataclass(frozen=True, slots=True)
class SignedJWS:
    _profile: ClassVar[Profile]

    protected: str = field(metadata={"min_length": 1, "max_length": MAX_PROTECTED_LENGTH})
    payload: str = field(metadata={"min_length": 1, "max_length": MAX_PAYLOAD_LENGTH})
    signature: str = field(metadata={"min_length": SIGNATURE_LENGTH, "max_length": SIGNATURE_LENGTH})

    def __post_init__(self):
        profile = self._profile
        header = load_json(
            _decode_segment(self.protected, MAX_PROTECTED_BYTES, "protected", profile), error=profile.error, name=profile.name
        )
        if type(header) is not dict or header.keys() != {"alg", "typ"} or header["alg"] != "Ed25519":
            raise profile.error(
                f"Cannot parse {profile.name} JWS: protected header must contain only alg Ed25519 and the {profile.name} profile typ."
            )
        typ = header["typ"]
        if type(typ) is not str or not typ.isascii():
            raise profile.error(f"Cannot parse {profile.name} JWS: typ must identify the {profile.name} media type.")
        # RFC 7515 section 4.1.9: media types ignore case and may omit application/.
        media_type = typ if "/" in typ else "application/" + typ
        if media_type.lower() != profile.media_type:
            raise profile.error(f"Cannot parse {profile.name} JWS: typ does not identify the {profile.name} profile.")
        profile.decode_payload(self.payload_bytes)
        if len(self._signature_bytes) != 64:
            raise profile.error(f"Cannot parse {profile.name} JWS: Ed25519 signature must contain exactly 64 bytes.")

    @classmethod
    def from_json(cls, raw: bytes):
        """Parse duplicate-aware flattened JWS JSON within the 32768-byte bound."""
        profile = cls._profile
        if type(raw) is not bytes:
            raise TypeError(f"{profile.name.capitalize()} JWS JSON must be supplied as exact UTF-8 bytes.")
        if len(raw) > MAX_JSON_BYTES:
            raise profile.error(f"Cannot parse {profile.name} JWS: flattened JSON exceeds 32768 bytes.")
        document = load_json(raw, error=profile.error, name=profile.name)
        if type(document) is not dict:
            raise profile.error(f"Cannot parse {profile.name} JWS: flattened JSON must be an object.")
        return cls.from_dict(document)

    @classmethod
    def from_dict(cls, document: dict):
        """Parse a flattened mapping; raw duplicate detection requires from_json."""
        if type(document) is not dict:
            raise TypeError(f"{cls._profile.name.capitalize()} JWS mapping must be a dictionary.")
        if document.keys() != {member.name for member in fields(cls)}:
            raise cls._profile.error(
                f"Cannot parse {cls._profile.name} JWS: flattened JSON must contain exactly protected, payload and signature."
            )
        if any(type(value) is not str for value in document.values()):
            raise cls._profile.error(f"Cannot parse {cls._profile.name} JWS: all three flattened members must be strings.")
        return cls(**document)

    @classmethod
    def json_schema(cls):
        """Describe transport structure; decoded profile and signature checks stay explicit."""
        schema = object_schema(
            {
                member.name: {
                    "type": "string",
                    "pattern": "^" + BASE64URL.pattern + "$",
                    "minLength": member.metadata["min_length"],
                    "maxLength": member.metadata["max_length"],
                }
                for member in fields(cls)
            }
        )
        schema.update(title=cls.__name__, description=cls._profile.description)
        return schema

    @classmethod
    def from_compact(cls, compact: str):
        """Read the exact bounded three-segment compact artifact, without normalization."""
        if type(compact) is not str:
            raise TypeError(f"Compact {cls._profile.name} JWS must be a string.")
        if len(compact) > MAX_COMPACT_LENGTH or compact.count(".") != 2:
            raise cls._profile.error(
                f"Cannot parse {cls._profile.name} JWS: compact form must contain three bounded base64url segments."
            )
        return cls(*compact.split("."))

    @property
    def compact(self) -> str:
        return self.protected + "." + self.payload + "." + self.signature

    @property
    def signing_input(self) -> bytes:
        return (self.protected + "." + self.payload).encode("ascii")

    @property
    def payload_bytes(self) -> bytes:
        return _decode_segment(self.payload, MAX_PAYLOAD_BYTES, "payload", self._profile)

    @property
    def _signature_bytes(self):
        return _decode_segment(self.signature, 64, "signature", self._profile)

    @property
    def document(self) -> dict:
        """Return a fresh validated projection, without authenticating it."""
        return self._profile.decode_payload(self.payload_bytes)

    def to_dict(self) -> dict[str, str]:
        return {member.name: getattr(self, member.name) for member in fields(self)}

    def to_json(self) -> bytes:
        return json.dumps(self.to_dict(), separators=(",", ":")).encode("ascii")


def sign_segments(raw, private_key, artifact_type):
    protected, payload = encode_segment(artifact_type._profile.protected_bytes), encode_segment(raw)
    signature = private_key.sign((protected + "." + payload).encode("ascii"))
    return artifact_type(protected, payload, encode_segment(signature))


def verify_signature(artifact, public_key):
    try:
        public_key.verify(artifact._signature_bytes, artifact.signing_input)
    except InvalidSignature as exc:
        profile = artifact._profile
        raise profile.error(
            f"Cannot verify {profile.name} JWS: signature does not match the trusted {profile.key_role} key and exact segments."
        ) from exc
