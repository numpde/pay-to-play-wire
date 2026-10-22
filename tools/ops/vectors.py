"""Print byte/hash/signature expectations for manual vector updates.

This explicit offline lane never writes the installed fixture. Its signing key
is the public RFC 8032 test seed. Voucher digests require a separate EIP-712
oracle before the fixture can be qualified.
"""

from tools.ops.container_guard import require_container

require_container()

import json
from importlib.resources import files

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from signed_invoice import sign_invoice

vectors = json.loads(files("signed_invoice").joinpath("vectors/invoice.json").read_bytes())
key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"))
for case in vectors["cases"]:
    raw = case["payloadUtf8"].encode("utf-8")
    artifact = sign_invoice(raw, key)
    print(
        json.dumps(
            {
                "name": case["name"],
                "invoice": artifact.to_dict(),
                "compact": artifact.compact,
                "invoiceHash": artifact.invoice_hash,
            },
            indent=2,
        )
    )
