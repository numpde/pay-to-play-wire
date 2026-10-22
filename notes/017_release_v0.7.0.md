# wire 0.7.0

Purchase acceptance is a fixed Ed25519 flattened JWS containing exactly `voucher` and `acceptedAt`. The voucher is the complete strict PayToPlay/2 object, including its original 65-byte signature. `acceptedAt` is a canonical nonnegative JSON integer in `0..2**53 - 1`, using the agreed existing timestamp convention. The protected header emits `{"alg":"Ed25519","typ":"application/vnd.signed-purchase-acceptance.v1+json"}`; it has no key selector.

The public API is `wire.acceptance.SignedAcceptance`, `encode_acceptance`, `decode_acceptance`, `sign_acceptance` and `verify_acceptance`. `SignedAcceptance` preserves the carried segments and provides `from_json`, `from_dict`, `from_compact`, `to_json`, `to_dict`, `json_schema`, `compact`, `signing_input`, `payload_bytes`, `document`, `voucher` and `accepted_at`. Verification requires an explicit trusted Ed25519 public key and returns the authenticated two-field document. `wire.acceptance.pydantic.SignedAcceptanceValue` uses the same adapter as the existing artifacts. Protocol and signature failures raise `AcceptanceError`, a `ValueError`; typed API arguments retain their `TypeError` contracts.

Acceptance authenticates the receipt key's signed statement. It does not independently verify historical voucher-signer authority, grant fulfillment, consult current status or establish settlement. No receipt hash, signer field, UUID or duplicated invoice-hash field is introduced. Invoice, voucher and on-chain profiles remain unchanged.

The existing invoice JWS and strict JSON owners were copied and extracted from source `b71210e4c15f2be19d00744972389a2230e47605`. Their shared private implementation fixes Ed25519, strict protected profiles, canonical base64url, duplicate-aware JSON, original segments and bounded inputs. Invoice provider binding and complete signed-artifact hashing remain invoice-owned. Acceptance delegates full voucher validation to `SignedVoucher`; JSON numeric tokens remain distinct from strings, preventing invalid numeric voucher fields from being coerced into allowed strings.

Structural voucher parsing and acceptance parsing, schema presentation and signature verification do not import Ethereum backends. Voucher signing, verification and digest computation load their backend when used. The explicit complete-default installation decision from 0.6.0 remains: ordinary `wire` installs all dependencies, with no extras. Consumers expanding from older lightweight selections must account for that full dependency closure. Versions and admitted wheel hashes are unchanged.

Qualification includes the unchanged invoice/voucher campaigns, acceptance success and rejection cases, original-signature and timestamp mutation controls, same-key cross-profile rejection, independent `joserfc` verification and exact regeneration, the shared Pydantic adapter, runnable guide examples, and source-free checks of both wheel and sdist-derived wheel. Fresh processes actively reject attempted Ethereum imports during structural parsing and acceptance verification. Downloaded draft assets and qualification logs are compared before public release; final immutable identities are recorded after publication.

The exact locked versions were checked against OSV on 2026-10-23 before installed qualification. The result retained the previously reviewed tool-only setuptools Unicode-normalization advisory, [GHSA-h35f-9h28-mq5c](https://github.com/advisories/GHSA-h35f-9h28-mq5c), with no runtime-package matches in that query. Its non-ASCII manifest-normalization condition is absent from this Linux build with ASCII paths/rules and independent pre-build inventory checks. This is a dated advisory review, not a universal vulnerability-free claim.

Published from source `3c0930fa54386692af45af08aee3ca5473486fba`. Frozen qualification passed lint, 53 repository tests, 44 invoice tests, 18 voucher tests, 19 acceptance tests and both fresh installed-distribution environments. Downloaded draft artifacts and both qualification logs matched before publication. An anonymous public wheel download matched the qualified bytes. These are library and synthetic-consumer proofs; they establish no application adoption, deployment, fulfillment or settlement.

```text
wire @ https://github.com/numpde/pay-to-play-wire/releases/download/v0.7.0/wire-0.7.0-py3-none-any.whl#sha256=bf009da1d19a48c3bf7fa7d1d324af75d4201301c0dde377be08db829c90b1da
sdist SHA256: 3810653ebb18e453704ddadb55e18e5a653923633749d42a87312079fa32b715
source.json SHA256: 5b91615ff936dd82c87ae5d070116d1a5532030a324cc6a009f47fd758f94366
sha256.json SHA256: 896d1e0ec08c3b20d5552023c934af2e59106561dbe61c0d3af6225194c2264f
acceptance.json SHA256: d109cdf8f21c608d7485adc7043976a52f60b37692407d7ace2a4b3e8fac4f25
```

The published [build log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.7.0/release-build.log) and [test log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.7.0/release-test.log) record release qualification. Downloaded draft assets and the anonymous public wheel were checked against the artifacts built from the source revision above. No older release assets were replaced.
