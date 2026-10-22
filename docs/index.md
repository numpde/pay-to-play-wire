---
layout: default
title: signed-invoice
---

# signed-invoice

Produce and verify five-field invoices carried as Ed25519 JSON Web Signatures. The package owns payload grammar, exact JWS segments and signed-artifact identity. Applications own provider trust and authorization, service schemas, payment admission, storage, collection and fulfillment.

The [0.3.0 release](https://github.com/numpde/signed-invoice/releases/tag/v0.3.0) was qualified from frozen source `be92d1594540f82b73e3765833b42f15804e36d8`. Published 0.2.0 uses its original domain-prefix signature and hash rules; its artifacts remain unchanged. This source accepts and emits only the new JWS profile. A package upgrade does not reinterpret stored legacy offers or migrate consumer policy.

The immutable base wheel requirement is:

```text
signed-invoice @ https://github.com/numpde/signed-invoice/releases/download/v0.3.0/signed_invoice-0.3.0-py3-none-any.whl#sha256=598e0bf346d41a517a788b0847635805b8ae068d194fba7cad43661d87a4729b
```

Acquire and verify the actual wheel explicitly, then install offline in the consumer's maintained environment. To declare optional adapter dependencies, use `signed-invoice[pydantic]` with the same URL and hash. The release also carries the sdist, hash manifest and qualification logs. Downloaded draft assets were verified before publication.

## Sign, preserve and verify an invoice

```python
from signed_invoice import SignedInvoice, encode_invoice, sign_invoice, verify_invoice

# fields contains the five-field offer below. private_key is the provider's
# Ed25519PrivateKey; trusted_key comes from application enrollment/authorization.
payload_bytes = encode_invoice(fields)
invoice = sign_invoice(payload_bytes, private_key)
wire_bytes = invoice.to_json()

received = SignedInvoice.from_json(wire_bytes)
document = verify_invoice(received, public_key=trusted_key)
invoice_hash = received.invoice_hash
```

`SignedInvoice` is a frozen framework-neutral value with exactly three strings: `protected`, `payload` and `signature`. Its constructor validates the wire profile and payload, without authenticating the signature. Parsing, `document`, `payload_bytes` and `invoice_hash` do not establish trust. `verify_invoice` separately checks the signature and requires the payload's `provider` key to equal the caller-supplied trusted Ed25519 verification key. Signing similarly requires the private key to match `provider`.

Each recipient must authorize that provider through its own trusted configuration or registry. A key supplied by the invoice cannot authorize itself. A matching hash alone authenticates neither the signature nor the provider, and successful verification accepts no payment or service request.

## JWS profile and identity

The transport is [RFC 7515 flattened JWS JSON](https://www.rfc-editor.org/rfc/rfc7515#section-7.2.2), with exactly these members and canonical **unpadded base64url** string values:

```json
{"protected":"...","payload":"...","signature":"..."}
```

The decoded protected header contains exactly `alg` and `typ`. Canonical emission uses `{"alg":"Ed25519","typ":"application/vnd.signed-invoice.v1+json"}`. `Ed25519` is the fully specified algorithm registered by [RFC 9864](https://www.rfc-editor.org/rfc/rfc9864#section-2.2). The `typ` is this application's profile identifier, not a registered media type. Verification follows RFC 7515 media-type comparison: case is ignored and an omitted `application/` prefix is understood. Those equivalent spellings retain their original signed bytes and have distinct artifact identities.

The signing input is ASCII(`protected + "." + payload`), using the encoded strings actually carried. Ordinary Ed25519 signs those bytes directly. Verification never reconstructs the protected header or payload. No custom domain prefix, unprotected header, key selector, detached payload, alternate algorithm, `crit`, `b64` option or general multi-signature serialization is accepted.

After signing, `invoice.compact` is `protected + "." + payload + "." + signature`. `invoice.invoice_hash` is `0x` plus lowercase SHA-256 of the ASCII bytes of that **complete compact artifact**, including its signature. `invoice_hash(invoice)` computes the same value. This identity rule is part of the invoice profile; JWS does not prescribe it. The buyer can compute it after the provider signs and then bind a payment authorization to it.

Preserve and forward the original three strings. Any segment change, including signature bytes, changes identity. Outer JSON whitespace, escaping and member ordering do not change the carried strings or identity. Do not hash the outer JSON or reconstruct segments from decoded values. Distinct artifacts can still offer the same service; exclusive-offer and duplicate-fulfillment policy remain application responsibilities.

## The five-field payload

Exactly these top-level members are present:

```json
{
  "provider": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
  "payment": {"asset": "eip155:1/slip44:60", "amount": "1000000000000000"},
  "bestBefore": 2000003600,
  "beneficiary": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8",
  "service": {"address": "fixture@mail.example.invalid"}
}
```

This uses synthetic public test identities, not an enrolled provider or commercial offer. Both key fields are 43-character canonical unpadded base64url encodings of 32 raw Ed25519 public bytes. Provider and beneficiary are independent identities; possession and authority remain application checks.

`payment` contains exactly `asset` and `amount`. The asset accepts generic [CAIP-19](https://standards.chainagnostic.org/CAIPs/caip-19) asset-type or asset-ID syntax, with optional token ID and [CAIP-2](https://standards.chainagnostic.org/CAIPs/caip-2) chain syntax. Case and spelling are preserved; parsing proves no namespace support, denomination, route qualification or token behavior.

`amount` matches `[1-9][0-9]*` in asset base units. It remains a string, without EVM limits or integer conversion. The scalar limit is 16384 digits; the complete payload must still fit the byte limit below. Adapters own narrower payment bounds.

`bestBefore` is a canonical JSON integer token in `0..9007199254740991` Unix seconds. Strings, booleans, negative zero, exponents and fractions are rejected. The codec consults no clock. Providers decide whether they can accept and fulfill the offer; this value authorizes no reservation release or hard redemption cutoff.

`service` may be any JSON value, including arrays, scalars and null. Providers own its meaning. `decode_invoice(bytes)` returns a fresh dictionary with `bestBefore` as an integer and every service number as `JsonNumber(token)`, preserving precision and original number spelling. Use `JsonNumber` to encode fractions, exponents or very large integers; Python floats are rejected. `encode_invoice(dict)` serializes once in insertion order and validates the payload. Keep the returned bytes unchanged through signing.

## Boundaries and resource limits

| Boundary | Contract |
| --- | --- |
| `SignedInvoice.from_json(bytes)` | Duplicate-aware strict UTF-8 flattened JSON, at most 32768 bytes |
| `SignedInvoice.from_compact(str)` | Exact three-segment compact form, at most 22276 characters |
| Protected header | Strict JSON, at most 256 decoded bytes, exactly the approved `alg` and `typ` |
| Payload | Strict JSON, at most 16384 decoded UTF-8 bytes, container depth at most 16 with root counted as 1 |
| Signature | Canonical unpadded base64url encoding of exactly 64 bytes, 86 characters |

Duplicate decoded member names, BOMs, malformed UTF-8/JSON, nonfinite numbers and unpaired Unicode surrogates are rejected. Payload limits and lossless numeric handling apply equally to scalar and nested services. The HTTP boundary must also enforce its request-body limit before parsing.

`invoice.payload_bytes` returns the original decoded payload. `invoice.document` returns a fresh validated projection without authentication. `invoice.signing_input` exposes the exact signing input. `invoice.to_dict()` returns the three carried strings; `invoice.to_json()` emits flattened JSON. Verification returns the authenticated document dictionary while the original artifact remains available for retention and forwarding.

Wrong Python argument types raise `TypeError`; malformed protocol inputs raise `InvoiceError`, a `ValueError`. Key/backend failures propagate. Diagnostics do not echo the document. The scalar helpers `require_public_key`, `require_asset`, `require_amount` and `require_best_before` retain their five-field validation contracts and return inputs without normalization.

## Optional Pydantic and OpenAPI integration

The core requires only `cryptography==50.0.2`. The optional `pydantic` extra selects the qualified Pydantic version. Applications can use the shared annotation directly:

```python
from pydantic import BaseModel, ConfigDict
from signed_invoice.pydantic import SignedInvoiceValue

class Response(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    invoice: SignedInvoiceValue
```

The field validates three-string mappings or core `SignedInvoice` values, returns a core artifact and serializes it as the flattened object. Its required fields and bounds are projected from the core artifact; protocol semantics delegate to the same constructor. Pydantic/FastAPI can generate the extra-forbidden object schema from this annotation. Applications need no local JWS mirror model. Validation is structural and does not verify a provider signature or authorization.

**Raw duplicate-member protection belongs before framework JSON parsing.** Pydantic/FastAPI mapping inputs have already lost duplicate-name information; even Pydantic's JSON validation cannot restore it. The raw HTTP JSON owner must reject duplicate names before passing the parsed request to the adapter. `SignedInvoice.from_json(original_bytes)` enforces that rule for a standalone flattened artifact. Encoded protected-header and payload JSON remain duplicate-aware in the shared codec because their original bytes are available.

## Compatibility and qualification

0.3.0 removes the old `domain` arguments, detached-signature APIs and `bytes`/`signature` envelope. It provides no legacy verification path. The full-artifact hash differs from every pre-JWS invoice hash. Coordinate explicit consumer package pins and stored-artifact policy; do not reinterpret old records. Portable EVM voucher schemas and verification belong to their separate contract owner, outside this package.

Shared authoritative vectors are installed at `importlib.resources.files("signed_invoice").joinpath("vectors/invoice.json")`. They contain exact payloads, flattened artifacts, compact strings and full hashes. The public signing test seed is from RFC 8032 and must never identify real offers. Independent Python `joserfc` and JavaScript `jose` checks verify and regenerate the same Ed25519 artifacts; the JWS profile still enforces the expected type separately from generic cryptographic verification.

Use [the maintained Make/container workflows](https://github.com/numpde/signed-invoice#development) for development and qualification. `make vectors/show` prints candidate vector expectations for manual review and never rewrites source. [The JWS record](https://github.com/numpde/signed-invoice/blob/main/notes/008_jws_profile.txt) records provenance, reviewed dependencies, independent evidence, limitations and publication status.
