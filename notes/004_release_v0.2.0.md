# 0.2.0 — unreleased design draft

## Status

The five-field design was agreed in the Mail workshop and confirmed by the user's JSON example on 2026-10-22. This supersedes the eleven- and twelve-field candidates. Implementation and release remain paused. The obsolete candidate code, API guide and vector changes were removed; the maintained implementation remains at 0.1.1 with the existing wire version 2 grammar. No five-field package has been built, validated or published. The existing published releases are unchanged.

## Planned changes

- Use exactly five top-level members: `provider`, `payment`, `bestBefore`, `beneficiary` and `service`.
- Identify the provider and beneficiary by encoded public keys. The key representation remains to be fixed before implementation; provider trust and registration remain application responsibilities.
- Put the explicit CAIP-19 asset identifier and base-unit integer-string amount inside `payment`. Asset syntax does not establish payment support or authorize a settlement route.
- Treat `bestBefore` as best-effort offer validity expressed in Unix seconds. A provider may decline an earlier offer or consider a later one; this field is not a mandatory acceptance or fulfillment cutoff.
- Preserve `service` as an opaque, provider-owned JSON value, including scalar or null values. The shared invoice grammar does not prescribe a product object schema.
- Remove document version, merchant UUID, key alias, invoice ID, customer, channel, settlement contract, quoted payee and redemption deadline. The trusted signing context selects the grammar. P2P owns provider registration, authorized route and asset qualification, and payment-voucher admission.
- Derive the sole invoice identity from the trusted domain and exact verified document bytes; never trust a client-supplied hash label. The detached signature covers the same complete preimage.

## Work remaining

The field-by-field rationale, the user's exact JSON example, encoding decisions and consumer lifecycle obligations are recorded in notes/005_invoice_design.txt. Fix those wire details before producing new bytes and independent interoperability vectors. Qualify a coherent committed source snapshot and downloaded release artifacts before publication; retain existing published tags and assets.
