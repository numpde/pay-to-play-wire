"""Invoice wire laws, real signatures, and independent retained byte expectations."""

from tools.ops.container_guard import require_container

require_container()

import base64
import hashlib
import json
import unittest
from importlib.resources import files

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from signed_invoice import InvoiceError, JsonNumber, decode_invoice, encode_invoice, invoice_hash, sign_invoice, verify_invoice
from tests.helpers.invoices import BENEFICIARY, signing_key

FIXTURE = files("signed_invoice").joinpath("vectors/invoice.json")


class InvoiceCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = json.loads(FIXTURE.read_bytes())
        cls.domain = cls.vectors["invoicePrefixUtf8"].encode()
        cls.raw = cls.vectors["cases"][0]["invoiceUtf8"].encode()
        cls.key = signing_key()
        cls.other_key = Ed25519PrivateKey.generate()
        cls.trust = {
            "domain": cls.domain,
            "public_key": cls.key.public_key(),
        }

    def changed(self, field, value):
        fields = json.loads(self.raw)
        fields[field] = value
        return json.dumps(fields, ensure_ascii=False).encode()

    def verify(self, envelope):
        return verify_invoice(envelope, **self.trust)

    def test_signs_prefixed_original_bytes_directly(self):
        envelope = json.loads(sign_invoice(self.raw, self.key, domain=self.domain))
        signature = base64.b64decode(envelope["signature"])
        self.key.public_key().verify(signature, self.domain + self.raw)
        for wrong in (self.raw, hashlib.sha256(self.domain + self.raw).digest(), self.domain + self.raw + b"\n"):
            with self.subTest(preimage=wrong[:20]), self.assertRaises(InvalidSignature):
                self.key.public_key().verify(signature, wrong)

    def test_whitespace_order_unicode_and_escapes_are_never_normalized(self):
        for raw in (
            self.raw + b"\n",
            json.dumps(json.loads(self.raw), indent=2).encode(),
            self.raw.replace(b'"provider"', b'"provid\\u0065r"'),
            self.raw.replace(b'"fixtureOnly":true', '"fixtureOnly":true,"text":"é𐐀"'.encode()),
        ):
            with self.subTest(raw=raw[:20]):
                self.assertEqual(raw, self.verify(sign_invoice(raw, self.key, domain=self.domain)))
                self.assertNotEqual(invoice_hash(self.raw, domain=self.domain), invoice_hash(raw, domain=self.domain))

    def test_wrong_key_signature_bytes_and_binding_are_rejected(self):
        envelope = json.loads(sign_invoice(self.raw, self.key, domain=self.domain))
        variants = [
            dict(envelope, signature=base64.b64encode(bytes(64)).decode()),
            dict(envelope, bytes=base64.b64encode(self.raw + b"\n").decode()),
        ]
        for variant in variants:
            with self.subTest(variant=tuple(variant)), self.assertRaises(InvoiceError):
                self.verify(json.dumps(variant).encode())
        with self.assertRaises(InvoiceError):
            verify_invoice(json.dumps(envelope).encode(), **dict(self.trust, public_key=self.other_key.public_key()))

    def test_valid_signature_by_another_trusted_provider_cannot_authorize_named_provider(self):
        # B is trusted by the caller and correctly signs bytes naming A. Both
        # independent trust checks could succeed; equality must still reject it.
        envelope = {
            "bytes": base64.b64encode(self.raw).decode(),
            "signature": base64.b64encode(self.other_key.sign(self.domain + self.raw)).decode(),
        }
        with self.assertRaisesRegex(InvoiceError, "provider differs"):
            verify_invoice(json.dumps(envelope).encode(), **dict(self.trust, public_key=self.other_key.public_key()))
        with self.assertRaisesRegex(InvoiceError, "provider differs"):
            sign_invoice(self.raw, self.other_key, domain=self.domain)

    def test_every_offer_field_is_covered_by_hash_and_signature(self):
        signature = json.loads(sign_invoice(self.raw, self.key, domain=self.domain))["signature"]
        changes = {
            "provider": BENEFICIARY,
            "payment": {"asset": "eip155:1/slip44:60", "amount": "6"},
            "bestBefore": 0,
            "beneficiary": json.loads(self.raw)["provider"],
            "service": None,
        }
        for field, value in changes.items():
            raw = self.changed(field, value)
            envelope = {"bytes": base64.b64encode(raw).decode(), "signature": signature}
            with self.subTest(field=field):
                self.assertNotEqual(invoice_hash(self.raw, domain=self.domain), invoice_hash(raw, domain=self.domain))
                with self.assertRaises(InvoiceError):
                    self.verify(json.dumps(envelope).encode())
        raw = self.changed("payment", {"asset": "cosmos:cosmoshub-3/slip44:118", "amount": "5"})
        with self.assertRaises(InvoiceError):
            self.verify(json.dumps({"bytes": base64.b64encode(raw).decode(), "signature": signature}).encode())

    def test_base64_rejects_noncanonical_and_oversize_representations(self):
        # Force padding so the missing-padding stimulus changes the wire value.
        padded = self.raw + b" " * ((1 - len(self.raw)) % 3)
        original = json.loads(sign_invoice(padded, self.key, domain=self.domain))
        for field, oversized_length in (("bytes", 16385), ("signature", 65)):
            value = original[field]
            for invalid in (
                value + "=",
                value + "\n",
                " " + value,
                value.rstrip("="),
                "_" + value[1:],
                "é",
                1,
                None,
                base64.b64encode(bytes(oversized_length)).decode(),
            ):
                with self.subTest(field=field, value_type=type(invalid)), self.assertRaises(InvoiceError):
                    self.verify(json.dumps(dict(original, **{field: invalid})).encode())
        # A 64-byte signature ends in ==; change unused pad bits without changing its decoded value.
        value = original["signature"]
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        invalid = value[:-3] + alphabet[alphabet.index(value[-3]) + 1] + "=="
        self.assertEqual(base64.b64decode(value), base64.b64decode(invalid))
        with self.assertRaises(InvoiceError):
            self.verify(json.dumps(dict(original, signature=invalid)).encode())

    def test_envelope_shape_duplicates_and_json_are_rejected(self):
        original = sign_invoice(self.raw, self.key, domain=self.domain)
        for raw in (
            b"{}",
            b"[]",
            b"null",
            b"true",
            b"",
            b"\xef\xbb\xbf" + original,
            b"\xff",
            original[:-1] + b',"bytes":"duplicate"}',
            original[:-1] + b',"extra":1}',
            original.replace(b'"signature"', b'"signature":null,"signat\\u0075re"'),
        ):
            with self.subTest(raw=raw[:24]), self.assertRaises(InvoiceError):
                self.verify(raw)

    def test_top_level_members_are_exact(self):
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

    def test_integer_token_grammar_is_strict(self):
        for field in ("bestBefore",):
            old = b'"' + field.encode() + b'":' + str(json.loads(self.raw)[field]).encode()
            for token in (b"true", b'"1"', b"-0", b"1.0", b"1e0", b"-1", b"01", b"9007199254740992"):
                raw = self.raw.replace(old, b'"' + field.encode() + b'":' + token)
                with self.subTest(field=field, token=token), self.assertRaises(InvoiceError):
                    decode_invoice(raw)

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
            # root/service are two containers; the leaf is scalar.
            nested = b"[" * (depth - 2) + b"0" + b"]" * (depth - 2)
            fields = json.loads(self.raw)
            fields["service"] = {}
            raw = json.dumps(fields, separators=(",", ":")).encode().replace(b'"service":{}', b'"service":{"x":' + nested + b"}")
            if depth == 16:
                self.assertEqual(raw, self.verify(sign_invoice(raw, self.key, domain=self.domain)))
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

    def test_byte_limit_counts_utf8_and_excludes_prefix(self):
        fields = json.loads(self.raw)
        fields["service"] = {"text": "é"}
        raw = encode_invoice(fields)
        padded = raw + b" " * (16384 - len(raw))
        envelope = sign_invoice(padded, self.key, domain=self.domain)
        self.assertEqual(21963, len(envelope))
        self.assertEqual(padded, self.verify(envelope))
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

    def test_signer_rejects_invalid_document_before_issuing_signature(self):
        with self.assertRaises(InvoiceError):
            sign_invoice(self.changed("payment", {"asset": "eip155:1/slip44:60", "amount": "0"}), self.key, domain=self.domain)
        with self.assertRaises(TypeError):
            sign_invoice(self.raw, self.key.public_key(), domain=self.domain)
        for value in (self.raw.decode(), bytearray(self.raw), None):
            with self.assertRaises(TypeError):
                decode_invoice(value)
