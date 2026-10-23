# wire 0.8.0

Purchase acceptances now carry their signing public key in the signed payload. The artifact identifies its signer without a separate stored key or database lookup. The recipient still supplies an independently trusted public key; a carried key does not grant itself trust or authorization.

## Acceptance v2

The payload contains exactly `signer`, `voucher` and `acceptedAt`:

- `signer` is the full Ed25519 public key, encoded as canonical unpadded base64url of 32 raw bytes: 43 characters, as used by invoice `provider`.
- `voucher` is the complete strict PayToPlay/2 signed voucher, including its original 65-byte signature.
- `acceptedAt` is signing time in integer Unix seconds, from `0` through `2**53 - 1`. It is independent of application decision, database creation and commit times. The caller supplies it; wire reads no clock.

The protected header emitted by signing is `{"alg":"Ed25519","typ":"application/vnd.signed-purchase-acceptance.v2+json"}`. `sign_acceptance(raw, private_key)` requires the carried `signer` to equal the private key's public key before signing the exact payload bytes. It never inserts or rewrites a field. `verify_acceptance(artifact, *, public_key)` requires that signer to equal the caller's trusted key and verifies the signature over the original segments. The authenticated payload dictionary contains all three fields.

`SignedAcceptance.signer` exposes the encoded public key. Other API names and the shared Pydantic/OpenAPI adapter remain unchanged. Parsing and Pydantic validation check structure, not signer authentication. Acceptance verification does not verify the embedded voucher's Ethereum signature or historical signer authority. Applications retain key trust, authorization, purchase decisions, fulfillment, settlement and later status policy.

## Upgrading

This is an incompatible acceptance-profile change. The 0.7.0 two-field payload and v1 media type are rejected. Producers must supply `signer` before encoding and signing; consumers must adopt v2 together. Published 0.7.0 assets remain available unchanged. See the [guide](https://numpde.github.io/pay-to-play-wire/#sign-and-verify-an-acceptance) for the complete v2 example.

Invoice and voucher formats, signature rules, invoice hashes and public APIs are unchanged. Plain `wire` still installs every backend and Pydantic adapter, with no extras; Python 3.12 or later is required. Dependency versions and locked wheel hashes are unchanged. Acceptance operations and structural voucher parsing continue to avoid importing Ethereum backends.

## Qualification and provenance

The implemented acceptance campaign covers successful exact-byte signing and verification, canonical key encoding, mismatched signing keys, untrusted self-declared keys, disagreement between carried signer and actual signature key, signer/voucher/time mutation, v1 rejection, independent JWS interoperability and blocked Ethereum imports. Installed-package checks exercise the same key/trust boundaries against both the wheel and a wheel rebuilt from the source distribution. Frozen release results are recorded after qualification and publication. The shared v2 vector is installed at `wire/vectors/acceptance.json`.

The public-key representation validator was copied from `src/wire/invoice/fields.py` at revision `72c3de87c54e777032caced26a5650aae7e6abaf` into a shared private module. Invoice validation retains its public API and errors; acceptance uses its own protocol errors. Signing-key equality follows the existing invoice provider-binding rule. No parallel voucher schema, signer registry, key loader or acceptance hash was added.

The exact locked versions were reviewed against OSV on 2026-10-23 before installation. No runtime-package matches were returned. The build-tool setuptools advisory [GHSA-h35f-9h28-mq5c](https://github.com/advisories/GHSA-h35f-9h28-mq5c) remains: it concerns Unicode normalization in source-distribution file exclusions. This Linux build uses ASCII paths and rules and independently checks the source inventory. No dependencies were changed for this release.
