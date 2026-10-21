"""Synthetic offers signed with the public RFC 8032 test key; never a secret."""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DOMAIN = b"P2P-INVOICE-4\n"
PROVIDER = "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"
BENEFICIARY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"


def signing_key():
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"))


def invoice_fields():
    return {
        "provider": PROVIDER,
        "payment": {"asset": "eip155:1/slip44:60", "amount": "5"},
        "bestBefore": 2000003600,
        "beneficiary": BENEFICIARY,
        "service": {"fixtureOnly": True, "address": "fixture-1@mail.example.invalid"},
    }
