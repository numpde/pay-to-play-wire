# 0.3.0 — Ed25519 JWS invoices

## Status

Published [0.3.0](https://github.com/numpde/signed-invoice/releases/tag/v0.3.0) from frozen source `be92d1594540f82b73e3765833b42f15804e36d8` through `make publish/release TAG=v0.3.0`. Full frozen qualification passed, and downloaded draft assets matched their qualified identities before publication. Existing 0.2.0 and earlier assets and tags are unchanged.

## Breaking transport and identity changes

Invoices now use RFC 7515 flattened JWS JSON with exactly `protected`, `payload` and `signature`, all canonical unpadded base64url strings. The protected header contains exactly `alg: Ed25519` (RFC 9864) and the application profile `typ: application/vnd.signed-invoice.v1+json`; this profile name is not a registered media type. Generic RFC media-type case/prefix equivalence is accepted without rewriting the signed header.

Ed25519 signs ASCII(`protected + "." + payload`). Invoice identity is `0x` plus lowercase SHA-256 of the complete compact artifact, ASCII(`protected + "." + payload + "." + signature`). Identity now includes the signature. Outer JSON formatting is excluded. The previous custom domain, detached-signature and `bytes`/`signature` envelope APIs are removed, with no legacy emission or verification path. Consumers must explicitly adopt the new artifact and hash rules rather than reinterpret stored offers.

The five-field payload remains `provider`, `payment{asset,amount}`, `bestBefore`, `beneficiary` and arbitrary JSON `service`. Exact payload bytes, strict JSON, lossless service numbers, base-unit strings and best-effort time semantics are unchanged. Verification requires the trusted Ed25519 key to equal `provider`; hashing and parsing alone do not authenticate it.

## API and integration

`SignedInvoice` is the immutable framework-neutral owner of the three carried segments, with flattened/compact parsing, original payload bytes, a fresh document projection and complete-artifact hash. `sign_invoice(raw, key)` returns it; `verify_invoice(artifact, public_key=key)` returns the authenticated document. Applications retain provider authorization, service schema, persistence and payment responsibilities.

The optional `pydantic` extra supplies `signed_invoice.pydantic.SignedInvoiceValue`, an Annotated adapter over the core artifact. It derives strict required/extra-forbidden transport fields and bounds from that owner and supports Pydantic/FastAPI schema generation without a consumer mirror model. The base package still requires only cryptography 50.0.2. Raw duplicate-member rejection must happen before framework JSON parsing; the adapter cannot recover names already discarded by a parser.

## Qualification

The frozen release passed lint, all 43 repository checks, all 41 invoice tests, and source-free installation of original and sdist-rebuilt wheels. The optional adapter was installed and checked separately after proving the core works without Pydantic. Real Python joserfc 1.7.5 and independently acquired, integrity-verified JavaScript jose 6.2.13 verified and regenerated the exact same flattened and compact Ed25519 artifacts. Mutation controls distinguish complete signed identity from outer JSON formatting.

Wheel SHA-256: `598e0bf346d41a517a788b0847635805b8ae068d194fba7cad43661d87a4729b`. Sdist SHA-256: `1ddf6ef704b07602cfc41bd3901ec8e663b8acfd7f5aacc7c9fa71e208a6b80d`.

The installed vector resource SHA-256 is `a83eaebab9e17bd5320d29c17ea1d40398cae8715d9e1b90e5698adfb829dc2f`. Exact source/image/dependency/probe/receipt identities and limits are recorded in notes/008_jws_profile.txt. These checks establish no consumer deployment, registered-provider authorization, payment admission, fulfillment or settlement.
