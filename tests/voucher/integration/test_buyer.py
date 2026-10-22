"""A buyer signs once; independent services verify using their trusted authority."""

from tools.ops.container_guard import require_container

require_container()

import json
import unittest
from importlib.resources import files

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.helpers.invoices import signing_key
from wire.invoice import InvoiceError, SignedInvoice, verify_invoice
from wire.voucher import SignedVoucher, VoucherDomain, build_voucher_typed_data, sign_voucher, verify_voucher


class BuyerTests(unittest.TestCase):
    def test_voucher_authorizes_the_exact_verified_invoice_under_separate_trust_inputs(self):
        vectors = json.loads(files("wire").joinpath("vectors/invoice.json").read_bytes())
        invoice = SignedInvoice(**vectors["cases"][0]["invoice"])
        other_invoice = SignedInvoice(**vectors["cases"][1]["invoice"])
        provider_key = signing_key().public_key()
        verify_invoice(invoice, public_key=provider_key)
        verify_invoice(other_invoice, public_key=provider_key)
        domain = VoucherDomain(31337, bytes.fromhex("33" * 20))
        signer = bytes.fromhex("19e7e376e7c213b7e7e7e46cc70a5dd086daff2a")
        buyer = sign_voucher(
            build_voucher_typed_data(
                domain=domain,
                customer=bytes.fromhex("22" * 20),
                channel_id=7,
                cumulative_total=5,
                invoice_hash=bytes.fromhex(invoice.invoice_hash[2:]),
            ),
            bytes.fromhex("11" * 32),
        )
        merchant = SignedVoucher.from_json(buyer.to_json())
        self.assertIsNone(verify_voucher(merchant, expected_domain=domain, expected_signer=signer))
        self.assertEqual(invoice.invoice_hash, merchant.message["invoiceHash"])
        self.assertNotEqual(other_invoice.invoice_hash, merchant.message["invoiceHash"])

        # Authenticating each artifact does not authorize substituting another signed offer.
        changed = merchant.typed_data
        changed["message"]["invoiceHash"] = other_invoice.invoice_hash
        with self.assertRaises(ValueError):
            verify_voucher(SignedVoucher(changed, merchant.signature), expected_domain=domain, expected_signer=signer)
        with self.assertRaises(InvoiceError):
            verify_invoice(invoice, public_key=Ed25519PrivateKey.from_private_bytes(bytes(32)).public_key())
        with self.assertRaises(ValueError):
            verify_voucher(merchant, expected_domain=domain, expected_signer=bytes.fromhex("22" * 20))
        with self.assertRaises(ValueError):
            verify_voucher(merchant, expected_domain=VoucherDomain(1, domain.verifying_contract), expected_signer=signer)

    def test_transport_preserves_the_signed_invoice_hash_and_signature(self):
        domain = VoucherDomain(31337, bytes.fromhex("33" * 20))
        invoice_hash = bytes.fromhex("6e27a482816c7592f8c08421db21ab5837da7545cdfa54b9904877609fb423c7")
        wallet = build_voucher_typed_data(
            domain=domain, customer=bytes.fromhex("22" * 20), channel_id=7, cumulative_total=5, invoice_hash=invoice_hash
        )
        buyer = sign_voucher(wallet, bytes.fromhex("11" * 32))
        accounting = SignedVoucher.from_json(buyer.to_json())
        merchant = SignedVoucher.from_json(accounting.to_json())
        for service in (accounting, merchant):
            self.assertIsNone(
                verify_voucher(
                    service, expected_domain=domain, expected_signer=bytes.fromhex("19e7e376e7c213b7e7e7e46cc70a5dd086daff2a")
                )
            )
            self.assertEqual("0x" + invoice_hash.hex(), service.message["invoiceHash"])
            self.assertEqual(buyer.signature, service.signature)
            self.assertEqual(buyer.digest, service.digest)
