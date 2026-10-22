# wire 0.6.0

Installing `wire` now provides invoice JWS, PayToPlay/2 vouchers and both Pydantic/OpenAPI adapters. The `pydantic` and `voucher` extras are removed. Consumers can use the ordinary `wire` requirement with one qualified release URL and hash.

The package declares all signing and adapter dependencies directly. Versions and admitted wheel hashes are unchanged; the runtime dependency closures are consolidated into one lock. Invoice imports still avoid eagerly importing the Ethereum backend or Pydantic. Wire profiles, signatures, hashes, schemas and verification rules are unchanged.

Installed qualification exercises the complete ordinary installation in separate fresh environments for the wheel and sdist-derived wheel. It checks metadata with no extras, dependency closure, vectors, signing, verification, schema generation and both Pydantic adapters. Frozen release qualification also runs lint and all repository, invoice and voucher tests in the maintained containers. Downloaded draft assets and qualification logs must match before publication.
