"""Preserve one contract profile across wallet signing and service verification.

An artifact carries the schema for portability, but cannot select its own
verification rules. Successful verification proves a signature under the
supplied authority; it says nothing about current collateral or collectibility.
"""

import json
import re
from dataclasses import dataclass, field

from wire._schema import object_schema

# Ordered Solidity types are the only source for schema projections and parsing.
_SCHEMA = (
    ("EIP712Domain", (("name", "string"), ("version", "string"), ("chainId", "uint256"), ("verifyingContract", "address"))),
    ("Voucher", (("customer", "address"), ("channelId", "uint256"), ("cumulativeTotal", "uint256"), ("invoiceHash", "bytes32"))),
)
_DOMAIN_CONSTANTS = {"name": "PayToPlay", "version": "2"}
_UINT256_LIMIT = 1 << 256
_UINT256_DIGITS = len(str(_UINT256_LIMIT - 1))
_MAX_ARTIFACT_BYTES = 8192
_DECIMAL = re.compile(rf"0|[1-9][0-9]{{0,{_UINT256_DIGITS - 1}}}", re.ASCII)
_HEX = re.compile(r"0x[0-9a-f]+", re.ASCII)
_HEX_BYTES = {"address": 20, "bytes32": 32}
_SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def _bytes(value, length, name):
    if type(value) is not bytes:
        raise TypeError(f"Cannot construct voucher: {name} must be bytes.")
    if len(value) != length:
        raise ValueError(f"Cannot construct voucher: {name} must contain {length} bytes.")
    return value


def _uint(value, name):
    if type(value) is not int:
        raise TypeError(f"Cannot construct voucher: {name} must be an integer.")
    if not 0 <= value < _UINT256_LIMIT:
        raise ValueError(f"Cannot construct voucher: {name} must fit an unsigned 256-bit integer.")
    return value


def _hex(value, length, name):
    if type(value) is not str or len(value) != 2 + length * 2 or _HEX.fullmatch(value) is None:
        raise ValueError(f"Cannot read voucher: {name} must be lowercase 0x-prefixed hex for {length} bytes.")
    return bytes.fromhex(value[2:])


def _hex_schema(length):
    return {"type": "string", "pattern": "^" + _HEX.pattern + "$", "minLength": 2 + 2 * length, "maxLength": 2 + 2 * length}


def _object(value, names, name):
    if type(value) is not dict or value.keys() != set(names):
        raise ValueError(f"Cannot read voucher: {name} must contain exactly {', '.join(names)}.")


def _types():
    return {name: [{"name": field_name, "type": kind} for field_name, kind in fields] for name, fields in _SCHEMA}


def _typed_data(value):
    _object(value, ("types", "primaryType", "domain", "message"), "typedData")
    if value["primaryType"] != "Voucher" or value["types"] != _types():
        raise ValueError("Cannot read voucher: types and primaryType must match the ordered PayToPlay/2 contract profile.")
    result = {"types": _types(), "primaryType": "Voucher"}
    for (type_name, fields), section in zip(_SCHEMA, ("domain", "message"), strict=True):
        source = value[section]
        _object(source, [name for name, _ in fields], section)
        normalized = {}
        for name, kind in fields:
            item = source[name]
            label = f"{type_name}.{name}"
            if kind == "uint256":
                if type(item) is not str or _DECIMAL.fullmatch(item) is None or int(item) >= _UINT256_LIMIT:
                    raise ValueError(f"Cannot read voucher: {label} must be a canonical decimal uint256 string.")
            elif kind in _HEX_BYTES:
                _hex(item, _HEX_BYTES[kind], label)
            elif item != _DOMAIN_CONSTANTS[name] or type(item) is not str:
                raise ValueError(f"Cannot read voucher: {label} does not match the PayToPlay/2 contract profile.")
            normalized[name] = item
        result[section] = normalized
    return result


