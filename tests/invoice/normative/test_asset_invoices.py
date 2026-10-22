"""Five-field payload reachability and retained signed-artifact vectors."""

from tools.ops.container_guard import require_container

require_container()

import hashlib
import json
import unittest
from importlib.resources import files

from tests.helpers.invoices import invoice_fields, signing_key
from wire.invoice import JsonNumber, SignedInvoice, decode_invoice, encode_invoice, invoice_hash, sign_invoice, verify_invoice


class InvoiceTests(unittest.TestCase):
    def test_assets_round_trip_without_namespace_policy_or_normalization(self):
        key = signing_key()
        for asset in (
            "eip155:1/slip44:60",
            "eip155:1/erc20:0x" + "a" * 40,
            "cosmos:cosmoshub-3/slip44:118",
            "eip155:1/erc721:0x06012c8cf97BEaD5deAe237070F9587f8E7A266d/771769",
        ):
            fields = invoice_fields()
            fields["payment"] = {"asset": asset, "amount": "5000000"}
            raw = encode_invoice(fields)
            self.assertEqual(fields, decode_invoice(raw))
            self.assertEqual(fields, verify_invoice(sign_invoice(raw, key), public_key=key.public_key()))

    def test_service_accepts_every_json_kind_and_lossless_numbers(self):
        for value in ({}, [], "text", 7, True, False, None, JsonNumber("1.234567890123456789e999999"), JsonNumber("-0")):
            fields = dict(invoice_fields(), service=value)
            raw = encode_invoice(fields)
            expected = JsonNumber("7") if type(value) is int else value
            self.assertEqual(expected, decode_invoice(raw)["service"])
            self.assertEqual(raw, encode_invoice(decode_invoice(raw)))

    def test_best_before_has_no_clock_or_acceptance_policy(self):
        key = signing_key()
        for seconds in (0, 1, 2000003600, 2**53 - 1):
            raw = encode_invoice(dict(invoice_fields(), bestBefore=seconds))
            self.assertEqual(seconds, verify_invoice(sign_invoice(raw, key), public_key=key.public_key())["bestBefore"])

    def test_amount_has_no_evm_or_python_integer_conversion_limit(self):
        for amount in (str(2**256), "9" * 5000):
            fields = invoice_fields()
            fields["payment"]["amount"] = amount
            self.assertEqual(amount, decode_invoice(encode_invoice(fields))["payment"]["amount"])


class VectorTests(unittest.TestCase):
    def test_published_invoice_0_3_0_vector_bytes_are_unchanged(self):
        raw = files("wire").joinpath("vectors/invoice.json").read_bytes()
        self.assertEqual("a83eaebab9e17bd5320d29c17ea1d40398cae8715d9e1b90e5698adfb829dc2f", hashlib.sha256(raw).hexdigest())

    def test_retained_jws_vectors_preserve_exact_segments_payload_and_identity(self):
        vectors = json.loads(files("wire").joinpath("vectors/invoice.json").read_bytes())
        key = signing_key()
        self.assertEqual(["native", "erc20"], [case["name"] for case in vectors["cases"]])
        for case in vectors["cases"]:
            with self.subTest(case=case["name"]):
                raw = case["payloadUtf8"].encode()
                artifact = SignedInvoice(**case["invoice"])
                self.assertEqual(raw, artifact.payload_bytes)
                self.assertEqual(case["compact"], artifact.compact)
                self.assertEqual(case["invoiceHash"], invoice_hash(artifact))
                self.assertEqual(artifact, SignedInvoice.from_json(artifact.to_json()))
                self.assertEqual(artifact, SignedInvoice.from_compact(case["compact"]))
                self.assertEqual(artifact, sign_invoice(raw, key))
                self.assertEqual(decode_invoice(raw), verify_invoice(artifact, public_key=key.public_key()))
