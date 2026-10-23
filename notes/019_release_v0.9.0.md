# wire 0.9.0

`CanonicalJSON` is a new immutable value for canonical UTF-8 JSON. It separates producing canonical bytes from admitting bytes that must already be canonical. This release adds that shared API; existing invoice, voucher and acceptance profiles and consumers are unchanged. It does not migrate invoice `JsonNumber` or require canonical HTTP request bodies automatically.

## Encode unsigned values or admit received bytes

```python
from wire import CanonicalJSON, CanonicalJSONError

encoded = CanonicalJSON.encode({"z": 2, "a": 1})
assert encoded.bytes == b'{"a":1,"z":2}'
admitted = CanonicalJSON.from_bytes(encoded.bytes)
assert bytes(admitted) == encoded.bytes
assert admitted.value == {"a": 1, "z": 2}
```

`encode` accepts plain JSON values and produces JCS bytes. `from_bytes` requires exact UTF-8 `bytes`, rejects duplicates and invalid Unicode, and compares the original bytes with their JCS encoding. Whitespace, different object-member order and alternative escapes or number spellings are rejected rather than repaired. Both methods return `CanonicalJSON`; `.bytes` and `bytes(value)` expose immutable bytes, and `.value` returns a fresh parsed projection. Direct construction from bytes performs the same strict admission.

The default byte limit is 16,384 and the fixed maximum container depth is 16. A caller handling a larger body can pass an explicit positive integer `max_bytes` to either method. Applications must also bound body acquisition before calling the parser. Encoding or admission failures raise `CanonicalJSONError`, a `ValueError`; a non-bytes admission argument or non-integer limit raises `TypeError`. A nonpositive limit raises `ValueError`.

Canonical encoding establishes neither a product schema nor a valid signature, trusted key or authorized action. Applications can invoke this shared raw-byte admission before Pydantic when an endpoint explicitly requires a canonical body. They must authenticate HTTP signatures over the original received body and must not rewrite already-signed data to make it acceptable. This release leaves those endpoint contracts to applications.

## Numbers and Unicode

Numbers follow JCS finite binary64 semantics. Python `int` input must be within `-(2**53 - 1)..2**53 - 1`; Python `float` explicitly supplies a binary64 value. Large exact integers and exact decimal quantities must use strings whose interpretation is owned by the product schema. `Decimal`, invoice `JsonNumber` and other non-JSON objects are rejected without coercion.

Canonical binary64 output can look like a large integer: `CanonicalJSON.encode(1e20).bytes` is `b'100000000000000000000'`. Raw admission interprets integer tokens beyond the safe range as binary64 and still requires exact canonical byte equality. `.value` returns `int` for safe integer tokens and `float` for other number tokens. An integer-looking token therefore does not establish exact-integer semantics. Timestamp and payment schemas retain their own existing rules.

Object keys use JCS UTF-16 ordering. Strings reject surrogates and I-JSON noncharacters. They are not Unicode-normalized: precomposed and decomposed text remain different values. Canonicalization does not merge product-level equivalents or different valid cryptographic signatures.

## Implementation and qualification

The serializer is the established no-dependency `rfc8785==0.1.4` implementation, added as a direct runtime dependency. Its wheel SHA256 is `520d690b448ecf0703691c76e1a34a24ddcd4fc5bc41d589cb7c58ec651bcd48`; existing dependency versions and hashes are unchanged. The exact version was checked against OSV on 2026-10-23 before installation and returned no advisory matches. The existing build-tool setuptools advisory remains documented in the preceding release record.

Strict reading reuses the duplicate-aware bounded JSON owner from revision `707722ee1ad28d934ad553ba5a0a3f35021d9d8b`. The new layer adds canonical byte comparison, the explicit binary64 projection, I-JSON noncharacter rejection, immutable ownership and encoding resource bounds. Serialization rules are defined by [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html); exact-number guidance follows [RFC 7493 section 2.2](https://www.rfc-editor.org/rfc/rfc7493.html#section-2.2).

Shared interoperability cases are installed at `wire/vectors/json.json`, SHA256 `227a0d80f3660dba749fa1f9f3470fd50957335abc295a1249ec912323498746`. They cover canonical key ordering, number rendering, negative zero, large integral binary64 output, Unicode preservation and rejected alternative encodings. Source tests also exercise duplicate names, malformed UTF-8, nonfinite numbers, depth/size boundaries, cyclic and hostile inputs, fresh projections and explicit larger HTTP-body limits.

Published from committed source `3de987104e703fd414488a25105f5a416791bfd5`. Lint and all 146 tests passed: 53 repository, nine canonical JSON, 44 invoice, 18 voucher and 22 acceptance tests. Both fresh installed environments—the wheel and a wheel rebuilt from the source distribution—passed the new API's origin, vector, binary64 and strict byte-admission checks alongside the unchanged protocol checks.

The release includes the [build log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.9.0/release-build.log), [test log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.9.0/release-test.log), [source inventory](https://github.com/numpde/pay-to-play-wire/releases/download/v0.9.0/source.json) and [artifact hashes](https://github.com/numpde/pay-to-play-wire/releases/download/v0.9.0/sha256.json). Downloaded draft assets and logs matched the qualified files before publication; an anonymous public-wheel download also matched. These checks establish package behavior, not application adoption, endpoint migration or deployment.

Use this requirements-file entry with the release's [runtime dependency lock](https://github.com/numpde/pay-to-play-wire/blob/3de987104e703fd414488a25105f5a416791bfd5/requirements/runtime.lock) and your dependency verification workflow:

```text
wire @ https://github.com/numpde/pay-to-play-wire/releases/download/v0.9.0/wire-0.9.0-py3-none-any.whl#sha256=4a306070e06fe55b04583ab908dfb8d1392893da5c8c0e067b2f01a907ca047c
```
