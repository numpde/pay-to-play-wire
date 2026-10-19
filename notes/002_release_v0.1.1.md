# 0.1.1

Maintenance release for package publication, documentation and regression checks.
The shared library API, invoice version 2 wire format, signing rules and runtime
dependency are unchanged from 0.1.0.

## Changes

- Added separate `make publish/release TAG=vX.Y.Z` and `make publish/pages`
  commands. Release publication qualifies a frozen committed source snapshot,
  verifies downloaded draft assets against the installed-artifact receipts,
  and publishes the verified draft.
- Bound publication to the inspected GitHub repository. Matching Git URL
  rewrite rules are rejected before publication to prevent a second rewrite
  from changing the push destination.
- Stopped publication immediately when the native process owner cannot confirm
  process retirement. An HTTP 404 cannot override that uncertainty.
- Added offline regression checks for URL routing and uncertain retirement.
- Made installed-artifact metadata checks follow the package version declared
  in the source distribution.
- Added Pages deployment verification against the exact live source revision
  and avoided duplicate build requests after source/configuration changes.
- Expanded installation and API documentation; the root README focuses on
  development and operations and links prominently to Pages.

Source: `74339b5fc243760ae39fbbc08ae88eafe449309a`.

## Installation input

```text
signed-invoice @ https://github.com/numpde/signed-invoice/releases/download/v0.1.1/signed_invoice-0.1.1-py3-none-any.whl#sha256=08d1635413d0ceeb6d3985b10b037cac5589c6e54e6c2dc1dd50d931e910a38a
```

Download the declared artifact during dependency acquisition, verify its hash
and install offline. Runtime dependency: `cryptography==50.0.2`.

The accompanying `sha256.json` records the exact wheel and sdist hashes.

## Qualification

Built from the clean source revision above on Linux amd64, Python 3.12.12,
using the repository's offline containers. `make test` passed: Ruff, 33 repository
checks, 46 invoice tests, and fresh source-free installations of the original
wheel and the wheel rebuilt from the sdist. Build and test logs accompany the
release. Downloaded draft assets were verified before publication.
Other interpreter/platform combinations were not executed.

Consumer integrations require their own runtime checks for this pinned release.
[Documentation](https://numpde.github.io/signed-invoice/) is published through
GitHub Pages from `docs/` on the main branch.
