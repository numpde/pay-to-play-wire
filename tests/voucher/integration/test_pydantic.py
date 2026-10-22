"""The shared field bridge retains voucher protocol ownership and explicit trust."""

from tools.ops.container_guard import require_container

require_container()

import json
import unittest

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from wire.voucher import SignedVoucher, VoucherDomain, build_voucher_typed_data, sign_voucher, verify_voucher
from wire.voucher.pydantic import SignedVoucherValue


class Response(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    voucher: SignedVoucherValue


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.domain = VoucherDomain(31337, bytes.fromhex("33" * 20))
        self.signer = bytes.fromhex("19e7e376e7c213b7e7e7e46cc70a5dd086daff2a")
        self.artifact = sign_voucher(
            build_voucher_typed_data(
                domain=self.domain, customer=bytes(20), channel_id=0, cumulative_total=2**256 - 1, invoice_hash=bytes(32)
            ),
            bytes.fromhex("11" * 32),
        )
        self.adapter = TypeAdapter(SignedVoucherValue)

    def test_core_mapping_and_framework_roundtrips_preserve_signature_and_identity(self):
        self.assertEqual(self.artifact, SignedVoucher.from_dict(self.artifact.to_dict()))
        for value in (self.artifact, self.artifact.to_dict()):
            response = Response(voucher=value)
            self.assertEqual(SignedVoucher, type(response.voucher))
            self.assertEqual(self.artifact, response.voucher)
            self.assertEqual({"voucher": self.artifact.to_dict()}, response.model_dump())
            self.assertEqual(response, Response.model_validate_json(response.model_dump_json()))
        self.assertEqual(self.artifact, self.adapter.validate_json(self.artifact.to_json()))
        self.assertEqual(self.artifact.to_dict(), self.adapter.dump_python(self.artifact))
        self.assertEqual(self.artifact.to_dict(), json.loads(self.adapter.dump_json(self.artifact)))

    def test_core_schema_projects_the_ordered_contract_without_leaking_mutable_state(self):
        for mode in ("validation", "serialization"):
            schema = self.adapter.json_schema(mode=mode)
            self.assertEqual(SignedVoucher.json_schema(), schema)
            self.assertEqual(schema, Response.model_json_schema(mode=mode)["properties"]["voucher"])
            typed = schema["properties"]["typedData"]
            self.assertEqual(self.artifact.typed_data["types"], typed["properties"]["types"]["const"])
            for type_name, section in (("EIP712Domain", "domain"), ("Voucher", "message")):
                projected = typed["properties"][section]
                names = [field["name"] for field in self.artifact.typed_data["types"][type_name]]
                self.assertEqual(names, projected["required"])
                self.assertEqual(names, list(projected["properties"]))
                self.assertEqual(False, projected["additionalProperties"])
        schema["properties"]["typedData"]["properties"]["types"]["const"]["Voucher"].clear()
        schema["required"].clear()
        self.assertEqual(
            self.artifact.typed_data["types"],
            SignedVoucher.json_schema()["properties"]["typedData"]["properties"]["types"]["const"],
        )
        self.assertEqual(self.adapter.json_schema(), SignedVoucher.json_schema())

    def test_core_and_framework_reject_the_same_unsafe_mappings(self):
        documents = [{}, dict(self.artifact.to_dict(), extra=True)]
        for section, name, value in (
            ("domain", "version", "1"),
            ("domain", "chainId", 31337),
            ("message", "channelId", "01"),
            ("message", "cumulativeTotal", str(2**256)),
            ("message", "invoiceHash", "0x" + "AB" * 32),
        ):
            document = self.artifact.to_dict()
            document["typedData"][section][name] = value
            documents.append(document)
        document = self.artifact.to_dict()
        document["typedData"]["types"]["Voucher"].reverse()
        documents.append(document)
        documents.append(dict(self.artifact.to_dict(), signature="0x" + "00" * 65))
        for document in documents:
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    SignedVoucher.from_dict(document)
                with self.assertRaises(ValidationError):
                    self.adapter.validate_python(document)
                with self.assertRaises(ValidationError):
                    self.adapter.validate_json(json.dumps(document))
        for value in (None, [], self.artifact.to_json()):
            with self.assertRaises(TypeError):
                SignedVoucher.from_dict(value)
            with self.assertRaises(ValidationError):
                self.adapter.validate_python(value)

    def test_framework_parsing_does_not_verify_the_registered_signer(self):
        carried = self.artifact.to_dict()
        carried["typedData"]["message"]["channelId"] = "1"
        artifact = self.adapter.validate_python(carried)
        self.assertEqual(carried, artifact.to_dict())
        with self.assertRaises(ValueError):
            verify_voucher(artifact, expected_domain=self.domain, expected_signer=self.signer)

    def test_raw_duplicate_rejection_remains_at_the_byte_boundary(self):
        raw = self.artifact.to_json().replace(b'"channelId":"0"', b'"channelId":"0","channelId":"0"')
        with self.assertRaises(ValueError):
            SignedVoucher.from_json(raw)
        self.assertEqual(self.artifact, self.adapter.validate_python(json.loads(raw)))
