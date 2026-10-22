"""Shared JSON Schema object projection; protocol parsers remain authoritative."""


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
