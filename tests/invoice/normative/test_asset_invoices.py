"""Explicit denomination, signing domains and exact-byte interoperability."""

from tools.ops.container_guard import require_container

require_container()

import base64
import hashlib
import json
import unittest
from importlib.resources import files

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from signed_invoice import (
    InvoiceError,
    JsonNumber,
    decode_invoice,
    encode_invoice,
    invoice_hash,
    sign_invoice,
    validate_payment_route,
    verify_invoice,
)


class AssetInvoiceTests(unittest.TestCase):
    def setUp(self):
        fixture = json.loads(files("signed_invoice").joinpath("vectors/invoice.json").read_bytes())
        self.domain = fixture["invoicePrefixUtf8"].encode()
        self.original = fixture["cases"][0]
        self.fields = json.loads(self.original["invoiceUtf8"])
        self.fields.update(version=2, asset="0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee")
        self.key = Ed25519PrivateKey.generate()
        self.trust = {
            "domain": self.domain,
            "merchant_id": self.fields["merchantId"],
            "merchant_key_id": self.fields["merchantKeyId"],
            "public_key": self.key.public_key(),
        }

    def test_native_and_token_invoices_round_trip_in_base_units(self):
        for asset in ("0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "0x" + "a" * 40):
            with self.subTest(asset=asset):
                self.fields["asset"] = asset
                self.fields["amount"] = "5000000"
                raw = encode_invoice(self.fields)
                decoded = decode_invoice(raw)
                self.assertEqual(2, decoded["version"])
                self.assertEqual(asset, decoded["asset"])
                self.assertEqual("5000000", decoded["amount"])
                self.assertEqual(raw, verify_invoice(sign_invoice(raw, self.key, domain=self.domain), **self.trust))

    def test_exactly_fifteen_fields_are_required_without_native_defaults(self):
        del self.fields["asset"]
        with self.assertRaises(InvoiceError):
            encode_invoice(self.fields)
        self.fields["asset"] = "0x" + "e" * 40
        for name in ("unit", "currency", "decimals", "symbol", "paymentOptions"):
            with self.subTest(name=name):
                fields = dict(self.fields)
                fields[name] = "unrequested metadata"
                with self.assertRaises(InvoiceError):
                    encode_invoice(fields)

    def test_unsupported_document_version_cannot_be_encoded_or_verified(self):
        original = self.original["invoiceUtf8"].encode()
        self.assertEqual(self.original["invoiceHash"], invoice_hash(original, domain=self.domain))
        self.fields["version"] = 1
        with self.assertRaises(InvoiceError):
            encode_invoice(self.fields)
        self.assertEqual(original, verify_invoice(sign_invoice(original, self.key, domain=self.domain), **self.trust))

    def test_only_explicit_integer_versions_are_supported(self):
        for version in (None, True, "2", 0, 1, 3, JsonNumber("2.0"), JsonNumber("2e0")):
            with self.subTest(version=version), self.assertRaises(InvoiceError):
                encode_invoice(dict(self.fields, version=version))
        del self.fields["version"]
        with self.assertRaises(InvoiceError):
            encode_invoice(self.fields)

    def test_asset_address_is_canonical_and_zero_is_not_a_native_alias(self):
        for asset in (
            None,
            True,
            {},
            {"kind": "native"},
            "native",
            "ETH",
            "0x" + "0" * 40,
            "0x" + "E" * 40,
            "0x" + "e" * 39,
            "eip155:1/slip44:60",
        ):
            with self.subTest(asset=asset), self.assertRaises(InvoiceError):
                encode_invoice(dict(self.fields, asset=asset))

    def test_supplied_domain_is_prepended_to_original_bytes(self):
        raw = encode_invoice(self.fields) + b"\n"
        envelope = json.loads(sign_invoice(raw, self.key, domain=self.domain))
        signature = base64.b64decode(envelope["signature"])
        self.key.public_key().verify(signature, self.domain + raw)
        self.assertEqual("0x" + hashlib.sha256(self.domain + raw).hexdigest(), invoice_hash(raw, domain=self.domain))
        for wrong in (b"another-domain\n" + raw, raw, hashlib.sha256(self.domain + raw).digest()):
            with self.subTest(preimage=wrong[:20]), self.assertRaises(InvalidSignature):
                self.key.public_key().verify(signature, wrong)

    def test_signature_from_another_domain_cannot_authorize_invoice(self):
        raw = encode_invoice(self.fields)
        envelope = {
            "bytes": base64.b64encode(raw).decode(),
            "signature": base64.b64encode(self.key.sign(b"another-domain\n" + raw)).decode(),
        }
        with self.assertRaises(InvoiceError):
            verify_invoice(json.dumps(envelope).encode(), **self.trust)

    def test_changing_asset_or_amount_invalidates_signature(self):
        raw = encode_invoice(self.fields)
        envelope = json.loads(sign_invoice(raw, self.key, domain=self.domain))
        changed = encode_invoice(dict(self.fields, asset="0x" + "a" * 40))
        changed_amount = encode_invoice(dict(self.fields, amount="7"))
        for document in (changed, changed_amount):
            with self.subTest(document=document[:20]):
                forged = dict(envelope, bytes=base64.b64encode(document).decode())
                with self.assertRaises(InvoiceError):
                    verify_invoice(json.dumps(forged).encode(), **self.trust)
                self.assertNotEqual(invoice_hash(raw, domain=self.domain), invoice_hash(document, domain=self.domain))

    def test_duplicate_depth_and_integer_rules_remain_strict(self):
        raw = encode_invoice(self.fields)
        for invalid in (
            raw[:-1] + b',"\\u0061sset":"0x' + b"e" * 40 + b'"}',
            raw.replace(b'"amount":"5"', b'"amount":5'),
            raw.replace(b'"amount":"5"', b'"amount":"0"'),
            raw.replace(b'"asset":', b'"ASSET":'),
            b"\xef\xbb\xbf" + raw,
        ):
            with self.subTest(invalid=invalid[:20]), self.assertRaises(InvoiceError):
                decode_invoice(invalid)

    def test_exact_byte_and_depth_limits(self):
        raw = encode_invoice(self.fields)
        padded = raw + b" " * (16384 - len(raw))
        self.assertEqual(21963, len(sign_invoice(padded, self.key, domain=self.domain)))
        with self.assertRaises(InvoiceError):
            decode_invoice(padded + b" ")
        for depth in (16, 17):
            fields = dict(self.fields)
            value = 0
            for _ in range(depth - 2):
                value = [value]
            fields["serviceTerms"] = {"value": value}
            if depth == 16:
                self.assertEqual(2, decode_invoice(encode_invoice(fields))["version"])
            else:
                with self.assertRaises(InvoiceError):
                    encode_invoice(fields)


class PaymentRouteTests(unittest.TestCase):
    def setUp(self):
        self.original = json.loads(files("signed_invoice").joinpath("vectors/invoice.json").read_bytes())["cases"][0][
            "invoiceUtf8"
        ].encode()
        self.fields = json.loads(self.original)
        self.fields.update(version=2, asset="0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee")
        self.route = {
            "chain_id": self.fields["chainId"],
            "payment_contract": self.fields["paymentContract"],
            "asset": self.fields["asset"],
        }

    def test_each_selected_currency_has_one_exact_payment_route(self):
        for chain, contract, asset in (
            ("1", "0x" + "3" * 40, "0x" + "e" * 40),
            ("137", "0x" + "3" * 40, "0x" + "e" * 40),
            ("1", "0x" + "4" * 40, "0x" + "a" * 40),
        ):
            with self.subTest(chain=chain, asset=asset):
                fields = dict(self.fields, chainId=chain, paymentContract=contract, asset=asset)
                raw = encode_invoice(fields)
                validate_payment_route(raw, chain_id=chain, payment_contract=contract, asset=asset)
                self.assertEqual("5", decode_invoice(raw)["amount"])

    def test_another_advertised_currency_cannot_substitute_for_selected_option(self):
        raw = encode_invoice(self.fields)
        for name, alternate in (("chain_id", "1"), ("payment_contract", "0x" + "4" * 40), ("asset", "0x" + "a" * 40)):
            with self.subTest(name=name), self.assertRaisesRegex(InvoiceError, "trusted deployment observation"):
                validate_payment_route(raw, **dict(self.route, **{name: alternate}))

    def test_wrapped_native_and_native_asset_are_distinct(self):
        raw = encode_invoice(dict(self.fields, asset="0x" + "a" * 40))
        with self.assertRaisesRegex(InvoiceError, "asset differs"):
            validate_payment_route(raw, **self.route)

    def test_missing_asset_cannot_gain_an_implicit_denomination(self):
        fields = dict(self.fields)
        del fields["asset"]
        with self.assertRaises(InvoiceError):
            validate_payment_route(json.dumps(fields).encode(), **self.route)

    def test_observation_types_are_not_coerced(self):
        raw = encode_invoice(self.fields)
        for name in self.route:
            with self.subTest(name=name), self.assertRaises(TypeError):
                validate_payment_route(raw, **dict(self.route, **{name: 1}))


class AssetVectorTests(unittest.TestCase):
    def test_shared_vectors_preserve_exact_bytes_hash_and_signature_profile(self):
        fixture = json.loads(files("signed_invoice").joinpath("vectors/invoice.json").read_bytes())
        domain = fixture["invoicePrefixUtf8"].encode()
        self.assertEqual(["native", "erc20"], [case["name"] for case in fixture["cases"]])
        key = Ed25519PrivateKey.generate()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                raw = case["invoiceUtf8"].encode()
                fields = decode_invoice(raw)
                self.assertEqual(raw, encode_invoice(fields))
                self.assertEqual(case["invoiceHash"], invoice_hash(raw, domain=domain))
                envelope = sign_invoice(raw, key, domain=domain)
                self.assertEqual(case["invoiceBase64"], json.loads(envelope)["bytes"])
                self.assertEqual(
                    raw,
                    verify_invoice(
                        envelope,
                        domain=domain,
                        merchant_id=fields["merchantId"],
                        merchant_key_id=fields["merchantKeyId"],
                        public_key=key.public_key(),
                    ),
                )
                self.assertEqual(case["voucher"]["invoiceHash"], invoice_hash(raw, domain=domain))
                self.assertEqual(fields["paymentContract"], case["voucherDomain"]["verifyingContract"])
                self.assertEqual(fields["amount"], case["voucher"]["cumulativeTotal"])