def _signature(value):
    raw = _hex(value, 65, "signature")
    r, s, v = int.from_bytes(raw[:32]), int.from_bytes(raw[32:64]), raw[64]
    if not (0 < r < _SECP256K1_ORDER and 0 < s <= _SECP256K1_ORDER // 2 and v in (27, 28)):
        raise ValueError("Cannot read voucher: signature must use nonzero secp256k1 scalars, low s, and recovery byte 27 or 28.")
    return value


def _unique_fields(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Cannot read voucher: JSON object contains a duplicate field.")
        result[name] = value
    return result


def _reject_constant(_value):
    raise ValueError("Cannot read voucher: JSON must not contain non-finite numbers.")


def _json(raw):
    if type(raw) is not bytes:
        raise TypeError("Cannot read voucher: JSON input must be bytes.")
    if len(raw) > _MAX_ARTIFACT_BYTES:
        raise ValueError("Cannot read voucher: JSON input exceeds 8192 bytes.")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_fields, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Cannot read voucher: input must be a bounded UTF-8 JSON document.") from exc


@dataclass(frozen=True, slots=True)
class VoucherDomain:
    """Trusted deployment identity; the contract fixes the profile name/version."""

    chain_id: int
    verifying_contract: bytes

    def __post_init__(self):
        _uint(self.chain_id, "chain_id")
        _bytes(self.verifying_contract, 20, "verifying_contract")


def build_voucher_typed_data(
    *, domain: VoucherDomain, customer: bytes, channel_id: int, cumulative_total: int, invoice_hash: bytes
):
    """Build wallet input without applying channel lifecycle or purchase policy."""
    if type(domain) is not VoucherDomain:
        raise TypeError("Cannot construct voucher: domain must be VoucherDomain.")
    return {
        "types": _types(),
        "primaryType": "Voucher",
        "domain": {
            **_DOMAIN_CONSTANTS,
            "chainId": str(domain.chain_id),
            "verifyingContract": "0x" + domain.verifying_contract.hex(),
        },
        "message": {
            "customer": "0x" + _bytes(customer, 20, "customer").hex(),
            "channelId": str(_uint(channel_id, "channel_id")),
            "cumulativeTotal": str(_uint(cumulative_total, "cumulative_total")),
            "invoiceHash": "0x" + _bytes(invoice_hash, 32, "invoice_hash").hex(),
        },
    }


@dataclass(frozen=True, slots=True, init=False)
class SignedVoucher:
    """An immutable parsed artifact; JSON spelling is not EIP-712 identity."""

    _typed_data_json: bytes = field(repr=False)
    signature: str = field(repr=False)

    def __init__(self, typed_data: dict, signature: str):
        normalized = _typed_data(typed_data)
        object.__setattr__(self, "_typed_data_json", json.dumps(normalized, separators=(",", ":")).encode("ascii"))
        object.__setattr__(self, "signature", _signature(signature))

    @classmethod
    def from_json(cls, raw: bytes):
        document = _json(raw)
        if type(document) is not dict:
            raise ValueError("Cannot read voucher: artifact must be an object.")
        return cls.from_dict(document)

    @classmethod
    def from_dict(cls, document: dict):
        """Parse a transport mapping; raw duplicate detection requires from_json."""
        if type(document) is not dict:
            raise TypeError("Cannot read voucher: artifact mapping must be a dictionary.")
        _object(document, ("typedData", "signature"), "artifact")
        return cls(document["typedData"], document["signature"])

    @classmethod
    def json_schema(cls):
        """Describe lexical structure; uint256 bounds and signature rules stay in the parser."""
        sections = {}
        for (_type_name, fields), section in zip(_SCHEMA, ("domain", "message"), strict=True):
            properties = {}
            for name, kind in fields:
                if kind == "uint256":
                    value = {"type": "string", "pattern": "^(?:" + _DECIMAL.pattern + ")$", "maxLength": _UINT256_DIGITS}
                elif kind in _HEX_BYTES:
                    value = _hex_schema(_HEX_BYTES[kind])
                else:
                    value = {"type": "string", "const": _DOMAIN_CONSTANTS[name]}
                properties[name] = value
            sections[section] = object_schema(properties)
        typed_data = object_schema(
            {
                "types": {"const": _types()},
                "primaryType": {"type": "string", "const": "Voucher"},
                **sections,
            }
        )
        schema = object_schema({"typedData": typed_data, "signature": _hex_schema(65)})
        schema.update(
            title="SignedVoucher",
            description="Fixed-profile PayToPlay/2 voucher. Structural validity does not authenticate or authorize its signer.",
        )
        return schema

    @property
    def typed_data(self):
        return json.loads(self._typed_data_json)

    @property
    def domain(self):
        return self.typed_data["domain"]

    @property
    def message(self):
        return self.typed_data["message"]

    @property
    def digest(self):
        from eth_account.messages import encode_typed_data
        from eth_utils import keccak

        encoded = encode_typed_data(full_message=self.typed_data)
        return keccak(b"\x19" + encoded.version + encoded.header + encoded.body)

    def to_dict(self):
        return {"typedData": self.typed_data, "signature": self.signature}

    def to_json(self):
        return json.dumps(self.to_dict(), separators=(",", ":")).encode("ascii")


def sign_voucher(typed_data: dict, private_key: bytes) -> SignedVoucher:
    """Sign as the buyer; the caller supplies and retains custody of its key."""
    normalized = _typed_data(typed_data)
    key = _bytes(private_key, 32, "private_key")
    from eth_account import Account
    from eth_account.messages import encode_typed_data

    signed = Account.sign_message(encode_typed_data(full_message=normalized), private_key=key)
    return SignedVoucher(normalized, "0x" + bytes(signed.signature).hex())


def verify_voucher(artifact: SignedVoucher, *, expected_domain: VoucherDomain, expected_signer: bytes) -> None:
    """Verify the supplied deployment and registered key, without chain access."""
    if type(artifact) is not SignedVoucher or type(expected_domain) is not VoucherDomain:
        raise TypeError("Cannot verify voucher: supply a SignedVoucher and trusted VoucherDomain.")
    signer = _bytes(expected_signer, 20, "expected_signer")
    if artifact.domain != {
        **_DOMAIN_CONSTANTS,
        "chainId": str(expected_domain.chain_id),
        "verifyingContract": "0x" + expected_domain.verifying_contract.hex(),
    }:
        raise ValueError("Cannot verify voucher: its domain differs from the trusted deployment.")
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    from eth_keys.exceptions import BadSignature

    try:
        recovered = Account.recover_message(encode_typed_data(full_message=artifact.typed_data), signature=artifact.signature)
    except (BadSignature, ValueError) as exc:
        raise ValueError("Cannot verify voucher: its signature does not recover a secp256k1 signer.") from exc
    if bytes.fromhex(recovered[2:]) != signer:
        raise ValueError("Cannot verify voucher: its signature does not match the registered voucher key.")
