"""Optional Pydantic integration over the framework-neutral artifact.

Mappings have already lost raw JSON duplicate information. HTTP consumers must
reject duplicate member names before framework parsing. The core from_json
boundary provides that guarantee when the original bytes are available.
"""

from dataclasses import fields
from typing import Annotated

from pydantic_core import core_schema

from .jws import SignedInvoice


def _artifact_fields(value):
    return value.to_dict() if type(value) is SignedInvoice else value


def _construct(values):
    return SignedInvoice(**values)


def _serialize(artifact):
    return artifact.to_dict()


class _SignedInvoiceSchema:
    def __get_pydantic_core_schema__(self, _source_type, _handler):
        mapping = core_schema.typed_dict_schema(
            {
                member.name: core_schema.typed_dict_field(
                    core_schema.str_schema(strict=True, pattern=r"^[A-Za-z0-9_-]+$", **member.metadata)
                )
                for member in fields(SignedInvoice)
            },
            extra_behavior="forbid",
            strict=True,
        )
        construct = core_schema.no_info_after_validator_function(_construct, mapping)
        return core_schema.json_or_python_schema(
            json_schema=construct,
            python_schema=core_schema.no_info_before_validator_function(_artifact_fields, construct),
            serialization=core_schema.plain_serializer_function_ser_schema(_serialize, return_schema=mapping),
        )

    def __get_pydantic_json_schema__(self, schema, handler):
        result = handler(schema)
        result["title"] = "SignedInvoice"
        result["description"] = (
            "Fixed-profile Ed25519 invoice JWS. Structural validity does not authenticate or authorize the provider."
        )
        return result


SignedInvoiceValue = Annotated[SignedInvoice, _SignedInvoiceSchema()]
