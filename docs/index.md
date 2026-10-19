---
layout: default
---

# signed-invoice

`signed-invoice` is a small shared Python >=3.12 library for merchant invoices.
It implements strict encoding and decoding, exact-byte SHA-256 hashes,
Ed25519 signatures, signed envelopes and pure payment-route comparison.

## Install

Use the tested wheel from the tagged GitHub release as an application dependency:

```text
signed-invoice @ https://github.com/numpde/signed-invoice/releases/download/v0.1.1/signed_invoice-0.1.1-py3-none-any.whl#sha256=08d1635413d0ceeb6d3985b10b037cac5589c6e54e6c2dc1dd50d931e910a38a
```

The [release](https://github.com/numpde/signed-invoice/releases/tag/v0.1.1)
includes the source distribution, hashes and validation logs. Acquire dependencies
explicitly, verify their hashes and install offline using the consuming
application's maintained workflow. The runtime dependency is `cryptography==50.0.2`.

## Signing and verification

```python
from signed_invoice import (
    decode_invoice, encode_invoice, invoice_hash, sign_invoice, verify_invoice,
)

raw = encode_invoice(fields)
# Persist these original bytes and the selected key binding before signing.
envelope = sign_invoice(raw, merchant_private_key, domain=trusted_signing_domain)
verified = verify_invoice(
    envelope,
    domain=trusted_signing_domain,
    merchant_id=trusted_merchant_id,
    merchant_key_id=trusted_key_id,
    public_key=trusted_public_key,
)
assert verified == raw
digest_hex = invoice_hash(verified, domain=trusted_signing_domain)
decoded = decode_invoice(verified)
```

The application supplies its trusted signing domain as required nonempty bytes.
The library adds no delimiter and derives no domain from invoice contents.
Hashing computes SHA-256(domain + original JSON bytes).
Ordinary Ed25519 signs that preimage directly, without hashing it first.
Verification never reconstructs JSON. Retain original bytes for retries,
storage, hashing and retransmission; re-encoding fields may change the hash.

## Wire format

The document has exactly 15 required members, including the JSON integer
`version: 2` and the explicit `asset`. Amounts are positive uint256 decimal
strings in integer base units. Assets use
canonical lowercase EVM asset addresses, with `NATIVE_ASSET` identifying native
assets using ERC-7528. Zero is rejected. Chain, contract and asset are distinct
parts of the denomination; a contract deployment has one immutable asset.

| Required members | Wire value |
| --- | --- |
| `version` | JSON integer `2` |
| `merchantId` | Lowercase hyphenated UUID string |
| `merchantKeyId`, `invoiceId` | 1–128 ASCII letters, digits, underscores or hyphens |
| `chainId`, `channelId` | Canonical uint256 decimal strings |
| `paymentContract`, `customer`, `quotedPayee` | Lowercase 20-byte EVM address strings |
| `asset` | Nonzero lowercase EVM address string, including `NATIVE_ASSET` |
| `amount` | Positive uint256 decimal string |
| `acceptBy`, `redeemBy` | JSON integers in 0 through 2^53−1, with `acceptBy < redeemBy` |
| `beneficiary`, `serviceTerms` | JSON objects with merchant-owned schemas |

The codec rejects duplicate decoded member names at every depth, malformed
UTF-8/JSON, BOMs, nonfinite numbers, unpaired surrogates, documents over 16384
bytes and container depth over 16. Integer fields have exact lexical/range
rules; booleans, fractions and exponents cannot replace them. Beneficiary and
serviceTerms must be objects; their meaning belongs to the merchant.

`encode_invoice` accepts JSON dictionaries/lists/strings/bools/null, Python
integers, and `JsonNumber(token)`. Python floats are rejected. `decode_invoice`
returns fresh dictionaries, with version and deadlines as integers and nested
merchant numbers as lossless `JsonNumber` values. It does not mutate input bytes.

## Envelopes and hashes

Keys are `cryptography` Ed25519 key objects. `sign_invoice_detached` returns a
64-byte signature; `encode_envelope` encodes original bytes plus that signature.
`decode_envelope` returns `(raw, signature)` without authenticating them.
`invoice_signing_message` exposes the validated preimage. Hashing, signing and
verification require the same explicit `domain`. All operations validate the
complete document. Envelopes are original JSON bytes containing exactly
`bytes` and `signature`, both canonical padded standard base64. The containing
transport owns its total request-body limit.

`invoice_hash` returns `0x` plus 64 lowercase hex digits. Applications needing
raw hash bytes can decode the returned hex with `bytes.fromhex(digest_hex[2:])`. Parsing/hashing
does not authenticate the invoice. `verify_invoice` requires an explicitly
trusted merchant/key/public-key binding; a beneficiary key cannot supply trust.

## Payment routes

`validate_payment_route(raw, *, chain_id, payment_contract, asset)` requires
an explicit asset and compares the three signed values against supplied canonical strings.
It performs no RPC or deployment qualification. Call after signature verification
with coherent qualified observations. Equality does not establish payment
admission, balances, funding, collection, acceptance or fulfillment.

## Scalar validation

Applications can validate shared scalar facts before constructing an invoice:

| Validator | Accepted value |
| --- | --- |
| `require_merchant_id` | Lowercase hyphenated UUID string |
| `require_identifier` | 1–128 ASCII letters, digits, underscores or hyphens |
| `require_evm_address` | Lowercase 20-byte EVM address string |
| `require_asset` | Nonzero EVM asset identifier, including `NATIVE_ASSET` |
| `require_uint256` | Canonical unsigned decimal string; `positive=True` excludes zero |
| `require_deadline` | Python integer in 0 through 2^53−1 |

Each returns the original value without coercion and accepts an optional `name`
for a trusted diagnostic field label. These functions check wire facts; they do
not choose a price, establish enrollment, check current time or authorize an
offer. The document decoder additionally checks exact JSON integer-token syntax
and deadline ordering. Merchant-owned schemas retain their own version fields.

`EVM_ADDRESS_PATTERN` and `EVM_ADDRESS_LENGTH` support schema metadata. Use the
pattern with a maximum length of `EVM_ADDRESS_LENGTH`: a JSON Schema regex end
anchor can otherwise match before a trailing newline. Runtime validation uses
strict full matching. The library has no web-framework dependency.

## Errors and interoperability

Malformed protocol inputs raise `InvoiceError`, a `ValueError`, without echoing
invoice contents. Wrong Python argument types raise `TypeError`. Backend errors
propagate. Error wording is diagnostic prose, not a stable machine error code.

Shared synthetic vectors are installed as package data. Consumers can read
`importlib.resources.files("signed_invoice").joinpath("vectors/invoice.json")`.
These preserve the original byte/hash expectations; their voucher metadata is
interoperability context, not payment or deployment proof.

[Development and operations](https://github.com/numpde/signed-invoice#development)
are containerized and entered through `make help`.
[Source provenance and validation records](https://github.com/numpde/signed-invoice/blob/main/notes/001_extraction.txt)
document the selected donor practices and release checks.
