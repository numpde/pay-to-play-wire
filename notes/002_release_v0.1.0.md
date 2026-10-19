# 0.1.0

Strict invoice version 2 encoding/decoding, exact-byte SHA-256 and Ed25519, detached signatures, envelopes, shared scalar validation and payment-route comparison. Signing domains are required caller-supplied bytes.

Source: `218a6be93f8c00ad9838c423b60353981decf1fc`.

## Installation input

```text
signed-invoice @ https://github.com/numpde/signed-invoice/releases/download/v0.1.0/signed_invoice-0.1.0-py3-none-any.whl#sha256=82247ada0220f3401a7991cdd4bbb65defe3a57467ca1210f65a23855395dafb
```

Download the declared artifact during dependency acquisition, verify its hash and install offline. Runtime dependency: `cryptography==50.0.2`.

The accompanying `sha256.json` records the exact wheel and sdist hashes.

## Qualification

Built from the clean source revision above on Linux amd64, Python 3.12.12, using the repository's offline containers. `make test` passed: Ruff, 29 repository checks, 46 invoice tests, and fresh source-free installations of the original wheel and the wheel rebuilt from the sdist. Build and test logs accompany the release. Other interpreter/platform combinations were not executed.

Consumer integrations require their own runtime checks. [Documentation](https://numpde.github.io/signed-invoice/) is published through GitHub Pages from `docs/` on the main branch.
