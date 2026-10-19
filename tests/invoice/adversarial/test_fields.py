"""Malformed scalar facts are rejected without lossy conversion or normalization."""

from tools.ops.container_guard import require_container

require_container()

import unittest

from signed_invoice import (
    InvoiceError,
    require_asset,
    require_deadline,
    require_evm_address,
    require_identifier,
    require_merchant_id,
    require_uint256,
)


class FieldRejectionTests(unittest.TestCase):
    def test_wrong_python_types_are_not_coerced(self):
        for validate in (require_asset, require_evm_address, require_identifier, require_merchant_id, require_uint256):
            for value in (None, True, 1, b"value"):
                with self.subTest(validate=validate.__name__, value=value), self.assertRaises(TypeError):
                    validate(value)
        for value in (True, "1", 1.0, None):
            with self.assertRaises(TypeError):
                require_deadline(value)

    def test_identifier_merchant_and_address_representations_are_exact(self):
        for value in ("", "x" * 129, "unicode-é", "a.b", "a\n"):
            with self.assertRaises(InvoiceError):
                require_identifier(value)
        for value in ("0" * 32, "00000000-0000-ABCD-0000-000000000000", "00000000-0000-0000-0000-000000000000\n"):
            with self.assertRaises(InvoiceError):
                require_merchant_id(value)
        for value in ("0x" + "A" * 40, "0x" + "a" * 39, "0x" + "a" * 40 + "\n", "0X" + "a" * 40):
            with self.assertRaises(InvoiceError):
                require_evm_address(value)
        with self.assertRaises(InvoiceError):
            require_asset("0x" + "0" * 40)

    def test_numeric_limits_reject_noncanonical_and_oversized_values(self):
        for value in ("", "01", "+1", "-0", "1.0", "1e0", "\u0661", str(2**256), "9" * 5000):
            with self.subTest(value=value[:20]), self.assertRaises(InvoiceError):
                require_uint256(value)
        with self.assertRaises(InvoiceError):
            require_uint256("0", positive=True)
        with self.assertRaises(TypeError):
            require_uint256("1", positive=1)
        for value in (-1, 2**53):
            with self.assertRaises(InvoiceError):
                require_deadline(value)
