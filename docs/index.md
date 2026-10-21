---
layout: default
title: signed-invoice
---

# signed-invoice

The Python package owns the five-field invoice grammar, strict JSON, exact-byte hashing and Ed25519 signatures and envelopes. Applications own provider enrollment and authorization, product schemas, payment routes, admission, persistence, collection and fulfillment.

The main branch prepares the breaking 0.2.0 format described here. Published 0.1.x releases retain their original version-2 grammar and exact assets. Acquire the intended release explicitly and verify its immutable wheel hash before offline installation; switching packages does not migrate stored offers or consumer policy.

## Invoice document

Exactly these five members are required:

```json
{
  "provider": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
  "payment": {"asset": "eip155:1/slip44:60", "amount": "1000000000000000"},
  "bestBefore": 2000003600,
  "beneficiary": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8",
  "service": {"address": "fixture@mail.example.invalid"}
}
```

This is a synthetic example, not an enrolled provider or commercial offer. The provider and beneficiary are independently selected public keys. Both use 43 canonical unpadded base64url characters encoding exactly 32 raw Ed25519 public bytes. Padding, another alphabet, nonzero unused padding bits and JWK objects are rejected. The trusted profile and key APIs fix the algorithm as Ed25519; there is no algorithm negotiation or key alias.

`payment` contains exactly `asset` and `amount`. The asset accepts generic [CAIP-19](https://standards.chainagnostic.org/CAIPs/caip-19) asset-type or asset-ID syntax, including optional token IDs, with the [CAIP-2](https://standards.chainagnostic.org/CAIPs/caip-2) chain component. Spelling and case are preserved. This syntactic check supplies no namespace-specific canonicalization, payable-asset support, denomination, token behavior or route qualification.

`amount` is a positive base-unit decimal string matching `[1-9][0-9]*`. No integer conversion or EVM bound is imposed. Its maximum of 16384 digits derives from the document resource limit; the complete encoded document must still fit within 16384 bytes. A payment adapter must enforce its narrower bounds and supported assets.

`bestBefore` is a canonical JSON integer token in `0..9007199254740991` Unix seconds. Negative zero, fractions, exponents, booleans and strings are rejected. The codec consults no clock: the provider decides whether it can accept and fulfill an offer, including one received late. This field supplies no hard redemption deadline or reservation-release authority.

`service` accepts any JSON value: object, array, string, number, boolean or null. The provider owns its meaning and schema. Every field participates in the hash and signature. No document version, invoice ID, merchant alias, payer, channel, settlement contract or redemption deadline is embedded. The caller's trusted signing context selects this grammar; there is no old-grammar fallback.

## Encoding and verification

```python
from signed_invoice import encode_invoice, sign_invoice, verify_invoice, invoice_hash

# fields is the five-field document above. private_key is the provider's
# cryptography Ed25519PrivateKey. trusted_key comes from application enrollment.
domain = b"P2P-INVOICE-4\n"
raw = encode_invoice(fields)
envelope = sign_invoice(raw, private_key, domain=domain)
authenticated = verify_invoice(envelope, domain=domain, public_key=trusted_key)
digest_hex = invoice_hash(authenticated, domain=domain)
```

The reference consumer profile uses the exact 14 bytes `50 32 50 2d 49 4e 56 4f 49 43 45 2d 34 0a` (`P2P-INVOICE-4` followed by LF). Every cryptographic API requires caller-supplied nonempty `domain` bytes. The library has no default domain, adds no delimiter and never infers trusted context from an invoice. Old candidate profiles must not be used to interpret the new grammar.

The signing message is `domain + raw`. Invoice identity is `0x` plus lowercase SHA-256 of that message. Ordinary Ed25519 signs the full message directly, not its hash. Whitespace, member order, Unicode spelling and escapes are never reconstructed for verification. Retain original invoice bytes and signatures for storage, replay and retransmission. Identical bytes under the same domain have the same identity; issuance recovery and single acceptance or fulfillment remain server responsibilities.

`verify_invoice(envelope, *, domain, public_key)` requires a caller-trusted `cryptography` Ed25519 public-key object. It also requires the document's decoded provider bytes to equal that exact key. A valid signature by a different trusted key is rejected. Signing similarly rejects a private key that does not match the named provider. A document-supplied key cannot establish its own trust.

`encode_invoice(dict)` serializes once in insertion order and validates the result. `decode_invoice(bytes)` returns fresh fields with `bestBefore` as a Python integer and every service number as a lossless `JsonNumber(token)`. Use `JsonNumber` to encode fractions, exponents or very large numbers without rounding. Python floats are rejected. Parsing and hashing do not authenticate an offer.

All documents require strict UTF-8 JSON without a BOM, duplicate decoded member names at any depth, nonfinite numbers or unpaired Unicode surrogates. The maximum document size is 16384 encoded bytes. Maximum container depth is 16, counting the root object as 1. Scalar services do not consume a container level. Lossless numbers and all service value kinds remain subject to these limits.

## Envelopes and scalar helpers

`sign_invoice_detached(raw, private_key, *, domain)` returns the 64-byte signature. `encode_envelope(raw, signature)` returns compact JSON containing exactly `bytes` and `signature`, both canonical padded standard base64. `decode_envelope(envelope)` returns `(raw, signature)` after wire validation without authentication. `invoice_signing_message(raw, *, domain)` returns the validated preimage. The containing transport owns its total envelope-body limit, including whitespace.

Applications can validate individual wire values before constructing an offer:

| Validator | Accepted value |
| --- | --- |
| `require_public_key` | Canonical unpadded base64url of 32 Ed25519 public bytes |
| `require_asset` | Case-sensitive CAIP-19 asset type or asset ID |
| `require_amount` | Positive canonical decimal string, at most 16384 digits |
| `require_best_before` | Python integer in 0 through 2^53−1 |

Each returns its input without normalization and accepts an optional trusted diagnostic `name`. Wrong Python API argument types raise `TypeError`; malformed protocol inputs raise `InvoiceError`, a `ValueError`. The decoder maps wrong JSON field types to `InvoiceError`. Backend and key-operation failures propagate. Diagnostics do not echo document contents and are not stable machine error codes.

0.2.0 removes `validate_payment_route`, `NATIVE_ASSET`, the EVM address metadata, merchant and identifier helpers, `require_uint256` and `require_deadline`. Consumers must remove their old field access and verification arguments. P2P owns settlement-route authorization, payee and asset qualification through trusted registration and voucher context. Asset equality alone cannot qualify a route. Consumer repositories require their own adoption and runtime qualification.

## Interoperability and development

The installed resource `importlib.resources.files("signed_invoice").joinpath("vectors/invoice.json")` carries authoritative synthetic exact-byte invoices, base64, hashes and Ed25519 signatures plus external payment-voucher contexts. The public test signing identity comes from RFC 8032; it must never be used for real offers. Voucher evidence is separate from invoice signatures and proves no enrollment, collection, settlement or deployment.

Use `make vectors/show` to print hash, base64 and signature expectations offline for manual review; it never rewrites the fixture and does not compute EIP-712 digests. [Development and release operations](https://github.com/numpde/signed-invoice#development) use the maintained container lanes through `make help`. [Design and consumer obligations](https://github.com/numpde/signed-invoice/blob/main/notes/005_invoice_design.txt) and the extraction record preserve source provenance.
