# 0.2.0 — draft release note

## Status

This is the release note for the planned five-field invoice format. The design and two QA/QC passes are complete; implementation, interoperability vectors and package qualification are pending. The current package remains 0.1.1 with wire version 2. No 0.2.0 package or release has been published.

## Planned invoice format

The document contains exactly five top-level fields:

- `provider`: the provider's encoded public key, which must match the signature-verification key. Applications establish its trust and authorization.
- `payment`: the explicit CAIP-19 `asset` and base-unit integer-string `amount`.
- `bestBefore`: best-effort offer validity in Unix seconds. Earlier receipt does not guarantee acceptance; later receipt does not require rejection. The codec imposes no clock-based acceptance or fulfillment cutoff.
- `beneficiary`: the intended recipient's encoded public key, independently of the payer.
- `service`: any provider-owned JSON value, including arrays, scalars and null. The shared codec does not interpret product semantics.

## Planned breaking changes

Remove the embedded version, merchant UUID, key alias, invoice ID, payer, channel, settlement contract, quoted payee and acceptance/redemption deadlines. The trusted signing context selects the grammar. Remove merchant/key-alias verification arguments and the `validate_payment_route` API. Applications own provider enrollment, settlement-route and asset qualification, admission, collection and fulfillment.

The sole invoice identity remains SHA-256 of the caller's nonempty trusted domain bytes followed by the exact original document bytes. Ordinary Ed25519 signs that complete preimage directly. The library supplies no domain default, adds no delimiter and reconstructs no JSON for verification. A client-supplied hash label cannot establish invoice identity or authenticity.

Retain strict UTF-8/JSON, duplicate-member rejection, lossless nested numbers, the 16384-byte document limit and container depth 16. Arbitrary service value kinds remain subject to those limits. Existing published tags, artifacts and document bytes remain unchanged.

## Readiness

The recorded design passed independent review, lint and 43 repository checks. These checks cover the notes and existing repository workflows; they do not qualify a five-field implementation, package or consumer integration.

Before publication, settle key encoding, accepted asset forms, numeric bounds and trusted domain bytes; implement the complete API cutover; regenerate independent vectors; and qualify a committed source snapshot, installed wheel/sdist artifacts and downloaded release assets. Consumer reservation/admission coordination is a separate prerequisite for production payment promises.

The complete design, exact JSON example and consumer responsibilities are recorded in notes/005_invoice_design.txt.
