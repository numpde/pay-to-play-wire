"""Print byte/hash/signature expectations for manual vector updates.

This explicit offline lane never writes the installed fixture. Its signing key
is the public RFC 8032 test seed. Voucher digests require a separate EIP-712
oracle before the fixture can be qualified.
"""

from tools.ops.container_guard import require_container

require_container()

import base64
import json
from importlib.resources import files

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from wire.acceptance import encode_acceptance, sign_acceptance
from wire.invoice import SignedInvoice, sign_invoice
from wire.voucher import VoucherDomain, build_voucher_typed_data, sign_voucher

vectors = json.loads(files("wire").joinpath("vectors/invoice.json").read_bytes())
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

voucher_vectors = json.loads(files("wire").joinpath("vectors/voucher.json").read_bytes())
domain_data = voucher_vectors["domain"]
domain = VoucherDomain(int(domain_data["chainId"]), bytes.fromhex(domain_data["verifyingContract"][2:]))
invoice = SignedInvoice.from_dict(vectors["cases"][0]["invoice"])
voucher = sign_voucher(
    build_voucher_typed_data(
        domain=domain,
        customer=bytes.fromhex(voucher_vectors["customer"][2:]),
        channel_id=int(voucher_vectors["channelId"]),
        cumulative_total=5,
        invoice_hash=bytes.fromhex(invoice.invoice_hash[2:]),
    ),
    bytes.fromhex(voucher_vectors["testPrivateKey"][2:]),
)
raw = encode_acceptance(
    {
        "signer": base64.urlsafe_b64encode(key.public_key().public_bytes_raw()).rstrip(b"=").decode("ascii"),
        "voucher": voucher.to_dict(),
        "acceptedAt": 2000000000,
    }
)
acceptance = sign_acceptance(raw, key)
print(
    json.dumps(
        {
            "description": "Synthetic acceptance of a complete PayToPlay/2 voucher referring to the native invoice vector. No deployed acceptance or historical signer authority is claimed.",
            "testPrivateKey": "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
            "testPublicKey": key.public_key().public_bytes_raw().hex(),
            "cases": [
                {"name": "native-voucher-acceptance", "payloadUtf8": raw.decode("ascii"), "acceptance": acceptance.to_dict()}
            ],
        },
        indent=2,
    )
)
