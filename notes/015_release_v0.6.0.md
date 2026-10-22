# wire 0.6.0

Installing `wire` now provides invoice JWS, PayToPlay/2 vouchers and both Pydantic/OpenAPI adapters. The `pydantic` and `voucher` extras are removed. Consumers can use the ordinary `wire` requirement with one qualified release URL and hash.

The package declares all signing and adapter dependencies directly. Versions and admitted wheel hashes are unchanged; the runtime dependency closures are consolidated into one lock. Invoice imports still avoid eagerly importing the Ethereum backend or Pydantic. Wire profiles, signatures, hashes, schemas and verification rules are unchanged.

Installed qualification exercises the complete ordinary installation in separate fresh environments for the wheel and sdist-derived wheel. It checks metadata with no extras, dependency closure, vectors, signing, verification, schema generation and both Pydantic adapters. Frozen release qualification also runs lint and all repository, invoice and voucher tests in the maintained containers. Downloaded draft assets and qualification logs must match before publication.

Source: `be80276d38f80a2bade5df359c77797107672207`. Lint, all 114 tests and both fresh full installations passed. Downloaded draft assets and qualification logs matched before public release.

```text
wire @ https://github.com/numpde/pay-to-play-wire/releases/download/v0.6.0/wire-0.6.0-py3-none-any.whl#sha256=5f90763f703f4c408c2223458cf3d37980c0de844b0683ac87ced1202a4aedcd
```
