---
layout: default
title: wire — invoices, vouchers and signed acceptances
---

# Invoices, vouchers and signed acceptances in Python

`wire` lets applications create, read and verify three kinds of signed messages:

| Message | Who signs it | What it contains |
| --- | --- | --- |
| Invoice | A service provider | A service description, requested payment and named parties |
| Voucher | A buyer or an application-authorized signer | A cumulative payment authorization referring to a signed invoice |
| Acceptance | A receiving service's authorized acceptance signer | The signing public key, complete signed voucher and signing time |

For example, an analysis service could sign an offer to fit a spectrum. A client could verify that offer and sign a voucher containing its exact invoice hash. The receiving service would then check the voucher and decide whether to accept the purchase.

`wire` checks message formats and cryptographic signatures. Your application chooses trusted keys, interprets the service description, checks payment conditions and performs the analysis or payment. Successful signature verification alone establishes neither an acceptable purchase nor a transfer of funds.

A valid signature links a message to a signing key. Your application establishes whose key it is and what that party may authorize. The invoice format uses Ed25519 keys; the voucher format uses Ethereum's secp256k1 signatures to match the payment contract's rules. These key types are not interchangeable.

Acceptance uses Ed25519. It lets a recipient authenticate a service's signed statement about one exact voucher. The producing application owns the decision to accept and the historical authority of the voucher signer. This format defines no later status or fulfillment policy.

The examples below use release 0.9.0, pinned below. Its signed-message profiles are unchanged from 0.8.0. Version 0.7.0 supports the earlier acceptance profile without `signer`; its artifacts require that older version. To exercise this guide from the repository, use the README's dependency and image preparation, then `make test/repository`; that maintained container command executes every Python example in order.

## Install the complete package

Installing `wire` provides all message types and their Pydantic adapters. There are no extras to select. Python 3.12 or later is required; the maintained installation checks use Python 3.12 on Linux amd64.

