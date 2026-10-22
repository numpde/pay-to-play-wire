"""Independent JWS checks and framework integration preserve the signed full voucher."""

from tools.ops.container_guard import require_container

require_container()

import json
import subprocess
import sys
import unittest

from joserfc import jwk, jws
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from tests.helpers.acceptances import document, receipt_key, vector
from wire.acceptance import AcceptanceError, SignedAcceptance, encode_acceptance, sign_acceptance, verify_acceptance
from wire.acceptance.jws import ACCEPTANCE_TYPE
from wire.acceptance.pydantic import SignedAcceptanceValue
from wire.voucher import VoucherDomain, verify_voucher


class Response(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    acceptance: SignedAcceptanceValue


class IntegrationTests(unittest.TestCase):
    def test_joserfc_verifies_and_regenerates_installed_acceptance_vectors(self):
        key = receipt_key()
        private = jwk.OKPKey.import_key(key)
        public = jwk.OKPKey.import_key(key.public_key())
        for case in vector()["cases"]:
            artifact = SignedAcceptance.from_dict(case["acceptance"])
            raw = case["payloadUtf8"].encode()
            compact = jws.deserialize_compact(artifact.compact, public, algorithms=["Ed25519"])
            flattened = jws.deserialize_json(artifact.to_dict(), public, algorithms=["Ed25519"])
            self.assertEqual(raw, compact.payload)
            self.assertEqual(raw, flattened.payload)
            header = {"alg": "Ed25519", "typ": ACCEPTANCE_TYPE}
            self.assertEqual(artifact.compact, jws.serialize_compact(header, raw, private, algorithms=["Ed25519"]))
            self.assertEqual(artifact.to_dict(), jws.serialize_json({"protected": header}, raw, private, algorithms=["Ed25519"]))

    def test_carried_full_voucher_remains_independently_verifiable(self):
        artifact = SignedAcceptance.from_dict(vector()["cases"][0]["acceptance"])
        self.assertEqual(document(), verify_acceptance(artifact, public_key=receipt_key().public_key()))
        self.assertIsNone(
            verify_voucher(
                artifact.voucher,
                expected_domain=VoucherDomain(31337, bytes.fromhex("33" * 20)),
                expected_signer=bytes.fromhex("19e7e376e7c213b7e7e7e46cc70a5dd086daff2a"),
            )
        )

    def test_framework_returns_core_objects_and_projects_schema_without_authenticating(self):
        adapter = TypeAdapter(SignedAcceptanceValue)
        artifact = sign_acceptance(encode_acceptance(document()), receipt_key())
        for value in (artifact, artifact.to_dict()):
            response = Response(acceptance=value)
            self.assertEqual(SignedAcceptance, type(response.acceptance))
            self.assertEqual(artifact, response.acceptance)
            self.assertEqual({"acceptance": artifact.to_dict()}, response.model_dump())
            self.assertEqual(response, Response.model_validate_json(response.model_dump_json()))
        self.assertEqual(artifact, adapter.validate_json(artifact.to_json()))
        self.assertEqual(artifact.to_dict(), adapter.dump_python(artifact))
        self.assertEqual(artifact.to_dict(), json.loads(adapter.dump_json(artifact)))
        for mode in ("validation", "serialization"):
            self.assertEqual(SignedAcceptance.json_schema(), adapter.json_schema(mode=mode))
            self.assertEqual(adapter.json_schema(mode=mode), Response.model_json_schema(mode=mode)["properties"]["acceptance"])
        schema = SignedAcceptance.json_schema()
        schema["properties"]["payload"]["maxLength"] = 0
        self.assertEqual(adapter.json_schema(), SignedAcceptance.json_schema())
        fields = document()
        fields["acceptedAt"] += 1
        payload = sign_acceptance(encode_acceptance(fields), receipt_key()).payload
        carried = dict(artifact.to_dict(), payload=payload)
        parsed = adapter.validate_python(carried)
        self.assertEqual(fields, parsed.document)
        with self.assertRaises(AcceptanceError):
            verify_acceptance(parsed, public_key=receipt_key().public_key())
        for invalid in (None, [], dict(artifact.to_dict(), extra=True), dict(artifact.to_dict(), signature="AA")):
            with self.subTest(value=invalid), self.assertRaises(ValidationError):
                adapter.validate_python(invalid)

    def test_structural_parse_schema_and_receipt_verification_cannot_import_ethereum(self):
        code = """
import importlib.abc
import json
import sys
from importlib.resources import files
sys.path.insert(0, '/workspace/src')
class NoEthereum(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split('.')[0]
        if root.startswith('eth_') or root in {'hexbytes', 'rlp', 'py_ecc', 'ckzg'}:
            raise AssertionError('Structural acceptance attempted Ethereum import: ' + fullname)
sys.meta_path.insert(0, NoEthereum())
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import TypeAdapter
from wire.acceptance import SignedAcceptance, verify_acceptance
from wire.acceptance.pydantic import SignedAcceptanceValue
from wire.voucher import SignedVoucher
vectors = json.loads(files('wire').joinpath('vectors/acceptance.json').read_bytes())
key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(vectors['testPublicKey']))
adapter = TypeAdapter(SignedAcceptanceValue)
for case in vectors['cases']:
    artifact = SignedAcceptance.from_dict(case['acceptance'])
    assert artifact == adapter.validate_json(artifact.to_json())
    assert artifact.to_dict() == adapter.dump_python(artifact)
    assert artifact.document == verify_acceptance(artifact, public_key=key)
    assert artifact.voucher == SignedVoucher.from_json(artifact.voucher.to_json())
    assert SignedVoucher.json_schema()['type'] == 'object'
assert adapter.json_schema() == SignedAcceptance.json_schema()
"""
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)
