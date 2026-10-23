# wire 0.10.0

`CanonicalJSON.encode_json(raw)` derives canonical bytes from ordinary UTF-8 JSON for use before hashing or signing a new document. Input may contain whitespace, unsorted object members and equivalent number spellings. Canonicalization no longer requires callers to parse raw numbers into Python floats first, where precision could already be lost.

```python
from wire import CanonicalJSON

raw = b'{ "z": 1e0, "a": -0 }\n'
canonical = CanonicalJSON.encode_json(raw)
assert canonical.bytes == b'{"a":0,"z":1}'
assert canonical.value == {"a": 0, "z": 1}
```

## Choose the input operation

- `encode(value)` constructs canonical bytes from plain Python JSON values.
- `encode_json(raw)` parses ordinary JSON and constructs canonical bytes, rejecting duplicate member names and precision-changing number conversions.
- `from_bytes(raw)` admits only bytes that are already canonical, preserving them exactly. Use it when the caller's contract explicitly requires canonical input.

All three operations return the same immutable `CanonicalJSON`. `.bytes`, `bytes(value)` and the fresh `.value` projection are unchanged. Raw methods require exact UTF-8 `bytes`. The default byte limit is 16,384; callers can pass an explicit positive integer `max_bytes`. For `encode_json`, it bounds both incoming and resulting canonical bytes, since canonical number spelling may expand the output. For `encode`, it bounds the resulting bytes. The fixed container-depth limit remains 16. Limit body acquisition separately before parsing.

## Number precision and original signed bytes

`encode_json` uses the existing JCS binary64 serializer, then compares each original number's exact decimal value with its canonical decimal spelling. Forms such as `1.0`, `1e0` and `-0` may normalize to `1`, `1` and `0`. Input such as `9007199254740993` or `0.10000000000000001` is rejected because its canonical binary64 spelling would change the decimal value. Decimal comparison is exact and independent of the caller's decimal-context precision; it does not replace JCS serialization with a custom decimal format. Exact quantities outside this contract remain schema-defined strings, without automatic conversion.

Canonicalization proves encoding only, not a product schema, signature, trusted identity or authorized action. A signed HTTP request or JSON artifact may have a separate canonical projection, but the application must retain and authenticate the original bytes under that protocol. Do not substitute the projection for RFC 9421 body verification, JWS signing input, or the complete signed-invoice hash. Existing invoice, voucher and acceptance profiles and invoice `JsonNumber` semantics are unchanged.

## Installation and qualification

This is a core-only release. It adds no CLI, standalone bundle, JavaScript module, extra or alternate package namespace. Plain `wire` retains its complete dependency declaration. Dependency versions and locked wheel hashes are unchanged from 0.9.0.

The implementation extends the shared reader and serializer at revision `e1398263ed5f9b4d415d4c9c4a28490b297a3774`; it introduces no separate JSON parser or canonicalizer. Malformed input, duplicate names, invalid Unicode, depth/size violations and precision-changing conversions raise `CanonicalJSONError`, a `ValueError`. Incorrect byte argument types raise `TypeError`.

Shared cases in `wire/vectors/json.json` distinguish ordinary-input normalization from strict byte admission. They include equivalent number forms, duplicate rejection, rounding loss and underflow. Source tests additionally exercise decimal-context independence and larger explicit input/output limits. Installed checks exercise those shared cases against both the wheel and a wheel rebuilt from the source distribution.

Published from committed source `2e5c476f80991ebc1961368c1c6caae46f203360`. Lint and all 148 tests passed: 53 repository, 11 canonical JSON, 44 invoice, 18 voucher and 22 acceptance tests. Both fresh installed environments passed the ordinary-input and existing protocol checks. Downloaded draft artifacts and logs matched before publication; an anonymous public-wheel download also matched.

The release includes the [build log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.10.0/release-build.log), [test log](https://github.com/numpde/pay-to-play-wire/releases/download/v0.10.0/release-test.log), [source inventory](https://github.com/numpde/pay-to-play-wire/releases/download/v0.10.0/source.json) and [artifact hashes](https://github.com/numpde/pay-to-play-wire/releases/download/v0.10.0/sha256.json). These establish package qualification, not consumer adoption or deployment.

```text
wire @ https://github.com/numpde/pay-to-play-wire/releases/download/v0.10.0/wire-0.10.0-py3-none-any.whl#sha256=a65715d657c47d8a4c38d511f503a3f896b4a2c3497c2a54b8523ac5e131679d
```
