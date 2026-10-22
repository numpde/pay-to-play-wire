"""Profile, canonical segments, provider binding and full-artifact identity."""

from tools.ops.container_guard import require_container

require_container()

import base64
import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError, replace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from signed_invoice import InvoiceError, SignedInvoice, decode_invoice, encode_invoice, invoice_hash, sign_invoice, verify_invoice
from signed_invoice.jws import INVOICE_TYPE, MAX_JSON_BYTES, PROTECTED_BYTES
from tests.helpers.invoices import BENEFICIARY, invoice_fields, signing_key


def encoded(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class JWSTests(unittest.TestCase):
    def setUp(self):
        self.key = signing_key()
        self.raw = encode_invoice(invoice_fields())
        self.artifact = sign_invoice(self.raw, self.key)

    def external(self, *, header=PROTECTED_BYTES, raw=None, key=None):
        protected = encoded(header)
        payload = encoded(self.raw if raw is None else raw)
        signature = (self.key if key is None else key).sign((protected + "." + payload).encode())
        return SignedInvoice(protected, payload, encoded(signature))

    def test_header_order_whitespace_case_and_type_prefix_preserve_carried_segments(self):
        for typ in (INVOICE_TYPE, INVOICE_TYPE.upper(), INVOICE_TYPE.removeprefix("application/")):
            header = json.dumps({"typ": typ, "alg": "Ed25519"}, indent=2).encode()
            artifact = self.external(header=header)
            self.assertEqual(encoded(header), artifact.protected)
            self.assertEqual(decode_invoice(self.raw), verify_invoice(artifact, public_key=self.key.public_key()))
            self.assertNotEqual(self.artifact.invoice_hash, artifact.invoice_hash)
        # Replacing an equivalent decoded header without re-signing must fail.
        with self.assertRaises(InvoiceError):
            verify_invoice(replace(self.artifact, protected=artifact.protected), public_key=self.key.public_key())

    def test_hash_includes_all_three_segments_but_excludes_outer_json(self):
        expected = "0x" + hashlib.sha256(self.artifact.compact.encode("ascii")).hexdigest()
        self.assertEqual(expected, self.artifact.invoice_hash)
        self.assertEqual(expected, invoice_hash(self.artifact))
        fields = self.artifact.to_dict()
        fields = dict(reversed(list(fields.items())))
        outer = json.dumps(fields, indent=4).encode() + b"\n"
        self.assertEqual(self.artifact, SignedInvoice.from_json(outer))
        self.assertEqual(expected, SignedInvoice.from_json(outer).invoice_hash)
        different_signature = replace(self.artifact, signature=encoded(bytes(64)))
        self.assertNotEqual(expected, different_signature.invoice_hash)
        with self.assertRaises(InvoiceError):
            verify_invoice(different_signature, public_key=self.key.public_key())

    def test_payload_whitespace_order_unicode_and_escapes_are_never_normalized(self):
        for raw in (
            self.raw + b"\n",
            json.dumps(json.loads(self.raw), indent=2).encode(),
            self.raw.replace(b'"provider"', b'"provid\\u0065r"'),
            self.raw.replace(b'"fixtureOnly":true', '"fixtureOnly":true,"text":"é𐐀"'.encode()),
        ):
            artifact = sign_invoice(raw, self.key)
            self.assertEqual(raw, artifact.payload_bytes)
            self.assertEqual(decode_invoice(raw), verify_invoice(artifact, public_key=self.key.public_key()))
            self.assertNotEqual(self.artifact.invoice_hash, artifact.invoice_hash)

    def test_every_payload_field_participates_in_signature_and_hash(self):
        changes = {
            "provider": BENEFICIARY,
            "payment": {"asset": "eip155:1/slip44:60", "amount": "6"},
            "bestBefore": 0,
            "beneficiary": invoice_fields()["provider"],
            "service": None,
        }
        for field, value in changes.items():
            raw = encode_invoice(dict(invoice_fields(), **{field: value}))
            altered = replace(self.artifact, payload=encoded(raw))
            with self.subTest(field=field):
                self.assertNotEqual(self.artifact.invoice_hash, altered.invoice_hash)
                with self.assertRaises(InvoiceError):
                    verify_invoice(altered, public_key=self.key.public_key())
        asset_only = dict(invoice_fields(), payment={"asset": "cosmos:cosmoshub-3/slip44:118", "amount": "5"})
        altered = replace(self.artifact, payload=encoded(encode_invoice(asset_only)))
        self.assertNotEqual(self.artifact.invoice_hash, altered.invoice_hash)
        with self.assertRaises(InvoiceError):
            verify_invoice(altered, public_key=self.key.public_key())

    def test_valid_signature_from_another_trusted_provider_is_rejected(self):
        other = Ed25519PrivateKey.generate()
        artifact = self.external(key=other)
        with self.assertRaisesRegex(InvoiceError, "provider differs"):
            verify_invoice(artifact, public_key=other.public_key())
        with self.assertRaisesRegex(InvoiceError, "provider differs"):
            sign_invoice(self.raw, other)
        with self.assertRaises(InvoiceError):
            verify_invoice(artifact, public_key=self.key.public_key())

    def test_rejects_wrong_algorithms_types_members_and_duplicate_header_names(self):
        for header in (
            b"{}",
            b"[]",
            b"null",
            b"\xff",
            b"\xef\xbb\xbf" + PROTECTED_BYTES,
            b'{"alg":"Ed25519","alg":"Ed25519","typ":"' + INVOICE_TYPE.encode() + b'"}',
            b'{"alg":"Ed25519","\\u0061lg":"Ed25519","typ":"' + INVOICE_TYPE.encode() + b'"}',
        ):
            with self.subTest(header=header[:24]), self.assertRaises(InvoiceError):
                self.external(header=header)
        for alg in ("none", "EdDSA", "Ed448", "HS256", "ed25519", True, None, {}):
            with self.subTest(alg=alg), self.assertRaises(InvoiceError):
                self.external(header=json.dumps({"alg": alg, "typ": INVOICE_TYPE}).encode())
        for typ in (None, True, {}, "JWT", "application/vnd.signed-invoice.v2+json", INVOICE_TYPE + ";charset=UTF-8"):
            with self.subTest(typ=typ), self.assertRaises(InvoiceError):
                self.external(header=json.dumps({"alg": "Ed25519", "typ": typ}).encode())
        for field in ("kid", "jwk", "jku", "x5u", "crit", "b64"):
            with self.subTest(field=field), self.assertRaises(InvoiceError):
                self.external(header=json.dumps({"alg": "Ed25519", "typ": INVOICE_TYPE, field: False}).encode())

    def test_all_segments_require_canonical_unpadded_base64url(self):
        for field in ("protected", "payload", "signature"):
            original = getattr(self.artifact, field)
            for value in ("", original + "=", original + "\n", "+" + original[1:], "/" + original[1:], "é", "A"):
                with self.subTest(field=field, value=value[:12]), self.assertRaises(InvoiceError):
                    replace(self.artifact, **{field: value})
            for value in (None, 1, True, b"A"):
                with self.assertRaises(TypeError):
                    replace(self.artifact, **{field: value})
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        signature = self.artifact.signature
        alternate = signature[:-1] + alphabet[alphabet.index(signature[-1]) + 1]
        self.assertEqual(base64.urlsafe_b64decode(signature + "=="), base64.urlsafe_b64decode(alternate + "=="))
        with self.assertRaises(InvoiceError):
            replace(self.artifact, signature=alternate)
        for size in (0, 63, 65):
            with self.assertRaises(InvoiceError):
                replace(self.artifact, signature=encoded(bytes(size)))

    def test_json_envelope_and_compact_shape_limits_and_duplicate_rejection(self):
        raw = self.artifact.to_json()
        for value in (
            b"{}",
            b"[]",
            b"null",
            b"true",
            b"",
            b"\xef\xbb\xbf" + raw,
            b"\xff",
            raw[:-1] + b',"payload":"duplicate"}',
            raw[:-1] + b',"payl\\u006fad":"duplicate"}',
            raw[:-1] + b',"header":{}}',
            raw[:-1] + b',"signatures":[]}',
            raw.replace(b'"payload":', b'"payload":null,"extra":'),
        ):
            with self.subTest(value=value[:20]), self.assertRaises(InvoiceError):
                SignedInvoice.from_json(value)
        self.assertEqual(self.artifact, SignedInvoice.from_json(raw + b" " * (MAX_JSON_BYTES - len(raw))))
        with self.assertRaises(InvoiceError):
            SignedInvoice.from_json(raw + b" " * (MAX_JSON_BYTES - len(raw) + 1))
        for value in ("", self.artifact.compact + ".", "." + self.artifact.compact, "x" * 22277, ".."):
            with self.assertRaises(InvoiceError):
                SignedInvoice.from_compact(value)
        for old in (b'{"bytes":"e30=","signature":"AA=="}', b'{"protected":"","payload":"","signature":""}'):
            with self.assertRaises(InvoiceError):
                SignedInvoice.from_json(old)

    def test_protected_header_resource_boundary(self):
        header = PROTECTED_BYTES + b" " * (256 - len(PROTECTED_BYTES))
        artifact = self.external(header=header)
        self.assertEqual(decode_invoice(self.raw), verify_invoice(artifact, public_key=self.key.public_key()))
        with self.assertRaises(InvoiceError):
            self.external(header=header + b" ")

    def test_accessors_are_fresh_and_artifact_is_immutable_without_authentication_claim(self):
        fields = self.artifact.document
        fields["payment"]["amount"] = "999"
        self.assertEqual("5", self.artifact.document["payment"]["amount"])
        with self.assertRaises(FrozenInstanceError):
            self.artifact.signature = "changed"
        with self.assertRaises(AttributeError):
            _ = self.artifact.__dict__

    def test_wrong_python_api_types_are_not_coerced(self):
        for value in (None, self.artifact.to_dict(), self.artifact.to_json(), self.artifact.compact):
            with self.assertRaises(TypeError):
                verify_invoice(value, public_key=self.key.public_key())
            with self.assertRaises(TypeError):
                invoice_hash(value)
        for value in (None, "{}", bytearray(b"{}")):
            with self.assertRaises(TypeError):
                SignedInvoice.from_json(value)
        for value in (None, b"..", {}):
            with self.assertRaises(TypeError):
                SignedInvoice.from_compact(value)
        for key in (None, b"key", self.key):
            with self.assertRaises(TypeError):
                verify_invoice(self.artifact, public_key=key)
        with self.assertRaises(TypeError):
            sign_invoice(self.raw, self.key.public_key())
