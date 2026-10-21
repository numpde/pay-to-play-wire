# 0.2.0 — draft release note

## Status

This is the release-candidate note for the implemented five-field invoice format. Source targets 0.2.0; independent interoperability evidence and qualification status are recorded in notes/007_five_field_implementation.txt. Publication is explicitly authorized and must still verify final frozen-source artifacts before becoming public.

## Invoice format

The document contains exactly five top-level fields:

- `provider`: the provider's 43-character canonical unpadded base64url Ed25519 public key, which must match the signature-verification key. Applications establish its trust and authorization.
- `payment`: exactly the explicit CAIP-19 `asset` (generic asset type or optional token-ID suffix) and positive canonical base-unit decimal-string `amount`. Case and spelling are preserved; adapters own asset qualification and narrower numeric limits.
- `bestBefore`: best-effort offer validity in Unix seconds, encoded as a canonical JSON integer token in 0..2^53-1. Earlier receipt does not guarantee acceptance; later receipt does not require rejection. The codec imposes no clock-based acceptance or fulfillment cutoff.
- `beneficiary`: the intended recipient's encoded public key, independently of the payer.
- `service`: any provider-owned JSON value, including arrays, scalars and null. The shared codec does not interpret product semantics.

## Breaking changes

Remove the embedded version, merchant UUID, key alias, invoice ID, payer, channel, settlement contract, quoted payee and acceptance/redemption deadlines. The trusted signing context selects the grammar. Remove merchant/key-alias verification arguments and the `validate_payment_route` API. Applications own provider enrollment, settlement-route and asset qualification, admission, collection and fulfillment.

Remove obsolete merchant/identifier/EVM/uint256/deadline scalar helpers and address metadata. The scalar API is `require_public_key`, `require_asset`, `require_amount` and `require_best_before`. Verification takes only the explicit trusted domain and Ed25519 public key; signing also rejects a key that differs from the named provider. The reference consumer profile uses exactly `P2P-INVOICE-4` followed by LF; the library supplies no default.

The sole invoice identity remains SHA-256 of the caller's nonempty trusted domain bytes followed by the exact original document bytes. Ordinary Ed25519 signs that complete preimage directly. The library supplies no domain default, adds no delimiter and reconstructs no JSON for verification. A client-supplied hash label cannot establish invoice identity or authenticity.

Retain strict UTF-8/JSON, duplicate-member rejection, lossless nested numbers, the 16384-byte document limit and container depth 16. Arbitrary service value kinds remain subject to those limits. Existing published tags, artifacts and document bytes remain unchanged.

## Readiness

The adapted normative, adversarial and integration campaigns cover strict JSON, lossless service values including null and numeric scalars, all field signatures, legacy rejection and provider/key equality. Source-only tests do not establish installed-package or consumer proof; see the implementation record for completed checks and remaining evidence.

Independent Node/OpenSSL checks verified both new byte/hash/base64/signature vectors and their whitespace-mutation controls. A separate cached-viem implementation supplied the new EIP-712 voucher digests. Exact image, input, module and receipt identities plus the cached-dependency integrity limitation are retained in the implementation record; these are no claim of Solidity execution or payment settlement.

Before publication, qualify the final committed source snapshot, installed wheel/sdist artifacts, independent voucher vectors and downloaded release assets. Consumer reservation/admission coordination and explicit package adoption are separate prerequisites for production payment promises. Existing published artifacts are preserved.

The complete design, exact JSON example and consumer responsibilities are recorded in notes/005_invoice_design.txt.
