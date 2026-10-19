"""Detached issuance and verification preserve exact bytes and caller authority."""

from tools.ops.container_guard import require_container

require_container()

import base64
import json
import unittest
from importlib.resources import files

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from signed_invoice import (
    InvoiceError,
    decode_envelope,
    encode_envelope,
    encode_invoice,
    invoice_hash,
    invoice_signing_message,
    sign_invoice,
    sign_invoice_detached,
    verify_invoice,
)


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        vectors = json.loads(files("signed_invoice").joinpath("vectors/invoice.json").read_bytes())
        self.domain = vectors["invoicePrefixUtf8"].encode()
        self.raw = vectors["cases"][0]["invoiceUtf8"].encode() + b"\n"
        fields = json.loads(self.raw)
        self.key = Ed25519PrivateKey.generate()
        self.trust = dict(
            merchant_id=fields["merchantId"], merchant_key_id=fields["merchantKeyId"], public_key=self.key.public_key()
        )

    def test_detached_signing_composes_with_envelope_encoding_and_verification(self):
        signature = sign_invoice_detached(self.raw, self.key, domain=self.domain)
        envelope = encode_envelope(self.raw, signature)
        self.assertEqual((self.raw, signature), decode_envelope(envelope))
        self.assertEqual(envelope, sign_invoice(self.raw, self.key, domain=self.domain))
        self.assertEqual(self.raw, verify_invoice(envelope, domain=self.domain, **self.trust))

    def test_external_issuer_signature_is_accepted(self):
        signature = self.key.sign(self.domain + self.raw)
        envelope = json.dumps({"signature": base64.b64encode(signature).decode(), "bytes": base64.b64encode(self.raw).decode()})
        self.assertEqual(self.raw, verify_invoice(envelope.encode(), domain=self.domain, **self.trust))

    def test_envelope_decoding_does_not_claim_authentication(self):
        envelope = encode_envelope(self.raw, bytes(64))
        self.assertEqual((self.raw, bytes(64)), decode_envelope(envelope))
        with self.assertRaises(InvoiceError):
            verify_invoice(envelope, domain=self.domain, **self.trust)

    def test_trusted_domain_is_required_and_is_not_read_from_document(self):
        for domain in (b"another-domain\n", b"domain-without-delimiter", b"\x00domain\xff"):
            with self.subTest(domain=domain):
                self.assertEqual(domain + self.raw, invoice_signing_message(self.raw, domain=domain))
                self.assertNotEqual(invoice_hash(self.raw, domain=self.domain), invoice_hash(self.raw, domain=domain))
                envelope = sign_invoice(self.raw, self.key, domain=domain)
                self.assertEqual(self.raw, verify_invoice(envelope, domain=domain, **self.trust))
                with self.assertRaises(InvoiceError):
                    verify_invoice(envelope, domain=self.domain, **self.trust)
        for operation in (invoice_hash, invoice_signing_message):
            with self.assertRaises(TypeError):
                operation(self.raw)
            for domain in ("domain", bytearray(b"domain"), None):
                with self.assertRaises(TypeError):
                    operation(self.raw, domain=domain)
            with self.assertRaises(ValueError):
                operation(self.raw, domain=b"")

    def test_unsupported_document_versions_fail_before_crypto(self):
        for version in (1, 0, 3):
            fields = json.loads(self.raw)
            fields["version"] = version
            raw = json.dumps(fields).encode()
            with self.subTest(version=version):
                for operation in (invoice_hash, invoice_signing_message):
                    with self.assertRaises(InvoiceError):
                        operation(raw, domain=self.domain)
                with self.assertRaises(InvoiceError):
                    sign_invoice_detached(raw, self.key, domain=self.domain)

    def test_envelope_encoder_rejects_wrong_signature_types_and_lengths(self):
        for signature in (None, "x" * 64, bytearray(64)):
            with self.assertRaises(TypeError):
                encode_envelope(self.raw, signature)
        for signature in (b"", bytes(63), bytes(65)):
            with self.assertRaises(InvoiceError):
                encode_envelope(self.raw, signature)

    def test_python_boundary_types_are_not_coerced(self):
        for fields in (None, [], "{}", b"{}"):
            with self.assertRaises(TypeError):
                encode_invoice(fields)
        envelope = sign_invoice(self.raw, self.key, domain=self.domain)
        for name in ("merchant_id", "merchant_key_id"):
            with self.assertRaises(TypeError):
                verify_invoice(envelope, domain=self.domain, **dict(self.trust, **{name: b"identifier"}))
