# 0.1.2

Maintenance release for repository checks, release notes and invoice-design documentation. The shared library API, invoice version 2 wire format, exact-byte cryptography, interoperability vectors and runtime dependencies are unchanged from 0.1.1.

## Changes

- Added repository discovery of release notes and checks rejecting manual paragraph/list wrapping and explicit Markdown line breaks.
- Retained the published 0.1.0 and 0.1.1 release notes in the repository, with one source line per paragraph or list item.
- Removed donor application module names from installed-package checks; exact wheel/sdist inventories and this repository's development-module import checks remain.
- Recorded the agreed five-field invoice design, the exact JSON example and consumer responsibilities. The planned format is not implemented in this release; key encoding, asset forms, numeric bounds and domain bytes remain open. The future breaking release has its own draft note.
- Recorded design and working notes as .txt files and completed two independent QA/QC passes on the design documentation.

## Installation and qualification

Use the wheel and sha256.json from the tagged release, verify the recorded artifact hash and install offline through the consuming application's maintained workflow. Runtime dependency remains cryptography==50.0.2.

Publication requires the maintained offline container build, lint, repository and invoice campaigns, and source-free installations of the original wheel and the wheel rebuilt from the sdist. The publisher verifies downloaded draft artifacts before publication. Build/test logs accompany the release. These checks qualify the existing version 2 package; they do not qualify the planned five-field format or a consumer deployment.
