# wire 0.11.0

Failed invoice and acceptance signature verification now includes a safe hint when the original payload does not pass this package's canonical JSON checks. The hint identifies differing serialization as a possible issue; it does not establish why the signature failed or require incoming payloads to be canonical.

Cryptographic verification still uses the original signed bytes. Only an `InvalidSignature` failure triggers the subsequent diagnostic. `InvoiceError` and `AcceptanceError` retain their exact types and original failure causes. Their new `.canonical_json_hint` attribute is either the fixed, bounded hint string or `None`; the ordinary error message includes the hint when present. Callers can propagate that attribute without rendering unrelated schema errors or payload contents.

## Behavior and limits

- A valid signature over a noncanonical payload still verifies successfully, without a canonicality check.
- A failed signature over a canonical payload receives no serialization hint.
- A failed signature whose payload does not pass the canonical checks remains a failure and receives the potential-serialization hint.
- Parse, profile and key-binding failures do not trigger this cryptographic-failure diagnostic.

There is no canonicalization retry, rewritten-payload verification or mutation of carried segments. Invoice hashes and all signed profiles are unchanged. Voucher verification is unchanged: its EIP-712 signature covers typed data, so JSON formatting is not its signed input.

## Reuse in another JSON signature owner

`wire.json.signature_failure_hint(payload, *, max_bytes=16384)` returns the same safe string or `None`. A caller verifying another JSON protocol can invoke it after an actual cryptographic failure, using the original payload bytes. The caller must know that the signature boundary carries JSON; the helper does not identify content types or classify exceptions. A general JOSE/schema error, a non-JSON HTTP body or an HTTP Content-Digest mismatch is not automatically a cryptographic JSON-signature failure.

Pass the caller's already-enforced body limit as `max_bytes` for larger payloads. The helper checks this package's bounded canonical-JSON rules, including its depth and Unicode constraints; a hint reports that those checks failed, not an independent proof about every possible canonicalization standard. The message contains no received fields, keys, signatures or raw exception text. The caller retains responsibility for original-byte authentication, schema validation and trust.

`None` means these payload checks passed, not that serialization of another signed input could not be involved. Wrong argument types and invalid byte limits retain the core API's `TypeError` and `ValueError` contracts.

## Implementation and qualification

Both JWS profiles use the existing shared verifier from revision `3b57b0cfa1f4e06ccce47273a805a877a811541d`. Canonicality inspection reuses `CanonicalJSON.from_bytes`; the public helper and structured error attribute avoid separate application canonicalizers or message parsing. Dependency versions, locked hashes and installation requirements are unchanged.

Tests cover both profiles with valid noncanonical signatures, canonical failed signatures, noncanonical failed signatures, and key-binding failures. A rejection case carries a signature that would succeed if the payload were rewritten, proving the verifier does not repair and retry it. Tests also check exact error types and causes, safe hint contents, successful larger-body inspection and unchanged artifacts. Installed-distribution checks cover both profiles, including the acceptance process with Ethereum imports blocked.

Published from committed source `ff661d790ad6e926f6eaac5d7ee7d85af44244d2`. Lint and all 153 tests passed: 53 repository, 16 JSON/diagnostic, 44 invoice, 18 voucher and 22 acceptance tests. Both fresh installed environments passed the diagnostic and existing protocol checks. Downloaded draft assets and logs matched before publication; an anonymous public-wheel download also matched.

The release includes the [build log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.11.0/release-build.log), [test log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.11.0/release-test.log), [source inventory](https://github.com/numpde/pay-to-play-wire/releases/download/v0.11.0/source.json) and [artifact hashes](https://github.com/numpde/pay-to-play-wire/releases/download/v0.11.0/sha256.json). These establish package qualification, not consumer adoption or deployment.

```text
wire @ https://github.com/numpde/pay-to-play-wire/releases/download/v0.11.0/wire-0.11.0-py3-none-any.whl#sha256=a8f4afdec06ae32436cdd058f5ca19b49d12b7bae743670ec9aa0e58a4543209
```
