"""Malformed scalar representations fail without normalization or conversion."""

from tools.ops.container_guard import require_container

require_container()

import unittest

from signed_invoice import InvoiceError, require_amount, require_asset, require_best_before, require_public_key
from tests.helpers.invoices import PROVIDER


class FieldRejectionTests(unittest.TestCase):
    def test_wrong_python_types_are_not_coerced(self):
        for validate in (require_amount, require_asset, require_public_key):
            for value in (None, True, 1, b"value", {}):
                with self.subTest(validate=validate.__name__, value=value), self.assertRaises(TypeError):
                    validate(value)
        for value in (True, "1", 1.0, None):
            with self.assertRaises(TypeError):
                require_best_before(value)

    def test_public_keys_have_one_spelling(self):
        for value in (
            "",
            PROVIDER + "=",
            PROVIDER[:-1],
            PROVIDER + "A",
            "+" + PROVIDER[1:],
            "/" + PROVIDER[1:],
            PROVIDER + "\n",
            "é" * 43,
            PROVIDER[:-1] + "p",
        ):
            with self.subTest(value=value), self.assertRaises(InvoiceError):
                require_public_key(value)

    def test_amounts_are_positive_canonical_decimal_strings(self):
        for value in ("", "0", "01", "+1", "-0", "-1", " 1", "1\n", "1.0", "1e0", "\u0661", "9" * 16385):
            with self.subTest(value=value[:10]), self.assertRaises(InvoiceError):
                require_amount(value)

    def test_best_before_range(self):
        for value in (-1, 2**53):
            with self.assertRaises(InvoiceError):
                require_best_before(value)

    def test_caip_component_bounds_separators_and_alphabets(self):
        for value in (
            "native",
            "ETH",
            "0x" + "e" * 40,
            "aa:1/slip44:60",
            "a" * 9 + ":1/slip44:60",
            "EIP155:1/slip44:60",
            "eip155:/slip44:60",
            "eip155:" + "x" * 33 + "/slip44:60",
            "eip155:a.b/slip44:60",
            "eip155:1/aa:60",
            "eip155:1/" + "a" * 9 + ":60",
            "eip155:1/SLIP44:60",
            "eip155:1/slip44:",
            "eip155:1/slip44:" + "a" * 129,
            "eip155:1/slip44:a_b",
            "eip155:1/slip44:60/",
            "eip155:1/slip44:60/" + "a" * 79,
            "eip155:1/slip44:60/a_b",
            "eip155:1/slip44:60/1/2",
            "eip155:1/slip44:60\n",
            "eip155:1/slip44:é",
        ):
            with self.subTest(value=value[:40]), self.assertRaises(InvoiceError):
                require_asset(value)
