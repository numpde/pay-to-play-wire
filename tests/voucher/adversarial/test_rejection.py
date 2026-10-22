"""Malformed wire input cannot choose its schema or authorize its own signer."""

from tools.ops.container_guard import require_container

require_container()

import json
import unittest

from wire.voucher import SignedVoucher, VoucherDomain, build_voucher_typed_data, sign_voucher, verify_voucher


class RejectionTests(unittest.TestCase):
    def setUp(self):
        self.domain = VoucherDomain(31337, bytes.fromhex("33" * 20))
        self.signer = bytes.fromhex("19e7e376e7c213b7e7e7e46cc70a5dd086daff2a")
        self.artifact = sign_voucher(
            build_voucher_typed_data(
                domain=self.domain, customer=bytes.fromhex("22" * 20), channel_id=7, cumulative_total=5, invoice_hash=bytes(32)
            ),
            bytes.fromhex("11" * 32),
        )

    def test_rejects_schema_changes(self):
        changes = (
            lambda item: item.update(extra=True),
            lambda item: item["typedData"].update(extra=True),
            lambda item: item["typedData"].update(primaryType="Other"),
            lambda item: item["typedData"]["types"]["Voucher"].reverse(),
            lambda item: item["typedData"]["types"].pop("EIP712Domain"),
            lambda item: item["typedData"]["domain"].update(name="Other"),
            lambda item: item["typedData"]["domain"].update(version="1"),
            lambda item: item["typedData"]["message"].update(extra=True),
            lambda item: item["typedData"]["message"].pop("invoiceHash"),
        )
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                document = self.artifact.to_dict()
                change(document)
                with self.assertRaises(ValueError):
                    SignedVoucher.from_json(json.dumps(document).encode())

    def test_rejects_wrong_uint_representations(self):
        for section, name in (("domain", "chainId"), ("message", "channelId"), ("message", "cumulativeTotal")):
            for value in (None, True, 1, 1.5, "-1", "01", "1.0", "+1", "", "1e4", "\u0661", str(2**256), "9" * 500):
                with self.subTest(section=section, name=name, value=value):
                    document = self.artifact.to_dict()
                    document["typedData"][section][name] = value
                    with self.assertRaises(ValueError):
                        SignedVoucher.from_json(json.dumps(document).encode())

    def test_rejects_wrong_hex_representations(self):
        for section, name, size in (
            ("domain", "verifyingContract", 20),
            ("message", "customer", 20),
            ("message", "invoiceHash", 32),
        ):
            for value in (None, True, 1, "AA" * size, "0x" + "AB" * size, "0x" + "gg" * size, "0x" + "00" * (size - 1)):
                with self.subTest(section=section, name=name, value=value):
                    document = self.artifact.to_dict()
                    document["typedData"][section][name] = value
                    with self.assertRaises(ValueError):
                        SignedVoucher.from_json(json.dumps(document).encode())

    def test_rejects_ambiguous_json_and_limits(self):
        document = self.artifact.to_json()
        for raw in (
            b"[]",
            b"null",
            b"{}",
            b"\xff",
            b"NaN",
            b"{",
            b" " * 8193,
            b"[" * 4000 + b"]" * 4000,
            document.replace(b'"signature":', b'"signature":"x","signature":'),
            document.replace(b'"channelId":"7"', b'"channelId":"7","channelId":"7"'),
        ):
            with self.subTest(prefix=raw[:20]), self.assertRaises(ValueError):
                SignedVoucher.from_json(raw)

    def test_contract_signature_encoding_and_unrecoverable_points(self):
        order = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
        original = bytes.fromhex(self.artifact.signature[2:])
        signatures = [b"", original[:64], original + b"\x00"]
        signatures.extend(original[:64] + bytes([v]) for v in (0, 1, 26, 29, 255))
        signatures.extend(
            r.to_bytes(32) + s.to_bytes(32) + b"\x1b" for r, s in ((0, 1), (1, 0), (order, 1), (1, order), (1, order // 2 + 1))
        )
        for raw in signatures:
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                SignedVoucher(self.artifact.typed_data, "0x" + raw.hex())
        # r=5 has no recoverable curve point; its format and scalar ranges are valid.
        artifact = SignedVoucher(self.artifact.typed_data, "0x" + ((5).to_bytes(32) + (1).to_bytes(32) + b"\x1b").hex())
        with self.assertRaises(ValueError) as caught:
            verify_voucher(artifact, expected_domain=self.domain, expected_signer=self.signer)
        self.assertIsNotNone(caught.exception.__cause__)

    def test_wrong_authority_and_tampering(self):
        for domain in (VoucherDomain(1, self.domain.verifying_contract), VoucherDomain(31337, bytes(20))):
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                verify_voucher(self.artifact, expected_domain=domain, expected_signer=self.signer)
        with self.assertRaises(ValueError):
            verify_voucher(self.artifact, expected_domain=self.domain, expected_signer=bytes.fromhex("22" * 20))
        for field, replacement in (
            ("customer", "0x" + "44" * 20),
            ("channelId", "8"),
            ("cumulativeTotal", "6"),
            ("invoiceHash", "0x" + "55" * 32),
        ):
            with self.subTest(field=field):
                changed = self.artifact.typed_data
                changed["message"][field] = replacement
                artifact = SignedVoucher(changed, self.artifact.signature)
                with self.assertRaises(ValueError):
                    verify_voucher(artifact, expected_domain=self.domain, expected_signer=self.signer)

    def test_python_types_are_not_silently_coerced(self):
        for value in (True, "1", 1.0):
            with self.subTest(value=value), self.assertRaises(TypeError):
                VoucherDomain(value, bytes(20))
        with self.assertRaises(TypeError):
            SignedVoucher.from_json("{}")
        with self.assertRaises(TypeError):
            sign_voucher(self.artifact.typed_data, "11" * 32)
