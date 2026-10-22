"""Duplicate-aware bounded JSON parsing shared by the signed JWS profiles."""

import json
import re
from dataclasses import dataclass

MAX_DEPTH = 16
MAX_DOCUMENT_BYTES = 16384
MAX_SAFE_INTEGER = (1 << 53) - 1
UNSIGNED = re.compile(r"0|[1-9][0-9]*", re.ASCII)


@dataclass(frozen=True)
class NumberToken:
    token: str


def load_json(raw, *, error, name, number_type=NumberToken):
    if type(raw) is not bytes:
        raise TypeError(f"{name.capitalize()} JSON must be supplied as exact UTF-8 bytes.")

    def object_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise error(f"Cannot decode {name} JSON: duplicate object member.")
            result[key] = value
        return result

    def reject_constant(_token):
        raise error(f"Cannot decode {name} JSON: NaN and Infinity are not JSON numbers.")

    def check_tree(value, depth):
        if isinstance(value, (dict, list)):
            depth += 1
            if depth > MAX_DEPTH:
                raise error(f"Cannot decode {name} JSON: container depth exceeds 16.")
            if isinstance(value, dict):
                for key in value:
                    check_tree(key, depth)
                children = value.values()
            else:
                children = value
            for child in children:
                check_tree(child, depth)
        elif isinstance(value, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise error(f"Cannot decode {name} JSON: unpaired Unicode surrogate.")

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=object_fields,
            parse_int=number_type,
            parse_float=number_type,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise error(f"Cannot decode {name} JSON: expected strict UTF-8 JSON without a BOM.") from exc
    check_tree(value, 0)
    return value
