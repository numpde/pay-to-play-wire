"""Print byte/hash/signature expectations for manual vector updates.

This explicit offline lane never writes the installed fixture. Its signing key
is the public RFC 8032 test seed. Voucher digests require a separate EIP-712
oracle before the fixture can be qualified.
"""

from tools.ops.container_guard import require_container

require_container()

import base64
import hashlib
import json
from importlib.resources import files

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

vectors = json.loads(files("signed_invoice").joinpath("vectors/invoice.json").read_bytes())
key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"))
for case in vectors["cases"]:
    raw = case["invoiceUtf8"].encode("utf-8")
    message = vectors["invoicePrefixUtf8"].encode("utf-8") + raw
    print(
        json.dumps(
            {
                "name": case["name"],
                "invoiceBase64": base64.b64encode(raw).decode("ascii"),
                "invoiceHash": "0x" + hashlib.sha256(message).hexdigest(),
                "signatureBase64": base64.b64encode(key.sign(message)).decode("ascii"),
            },
            indent=2,
        )
    )
