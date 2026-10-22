# 0.4.0 — shared invoice and voucher wire package

Published [wire 0.4.0](https://github.com/numpde/pay-to-play-wire/releases/tag/v0.4.0) from frozen source `7eb5b1dd87d07e5281bc07a387920625eeef3ab0` through `make publish/release TAG=v0.4.0`. All downloaded draft assets and qualification logs were verified before publication. Historical signed-invoice releases and their URLs remain unchanged.

The repository is `pay-to-play-wire`; the Python distribution and import namespace are `wire`. Import invoice APIs from `wire.invoice`, the actual Pydantic adapter from `wire.invoice.pydantic`, and voucher APIs from `wire.voucher`. Remove the displaced package pins and copied schemas coherently when adopting this release. No old import aliases are shipped.

The invoice implementation and authoritative vectors are byte-identical to signed-invoice 0.3.0. The protected Ed25519 profile, five-field payload, exact carried segments and SHA-256 identity over the complete compact JWS, including its signature, are unchanged. The signed `application/vnd.signed-invoice.v1+json` profile identifier deliberately keeps its spelling.

The voucher implementation and digest vectors are copied unchanged from qualified source `589f7bb9dca2b4de380b9800d8a63a994910c078`. They preserve the ordered PayToPlay/2 EIP-712 profile, `{typedData, signature}` transport, low-s signature form and caller-supplied expected deployment and registered signer. Voucher digest excludes its signature; it is distinct from the invoice identity rule. Applications retain registered-position authorization, invoice binding, purchase policy, storage, admission, fulfillment and settlement.

The base requires only cryptography 50.0.2. Select `pydantic` for the invoice adapter, `voucher` for the Ethereum backend, or both. The voucher backend brings Pydantic transitively; invoice imports do not load either optional integration.

```text
wire @ https://github.com/numpde/pay-to-play-wire/releases/download/v0.4.0/wire-0.4.0-py3-none-any.whl#sha256=7b58c25ed49f94e0c2194b8899c0d49e672bd768432186bdc2be2d29c67d8ffe
```

Replace `wire` with the required extras while keeping that exact URL and hash. Acquire and hash-verify the wheel explicitly, then install offline using the consumer's maintained lock and container lane.

Qualification passed lint, 50 repository workflow checks, 43 invoice tests and 13 voucher tests. Both original and sdist-rebuilt wheels passed fresh source-free installation under base, Pydantic, voucher and combined profiles. Each profile performed real selected-extra pip resolution offline with hash-locked dependencies and the exact candidate wheel hash. A pre-build path/hash inventory checks packaging completeness independently of agreement between the two distributions.

Independent real Python joserfc and JavaScript jose verified the invoice artifacts; JavaScript jose regenerated their exact segments and signatures. Donor/current wheel execution matched voucher typed data, signatures, digests and transport bytes for two historical vectors and both current invoice identities. Prepared viem 2.50.4 independently verified and exactly regenerated those signatures, with changed deployment and invoice rejection controls. These are offline compatibility checks, not consumer deployment or live settlement evidence.

Wheel SHA-256: `7b58c25ed49f94e0c2194b8899c0d49e672bd768432186bdc2be2d29c67d8ffe`. Sdist SHA-256: `f3679624c00cf8318c601c426a9adf48f35340d5aa26ad90feedea5132f6b030`. The release also includes `source.json`, `sha256.json` and build/test logs. Exact donor, dependency, image, probe and receipt evidence is recorded in notes/010_wire_consolidation.txt.
