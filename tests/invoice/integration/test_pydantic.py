"""Shared optional adapter owns structure/schema; raw duplicate parsing stays explicit."""

from tools.ops.container_guard import require_container

require_container()

import base64
import json
import unittest
from dataclasses import fields

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from tests.helpers.invoices import invoice_fields, signing_key
from wire.invoice import InvoiceError, SignedInvoice, encode_invoice, sign_invoice, verify_invoice
from wire.invoice.pydantic import SignedInvoiceValue


class Response(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    invoice: SignedInvoiceValue


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.artifact = sign_invoice(encode_invoice(invoice_fields()), signing_key())
        self.adapter = TypeAdapter(SignedInvoiceValue)

    def test_core_artifact_and_mapping_inputs_serialize_without_a_mirror_model(self):
        for value in (self.artifact, self.artifact.to_dict()):
            response = Response(invoice=value)
            self.assertEqual(SignedInvoice, type(response.invoice))
            self.assertEqual(self.artifact, response.invoice)
            self.assertEqual({"invoice": self.artifact.to_dict()}, response.model_dump())
            self.assertEqual({"invoice": self.artifact.to_dict()}, json.loads(response.model_dump_json()))
        self.assertEqual(self.artifact, self.adapter.validate_json(self.artifact.to_json()))
        self.assertEqual(self.artifact, SignedInvoice.from_dict(self.artifact.to_dict()))
        self.assertEqual(self.artifact.to_dict(), self.adapter.dump_python(self.artifact))
        self.assertEqual(self.artifact.to_dict(), json.loads(self.adapter.dump_json(self.artifact)))

    def test_schema_projects_required_fields_and_bounds_from_core_artifact(self):
        for mode in ("validation", "serialization"):
            schema = self.adapter.json_schema(mode=mode)
            self.assertEqual(SignedInvoice.json_schema(), schema)
            self.assertEqual("object", schema["type"])
            self.assertEqual(False, schema["additionalProperties"])
            self.assertEqual({member.name for member in fields(SignedInvoice)}, set(schema["required"]))
            self.assertEqual(set(schema["required"]), set(schema["properties"]))
            for member in fields(SignedInvoice):
                projected = schema["properties"][member.name]
                self.assertEqual("string", projected["type"])
                self.assertEqual(member.metadata["min_length"], projected["minLength"])
                self.assertEqual(member.metadata["max_length"], projected["maxLength"])
            response = Response.model_json_schema(mode=mode)
            self.assertEqual(schema, response["properties"]["invoice"])

    def test_mapping_type_contract_and_fresh_schema(self):
        for value in (None, [], self.artifact):
            with self.assertRaises(TypeError):
                SignedInvoice.from_dict(value)
        schema = SignedInvoice.json_schema()
        schema["properties"]["payload"]["maxLength"] = 0
        schema["required"].clear()
        self.assertEqual(self.adapter.json_schema(), SignedInvoice.json_schema())

    def test_structural_adapter_does_not_authenticate_the_signature(self):
        signature = bytearray(base64.urlsafe_b64decode(self.artifact.signature + "=="))
        signature[0] ^= 1
        carried = dict(self.artifact.to_dict(), signature=base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"))
        artifact = self.adapter.validate_python(carried)
        self.assertEqual(carried, artifact.to_dict())
        with self.assertRaises(InvoiceError):
            verify_invoice(artifact, public_key=signing_key().public_key())

    def test_structural_and_profile_rejections_are_enforced_for_python_and_json(self):
        for value in (
            None,
            [],
            self.artifact.compact,
            dict(self.artifact.to_dict(), kid="alias"),
            dict(self.artifact.to_dict(), payload=7),
            dict(self.artifact.to_dict(), protected="e30"),
            dict(self.artifact.to_dict(), signature=self.artifact.signature + "="),
        ):
            with self.subTest(value_type=type(value)), self.assertRaises(ValidationError):
                self.adapter.validate_python(value)
            with self.assertRaises(ValidationError):
                self.adapter.validate_json(json.dumps(value))

    def test_raw_json_duplicate_rejection_requires_the_raw_boundary(self):
        raw = self.artifact.to_json()[:-1] + b',"payload":' + json.dumps(self.artifact.payload).encode() + b"}"
        with self.assertRaises(InvoiceError):
            SignedInvoice.from_json(raw)
        # Framework parsing has already erased duplicate names before a mapping
        # adapter runs. HTTP consumers must reject them before this boundary.
        self.assertEqual(self.artifact, self.adapter.validate_python(json.loads(raw)))
