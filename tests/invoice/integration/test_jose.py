"""Independent Python JOSE library proves RFC 9864 Ed25519 interoperability."""

from tools.ops.container_guard import require_container

require_container()

import base64
import json
import unittest
from importlib.resources import files

from joserfc import jws
from joserfc.jwk import OKPKey

from tests.helpers.invoices import PROVIDER, signing_key
from wire.invoice import SignedInvoice, decode_invoice, verify_invoice
from wire.invoice.jws import INVOICE_TYPE


class JOSEInteropTests(unittest.TestCase):
    def test_real_joserfc_verifies_and_regenerates_flattened_and_compact_vectors(self):
        key = signing_key()
        private = OKPKey.import_key(
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": PROVIDER,
                "d": base64.urlsafe_b64encode(key.private_bytes_raw()).rstrip(b"=").decode(),
            }
        )
        public = OKPKey.import_key({"kty": "OKP", "crv": "Ed25519", "x": PROVIDER})
        vectors = json.loads(files("wire").joinpath("vectors/invoice.json").read_bytes())
        header = {"alg": "Ed25519", "typ": INVOICE_TYPE}
        for case in vectors["cases"]:
            with self.subTest(case=case["name"]):
                artifact = SignedInvoice(**case["invoice"])
                raw = case["payloadUtf8"].encode()
                compact = jws.deserialize_compact(artifact.compact, public, algorithms=["Ed25519"])
                flattened = jws.deserialize_json(artifact.to_dict(), public, algorithms=["Ed25519"])
                self.assertEqual(raw, compact.payload)
                self.assertEqual(header, compact.protected)
                self.assertEqual(raw, flattened.payload)
                self.assertEqual(header, flattened.headers())
                generated_compact = jws.serialize_compact(header, raw, private, algorithms=["Ed25519"])
                generated_json = jws.serialize_json({"protected": header}, raw, private, algorithms=["Ed25519"])
                self.assertEqual(artifact.compact, generated_compact)
                self.assertEqual(artifact.to_dict(), generated_json)
                self.assertEqual(
                    decode_invoice(raw),
                    verify_invoice(SignedInvoice.from_compact(generated_compact), public_key=key.public_key()),
                )
