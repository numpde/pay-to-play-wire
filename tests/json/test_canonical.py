"""Canonical JSON is encoding evidence, independently of schema and signature trust."""

from tools.ops.container_guard import require_container

require_container()

import json
import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal
from importlib.resources import files

from wire import CanonicalJSON, CanonicalJSONError
from wire.invoice import JsonNumber


class CanonicalTests(unittest.TestCase):
    def test_installed_shared_vectors(self):
        vectors = json.loads(files("wire").joinpath("vectors/json.json").read_bytes())
        for case in vectors["cases"]:
            raw = case["canonicalUtf8"].encode()
            self.assertEqual(raw, CanonicalJSON.encode(case["value"]).bytes)
            self.assertEqual(raw, CanonicalJSON.from_bytes(raw).bytes)
        for raw in vectors["rejectedUtf8"]:
            with self.subTest(raw=raw), self.assertRaises(CanonicalJSONError):
                CanonicalJSON.from_bytes(raw.encode())

    def test_jcs_reference_numbers_and_utf16_key_order(self):
        # RFC 8785 sections 3.2.2 and 3.2.3, independently specified bytes.
        value = {"numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27]}
        self.assertEqual(b'{"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27]}', bytes(CanonicalJSON.encode(value)))
        keys = {"\u20ac": 1, "\r": 2, "\ufb33": 3, "1": 4, "\U0001f600": 5, "\u0080": 6, "\u00f6": 7}
        expected = '{"\\r":2,"1":4,"\u0080":6,"ö":7,"€":1,"😀":5,"דּ":3}'.encode()
        self.assertEqual(expected, CanonicalJSON.encode(keys).bytes)

    def test_binary64_roundtrips_including_large_integer_spelling(self):
        cases = (
            (0.0, b"0"),
            (-0.0, b"0"),
            (1e20, b"100000000000000000000"),
            (1e21, b"1e+21"),
            (1e-6, b"0.000001"),
            (1e-7, b"1e-7"),
            (5e-324, b"5e-324"),
            (1.7976931348623157e308, b"1.7976931348623157e+308"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                encoded = CanonicalJSON.encode(value)
                self.assertEqual(expected, encoded.bytes)
                self.assertEqual(encoded, CanonicalJSON.from_bytes(expected))
                self.assertEqual(value, encoded.value)
        for value in (-(2**53) + 1, 2**53 - 1):
            self.assertEqual(value, CanonicalJSON.encode(value).value)
            self.assertEqual(int, type(CanonicalJSON.encode(value).value))
        self.assertEqual(float, type(CanonicalJSON.from_bytes(b"100000000000000000000").value))
        self.assertEqual(float, type(CanonicalJSON.from_bytes(b"9007199254740992").value))
        for value in (-(2**53), 2**53):
            with self.assertRaises(CanonicalJSONError):
                CanonicalJSON.encode(value)

    def test_unsigned_encoding_and_admitted_value_are_immutable_and_fresh(self):
        value = {"z": [None, True, False, 'line\nquote"slash\\/'], "a": {"n": 1}}
        encoded = CanonicalJSON.encode(value)
        value["z"].clear()
        projected = encoded.value
        projected["a"].clear()
        admitted = CanonicalJSON.from_bytes(encoded.bytes)
        self.assertEqual(encoded, admitted)
        self.assertEqual(hash(encoded), hash(admitted))
        self.assertEqual({"n": 1}, admitted.value["a"])
        self.assertEqual(True, admitted.value["z"][1])
        self.assertEqual(encoded.bytes, bytes(admitted))
        with self.assertRaises(FrozenInstanceError):
            admitted._raw = b"invalid"
        # Encoding validity makes no application-schema or signature claim.
        self.assertEqual("not-an-artifact", CanonicalJSON.from_bytes(b'"not-an-artifact"').value)

    def test_equivalent_byte_spellings_are_rejected_without_repair(self):
        for raw in (
            b' {"a":1}',
            b'{"a":1}\n',
            b'{ "a":1}',
            b'{"b":2,"a":1}',
            b'"\\u0061"',
            b'"\\/"',
            b"1.0",
            b"1e0",
            b"-0",
            b"1E+30",
            b"0.0000001",
            b"9007199254740993",
            b"1e-9999",
            b"1.234567890123456789",
        ):
            with self.subTest(raw=raw), self.assertRaises(CanonicalJSONError):
                CanonicalJSON.from_bytes(raw)
        self.assertEqual(b'{"a":1,"b":2}', CanonicalJSON.encode({"b": 2, "a": 1}).bytes)

    def test_duplicates_invalid_unicode_and_nonfinite_numbers_are_rejected(self):
        for raw in (
            b'{"a":1,"a":2}',
            b'{"a":1,"\\u0061":2}',
            b'{"x":{"a":1,"a":2}}',
            b"\xff",
            b"\xef\xbb\xbf{}",
            b'"\\ud800"',
            b'"\\uffff"',
            b'"\\ufdd0"',
            b"NaN",
            b"Infinity",
            b"1e9999",
            b"{}junk",
        ):
            with self.subTest(raw=raw), self.assertRaises(CanonicalJSONError):
                CanonicalJSON.from_bytes(raw)
        for value in (float("inf"), float("nan"), "\udfff", "\ufdd0", "\U0001ffff"):
            with self.subTest(value=value), self.assertRaises(CanonicalJSONError):
                CanonicalJSON.encode(value)
        # No Unicode normalization: these are distinct string values.
        self.assertNotEqual(CanonicalJSON.encode("é"), CanonicalJSON.encode("e\u0301"))

    def test_non_json_inputs_are_not_coerced(self):
        class Hostile:
            def __repr__(self):
                raise AssertionError("Untrusted value was rendered.")

        for value in (Decimal("1.1"), JsonNumber("1.1"), b"bytes", (1, 2), {1: "key"}, Hostile()):
            with self.assertRaises(CanonicalJSONError):
                CanonicalJSON.encode(value)
        for operation in (lambda: CanonicalJSON.from_bytes("{}"), lambda: CanonicalJSON(b"{}", max_bytes=True)):
            with self.assertRaises(TypeError):
                operation()
        with self.assertRaises(ValueError):
            CanonicalJSON.from_bytes(b"0", max_bytes=0)

    def test_size_depth_and_cyclic_inputs_are_bounded(self):
        self.assertEqual(b'"ab"', CanonicalJSON.encode("ab", max_bytes=4).bytes)
        for operation in (
            lambda: CanonicalJSON.encode("ab", max_bytes=3),
            lambda: CanonicalJSON.from_bytes(b'"ab"', max_bytes=3),
        ):
            with self.assertRaises(CanonicalJSONError):
                operation()
        self.assertEqual(b"[" * 16 + b"0" + b"]" * 16, CanonicalJSON.from_bytes(b"[" * 16 + b"0" + b"]" * 16).bytes)
        cyclic = []
        cyclic.append(cyclic)
        for value in (cyclic, [[[]]]):
            maximum = 100 if value is cyclic else 2
            with self.assertRaises(CanonicalJSONError):
                CanonicalJSON.encode(value, max_bytes=maximum)
        with self.assertRaises(CanonicalJSONError):
            CanonicalJSON.from_bytes(b"[" * 17 + b"0" + b"]" * 17)

    def test_http_caller_can_supply_a_larger_explicit_byte_limit(self):
        raw = b'"' + b"a" * 20000 + b'"'
        admitted = CanonicalJSON.from_bytes(raw, max_bytes=32768)
        self.assertEqual(raw, CanonicalJSON.encode("a" * 20000, max_bytes=32768).bytes)
        self.assertEqual(raw, admitted.bytes)
        self.assertEqual("a" * 20000, admitted.value)
        with self.assertRaises(CanonicalJSONError):
            CanonicalJSON.from_bytes(raw)
        with self.assertRaises(CanonicalJSONError):
            CanonicalJSON.from_bytes(raw, max_bytes=20001)
