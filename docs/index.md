---
layout: default
title: wire — signed invoices and payment vouchers
---

# Signed invoices and payment vouchers in Python

`wire` lets applications create, read and verify two kinds of signed messages:

| Message | Who signs it | What it contains |
| --- | --- | --- |
| Invoice | A service provider | A service description, requested payment and named parties |
| Voucher | A buyer or an application-authorized signer | A cumulative payment authorization referring to a signed invoice |

For example, an analysis service could sign an offer to fit a spectrum. A client could verify that offer and sign a voucher containing its exact invoice hash. The receiving service would then check the voucher and decide whether to accept the purchase.

`wire` checks message formats and cryptographic signatures. Your application chooses trusted keys, interprets the service description, checks payment conditions and performs the analysis or payment. Successful signature verification alone establishes neither an acceptable purchase nor a transfer of funds.

A valid signature links a message to a signing key. Your application establishes whose key it is and what that party may authorize. The invoice format uses Ed25519 keys; the voucher format uses Ethereum's secp256k1 signatures to match the payment contract's rules. These key types are not interchangeable.

## Install the complete package

Installing `wire` provides both message types and both Pydantic adapters. There are no extras to select. Python 3.12 or later is required; the maintained installation checks use Python 3.12 on Linux amd64.

The following is a requirements-file entry for [release 0.6.0](https://github.com/numpde/pay-to-play-wire/releases/tag/v0.6.0):

```text
wire @ https://github.com/numpde/pay-to-play-wire/releases/download/v0.6.0/wire-0.6.0-py3-none-any.whl#sha256=5f90763f703f4c408c2223458cf3d37980c0de844b0683ac87ced1202a4aedcd
```

Acquire the wheel and its dependencies through your application's dependency workflow, then verify the downloaded bytes before installing offline. The [runtime lock for this release](https://github.com/numpde/pay-to-play-wire/blob/be80276d38f80a2bade5df359c77797107672207/requirements/runtime.lock) lists the exact dependency versions and wheel hashes used for the maintained platform. A wheel file alone does not contain those dependencies. Repository contributors can reuse `.work/wire/wheels/` after `make dependencies/check`; that development dependency directory also contains the runtime wheels. Application users can supply their own verified dependency directory without preparing the development image.

For example, download the package wheel with an explicitly selected network interface. Replace `eth0` with an interface available on your machine:

```sh
curl --interface eth0 --fail --location \
  --output wire-0.6.0-py3-none-any.whl \
  https://github.com/numpde/pay-to-play-wire/releases/download/v0.6.0/wire-0.6.0-py3-none-any.whl
printf '%s\n' '5f90763f703f4c408c2223458cf3d37980c0de844b0683ac87ced1202a4aedcd  wire-0.6.0-py3-none-any.whl' | sha256sum --check
```

Once the wheel, runtime lock and dependency wheels have been acquired and verified, install inside your application's Python environment. Replace the three absolute paths below with their local locations. `--no-index` prevents this step from downloading dependencies:

```sh
python -m pip install --no-index --require-hashes \
  --find-links=/absolute/path/to/verified-dependency-wheels \
  -r /absolute/path/to/runtime.lock \
  'wire @ file:///absolute/path/to/wire-0.6.0-py3-none-any.whl#sha256=5f90763f703f4c408c2223458cf3d37980c0de844b0683ac87ced1202a4aedcd'
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

## Use the same objects in Pydantic models

Pydantic models validate and serialize application data; OpenAPI describes HTTP API data structures. Both integrations are included with `wire`:

```python
from pydantic import BaseModel, ConfigDict

from wire.invoice.pydantic import SignedInvoiceValue
from wire.voucher.pydantic import SignedVoucherValue


class PurchaseMessages(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    invoice: SignedInvoiceValue
    voucher: SignedVoucherValue


messages = PurchaseMessages(invoice=received_invoice.to_dict(), voucher=received_voucher)
assert type(messages.invoice) is SignedInvoice
assert type(messages.voucher) is SignedVoucher
assert PurchaseMessages.model_validate_json(messages.model_dump_json()) == messages
```

Both fields accept the corresponding core object or its dictionary representation, return a core object and serialize it as the transport object. Their validation enforces the core format and profile rules. Call `verify_invoice` or `verify_voucher` explicitly to check signatures with trusted inputs.

**Reject duplicate JSON field names before framework parsing.** A dictionary has already lost that information. For a standalone invoice or voucher, use its `from_json(original_bytes)` method. For a containing HTTP request such as `PurchaseMessages`, the application must reject duplicates in the original request body before passing it to Pydantic or FastAPI. Parsing encoded invoice headers and payloads remains duplicate-aware because those original bytes are still available.

## Shared API and message identity

Both `SignedInvoice` and `SignedVoucher` are immutable objects with these methods:

| Method | Result |
| --- | --- |
| `from_dict(mapping)` | Parse a transport dictionary; duplicate names cannot be detected here |
| `from_json(bytes)` | Parse bounded UTF-8 JSON and reject duplicate names |
| `to_dict()` | Return a fresh transport dictionary |
| `to_json()` | Return transport JSON as bytes |
| `json_schema()` | Return a fresh JSON Schema description without invoking Pydantic |

JSON Schema describes field structure and text constraints. Core parsing additionally checks decoded invoice contents, uint256 range and voucher signature form. Neither a schema nor a parsed object establishes a valid signature or permission to purchase.

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

The raw parsers reject duplicate field names and malformed UTF-8/JSON. Invoice JSON also rejects byte-order marks, nonfinite numbers and unpaired Unicode surrogates. The invoice document's depth and number rules apply to all allowed `service` values. Applications receiving HTTP requests must limit body size before parsing, including when the signed message is nested inside a larger request.

Core diagnostics identify the failed rule without echoing the document. Invoice protocol failures, including incorrect field types in message dictionaries, use `InvoiceError`; voucher protocol failures use `ValueError`. Explicitly typed API arguments, such as byte inputs, key objects and deployment-domain objects, use `TypeError` when their type contracts are violated. Backend failures propagate except for the deliberately translated verification errors. Pydantic reports format failures as `ValidationError` through its own interface.

## Reproducibility and verification evidence

The 0.6.0 release was built from committed source `be80276d38f80a2bade5df359c77797107672207`. Lint, 114 tests and fresh installations of both the wheel and the wheel rebuilt from the source distribution passed in the maintained containers. Downloaded draft assets and qualification logs matched the checked bytes before public release. The [release](https://github.com/numpde/pay-to-play-wire/releases/tag/v0.6.0) contains the source distribution, source inventory, hash manifest and logs.

Shared test vectors are installed with the package. They contain fixed expected messages and results for comparing implementations:

```python
from importlib.resources import files

invoice_vectors = files("wire").joinpath("vectors/invoice.json").read_bytes()
voucher_vectors = files("wire").joinpath("vectors/voucher.json").read_bytes()
assert invoice_vectors and voucher_vectors
```

The tests cover independent Python JWS verification, fixed voucher digest expectations and an invoice-to-voucher example. Additional recorded JavaScript comparisons checked invoice signatures with `jose` and voucher signatures with viem. These observations establish the particular interoperability checks recorded in the [consolidation record](https://github.com/numpde/pay-to-play-wire/blob/main/notes/010_wire_consolidation.txt); they establish no consumer deployment or live payment outcome.

Earlier packages used `signed_invoice` and `signed_voucher` imports. Their replacements are `wire.invoice` and `wire.voucher`; old import namespaces are not shipped. The invoice's signed `typ` spelling remains unchanged. Historical releases and their evidence remain available at their original locations.

For repository setup, focused tests, artifact builds and publication, use the [contributor README](https://github.com/numpde/pay-to-play-wire#development).
