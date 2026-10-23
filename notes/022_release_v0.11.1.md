# wire 0.11.1

Signature-failure hints now include the canonical JSON rule that failed. This helps callers relay a useful explanation instead of the same generic hint for malformed JSON, duplicate members, a byte limit or a noncanonical spelling. The explanation still describes a possible issue, not the proven cause of the signature failure.

JSON decoding errors now distinguish invalid UTF-8, invalid JSON syntax and excessive parser nesting. UTF-8 errors identify a zero-based byte offset; syntax errors identify a one-based line and column. These diagnostics apply to invoice, acceptance, voucher and canonical JSON parsing. They omit received field names and values.

## Relay and compatibility

Callers can continue forwarding a non-`None` `.canonical_json_hint` from `InvoiceError` or `AcceptanceError`, or the result of `wire.json.signature_failure_hint` at another known JSON signature boundary after an actual cryptographic failure. The helper returns `None` when the payload passes these canonical JSON checks. The error attribute also remains `None` for failures that do not trigger this diagnostic. The hint is now specific to the failed rule rather than a single fixed sentence. Treat it as human-readable text; do not parse it to classify failures.

The helper relays only wire's own payload-free canonical-rule explanation. It does not render the chained parser exception, which may retain the received document. Keep exception causes and tracebacks out of public responses. Applications own their public status, error code and disclosure policy.

Wrong argument types and invalid byte limits retain their existing API contracts. Exception families and original causes are preserved. Valid noncanonical signatures still verify, and failed signatures are never retried on rewritten bytes. Signed profiles, hashes, acceptance fields, EIP-712 behavior and dependencies are unchanged.

## Implementation and verification

Copied and edited the shared JSON reader, signature diagnostic and voucher parser from revision `207bf2aea22cb74928ef50a4014138df0bc4b4c1`. The changes select safe parser metadata and expose the existing canonical-rule explanation; they add no logging, new error taxonomy or application response format.

Tests exercise exact exception types and causes across all four public parsers, safe positions without secret contents, distinct failed-rule hints, preserved original-byte verification and unchanged successful verification. Fresh installed-wheel checks also require the specific noncanonical-encoding explanation for both JWS profiles.

Published from committed source `3312b3aa275bce5b6888cf467e776c0fc3ad437d`. Lint and all 155 tests passed: 53 repository, 18 JSON/diagnostic, 44 invoice, 18 voucher and 22 acceptance tests. Both fresh installed environments passed. Downloaded draft assets and qualification logs matched the checked bytes before public release.

The release includes the [build log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.11.1/release-build.log), [test log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.11.1/release-test.log), [source inventory](https://github.com/numpde/pay-to-play-wire/releases/download/v0.11.1/source.json) and [artifact hashes](https://github.com/numpde/pay-to-play-wire/releases/download/v0.11.1/sha256.json). These establish package qualification, not consumer adoption or deployment.

```text
wire @ https://github.com/numpde/pay-to-play-wire/releases/download/v0.11.1/wire-0.11.1-py3-none-any.whl#sha256=65cd5df565cb4169b93269022dc8b16c77f58397e42b1cd722ff699ea1a76ab9
```