The following is a requirements-file entry for [release 0.9.0](https://github.com/numpde/pay-to-play-wire/releases/tag/v0.9.0):

```text
wire @ https://github.com/numpde/pay-to-play-wire/releases/download/v0.9.0/wire-0.9.0-py3-none-any.whl#sha256=4a306070e06fe55b04583ab908dfb8d1392893da5c8c0e067b2f01a907ca047c
```

Acquire the wheel and its dependencies through your application's dependency workflow, then verify the downloaded bytes before installing offline. The [runtime lock for this release](https://github.com/numpde/pay-to-play-wire/blob/3de987104e703fd414488a25105f5a416791bfd5/requirements/runtime.lock) lists the exact dependency versions and wheel hashes used for the maintained platform. A wheel file alone does not contain those dependencies. Repository contributors can reuse `.work/wire/wheels/` after `make dependencies/check`; that development dependency directory also contains the runtime wheels. Application users can supply their own verified dependency directory without preparing the development image.

For example, download the package wheel with an explicitly selected network interface. Replace `eth0` with an interface available on your machine:

```sh
curl --interface eth0 --fail --location \
  --output wire-0.9.0-py3-none-any.whl \
  https://github.com/numpde/pay-to-play-wire/releases/download/v0.9.0/wire-0.9.0-py3-none-any.whl
printf '%s\n' '4a306070e06fe55b04583ab908dfb8d1392893da5c8c0e067b2f01a907ca047c  wire-0.9.0-py3-none-any.whl' | sha256sum --check
```

Once the wheel, runtime lock and dependency wheels have been acquired and verified, install inside your application's Python environment. Replace the three absolute paths below with their local locations. `--no-index` prevents this step from downloading dependencies:

```sh
python -m pip install --no-index --require-hashes \
  --find-links=/absolute/path/to/verified-dependency-wheels \
  -r /absolute/path/to/runtime.lock \
  'wire @ file:///absolute/path/to/wire-0.9.0-py3-none-any.whl#sha256=4a306070e06fe55b04583ab908dfb8d1392893da5c8c0e067b2f01a907ca047c'
```

For work in this repository, run project Python through Make and its maintained containers; see the README rather than installing into the host Python environment.

## Try a local invoice

This example is complete. It creates temporary demonstration keys, signs a synthetic offer and verifies the received message. It makes no network request. Each run generates different keys and signatures; the assertions should pass on every run.

Run the Python examples in this guide in order, in the same Python session; the later examples reuse the objects created here.

An Ed25519 key pair consists of a private signing key and a public verification key. The example obtains both in one process. In an application, the recipient must obtain the expected provider public key from its own trusted configuration or enrollment process, independently of the received invoice.

```python
import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from wire.invoice import SignedInvoice, encode_invoice, sign_invoice, verify_invoice

provider_key = Ed25519PrivateKey.generate()
beneficiary_key = Ed25519PrivateKey.generate().public_key()


def public_key_text(key):
    return base64.urlsafe_b64encode(key.public_bytes_raw()).rstrip(b"=").decode("ascii")


fields = {
    "provider": public_key_text(provider_key.public_key()),
    "payment": {"asset": "eip155:1/slip44:60", "amount": "5"},
    "bestBefore": 2000003600,
    "beneficiary": public_key_text(beneficiary_key),
    "service": {"analysis": "spectrum-fit", "sample": "demo-001"},
}

payload_bytes = encode_invoice(fields)
invoice = sign_invoice(payload_bytes, provider_key)
received_invoice = SignedInvoice.from_json(invoice.to_json())

trusted_provider_key = provider_key.public_key()  # Local demonstration only.
document = verify_invoice(received_invoice, public_key=trusted_provider_key)

assert document == fields
assert received_invoice.invoice_hash == invoice.invoice_hash
```

`verify_invoice` returns the authenticated document dictionary. It checks the signature against the supplied key and requires that key to match the invoice's `provider` field. A malformed message or signature failure raises `InvoiceError`, which is a subclass of `ValueError`. Wrong types for explicitly typed API arguments, such as the verification key, raise `TypeError`; wrong field types inside a message produce protocol errors.

The example proves that the message survives serialization and verifies under the chosen key. It does not establish that this provider is authorized to offer an analysis, that the sample exists, or that the requested payment is appropriate.

`invoice_hash` is a fixed-length identifier computed from the complete signed invoice. The voucher below carries it to identify this particular offer; the [identity rules](#invoice-identity-preserve-the-three-signed-strings) explain exactly which bytes it covers.

### What the invoice fields mean

Exactly five top-level fields are required:

| Field | Representation and interpretation |
| --- | --- |
| `provider` | The signing provider's Ed25519 public key, encoded as 43 unpadded base64url characters |
| `beneficiary` | An application-designated beneficiary's Ed25519 public key in the same encoding; the application defines and checks its relationship to the service and payment |
| `payment` | Exactly `asset` and `amount`; the application decides whether it supports that payment |
| `bestBefore` | A nonnegative integer in Unix seconds, at most `2**53 - 1`; the application decides how to apply it |
| `service` | Any JSON value describing the offered service; the application defines its meaning |

The field name `beneficiary` does not, by itself, establish a payment recipient, service user or Ethereum address. Use your application's protocol to determine that party's role.

Base64url is a text encoding for bytes. Here it uses letters, digits, `-` and `_`, without trailing `=` padding. It does not encrypt the message or establish who owns a key.

`payment.asset` uses [CAIP-19](https://standards.chainagnostic.org/CAIPs/caip-19) syntax to name an asset and its chain. The demonstration value `eip155:1/slip44:60` names native Ether on Ethereum chain 1. `amount` is a positive decimal string in the asset's smallest units, without a sign, fractional part or leading zeros. For Ether, `"5"` means five wei. `wire` checks the identifier's syntax and the amount's representation; applications determine denominations, supported assets and payment routes.

The invoice amount has no Ethereum integer bound. It may contain at most 16384 digits, subject to the smaller limit imposed by the complete document's byte size. A payment implementation can impose narrower limits.

`wire` does not read a clock when validating `bestBefore`. Successful verification therefore does not establish that an offer is timely. The timestamp alone also establishes no reservation release or redemption policy.

### Preserve scientific numbers

Python floats are rejected by `encode_invoice`. Use `JsonNumber` for a JSON number whose decimal spelling must survive without floating-point rounding:

```python
from wire.invoice import JsonNumber, decode_invoice

precise_fields = dict(fields, service={"tolerance": JsonNumber("1.234567890123456789e-12")})
precise_bytes = encode_invoice(precise_fields)
decoded = decode_invoice(precise_bytes)

assert decoded["service"]["tolerance"].token == "1.234567890123456789e-12"
```

`decode_invoice` returns `bestBefore` as a Python integer and every number within `service` as a `JsonNumber`, including integer tokens. It preserves the number's text; your application chooses the numerical type and precision for computation.

## Add a voucher referring to that invoice

A payment channel is an application-managed arrangement identified here by a contract and a channel number. A voucher authorizes a **cumulative total** for that channel: the total authorization so far, rather than necessarily the price of this one invoice. Applications determine the correct total from their own channel state and rules. `wire` neither calculates that total nor checks balances or earlier payments.

Voucher identities use Ethereum addresses, represented in Python as 20 bytes. These differ from the invoice's Ed25519 keys. `customer` is the address identifying the customer's side of the channel. The authorized voucher signer is the Ethereum address the receiving application permits to sign for that customer; that signer can differ from `customer`. The application or its payment contract determines how that permission is recorded. The package performs no lookup and creates no relationship between either address and the invoice's `beneficiary`.

Continue the invoice example above. These addresses and channel values are synthetic; no deployed contract or funded channel is required for this local signature demonstration:

Suppose an application's channel rules allow an additional five units after an earlier authorized total of twelve. It could choose a new cumulative total of seventeen. The example uses that chosen total; it does not retrieve earlier state or decide whether an increase is permitted.

```python
from eth_account import Account

from wire.voucher import (
    SignedVoucher,
    VoucherDomain,
    build_voucher_typed_data,
    sign_voucher,
    verify_voucher,
)

buyer = Account.create()
trusted_voucher_signer = bytes.fromhex(buyer.address[2:])  # Local demonstration only.
trusted_domain = VoucherDomain(chain_id=1, verifying_contract=bytes.fromhex("33" * 20))

typed_data = build_voucher_typed_data(
    domain=trusted_domain,
    customer=bytes.fromhex("22" * 20),
    channel_id=7,
    cumulative_total=17,  # Illustrative total: earlier 12 plus an approved increment of 5.
    invoice_hash=bytes.fromhex(received_invoice.invoice_hash[2:]),
)
voucher = sign_voucher(typed_data, bytes(buyer.key))
received_voucher = SignedVoucher.from_json(voucher.to_json())

result = verify_voucher(
    received_voucher,
    expected_domain=trusted_domain,
    expected_signer=trusted_voucher_signer,
)
assert result is None  # Verification succeeds by returning without an exception.
assert received_voucher.message["invoiceHash"] == received_invoice.invoice_hash
```

The **deployment domain** identifies the expected blockchain (`chain_id`) and contract (`verifying_contract`). In an application, obtain this domain and the authorized signer from trusted application state, independently of the voucher. `verify_voucher` checks that the carried domain matches and that the signature recovers the expected signer. It returns `None` on success and raises `ValueError` on a protocol or verification failure. Wrong types for explicitly typed API arguments, such as the expected `VoucherDomain`, raise `TypeError`; wrong field types inside a message produce protocol errors.

The final equality assertion checks the voucher's invoice reference separately. `verify_voucher` does not check that reference, the amount owed, the customer/signer relationship or whether the channel can pay. An application must check those conditions before accepting a purchase. Transferring or collecting funds, deciding when to run the analysis, and recording its result remain application operations.

## Sign and verify an acceptance

An acceptance v2 contains exactly three payload fields: `signer`, the signing Ed25519 public key; `voucher`, the **complete signed voucher**, including its original 65-byte signature; and `acceptedAt`, the signing time in Unix seconds. The public key uses the same canonical unpadded base64url encoding of 32 raw bytes as the invoice's `provider`. `acceptedAt` must be a canonical nonnegative JSON integer in `0..2**53 - 1`; booleans, strings, fractions, exponents and negative zero are rejected. The caller supplies the time; the codec reads no clock and applies no cutoff or ordering policy. Signing time is independent of application decision, database creation and commit times.

Continue the examples above. This creates a local demonstration statement; it does not make an actual purchase decision or consult a signer registry:

```python
from wire.acceptance import (
    SignedAcceptance,
    encode_acceptance,
    sign_acceptance,
    verify_acceptance,
)

acceptance_key = Ed25519PrivateKey.generate()
acceptance_bytes = encode_acceptance({
    "signer": public_key_text(acceptance_key.public_key()),
    "voucher": received_voucher.to_dict(),
    "acceptedAt": 2000000000,
})
acceptance = sign_acceptance(acceptance_bytes, acceptance_key)
received_acceptance = SignedAcceptance.from_json(acceptance.to_json())

trusted_acceptance_key = acceptance_key.public_key()  # Local demonstration only.
receipt_document = verify_acceptance(received_acceptance, public_key=trusted_acceptance_key)

assert received_acceptance.voucher == received_voucher
assert receipt_document["voucher"]["signature"] == received_voucher.signature
assert received_acceptance.accepted_at == 2000000000
assert received_acceptance.signer == public_key_text(trusted_acceptance_key)
```

`sign_acceptance` requires the carried `signer` to match the private key's public key before signing the exact supplied bytes. It does not insert or replace payload fields. `verify_acceptance` returns the authenticated three-field document only when the carried signer equals the caller's trusted public key and the signature verifies. Obtain that trusted key independently of the received message. The signature covers all three fields and the original voucher signature; changing any carried value requires a new receipt signature.

Carrying the full public key lets the artifact identify its signer without a separate stored key or database lookup. Verification authenticates that identity; it does not grant trust or authorization. The same principle applies to invoice `provider`, while voucher signatures use the protocol's standard signer recovery. Applications still own key delivery, trust, authorization and key rotation.

`SignedAcceptance.signer` returns the encoded public key, `.voucher` returns a structurally validated `SignedVoucher`, and `.accepted_at` returns the integer timestamp. Accessors do not authenticate the acceptance, verify an Ethereum signature or establish the voucher signer's historical authority. Structural voucher parsing, acceptance verification and the Pydantic adapters do not import Ethereum backends. The complete package installs those dependencies; voucher signing, signature verification and digest computation load them when called.

Acceptance protocol and signature failures raise `AcceptanceError`, a `ValueError`. The raw JSON and key arguments retain explicit `TypeError` contracts. Applications decide whether the verified statement is sufficient for their next operation; this API performs no fulfillment, settlement or later status check.

## Use the same objects in Pydantic models

Pydantic models validate and serialize application data; OpenAPI describes HTTP API data structures. Both integrations are included with `wire`:

```python
from pydantic import BaseModel, ConfigDict

from wire.invoice.pydantic import SignedInvoiceValue
from wire.voucher.pydantic import SignedVoucherValue
from wire.acceptance.pydantic import SignedAcceptanceValue


class PurchaseMessages(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    invoice: SignedInvoiceValue
    voucher: SignedVoucherValue
    acceptance: SignedAcceptanceValue


messages = PurchaseMessages(
    invoice=received_invoice.to_dict(), voucher=received_voucher, acceptance=received_acceptance
)
assert type(messages.invoice) is SignedInvoice
assert type(messages.voucher) is SignedVoucher
assert type(messages.acceptance) is SignedAcceptance
assert PurchaseMessages.model_validate_json(messages.model_dump_json()) == messages
```

Each field accepts the corresponding core object or its dictionary representation, returns a core object and serializes it as the transport object. Validation enforces the core format and profile rules. Call the corresponding `verify_invoice`, `verify_voucher` or `verify_acceptance` function explicitly to check its signature with trusted inputs.

**Reject duplicate JSON field names before framework parsing.** A dictionary has already lost that information. For a standalone signed message, use its `from_json(original_bytes)` method. For a containing HTTP request such as `PurchaseMessages`, the application must reject duplicates in the original request body before passing it to Pydantic or FastAPI. Parsing encoded JWS headers and payloads remains duplicate-aware because those original bytes are still available.

## Encode or admit canonical JSON

Release 0.9.0 adds a separate `CanonicalJSON` value. It does not change the signed profiles or the invoice `JsonNumber` behavior described above.

```python
from wire import CanonicalJSON

canonical = CanonicalJSON.encode({"z": 2, "a": 1})
assert canonical.bytes == b'{"a":1,"z":2}'
received = CanonicalJSON.from_bytes(canonical.bytes)
assert bytes(received) == canonical.bytes
projection = received.value
projection["a"] = 99
assert received.value["a"] == 1
```

`encode` produces JCS bytes from unsigned values: dictionaries with string keys, lists, strings, booleans, `None`, safe-range Python integers and finite binary64 floats. `from_bytes` admits only already-canonical UTF-8 bytes, retaining them exactly. It rejects duplicate names, invalid Unicode and alternative whitespace, member ordering, escaping or number spelling. The default byte limit is 16,384, with a fixed maximum container depth of 16; callers may supply a positive integer `max_bytes` when larger bodies are expected. Limit incoming body acquisition separately. Invalid encodings raise `CanonicalJSONError`, a `ValueError`.

This class uses binary64 numbers. Exact decimals and large exact integers must be schema-defined strings; `Decimal` and `JsonNumber` are not converted. A binary64 float such as `1e20` canonically encodes as the integer-looking token `100000000000000000000`; its `.value` projection is a float. Safe integer tokens project to Python integers. The spelling alone does not establish exact-integer semantics. JCS also preserves Unicode strings without normalizing different character sequences.

Canonical encoding proves no schema, signature, trusted identity or permission. Applications can use this raw admission before Pydantic when their endpoint explicitly requires a canonical JSON body. It does not impose that contract on existing HTTP endpoints or signed profiles. Never pass received signed bytes through `encode` to make them acceptable; verify and retain their original bytes using the artifact APIs.

The 0.10.0 candidate also accepts ordinary JSON through `encode_json`; this method is not included in the 0.9.0 installation pin above:

```python
ordinary_json = b'{ "z": 1e0, "a": -0 }\n'
normalized = CanonicalJSON.encode_json(ordinary_json)
assert normalized.bytes == b'{"a":0,"z":1}'
```

This method rejects duplicate names and compares each original numeric token's exact decimal value with its canonical binary64 spelling. Equivalent forms such as `1.0` may normalize; precision-changing values such as `9007199254740993` are rejected. An explicit positive integer `max_bytes` bounds both incoming and resulting canonical bytes, with the same default and depth limits as the other factories. Exact high-precision quantities still need schema-defined strings. `encode_json` returns a derived value suitable for hashing or signing a new document; it does not retain or authenticate the original input. Keep those bytes separately whenever a request signature, JWS profile or artifact identity refers to them. A canonical internal representation does not itself require external clients to send canonical bytes.

## Shared API and message identity

`SignedInvoice`, `SignedVoucher` and `SignedAcceptance` are immutable objects with these methods:

| Method | Result |
| --- | --- |
| `from_dict(mapping)` | Parse a transport dictionary; duplicate names cannot be detected here |
| `from_json(bytes)` | Parse bounded UTF-8 JSON and reject duplicate names |
| `to_dict()` | Return a fresh transport dictionary |
| `to_json()` | Return transport JSON as bytes |
| `json_schema()` | Return a fresh JSON Schema description without invoking Pydantic |

JSON Schema describes field structure and text constraints. Core parsing additionally checks decoded invoice contents, uint256 range and voucher signature form. Neither a schema nor a parsed object establishes a valid signature or permission to purchase.

### Acceptance identity: retain the original JWS

Acceptance uses the same three-string flattened JWS transport and canonical unpadded base64url as invoices. Its protected header is `{"alg":"Ed25519","typ":"application/vnd.signed-purchase-acceptance.v2+json"}`, with the same media-type comparison rules described below. The signature covers ASCII(`protected + "." + payload`). The earlier acceptance v1 profile is rejected. Invoice and acceptance profiles cannot substitute for one another, even under the same key.

Retain and forward the original acceptance segments. `acceptance.compact`, `.payload_bytes`, `.document`, `.signing_input` and `from_compact` have the same preservation contracts as their invoice counterparts. This profile defines no additional acceptance hash, UUID or duplicated invoice-hash field. The invoice reference remains inside the complete carried voucher.

### Invoice identity: preserve the three signed strings

An invoice uses the flattened [JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515#section-7.2.2) form, containing exactly `protected`, `payload` and `signature`. Each is an unpadded base64url string. The first encodes the protected header, the second the invoice document, and the third a 64-byte Ed25519 signature.

The header contains exactly `alg` and `typ`. Emission uses `{"alg":"Ed25519","typ":"application/vnd.signed-invoice.v1+json"}`. `Ed25519` is the fully specified algorithm defined by [RFC 9864](https://www.rfc-editor.org/rfc/rfc9864#section-2.2). The `typ` is this application's profile identifier. Its comparison ignores case and permits omission of `application/`, following RFC 7515; accepted spellings retain their original signed bytes.

The signature covers ASCII(`protected + "." + payload`). `invoice.compact` contains all three strings separated by dots; `SignedInvoice.from_compact(str)` parses that representation. `invoice.invoice_hash` and `invoice_hash(invoice)` return `0x` plus lowercase SHA-256 of the **complete compact artifact, including its signature**.

Keep and forward the original strings. Reconstructing the header or document can change signed bytes and identity even when its interpreted content appears unchanged. Outer transport JSON whitespace and field order do not change those strings. Hash the complete compact artifact, rather than the outer JSON or the unsigned document. Hash equality alone does not verify a signature.

`invoice.payload_bytes` returns the original decoded payload, `invoice.document` returns a fresh parsed document, and `invoice.signing_input` returns the signed bytes. None of these properties authenticates the invoice. Only the fixed protected profile is accepted: alternate algorithms, unprotected headers, key selectors, detached payloads, `crit`, `b64` options and general multi-signature forms are rejected.

### Voucher identity: typed values and deployment

Vouchers use [EIP-712](https://eips.ethereum.org/EIPS/eip-712), an Ethereum format for signing named, typed fields. The profile fixes domain name `PayToPlay`, version `2`, and the following field order:

| Type | Fields in signing order |
| --- | --- |
| `EIP712Domain` | `name/string`, `version/string`, `chainId/uint256`, `verifyingContract/address` |
| `Voucher` | `customer/address`, `channelId/uint256`, `cumulativeTotal/uint256`, `invoiceHash/bytes32` |

The transported object contains exactly `typedData` and `signature`. Python builders accept integer uint256 values in `0..2**256 - 1` and bytes for addresses and hashes. On the wire, uint256 values are decimal strings without signs or leading zeros; zero is `"0"`. Addresses, hashes and signatures use lowercase `0x` hex. The 65-byte signature must have nonzero secp256k1 scalars, low `s` and recovery byte 27 or 28; these are the contract's required signature encoding rules.

`voucher.typed_data`, `.domain` and `.message` return fresh dictionaries. `voucher.digest` returns the 32-byte EIP-712 digest, **excluding the signature**. This differs from the invoice hash rule. Formatting the outer voucher JSON does not change the typed values or digest. Always use explicit verification to check the expected domain and signer.

## Input limits and rejection

| Input | Limit or rule |
| --- | --- |
| Invoice transport JSON | At most 32768 bytes |
| Compact invoice | At most 22276 characters |
| Decoded invoice header | At most 256 bytes, exactly the required `alg` and `typ` |
| Decoded invoice document | At most 16384 UTF-8 bytes; nested container depth at most 16, counting the root as 1 |
| Invoice signature text | Exactly 86 canonical unpadded base64url characters encoding 64 bytes |
| Voucher transport JSON | At most 8192 bytes, with the fixed typed-data schema and signature form |
| Acceptance transport JSON / compact form | At most 32768 bytes / 22276 characters, with a decoded payload at most 16384 bytes and the same 256-byte header and 64-byte Ed25519 signature bounds |

The raw parsers reject duplicate field names and malformed UTF-8/JSON. Invoice JSON also rejects byte-order marks, nonfinite numbers and unpaired Unicode surrogates. The invoice document's depth and number rules apply to all allowed `service` values. Applications receiving HTTP requests must limit body size before parsing, including when the signed message is nested inside a larger request.

Core diagnostics identify the failed rule without echoing the document. Invoice protocol failures, including incorrect field types in message dictionaries, use `InvoiceError`; acceptance failures use `AcceptanceError`; voucher protocol failures use `ValueError`. Explicitly typed API arguments, such as byte inputs, key objects and deployment-domain objects, use `TypeError` when their type contracts are violated. Backend failures propagate except for the deliberately translated verification errors. Pydantic reports format failures as `ValidationError` through its own interface.

### Signature-failure format hints

The 0.11.0 candidate adds `.canonical_json_hint` to invoice and acceptance errors. Only an actual cryptographic signature failure triggers inspection of the original payload. If it does not pass this package's canonical JSON checks, the error includes a fixed safe hint that serialization differences may be a cause. The failure type and original cryptographic cause are preserved. A valid noncanonical payload still verifies; no payload is rewritten or retried.

This example deliberately damages a signature from the earlier local invoice demonstration:

```python
from wire.invoice import InvoiceError
from wire.json import signature_failure_hint

damaged = SignedInvoice(received_invoice.protected, received_invoice.payload, "A" * 86)
try:
    verify_invoice(damaged, public_key=trusted_provider_key)
except InvoiceError as failure:
    hint = failure.canonical_json_hint
    assert hint is not None
    assert "may be a cause" in hint
    assert signature_failure_hint(damaged.payload_bytes) == hint
else:
    raise AssertionError("The damaged signature unexpectedly verified.")
```

The reusable `signature_failure_hint(original_payload, *, max_bytes=16384)` returns a safe string or `None`, without echoing payload fields or exception text. Use it only after a cryptographic failure at a known JSON signature boundary, and pass the already-enforced body limit for larger payloads. It checks wire's bounded canonical-JSON rules and reports a possible issue, not a definitive cause. It does not apply automatically to non-JSON HTTP bodies, Content-Digest mismatches, parsing failures or general JOSE errors. Voucher EIP-712 verification is unchanged because JSON formatting is not its signed input.

## Reproducibility and verification evidence

Release 0.9.0 was built from committed source `3de987104e703fd414488a25105f5a416791bfd5`. Lint, 146 tests and fresh installations of both the wheel and the wheel rebuilt from the source distribution passed in the maintained containers. The combined campaign covers canonical JSON encoding and strict byte admission, independent JWS interoperability, exact vector reproduction, carried-signer and trusted-key binding, altered signer/voucher/time rejection, acceptance v1 rejection and acceptance use while Ethereum imports are blocked. Downloaded draft assets and qualification logs matched the checked bytes before public release; an anonymous public-wheel download also matched. The [release](https://github.com/numpde/pay-to-play-wire/releases/tag/v0.9.0) contains the source distribution, source inventory, hash manifest and logs. These are package checks, not proof of application deployment or live payment.

Shared test vectors are installed with the package. They contain fixed expected messages and results for comparing implementations. The acceptance vector uses the v2 profile introduced in 0.8.0:

```python
from importlib.resources import files

invoice_vectors = files("wire").joinpath("vectors/invoice.json").read_bytes()
voucher_vectors = files("wire").joinpath("vectors/voucher.json").read_bytes()
acceptance_vectors = files("wire").joinpath("vectors/acceptance.json").read_bytes()
json_vectors = files("wire").joinpath("vectors/json.json").read_bytes()
assert invoice_vectors and voucher_vectors and acceptance_vectors and json_vectors
```

The tests cover independent Python JWS verification, fixed voucher digest expectations and an invoice-to-voucher example. Additional recorded JavaScript comparisons checked invoice signatures with `jose` and voucher signatures with viem. These observations establish the particular interoperability checks recorded in the [consolidation record](https://github.com/numpde/pay-to-play-wire/blob/main/notes/010_wire_consolidation.txt); they establish no consumer deployment or live payment outcome.

Earlier packages used `signed_invoice` and `signed_voucher` imports. Their replacements are `wire.invoice` and `wire.voucher`; old import namespaces are not shipped. The invoice's signed `typ` spelling remains unchanged. Historical releases and their evidence remain available at their original locations.

For repository setup, focused tests, artifact builds and publication, use the [contributor README](https://github.com/numpde/pay-to-play-wire#development).
