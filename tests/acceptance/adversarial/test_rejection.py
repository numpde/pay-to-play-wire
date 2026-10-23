"""Each signed field and strict profile is checked without inventing purchase policy."""

from tools.ops.container_guard import require_container

require_container()

import base64
import json
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.helpers.acceptances import document, receipt_key, vector
from tests.helpers.invoices import invoice_fields
from wire.acceptance import (
    AcceptanceError,
    SignedAcceptance,
    decode_acceptance,
    encode_acceptance,
    sign_acceptance,
    verify_acceptance,
)
from wire.acceptance.jws import ACCEPTANCE_TYPE
from wire.invoice import InvoiceError, SignedInvoice, encode_invoice, sign_invoice


def segment(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class RejectionTests(unittest.TestCase):
    def setUp(self):
        self.raw = vector()["cases"][0]["payloadUtf8"].encode("utf-8")
        self.artifact = sign_acceptance(self.raw, receipt_key())

    def external(self, *, raw=None, header=None):
        protected = self.artifact.protected if header is None else segment(header)
        payload = segment(self.raw if raw is None else raw)
        signature = segment(receipt_key().sign((protected + "." + payload).encode("ascii")))
        return {"protected": protected, "payload": payload, "signature": signature}

    def test_only_the_three_payload_fields_are_accepted(self):
        values = [None, [], {}, {"voucher": document()["voucher"]}, {"acceptedAt": 0}]
        values.extend({key: value for key, value in document().items() if key != missing} for missing in document())
        values.extend(dict(document(), **{name: "extra"}) for name in ("invoiceHash", "kid", "uuid", "hash", "status"))
        for value in values:
            with self.subTest(value=value), self.assertRaises(AcceptanceError):
                decode_acceptance(json.dumps(value).encode())

    def test_signer_requires_canonical_raw32_public_key_text(self):
        for value in (None, True, 1, [], {}, "", "A" * 42, "A" * 44, "A" * 42 + "B", "A" * 43 + "=", "+" * 43, "é" * 43):
            with self.subTest(value=value), self.assertRaises(AcceptanceError):
                encode_acceptance(dict(document(), signer=value))
            with self.subTest(json_value=value), self.assertRaises(AcceptanceError):
                decode_acceptance(json.dumps(dict(document(), signer=value)).encode())

    def test_signer_identity_and_caller_trust_are_both_required(self):
        other_key = Ed25519PrivateKey.generate()
        other = dict(document(), signer=segment(other_key.public_key().public_bytes_raw()))
        raw = encode_acceptance(other)
        with self.assertRaises(AcceptanceError):
            sign_acceptance(raw, receipt_key())
        signed = sign_acceptance(raw, other_key)
        self.assertEqual(other, verify_acceptance(signed, public_key=other_key.public_key()))
        with self.assertRaises(AcceptanceError):
            verify_acceptance(signed, public_key=receipt_key().public_key())
        # Even a valid signature from the trusted key cannot name a different signer.
        mismatched = SignedAcceptance.from_dict(self.external(raw=raw))
        with self.assertRaises(AcceptanceError):
            verify_acceptance(mismatched, public_key=receipt_key().public_key())
        with self.assertRaises(AcceptanceError) as caught:
            verify_acceptance(mismatched, public_key=other_key.public_key())
        self.assertEqual(InvalidSignature, type(caught.exception.__cause__))

    def test_v1_profile_is_rejected_with_and_without_the_new_field(self):
        header = b'{"alg":"Ed25519","typ":"application/vnd.signed-purchase-acceptance.v1+json"}'
        with self.assertRaises(AcceptanceError):
            SignedAcceptance.from_dict(self.external(header=header))
        old = document()
        del old["signer"]
        with self.assertRaises(AcceptanceError):
            SignedAcceptance.from_dict(self.external(raw=json.dumps(old).encode(), header=header))
        with self.assertRaises(AcceptanceError):
            SignedAcceptance.from_dict(self.external(raw=json.dumps(old).encode()))

    def test_accepted_at_lexical_types_and_range_are_not_coerced(self):
        for token in (
            b'"0"',
            b"null",
            b"true",
            b"false",
            b"-0",
            b"-1",
            b"1.0",
            b"1e0",
            b"+1",
            b"01",
            b"9007199254740992",
            b"9" * 100,
        ):
            with self.subTest(token=token), self.assertRaises(AcceptanceError):
                decode_acceptance(self.raw.replace(b'"acceptedAt":2000000000', b'"acceptedAt":' + token))
        for value in (None, True, False, "0", 1.0, -1, 1 << 53):
            with self.subTest(value=value), self.assertRaises(AcceptanceError):
                encode_acceptance(dict(document(), acceptedAt=value))

    def test_full_voucher_schema_and_contract_signature_form_are_required(self):
        mutations = (
            lambda value: value.update(extra=True),
            lambda value: value.pop("signature"),
            lambda value: value.update(signature="0x" + "00" * 65),
            lambda value: value.update(signature=value["signature"][:-2] + "00"),
            lambda value: value["typedData"].update(primaryType="Other"),
            lambda value: value["typedData"]["types"]["Voucher"].reverse(),
            lambda value: value["typedData"]["domain"].update(version="1"),
            lambda value: value["typedData"]["domain"].update(chainId=31337),
            lambda value: value["typedData"]["message"].update(cumulativeTotal=str(1 << 256)),
            lambda value: value["typedData"]["message"].update(invoiceHash="0x" + "AB" * 32),
        )
        for index, mutate in enumerate(mutations):
            fields = document()
            mutate(fields["voucher"])
            with self.subTest(index=index), self.assertRaises(AcceptanceError):
                decode_acceptance(json.dumps(fields).encode())
        for numeric_field, token in ((b'"chainId":"31337"', b'"chainId":31337'), (b'"channelId":"7"', b'"channelId":7')):
            with self.subTest(token=token), self.assertRaises(AcceptanceError):
                decode_acceptance(self.raw.replace(numeric_field, token))

    def test_duplicates_unicode_nonfinite_and_deep_json_are_rejected(self):
        for raw in (
            b"\xff",
            b"\xef\xbb\xbf" + self.raw,
            b"{",
            b"[" * 2000 + b"]" * 2000,
            b'{"voucher":' + b"[" * 16 + b"0" + b"]" * 16 + b',"acceptedAt":0}',
            self.raw[:-1] + b',"acceptedAt":0}',
            self.raw[:-1] + b',"accepted\\u0041t":0}',
            self.raw[:-1] + b',"signer":"' + document()["signer"].encode() + b'"}',
            self.raw[:-1] + b',"sign\\u0065r":"' + document()["signer"].encode() + b'"}',
            self.raw.replace(b'"chainId":"31337"', b'"chainId":"31337","chainId":"31337"'),
            self.raw.replace(b'"version":"2"', b'"version":"\\ud800"'),
            self.raw.replace(b'"acceptedAt":2000000000', b'"acceptedAt":NaN'),
            self.raw.replace(b'"acceptedAt":2000000000', b'"acceptedAt":Infinity'),
        ):
            with self.subTest(prefix=raw[:45]), self.assertRaises(AcceptanceError):
                decode_acceptance(raw)

    def test_resource_boundaries_have_success_and_rejection_witnesses(self):
        bounded = self.raw + b" " * (16384 - len(self.raw))
        self.assertEqual(document(), decode_acceptance(bounded))
        artifact = sign_acceptance(bounded, receipt_key())
        self.assertEqual(bounded, artifact.payload_bytes)
        with self.assertRaises(AcceptanceError):
            decode_acceptance(bounded + b" ")
        raw = artifact.to_json()
        bounded_outer = raw + b" " * (32768 - len(raw))
        self.assertEqual(artifact, SignedAcceptance.from_json(bounded_outer))
        with self.assertRaises(AcceptanceError):
            SignedAcceptance.from_json(bounded_outer + b" ")
        header = json.dumps({"alg": "Ed25519", "typ": ACCEPTANCE_TYPE}).encode()
        bounded_header = header + b" " * (256 - len(header))
        self.assertEqual(document(), SignedAcceptance.from_dict(self.external(header=bounded_header)).document)
        with self.assertRaises(AcceptanceError):
            SignedAcceptance.from_dict(self.external(header=bounded_header + b" "))

    def test_wrong_protected_profiles_and_cross_profile_substitution_are_rejected(self):
        for header in (
            {"alg": "EdDSA", "typ": ACCEPTANCE_TYPE},
            {"alg": "none", "typ": ACCEPTANCE_TYPE},
            {"alg": "Ed25519", "typ": "application/vnd.signed-invoice.v1+json"},
            {"alg": "Ed25519", "typ": ACCEPTANCE_TYPE, "kid": "selector"},
            {"alg": "Ed25519", "typ": ACCEPTANCE_TYPE, "b64": False},
            {"alg": "Ed25519", "typ": None},
        ):
            with self.subTest(header=header), self.assertRaises(AcceptanceError):
                SignedAcceptance.from_dict(self.external(header=json.dumps(header).encode()))
        duplicate = b'{"alg":"Ed25519","alg":"Ed25519","typ":"' + ACCEPTANCE_TYPE.encode() + b'"}'
        with self.assertRaises(AcceptanceError):
            SignedAcceptance.from_dict(self.external(header=duplicate))
        with self.assertRaises(InvoiceError):
            SignedInvoice.from_dict(self.artifact.to_dict())
        invoice = sign_invoice(encode_invoice(invoice_fields()), receipt_key())
        with self.assertRaises(AcceptanceError):
            SignedAcceptance.from_dict(invoice.to_dict())
        with self.assertRaises(AcceptanceError):
            SignedAcceptance.from_dict(self.external(header=b'{"alg":"Ed25519","typ":"application/vnd.signed-invoice.v1+json"}'))

    def test_equivalent_media_spelling_retains_signed_bytes_and_verifies(self):
        header = b'{ "typ":"VND.SIGNED-PURCHASE-ACCEPTANCE.V2+JSON", "alg":"Ed25519" }'
        artifact = SignedAcceptance.from_dict(self.external(header=header))
        self.assertNotEqual(self.artifact.protected, artifact.protected)
        self.assertEqual(segment(header), artifact.protected)
        self.assertEqual(document(), verify_acceptance(artifact, public_key=receipt_key().public_key()))
        carried = SignedAcceptance(artifact.protected, artifact.payload, self.artifact.signature)
        with self.assertRaises(AcceptanceError):
            verify_acceptance(carried, public_key=receipt_key().public_key())

    def test_each_segment_is_strict_canonical_unpadded_base64url(self):
        for name in ("protected", "payload", "signature"):
            for value in ("", "*", getattr(self.artifact, name) + "=", "A", 7):
                with self.subTest(name=name, value=value), self.assertRaises(AcceptanceError):
                    SignedAcceptance.from_dict(dict(self.artifact.to_dict(), **{name: value}))
        # Last-character unused pad bits must not provide alternate spellings.
        for signature in (self.artifact.signature[:-1] + "x", segment(bytes(63)), segment(bytes(65))):
            with self.assertRaises(AcceptanceError):
                SignedAcceptance.from_dict(dict(self.artifact.to_dict(), signature=signature))

    def test_forgery_and_each_carried_field_mutation_fail_receipt_verification(self):
        with self.assertRaises(AcceptanceError):
            verify_acceptance(self.artifact, public_key=Ed25519PrivateKey.generate().public_key())
        signature = bytearray(base64.urlsafe_b64decode(self.artifact.signature + "=="))
        signature[0] ^= 1
        forged = SignedAcceptance(self.artifact.protected, self.artifact.payload, segment(bytes(signature)))
        with self.assertRaises(AcceptanceError) as caught:
            verify_acceptance(forged, public_key=receipt_key().public_key())
        self.assertEqual(InvalidSignature, type(caught.exception.__cause__))
        mutations = (
            lambda value: value.update(signer=segment(Ed25519PrivateKey.generate().public_key().public_bytes_raw())),
            lambda value: value.update(acceptedAt=value["acceptedAt"] + 1),
            lambda value: value["voucher"]["typedData"]["domain"].update(chainId="31338"),
            lambda value: value["voucher"]["typedData"]["domain"].update(verifyingContract="0x" + "44" * 20),
            lambda value: value["voucher"]["typedData"]["message"].update(customer="0x" + "22" * 20),
            lambda value: value["voucher"]["typedData"]["message"].update(channelId="8"),
            lambda value: value["voucher"]["typedData"]["message"].update(cumulativeTotal="6"),
            lambda value: value["voucher"]["typedData"]["message"].update(invoiceHash="0x" + "44" * 32),
            lambda value: value["voucher"].update(signature="0x27" + value["voucher"]["signature"][4:]),
        )
        for index, mutate in enumerate(mutations):
            fields = document()
            mutate(fields)
            altered = SignedAcceptance(self.artifact.protected, segment(encode_acceptance(fields)), self.artifact.signature)
            self.assertEqual(fields, altered.document)
            with self.subTest(index=index), self.assertRaises(AcceptanceError):
                verify_acceptance(altered, public_key=receipt_key().public_key())

    def test_outer_shape_and_typed_python_api_contracts(self):
        for value in ({}, dict(self.artifact.to_dict(), kid="x"), {"protected": "x"}, []):
            with self.subTest(value=value), self.assertRaises(AcceptanceError):
                SignedAcceptance.from_json(json.dumps(value).encode())
        duplicate = self.artifact.to_json()[:-1] + b',"payload":"duplicate"}'
        with self.assertRaises(AcceptanceError):
            SignedAcceptance.from_json(duplicate)
        for operation in (
            lambda: encode_acceptance([]),
            lambda: decode_acceptance("{}"),
            lambda: SignedAcceptance.from_dict([]),
            lambda: SignedAcceptance.from_json("{}"),
            lambda: SignedAcceptance.from_compact(b"x.y.z"),
            lambda: sign_acceptance(self.raw, b"not-a-key"),
            lambda: verify_acceptance({}, public_key=receipt_key().public_key()),
            lambda: verify_acceptance(self.artifact, public_key=b"not-a-key"),
        ):
            with self.assertRaises(TypeError):
                operation()
