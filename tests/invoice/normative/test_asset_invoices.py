"""Five-field offers, arbitrary services and exact-byte interoperability."""

from tools.ops.container_guard import require_container

require_container()

import base64
import hashlib
import json
import unittest
from importlib.resources import files

from cryptography.exceptions import InvalidSignature

from signed_invoice import JsonNumber, decode_invoice, encode_envelope, encode_invoice, invoice_hash, sign_invoice, verify_invoice
from tests.helpers.invoices import DOMAIN, invoice_fields, signing_key


class InvoiceTests(unittest.TestCase):
    def test_assets_round_trip_without_namespace_policy_or_normalization(self):
        key = signing_key()
        for asset in (
            "eip155:1/slip44:60",
            "eip155:1/erc20:0x" + "a" * 40,
            "cosmos:cosmoshub-3/slip44:118",
            "eip155:1/erc721:0x06012c8cf97BEaD5deAe237070F9587f8E7A266d/771769",
        ):
            with self.subTest(asset=asset):
                fields = invoice_fields()
                fields["payment"] = {"asset": asset, "amount": "5000000"}
                raw = encode_invoice(fields)
                self.assertEqual(fields, decode_invoice(raw))
                self.assertEqual(
                    raw, verify_invoice(sign_invoice(raw, key, domain=DOMAIN), domain=DOMAIN, public_key=key.public_key())
                )

    def test_service_accepts_every_json_value_kind_and_lossless_numbers(self):
        for value in ({}, [], "text", 7, True, False, None, JsonNumber("1.234567890123456789e999999"), JsonNumber("-0")):
            with self.subTest(value=value):
                fields = invoice_fields()
                fields["service"] = value
                raw = encode_invoice(fields)
                expected = JsonNumber("7") if type(value) is int else value
                self.assertEqual(expected, decode_invoice(raw)["service"])
                self.assertEqual(raw, encode_invoice(decode_invoice(raw)))

    def test_best_before_has_no_clock_or_acceptance_policy(self):
        key = signing_key()
        for seconds in (0, 1, 2000003600, 2**53 - 1):
            fields = invoice_fields()
            fields["bestBefore"] = seconds
            raw = encode_invoice(fields)
            self.assertEqual(seconds, decode_invoice(raw)["bestBefore"])
            self.assertEqual(
                raw, verify_invoice(sign_invoice(raw, key, domain=DOMAIN), domain=DOMAIN, public_key=key.public_key())
            )

    def test_amount_has_no_evm_or_python_integer_conversion_limit(self):
        for amount in (str(2**256), "9" * 5000):
            fields = invoice_fields()
            fields["payment"]["amount"] = amount
            self.assertEqual(amount, decode_invoice(encode_invoice(fields))["payment"]["amount"])

    def test_supplied_domain_prefixes_original_bytes_without_reconstruction(self):
        key = signing_key()
        raw = encode_invoice(invoice_fields()) + b"\n"
        envelope = json.loads(sign_invoice(raw, key, domain=DOMAIN))
        signature = base64.b64decode(envelope["signature"])
        key.public_key().verify(signature, DOMAIN + raw)
        self.assertEqual("0x" + hashlib.sha256(DOMAIN + raw).hexdigest(), invoice_hash(raw, domain=DOMAIN))
        for wrong in (raw, hashlib.sha256(DOMAIN + raw).digest(), DOMAIN + raw + b"\n"):
            with self.subTest(preimage=wrong[:20]), self.assertRaises(InvalidSignature):
                key.public_key().verify(signature, wrong)


class VectorTests(unittest.TestCase):
    def test_installed_vectors_preserve_independent_byte_hash_and_voucher_expectations(self):
        vectors = json.loads(files("signed_invoice").joinpath("vectors/invoice.json").read_bytes())
        self.assertEqual(DOMAIN, vectors["invoicePrefixUtf8"].encode())
        self.assertEqual(["native", "erc20"], [case["name"] for case in vectors["cases"]])
        key = signing_key()
        for case in vectors["cases"]:
            with self.subTest(case=case["name"]):
                raw = case["invoiceUtf8"].encode()
                fields = decode_invoice(raw)
                self.assertEqual(raw, encode_invoice(fields))
                self.assertEqual(case["invoiceBase64"], base64.b64encode(raw).decode())
                self.assertEqual(case["invoiceHash"], invoice_hash(raw, domain=DOMAIN))
                self.assertEqual(case["invoiceHash"], case["voucher"]["invoiceHash"])
                self.assertEqual(fields["payment"]["amount"], case["voucher"]["cumulativeTotal"])
                self.assertEqual(
                    raw,
                    verify_invoice(
                        encode_envelope(raw, base64.b64decode(case["signatureBase64"])),
                        domain=DOMAIN,
                        public_key=key.public_key(),
                    ),
                )
                self.assertEqual(
                    raw, verify_invoice(sign_invoice(raw, key, domain=DOMAIN), domain=DOMAIN, public_key=key.public_key())
                )
