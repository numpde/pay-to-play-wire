"""Payload wire laws retain every distinct unsafe-input rejection."""

from tools.ops.container_guard import require_container

require_container()

import json
import unittest

from tests.helpers.invoices import BENEFICIARY, invoice_fields, signing_key
from wire.invoice import InvoiceError, JsonNumber, decode_invoice, encode_invoice, sign_invoice, verify_invoice


class InvoiceCodecTests(unittest.TestCase):
    def setUp(self):
        self.raw = encode_invoice(invoice_fields())

    def changed(self, field, value):
        return json.dumps(dict(json.loads(self.raw), **{field: value}), ensure_ascii=False).encode()

    def test_top_level_members_are_exact_except_service_may_be_null(self):
        fields = json.loads(self.raw)
        for field in fields:
            variant = dict(fields)
            del variant[field]
            with self.subTest(missing=field), self.assertRaises(InvoiceError):
                decode_invoice(json.dumps(variant).encode())
            if field != "service":
                with self.subTest(null=field), self.assertRaises(InvoiceError):
                    decode_invoice(self.changed(field, None))
        for raw in (b"[]", b"null", b"true", self.raw[:-1] + b',"extra":1}'):
            with self.subTest(raw=raw[:10]), self.assertRaises(InvoiceError):
                decode_invoice(raw)

    def test_best_before_integer_token_grammar_is_strict(self):
        for token in (b"true", b'"1"', b"-0", b"1.0", b"1e0", b"-1", b"01", b"9007199254740992", b"9" * 5000):
            with self.subTest(token=token[:20]), self.assertRaises(InvoiceError):
                decode_invoice(self.raw.replace(b'"bestBefore":2000003600', b'"bestBefore":' + token))

    def test_payment_shape_and_types_are_exact(self):
        for payment in (
            None,
            [],
            "x",
            {},
            {"asset": "eip155:1/slip44:60"},
            {"amount": "5"},
            {"asset": "eip155:1/slip44:60", "amount": "5", "decimals": 18},
        ):
            with self.subTest(payment=payment), self.assertRaises(InvoiceError):
                decode_invoice(self.changed("payment", payment))
        for field in ("asset", "amount"):
            for value in (None, True, 1, {}):
                payment = dict(json.loads(self.raw)["payment"], **{field: value})
                with self.subTest(field=field, value=value), self.assertRaises(InvoiceError):
                    decode_invoice(self.changed("payment", payment))

    def test_legacy_members_are_rejected_without_profile_fallback(self):
        for field in (
            "version",
            "merchantId",
            "merchantKeyId",
            "invoiceId",
            "invoiceHash",
            "chainId",
            "paymentContract",
            "channelId",
            "customer",
            "quotedPayee",
            "amount",
            "asset",
            "acceptBy",
            "redeemBy",
            "serviceTerms",
        ):
            with self.subTest(field=field), self.assertRaises(InvoiceError):
                decode_invoice(self.changed(field, "legacy"))

    def test_provider_and_beneficiary_are_encoded_public_keys(self):
        for field in ("provider", "beneficiary"):
            for invalid in ({}, [], 1, True, "", BENEFICIARY + "=", BENEFICIARY[:-1] + "9"):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(InvoiceError):
                    decode_invoice(self.changed(field, invalid))

    def test_duplicate_decoded_names_are_rejected_at_every_depth(self):
        for raw in (
            self.raw[:-1] + b',"provider":"duplicate"}',
            self.raw[:-1] + b',"provid\\u0065r":"duplicate"}',
            self.raw.replace(b'"amount":"5"', b'"amount":"5","\\u0061mount":"6"'),
            self.raw.replace(b'"fixtureOnly":true', b'"fixtureOnly":true,"fixtureOnly":false'),
            self.raw.replace(b'"fixtureOnly":true', b'"nested":[{"x":1,"\\u0078":2}]'),
        ):
            with self.assertRaises(InvoiceError):
                decode_invoice(raw)

    def test_json_utf8_and_surrogates_are_strict(self):
        for raw in (
            b"\xef\xbb\xbf" + self.raw,
            b"\xff",
            self.raw + b"{}",
            self.raw[:-1],
            self.raw.replace(b'"fixtureOnly":true', b'"x":"\\ud800"'),
            self.raw.replace(b'"fixtureOnly":true', b'"\\udfff":1'),
            self.raw.replace(b'"fixtureOnly":true', b'"x":"\x01"'),
            self.raw.replace(b'"fixtureOnly":true', b'"x":NaN'),
            self.raw.replace(b'"fixtureOnly":true', b'"x":Infinity'),
            self.raw.replace(b'"fixtureOnly":true', b'"x":-Infinity'),
        ):
            with self.subTest(raw=raw[-30:]), self.assertRaises(InvoiceError):
                decode_invoice(raw)
        valid = self.raw.replace(b'"fixtureOnly":true', b'"x":"\\ud801\\udc00"')
        self.assertEqual("𐐀", decode_invoice(valid)["service"]["x"])

    def test_container_depth_counts_root_and_both_kinds(self):
        for depth in (16, 17, 1500):
            nested = b"[" * (depth - 2) + b"0" + b"]" * (depth - 2)
            fields = json.loads(self.raw)
            fields["service"] = {}
            raw = json.dumps(fields, separators=(",", ":")).encode().replace(b'"service":{}', b'"service":{"x":' + nested + b"}")
            if depth == 16:
                self.assertEqual(raw, encode_invoice(decode_invoice(raw)))
            else:
                with self.assertRaises(InvoiceError):
                    decode_invoice(raw)

    def test_encoder_depth_boundary_reaches_sixteen_and_rejects_seventeen(self):
        for depth in (16, 17):
            fields = json.loads(self.raw)
            service = "leaf"
            for _ in range(depth - 1):
                service = [service]
            fields["service"] = service
            if depth == 16:
                self.assertEqual(service, decode_invoice(encode_invoice(fields))["service"])
            else:
                with self.assertRaises(InvoiceError):
                    encode_invoice(fields)

    def test_byte_limit_counts_utf8(self):
        fields = json.loads(self.raw)
        fields["service"] = {"text": "é"}
        raw = encode_invoice(fields)
        padded = raw + b" " * (16384 - len(raw))
        key = signing_key()
        artifact = sign_invoice(padded, key)
        self.assertEqual(padded, artifact.payload_bytes)
        self.assertEqual(decode_invoice(padded), verify_invoice(artifact, public_key=key.public_key()))
        with self.assertRaises(InvoiceError):
            decode_invoice(padded + b" ")
        fields["service"] = {"text": "é" * 8192}
        with self.assertRaises(InvoiceError):
            encode_invoice(fields)

    def test_nested_numbers_are_lossless_and_reencodable(self):
        tokens = ["9007199254740993", "0.12345678901234567890123456789", "1e999999999999999999999", "-0", "9" * 5000]
        raw = self.raw.replace(b'"fixtureOnly":true', b'"numbers":[' + ",".join(tokens).encode() + b"]")
        fields = decode_invoice(raw)
        self.assertEqual([JsonNumber(token) for token in tokens], fields["service"]["numbers"])
        self.assertEqual(raw, encode_invoice(fields))

    def test_encoder_rejects_coercions_cycles_and_non_json_values(self):
        for value in ({1: "wrong key"}, {"x": float("inf")}, {"x": 0.5}, {"x": object()}, {"x": "\ud800"}):
            fields = json.loads(self.raw)
            fields["service"] = value
            with self.assertRaises(InvoiceError):
                encode_invoice(fields)
        cycle = []
        cycle.append(cycle)
        fields["service"] = {"cycle": cycle}
        with self.assertRaises(InvoiceError):
            encode_invoice(fields)
        for token in ("NaN", "01", "1 2", "", "\u0661"):
            with self.assertRaises(InvoiceError):
                JsonNumber(token)
        for token in (1, 0.5, None, True, b"1"):
            with self.assertRaises(TypeError):
                JsonNumber(token)

    def test_python_boundary_types_are_not_coerced(self):
        for raw in (self.raw.decode(), bytearray(self.raw), None):
            with self.assertRaises(TypeError):
                decode_invoice(raw)
        for fields in (None, [], "{}", b"{}"):
            with self.assertRaises(TypeError):
                encode_invoice(fields)
