---
layout: default
title: pay-to-play-wire
---

# pay-to-play-wire

Produce and verify provider invoices carried as Ed25519 JSON Web Signatures and buyer authorizations carried as PayToPlay/2 EIP-712 vouchers. The Python package is `wire`. It owns the two wire profiles, parsing, signing, verification and interoperability vectors. Applications own provider and registered-signer authorization, service schemas, payment admission, storage, collection and fulfillment.

Version 0.4.0 consolidates the qualified [signed-invoice 0.3.0](https://github.com/numpde/signed-invoice/releases/tag/v0.3.0) implementation and the local voucher implementation under one namespace. The local candidate passed the maintained protocol, workflow and installed-package checks; public release qualification and its acquisition receipt are pending. Historical releases stay at their original locations. Changing imports preserves both wire profiles; it does not reinterpret stored offers or migrate consumer policy.

The package's dependency selections are:

```text
wire                    # Invoice support; cryptography is the only direct dependency.
wire[pydantic]          # Invoice Pydantic/OpenAPI adapter.
wire[voucher]           # EIP-712 voucher backend, including transitive Pydantic.
wire[pydantic,voucher]  # Both integrations from the same release.
```

These names describe extras, not installation commands or immutable pins. Consumers must acquire the released wheel explicitly, verify its actual SHA-256, and pin the same URL and hash for every selected extra before offline installation. A public acquisition URL and digest will be recorded only after release qualification. Import `wire.invoice` or `wire.voucher` directly; the root package loads neither optional integration.

## Sign, preserve and verify an invoice

```python
from wire.invoice import SignedInvoice, encode_invoice, sign_invoice, verify_invoice

# fields contains the five-field offer below. private_key is the provider's
# Ed25519PrivateKey; trusted_key comes from application enrollment/authorization.
payload_bytes = encode_invoice(fields)
invoice = sign_invoice(payload_bytes, private_key)
wire_bytes = invoice.to_json()

received = SignedInvoice.from_json(wire_bytes)
document = verify_invoice(received, public_key=trusted_key)
invoice_hash = received.invoice_hash
```

`SignedInvoice` is a frozen framework-neutral value with exactly three strings: `protected`, `payload` and `signature`. Its constructor validates the wire profile and payload, without authenticating the signature. Parsing, `document`, `payload_bytes` and `invoice_hash` do not establish trust. `verify_invoice` separately checks the signature and requires the payload's `provider` key to equal the caller-supplied trusted Ed25519 verification key. Signing similarly requires the private key to match `provider`.

Each recipient must authorize that provider through its own trusted configuration or registry. A key supplied by the invoice cannot authorize itself. A matching hash alone authenticates neither the signature nor the provider, and successful verification accepts no payment or service request.

## JWS profile and identity

The transport is [RFC 7515 flattened JWS JSON](https://www.rfc-editor.org/rfc/rfc7515#section-7.2.2), with exactly these members and canonical **unpadded base64url** string values:

```json
{"protected":"...","payload":"...","signature":"..."}
```

The decoded protected header contains exactly `alg` and `typ`. Canonical emission uses `{"alg":"Ed25519","typ":"application/vnd.signed-invoice.v1+json"}`. `Ed25519` is the fully specified algorithm registered by [RFC 9864](https://www.rfc-editor.org/rfc/rfc9864#section-2.2). The `typ` is this application's profile identifier, not a registered media type. Verification follows RFC 7515 media-type comparison: case is ignored and an omitted `application/` prefix is understood. Those equivalent spellings retain their original signed bytes and have distinct artifact identities.

The signing input is ASCII(`protected + "." + payload`), using the encoded strings actually carried. Ordinary Ed25519 signs those bytes directly. Verification never reconstructs the protected header or payload. No custom domain prefix, unprotected header, key selector, detached payload, alternate algorithm, `crit`, `b64` option or general multi-signature serialization is accepted.

After signing, `invoice.compact` is `protected + "." + payload + "." + signature`. `invoice.invoice_hash` is `0x` plus lowercase SHA-256 of the ASCII bytes of that **complete compact artifact**, including its signature. `invoice_hash(invoice)` computes the same value. This identity rule is part of the invoice profile; JWS does not prescribe it. The buyer can compute it after the provider signs and then bind a payment authorization to it.

Preserve and forward the original three strings. Any segment change, including signature bytes, changes identity. Outer JSON whitespace, escaping and member ordering do not change the carried strings or identity. Do not hash the outer JSON or reconstruct segments from decoded values. Distinct artifacts can still offer the same service; exclusive-offer and duplicate-fulfillment policy remain application responsibilities.

## The five-field payload

Exactly these top-level members are present:

```json
{
  "provider": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
  "payment": {"asset": "eip155:1/slip44:60", "amount": "1000000000000000"},
  "bestBefore": 2000003600,
  "beneficiary": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8",
  "service": {"address": "fixture@mail.example.invalid"}
}
```

This uses synthetic public test identities, not an enrolled provider or commercial offer. Both key fields are 43-character canonical unpadded base64url encodings of 32 raw Ed25519 public bytes. Provider and beneficiary are independent identities; possession and authority remain application checks.

`payment` contains exactly `asset` and `amount`. The asset accepts generic [CAIP-19](https://standards.chainagnostic.org/CAIPs/caip-19) asset-type or asset-ID syntax, with optional token ID and [CAIP-2](https://standards.chainagnostic.org/CAIPs/caip-2) chain syntax. Case and spelling are preserved; parsing proves no namespace support, denomination, route qualification or token behavior.

`amount` matches `[1-9][0-9]*` in asset base units. It remains a string, without EVM limits or integer conversion. The scalar limit is 16384 digits; the complete payload must still fit the byte limit below. Adapters own narrower payment bounds.

`bestBefore` is a canonical JSON integer token in `0..9007199254740991` Unix seconds. Strings, booleans, negative zero, exponents and fractions are rejected. The codec consults no clock. Providers decide whether they can accept and fulfill the offer; this value authorizes no reservation release or hard redemption cutoff.

`service` may be any JSON value, including arrays, scalars and null. Providers own its meaning. `decode_invoice(bytes)` returns a fresh dictionary with `bestBefore` as an integer and every service number as `JsonNumber(token)`, preserving precision and original number spelling. Use `JsonNumber` to encode fractions, exponents or very large integers; Python floats are rejected. `encode_invoice(dict)` serializes once in insertion order and validates the payload. Keep the returned bytes unchanged through signing.

## Boundaries and resource limits

| Boundary | Contract |
| --- | --- |
| `SignedInvoice.from_json(bytes)` | Duplicate-aware strict UTF-8 flattened JSON, at most 32768 bytes |
| `SignedInvoice.from_compact(str)` | Exact three-segment compact form, at most 22276 characters |
| Protected header | Strict JSON, at most 256 decoded bytes, exactly the approved `alg` and `typ` |
| Payload | Strict JSON, at most 16384 decoded UTF-8 bytes, container depth at most 16 with root counted as 1 |
| Signature | Canonical unpadded base64url encoding of exactly 64 bytes, 86 characters |

Duplicate decoded member names, BOMs, malformed UTF-8/JSON, nonfinite numbers and unpaired Unicode surrogates are rejected. Payload limits and lossless numeric handling apply equally to scalar and nested services. The HTTP boundary must also enforce its request-body limit before parsing.

`invoice.payload_bytes` returns the original decoded payload. `invoice.document` returns a fresh validated projection without authentication. `invoice.signing_input` exposes the exact signing input. `invoice.to_dict()` returns the three carried strings; `invoice.to_json()` emits flattened JSON. Verification returns the authenticated document dictionary while the original artifact remains available for retention and forwarding.

Wrong Python argument types raise `TypeError`; malformed protocol inputs raise `InvoiceError`, a `ValueError`. Key/backend failures propagate. Diagnostics do not echo the document. The scalar helpers `require_public_key`, `require_asset`, `require_amount` and `require_best_before` retain their five-field validation contracts and return inputs without normalization.

## Optional Pydantic and OpenAPI integration

The core requires only `cryptography==50.0.2`. The optional `pydantic` extra selects the qualified Pydantic version. Applications can use the shared annotation directly:

```python
from pydantic import BaseModel, ConfigDict
from wire.invoice.pydantic import SignedInvoiceValue

class Response(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    invoice: SignedInvoiceValue
```

The field validates three-string mappings or core `SignedInvoice` values, returns a core artifact and serializes it as the flattened object. Its required fields and bounds are projected from the core artifact; protocol semantics delegate to the same constructor. Pydantic/FastAPI can generate the extra-forbidden object schema from this annotation. Applications need no local JWS mirror model. Validation is structural and does not verify a provider signature or authorization.

**Raw duplicate-member protection belongs before framework JSON parsing.** Pydantic/FastAPI mapping inputs have already lost duplicate-name information; even Pydantic's JSON validation cannot restore it. The raw HTTP JSON owner must reject duplicate names before passing the parsed request to the adapter. `SignedInvoice.from_json(original_bytes)` enforces that rule for a standalone flattened artifact. Encoded protected-header and payload JSON remain duplicate-aware in the shared codec because their original bytes are available.

## Sign and verify a voucher

Select the `voucher` extra. The contract profile fixes domain name `PayToPlay`, version `2`, and ordered `Voucher` fields `customer/address`, `channelId/uint256`, `cumulativeTotal/uint256`, `invoiceHash/bytes32`. The caller supplies a trusted chain ID, contract address and registered voucher signer. The signer may differ from the customer position owner.

```python
from wire.voucher import (
    SignedVoucher, VoucherDomain, build_voucher_typed_data,
    sign_voucher, verify_voucher,
)

# Addresses are bytes20, invoice identity is bytes32, and amounts are base units.
# The buyer owns buyer_private_key; services receive only the resulting artifact.
domain = VoucherDomain(chain_id, verifying_contract)
typed_data = build_voucher_typed_data(
    domain=domain, customer=customer, channel_id=channel_id,
    cumulative_total=cumulative_total,
    invoice_hash=bytes.fromhex(invoice.invoice_hash[2:]),
)
voucher = sign_voucher(typed_data, buyer_private_key)
received_voucher = SignedVoucher.from_json(voucher.to_json())
verify_voucher(received_voucher, expected_domain=domain,
               expected_signer=registered_voucher_signer)
```

`SignedVoucher` is immutable and exposes fresh `typed_data`, `domain` and `message` projections, a hex `signature`, a bytes32 `digest`, and `to_dict()` / `to_json()`. Transport contains exactly `typedData` and `signature`. Wire uint256 values are canonical decimal strings; addresses, hashes and signatures use lowercase `0x` hex. Signature form is 65 bytes, low-s, with recovery byte 27 or 28. Parsing bounded UTF-8 JSON rejects duplicate fields and accepts at most 8192 bytes. Protocol failures raise `ValueError`; the typed Python construction APIs reject wrong argument types with `TypeError`.

The EIP-712 digest excludes the signature. It is a different identity rule from the invoice's complete-JWS hash. Constructors validate structure and profile; only `verify_voucher` authenticates under the supplied expected domain and signer. Applications must separately check the voucher's invoice binding, channel, cumulative authorization and registered-position authority. The package queries no chain and establishes no collateral, collectibility, purchase acceptance or settlement.

## Compatibility and qualification

Imports move from `signed_invoice` to `wire.invoice` and from `signed_voucher` to `wire.voucher`. Remove the displaced package pins and copied schemas together when adopting one qualified `wire` release. No compatibility namespaces are shipped. The invoice profile still accepts only the JWS format introduced in 0.3.0, with no custom-domain or detached-signature verification path. Its `typ` profile identifier intentionally retains its signed spelling. Historical pre-JWS identities are not reinterpreted.

Read shared vectors using `importlib.resources.files("wire").joinpath("vectors/invoice.json")` and `vectors/voucher.json`. Invoice vectors preserve exact payloads, flattened artifacts, compact strings and full hashes from signed-invoice 0.3.0. Voucher vectors preserve the independent contract-owner digest expectations; their historical invoice hashes are opaque fixtures. Public fixture keys must never identify real offers or authorizations.

The campaigns cover independent Python `joserfc` invoice interoperability, voucher contract-digest expectations, and the composed invoice-to-voucher handoff. The integrity-verified JavaScript `jose` probe also verified and exactly regenerated the relocated invoice vectors. Direct donor/current wheel comparison preserved voucher signatures and transport bytes; the independent prepared viem backend verified and exactly regenerated those signatures for historical vectors and both current invoice identities. These offline checks do not prove consumer deployment or live chain settlement. The maintained Make/container lanes and qualification limits are described in [the repository README](https://github.com/numpde/pay-to-play-wire#development). `make vectors/show` prints candidate invoice expectations without rewriting source. [The consolidation record](https://github.com/numpde/pay-to-play-wire/blob/main/notes/010_wire_consolidation.txt) identifies donor revisions, deliberate adaptations and current verification status.
