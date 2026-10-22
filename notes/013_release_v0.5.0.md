# wire 0.5.0

Invoice and voucher artifacts now share `from_dict`, `from_json`, `to_dict`, `to_json` and framework-neutral `json_schema` interfaces. The new `wire.voucher.pydantic.SignedVoucherValue` annotation matches `wire.invoice.pydantic.SignedInvoiceValue`; both use one field-independent adapter that delegates parsing, serialization and schema presentation to the core artifact.

Existing `wire.voucher` imports remain available after moving the implementation into a package. Invoice segments, signatures and full compact hashes retain their profile; voucher schema order, digests, signatures and transport retain theirs. Parsing and schema generation do not authenticate either artifact. Applications still supply trusted verification keys, the voucher deployment domain and registered signer.

Use `wire[pydantic]` for the invoice adapter or `wire[pydantic,voucher]` for both adapters. No dependency versions changed. Both raw JSON parsers retain duplicate-member rejection; framework adapters require duplicate rejection before framework parsing. JSON Schema describes structure and lexical bounds, while core parsing additionally enforces decoded profiles, uint256 range and contract signature form.

Qualification runs from a frozen committed source snapshot through the maintained offline containers. It covers the source campaigns and both wheel and sdist-derived wheel installations in all four dependency selections. Publication verifies downloaded draft artifacts and qualification logs before making the release public; published assets are never replaced. Exact source and artifact identities are recorded in the release receipt after publication.

Source: `075e47ff75d73a3680e8863d0e13691a50a04670`. Lint, all 114 repository/invoice/voucher tests and all eight installed profiles passed. Downloaded draft artifacts and both qualification logs matched before public release.

```text
wire @ https://github.com/numpde/pay-to-play-wire/releases/download/v0.5.0/wire-0.5.0-py3-none-any.whl#sha256=2a62772e9edbfc236eb43d4619fa517d2575b21a8e656a13a1418130b5ef219d
```
