"""Shared wire facts return original values without normalization or policy."""

from tools.ops.container_guard import require_container

require_container()

import unittest

from tests.helpers.invoices import PROVIDER
from wire.invoice import require_amount, require_asset, require_best_before, require_public_key


class FieldTests(unittest.TestCase):
    def test_values_are_returned_without_policy_or_conversion(self):
        self.assertEqual(PROVIDER, require_public_key(PROVIDER))
        self.assertEqual("eip155:1/slip44:60", require_asset("eip155:1/slip44:60"))
        self.assertEqual("1", require_amount("1"))
        self.assertEqual("9" * 16384, require_amount("9" * 16384))
        self.assertEqual(0, require_best_before(0))
        self.assertEqual(2**53 - 1, require_best_before(2**53 - 1))

    def test_caip_component_boundaries_and_case_sensitive_reference_alphabet(self):
        for asset in ("aaa:A/a-a:%.-", "a" * 8 + ":" + "A_-0" * 8 + "/" + "a" * 8 + ":" + "B" * 128 + "/" + "C" * 78):
            self.assertEqual(asset, require_asset(asset))
