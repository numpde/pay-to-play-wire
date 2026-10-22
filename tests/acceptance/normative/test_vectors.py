"""Acceptance binds the complete voucher under exact retained Ed25519 JWS segments."""

from tools.ops.container_guard import require_container

require_container()

import json
import unittest
from dataclasses import FrozenInstanceError

from tests.helpers.acceptances import document, receipt_key, vector
from wire.acceptance import SignedAcceptance, decode_acceptance, encode_acceptance, sign_acceptance, verify_acceptance
from wire.voucher import SignedVoucher


class AcceptanceTests(unittest.TestCase):
    def test_installed_vectors_regenerate_and_verify_without_changing_carried_voucher(self):
        for case in vector()["cases"]:
            raw = case["payloadUtf8"].encode("utf-8")
            artifact = sign_acceptance(raw, receipt_key())
            self.assertEqual(case["acceptance"], artifact.to_dict())
            self.assertEqual(raw, artifact.payload_bytes)
            self.assertEqual(json.loads(raw), verify_acceptance(artifact, public_key=receipt_key().public_key()))
            self.assertEqual(artifact, SignedAcceptance.from_json(artifact.to_json()))
            self.assertEqual(artifact, SignedAcceptance.from_dict(artifact.to_dict()))
            self.assertEqual(artifact, SignedAcceptance.from_compact(artifact.compact))
            self.assertEqual(SignedVoucher.from_dict(json.loads(raw)["voucher"]), artifact.voucher)
            self.assertEqual(json.loads(raw)["voucher"]["signature"], artifact.voucher.signature)
            self.assertEqual(2000000000, artifact.accepted_at)

    def test_payload_whitespace_order_and_outer_json_formatting_preserve_original_segments(self):
        fields = document()
        raw = json.dumps({"acceptedAt": fields["acceptedAt"], "voucher": fields["voucher"]}, indent=2).encode("utf-8")
        artifact = sign_acceptance(raw, receipt_key())
        self.assertEqual(raw, artifact.payload_bytes)
        self.assertEqual(fields, artifact.document)
        self.assertEqual(artifact, SignedAcceptance.from_json(json.dumps(artifact.to_dict(), sort_keys=True, indent=4).encode()))
        self.assertNotEqual(sign_acceptance(encode_acceptance(fields), receipt_key()).payload, artifact.payload)

    def test_accepted_at_endpoints_are_reachable(self):
        for accepted_at in (0, (1 << 53) - 1):
            fields = dict(document(), acceptedAt=accepted_at)
            raw = encode_acceptance(fields)
            self.assertEqual(fields, decode_acceptance(raw))
            artifact = sign_acceptance(raw, receipt_key())
            self.assertEqual(accepted_at, artifact.accepted_at)
            self.assertEqual(fields, verify_acceptance(artifact, public_key=receipt_key().public_key()))

    def test_artifact_and_voucher_projections_are_immutable_or_fresh(self):
        artifact = sign_acceptance(encode_acceptance(document()), receipt_key())
        before = artifact.to_json()
        artifact.document["voucher"]["typedData"]["types"]["Voucher"].clear()
        artifact.voucher.message["channelId"] = "999"
        artifact.to_dict()["signature"] = "removed"
        self.assertEqual(before, artifact.to_json())
        with self.assertRaises(FrozenInstanceError):
            artifact.signature = "removed"
        for forbidden in ("acceptance_hash", "invoice_hash", "signer", "uuid"):
            self.assertEqual(False, hasattr(artifact, forbidden))

    def test_receipt_authentication_does_not_establish_historical_voucher_authority(self):
        fields = document()
        fields["voucher"]["signature"] = "0x" + ((1).to_bytes(32) + (1).to_bytes(32) + b"\x1b").hex()
        artifact = sign_acceptance(encode_acceptance(fields), receipt_key())
        self.assertEqual(fields, verify_acceptance(artifact, public_key=receipt_key().public_key()))
        self.assertEqual(fields["voucher"]["signature"], artifact.voucher.signature)
