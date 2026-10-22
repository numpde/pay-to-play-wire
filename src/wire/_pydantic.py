"""Shared framework bridge for core signed-artifact transport contracts.

Framework mappings have already lost duplicate JSON members. Use from_json on
the original bytes when that rejection is required. Parsing never authenticates.
"""

from dataclasses import dataclass

from pydantic_core import core_schema


@dataclass(frozen=True)
class ArtifactSchema:
    artifact_type: type

    def _mapping(self, value):
        return value.to_dict() if type(value) is self.artifact_type else value

    def __get_pydantic_core_schema__(self, _source_type, _handler):
        mapping = core_schema.dict_schema(strict=True)
        parse = core_schema.no_info_after_validator_function(self.artifact_type.from_dict, mapping)
        return core_schema.json_or_python_schema(
            json_schema=parse,
            python_schema=core_schema.no_info_before_validator_function(self._mapping, parse),
            serialization=core_schema.plain_serializer_function_ser_schema(self.artifact_type.to_dict, return_schema=mapping),
        )

    def __get_pydantic_json_schema__(self, _schema, _handler):
        return self.artifact_type.json_schema()
