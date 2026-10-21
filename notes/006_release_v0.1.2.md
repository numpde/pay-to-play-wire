# 0.1.2

Maintenance release for repository checks, release notes and invoice-design documentation. The shared library API, invoice version 2 wire format, exact-byte cryptography, interoperability vectors and runtime dependencies are unchanged from 0.1.1.

## Changes

- Added repository discovery of release notes and checks rejecting manual paragraph/list wrapping and explicit Markdown line breaks.
- Retained the published 0.1.0 and 0.1.1 release notes in the repository, with one source line per paragraph or list item.
- Removed donor application module names from installed-package checks; exact wheel/sdist inventories and this repository's development-module import checks remain.
- Recorded the agreed five-field invoice design, the exact JSON example and consumer responsibilities. The planned format is not implemented in this release; key encoding, asset forms, numeric bounds and domain bytes remain open. The future breaking release has its own draft note.
- Recorded design and working notes as .txt files and completed two independent QA/QC passes on the design documentation.

Source: `f39391c8031614813942a6b6ab97765dba188bb2`.

## Installation input

```text
signed-invoice @ https://github.com/numpde/signed-invoice/releases/download/v0.1.2/signed_invoice-0.1.2-py3-none-any.whl#sha256=a378138da68b70502bdc9630e21b9b3a3431678458f86851d3a1844bd5b64dee
```

Acquire the declared wheel, verify its hash and install offline through the consuming application's maintained workflow. Runtime dependency remains cryptography==50.0.2. The accompanying sha256.json records the exact wheel and sdist hashes.

## Qualification

Built from the clean source revision above on Linux amd64, Python 3.12.12, using the maintained offline containers. Qualification passed lint, 43 repository checks, 46 invoice tests and fresh source-free installations of both the original wheel and the wheel rebuilt from the sdist. The publisher downloaded and verified all release assets before publication. Build/test logs accompany the release. Other interpreter/platform combinations were not executed.

These checks qualify the existing version 2 package; they do not qualify the planned five-field format or a consumer deployment. The five-field format remains an unreleased design.
