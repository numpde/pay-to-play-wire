"""A format hint can explain failed original-byte verification, never repair it."""

from tools.ops.container_guard import require_container

require_container()

import base64
import json
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.helpers.acceptances import document, receipt_key
from tests.helpers.invoices import invoice_fields
from wire import CanonicalJSON, CanonicalJSONError
from wire.acceptance import (
    AcceptanceError,
    SignedAcceptance,
    decode_acceptance,
    encode_acceptance,
    sign_acceptance,
    verify_acceptance,
)
from wire.invoice import InvoiceError, SignedInvoice, decode_invoice, encode_invoice, sign_invoice, verify_invoice
from wire.json import signature_failure_hint
from wire.voucher import SignedVoucher


def segment(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class SignatureHintTests(unittest.TestCase):
    def profiles(self):
        return (
            (InvoiceError, SignedInvoice, encode_invoice(invoice_fields()), sign_invoice, verify_invoice),
            (AcceptanceError, SignedAcceptance, encode_acceptance(document()), sign_acceptance, verify_acceptance),
        )

    def test_valid_noncanonical_signed_payload_is_accepted_without_diagnostic_work(self):
        for _error, artifact_type, raw, sign, verify in self.profiles():
            with self.subTest(profile=artifact_type.__name__):
                noncanonical = b" " + CanonicalJSON.encode_json(raw).bytes + b"\n"
                artifact = sign(noncanonical, receipt_key())
                with patch("wire._jws.signature_failure_hint", side_effect=AssertionError("Success inspected canonicality.")):
                    self.assertEqual(artifact.document, verify(artifact, public_key=receipt_key().public_key()))
                self.assertEqual(noncanonical, artifact.payload_bytes)

    def test_canonical_bad_signature_preserves_exact_error_and_original_cause_without_hint(self):
        for error, artifact_type, raw, sign, verify in self.profiles():
            with self.subTest(profile=artifact_type.__name__):
                artifact = sign(CanonicalJSON.encode_json(raw).bytes, receipt_key())
                bad = artifact_type(artifact.protected, artifact.payload, segment(bytes(64)))
                with patch("wire._jws.signature_failure_hint", wraps=signature_failure_hint) as diagnostic:
                    with self.assertRaises(error) as caught:
                        verify(bad, public_key=receipt_key().public_key())
                diagnostic.assert_called_once_with(artifact.payload_bytes)
                self.assertEqual(error, type(caught.exception))
                self.assertEqual(InvalidSignature, type(caught.exception.__cause__))
                self.assertEqual(None, caught.exception.canonical_json_hint)
                self.assertNotIn("canonical JSON", str(caught.exception))

    def test_key_binding_failure_does_not_claim_a_cryptographic_canonicality_issue(self):
        for error, artifact_type, raw, sign, verify in self.profiles():
            with self.subTest(profile=artifact_type.__name__):
                artifact = sign(raw, receipt_key())
                with patch("wire._jws.signature_failure_hint", side_effect=AssertionError("Key binding inspected canonicality.")):
                    with self.assertRaises(error) as caught:
                        verify(artifact, public_key=Ed25519PrivateKey.generate().public_key())
                self.assertEqual(None, caught.exception.canonical_json_hint)
                self.assertEqual(None, caught.exception.__cause__)

    def test_noncanonical_bad_signature_is_not_retried_on_rewritten_bytes(self):
        for error, artifact_type, raw, sign, verify in self.profiles():
            with self.subTest(profile=artifact_type.__name__):
                canonical = sign(CanonicalJSON.encode_json(raw).bytes, receipt_key())
                noncanonical = b" " + canonical.payload_bytes + b"\n"
                bad = artifact_type(canonical.protected, segment(noncanonical), canonical.signature)
                original = bad.compact
                with patch("wire._jws.signature_failure_hint", wraps=signature_failure_hint) as diagnostic:
                    with self.assertRaises(error) as caught:
                        verify(bad, public_key=receipt_key().public_key())
                diagnostic.assert_called_once_with(noncanonical)
                self.assertEqual(error, type(caught.exception))
                self.assertEqual(InvalidSignature, type(caught.exception.__cause__))
                self.assertEqual(signature_failure_hint(noncanonical), caught.exception.canonical_json_hint)
                self.assertIn(caught.exception.canonical_json_hint, str(caught.exception))
                self.assertIn("may be a cause", str(caught.exception))
                self.assertNotIn(bad.payload, str(caught.exception))
                self.assertNotIn(bad.signature, str(caught.exception))
                self.assertEqual(original, bad.compact)
                # The old signature really verifies the canonical original;
                # retrying a rewritten input would have turned failure into success.
                self.assertEqual(canonical.document, verify(canonical, public_key=receipt_key().public_key()))

    def test_public_hint_is_bounded_safe_and_does_not_assert_signature_or_schema(self):
        self.assertEqual(None, signature_failure_hint(b'{"a":1}'))
        for raw in (b'{ "private":"do-not-echo"}', b"invalid-json", b"\xff", b'{"a":1,"a":2}'):
            hint = signature_failure_hint(raw)
            self.assertEqual(str, type(hint))
            self.assertLess(len(hint), 400)
            self.assertNotIn("do-not-echo", hint)
        with self.assertRaises(TypeError):
            signature_failure_hint("{}")
        raw = b'"' + b"a" * 20000 + b'"'
        self.assertEqual(None, signature_failure_hint(raw, max_bytes=32768))

    def test_hint_relays_the_failed_rule_without_parser_document_or_cause(self):
        for raw, reason in (
            (b'{"secret":"do-not-echo",}', "line 1, column 25"),
            (b'"do-not-echo\xff"', "invalid UTF-8 at byte 12"),
            (b'{"secret":"do-not-echo","secret":0}', "duplicate object member"),
            (b' {"secret":"do-not-echo"}', "received bytes must already use the canonical encoding"),
            (b'"' + b"x" * 20000 + b'"', "supplied byte limit"),
        ):
            with self.subTest(reason=reason):
                hint = signature_failure_hint(raw)
                self.assertIn(reason, hint)
                self.assertIn("may be a cause", hint)
                self.assertNotIn("do-not-echo", hint)
                self.assertNotIn("Traceback", hint)
                self.assertLess(len(hint), 400)

    def test_json_parsers_preserve_distinct_safe_diagnostics_and_original_causes(self):
        parsers = (
            (CanonicalJSONError, CanonicalJSON.from_bytes),
            (InvoiceError, decode_invoice),
            (AcceptanceError, decode_acceptance),
            (ValueError, SignedVoucher.from_json),
        )
        for error, parse in parsers:
            for raw, cause, reason in (
                (b'{"secret":"do-not-echo",}', json.JSONDecodeError, "line 1, column 25"),
                (b'"do-not-echo\xff"', UnicodeDecodeError, "invalid UTF-8 at byte 12"),
            ):
                with self.subTest(parser=parse, reason=reason):
                    with self.assertRaises(error) as caught:
                        parse(raw)
                    self.assertEqual(error, type(caught.exception))
                    self.assertEqual(cause, type(caught.exception.__cause__))
                    self.assertIn(reason, str(caught.exception))
                    self.assertNotIn("do-not-echo", str(caught.exception))
