# wire 0.7.0

wire 0.7.0 adds signed purchase acceptances: a service can sign one complete voucher together with the time it accepted it, and a recipient can verify that statement using a trusted service key.

## Acceptance API and format

`wire.acceptance` provides `SignedAcceptance`, `encode_acceptance`, `decode_acceptance`, `sign_acceptance` and `verify_acceptance`. The artifact supports JSON, dictionary and compact JWS representations, preserves the original signed segments, and exposes the embedded voucher and time through `.voucher` and `.accepted_at`. The Pydantic/OpenAPI adapter is `wire.acceptance.pydantic.SignedAcceptanceValue`. See the [guide](https://numpde.github.io/pay-to-play-wire/#sign-and-verify-an-acceptance) for a complete example.

The acceptance is an Ed25519 JSON Web Signature (JWS). Its payload contains exactly:

- `voucher`: a complete PayToPlay/2 signed voucher, including its original 65-byte signature.
- `acceptedAt`: integer Unix seconds from `0` through `2**53 - 1`. The JSON number must use ordinary nonnegative integer notation; booleans, fractions, exponents and negative zero are rejected.

Signing emits the protected header `{"alg":"Ed25519","typ":"application/vnd.signed-purchase-acceptance.v1+json"}`. The signature binds the complete embedded voucher, including its signature, and `acceptedAt`; changing either invalidates the acceptance signature. Invalid payload fields, protocol violations and signature failures raise `AcceptanceError`, a subclass of `ValueError`. Functions requiring payload bytes, key objects or a `SignedAcceptance` artifact raise `TypeError` when given the wrong argument type.

## What verification establishes

Parsing checks the acceptance format and the embedded voucher's structure. `verify_acceptance` additionally checks the acceptance signature using the trusted Ed25519 public key object supplied by the caller and returns the authenticated payload dictionary. Applications own key delivery, configuration, signer authorization and key rotation. Parsing or Pydantic validation alone does not authenticate either signer.

Acceptance verification does not check the embedded voucher's Ethereum signature, its signer's historical authority or the recorded time against a clock. It authenticates the service's statement about that voucher and time. Applications own the acceptance decision, invoice binding, current eligibility, fulfillment and settlement; a verified acceptance does not establish those outcomes.

## Installation and compatibility

Plain `wire` installs invoice, voucher and acceptance support together with all Pydantic adapters. The complete default installation introduced in 0.6.0 remains; there are no extras. Users of older optional installations should expect additional runtime dependencies when upgrading. Python 3.12 or later is required; dependency versions and locked wheel hashes are unchanged from 0.6.0.

Structural voucher parsing, acceptance parsing and schema generation, and acceptance signature verification do not import the Ethereum backend. Voucher signing, voucher signature verification and voucher digest computation import it when used. This changes import behavior, not the dependencies installed by `wire`.

Existing invoice and voucher wire formats, signature rules and invoice hashes are unchanged.

Use this requirements-file entry and the [runtime dependency lock](https://github.com/numpde/pay-to-play-wire/blob/3c0930fa54386692af45af08aee3ca5473486fba/requirements/runtime.lock) with your dependency acquisition and verification workflow:

```text
wire @ https://github.com/numpde/pay-to-play-wire/releases/download/v0.7.0/wire-0.7.0-py3-none-any.whl#sha256=bf009da1d19a48c3bf7fa7d1d324af75d4201301c0dde377be08db829c90b1da
```

## Verification evidence

The release was built from committed source `3c0930fa54386692af45af08aee3ca5473486fba`. Lint and all 134 tests passed: 53 repository, 44 invoice, 18 voucher and 19 acceptance tests. Fresh installations of both the published wheel and a wheel rebuilt from the source distribution passed the installed-package checks. The test suite and installed checks together cover independent JWS verification, exact reproduction of the acceptance vector, rejection of altered voucher/time values, and acceptance verification while attempted Ethereum imports are blocked. The shared vector is installed at `wire/vectors/acceptance.json`.

The release includes the [build log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.7.0/release-build.log), [test log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.7.0/release-test.log), [source inventory](https://github.com/numpde/pay-to-play-wire/releases/download/v0.7.0/source.json) and [artifact hashes](https://github.com/numpde/pay-to-play-wire/releases/download/v0.7.0/sha256.json). Downloaded draft assets and logs matched the qualified files before publication; an anonymous download of the public wheel also matched. These checks establish package behavior, not consumer deployment or live payment results.

An OSV review of the exact locked versions on 2026-10-23 found no runtime-package matches. It identified the build-tool setuptools advisory [GHSA-h35f-9h28-mq5c](https://github.com/advisories/GHSA-h35f-9h28-mq5c), concerning Unicode normalization in source-distribution file exclusions. This build uses ASCII paths and exclusion rules and checks its source inventory independently. The review describes that date and build configuration.

## Implementation provenance

Acceptance reuses the invoice JWS and strict JSON implementations from revision `b71210e4c15f2be19d00744972389a2230e47605`, extracted into shared private modules. The extraction preserves fixed Ed25519 profiles, original signed segments, strict JSON and size limits. Invoice-specific provider binding and complete signed-artifact hashing remain in the invoice module. Embedded voucher structure is checked by the existing `SignedVoucher` parser; acceptance does not add a second voucher schema or perform voucher signature verification.
