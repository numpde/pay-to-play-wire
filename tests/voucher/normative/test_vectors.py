"""The Python artifact agrees with the independent contract-owner digest vectors."""

from tools.ops.container_guard import require_container

require_container()

import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError
from importlib.resources import files

from wire.voucher import SignedVoucher, VoucherDomain, build_voucher_typed_data, sign_voucher, verify_voucher


class VectorTests(unittest.TestCase):
    def test_qualified_voucher_baseline_vector_bytes_are_unchanged(self):
        raw = files("wire").joinpath("vectors/voucher.json").read_bytes()
        self.assertEqual("edbb7f73b8157871a360aedee4f1463de1825c2246c50a852120bd9b4876100c", hashlib.sha256(raw).hexdigest())

    def test_independent_digest_vectors_and_registered_signer(self):
        vector = json.loads(files("wire").joinpath("vectors/voucher.json").read_bytes())
        domain = VoucherDomain(31337, bytes.fromhex("33" * 20))
        for case in vector["cases"]:
            with self.subTest(digest=case["digest"]):
                typed_data = build_voucher_typed_data(
                    domain=domain,
                    customer=bytes.fromhex(vector["customer"][2:]),
                    channel_id=int(vector["channelId"]),
                    cumulative_total=int(case["cumulativeTotal"]),
                    invoice_hash=bytes.fromhex(case["invoiceHash"][2:]),
                )
                artifact = sign_voucher(typed_data, bytes.fromhex(vector["testPrivateKey"][2:]))
                self.assertEqual(case["digest"], "0x" + artifact.digest.hex())
                self.assertEqual(typed_data, artifact.typed_data)
                self.assertEqual(artifact, SignedVoucher.from_json(artifact.to_json()))
                self.assertIsNone(
                    verify_voucher(artifact, expected_domain=domain, expected_signer=bytes.fromhex(vector["testSigner"][2:]))
                )
                self.assertNotEqual(vector["customer"], vector["testSigner"])

    def test_projections_do_not_mutate_artifact(self):
        artifact = sign_voucher(
            build_voucher_typed_data(
                domain=VoucherDomain(1, bytes(20)),
                customer=bytes(20),
                channel_id=0,
                cumulative_total=2**256 - 1,
                invoice_hash=bytes(32),
            ),
            bytes.fromhex("11" * 32),
        )
        before = artifact.to_json()
        artifact.typed_data["types"]["Voucher"].clear()
        artifact.message["channelId"] = "3"
        artifact.domain["chainId"] = "2"
        artifact.to_dict()["signature"] = "removed"
        self.assertEqual(before, artifact.to_json())
        with self.assertRaises(FrozenInstanceError):
            artifact.signature = "removed"

    def test_json_formatting_does_not_change_typed_identity(self):
        typed_data = build_voucher_typed_data(
            domain=VoucherDomain(1, bytes(20)), customer=bytes(20), channel_id=0, cumulative_total=0, invoice_hash=bytes(32)
        )
        artifact = sign_voucher(typed_data, bytes.fromhex("11" * 32))
        changed = SignedVoucher.from_json(json.dumps(artifact.to_dict(), indent=2, sort_keys=True).encode())
        self.assertEqual(artifact, changed)
        self.assertEqual(artifact.digest, changed.digest)
