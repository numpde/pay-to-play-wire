"""Offers can validate shared wire facts before a complete invoice exists."""

from tools.ops.container_guard import require_container

require_container()

import re
import unittest

from signed_invoice import (
    EVM_ADDRESS_LENGTH,
    EVM_ADDRESS_PATTERN,
    NATIVE_ASSET,
    require_asset,
    require_deadline,
    require_evm_address,
    require_identifier,
    require_merchant_id,
    require_uint256,
)


class FieldTests(unittest.TestCase):
    def test_values_are_returned_without_normalization_or_policy(self):
        merchant = "00000000-0000-0000-0000-000000000000"
        self.assertEqual(merchant, require_merchant_id(merchant))
        self.assertEqual("A_-09", require_identifier("A_-09"))
        zero = "0x" + "0" * 40
        self.assertEqual(zero, require_evm_address(zero))
        self.assertEqual(NATIVE_ASSET, require_asset(NATIVE_ASSET))
        self.assertEqual("0", require_uint256("0"))
        self.assertEqual(str(2**256 - 1), require_uint256(str(2**256 - 1), positive=True))
        self.assertEqual(0, require_deadline(0))
        self.assertEqual(2**53 - 1, require_deadline(2**53 - 1))

    def test_address_schema_metadata_matches_runtime_representation(self):
        self.assertEqual(EVM_ADDRESS_LENGTH, len(NATIVE_ASSET))
        self.assertIsNotNone(re.fullmatch(EVM_ADDRESS_PATTERN, NATIVE_ASSET))
        self.assertIsNone(re.fullmatch(EVM_ADDRESS_PATTERN, NATIVE_ASSET + "\n"))
