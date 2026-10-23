# pay-to-play-wire

`wire` is a Python package for creating, reading and verifying signed service invoices, PayToPlay/2 payment vouchers and signed purchase acceptances. Installing it includes all three formats and their Pydantic adapters. Applications supply trusted keys and decide whether to accept a purchase, perform a service or transfer funds.

**Using the package:** start with the [user guide and runnable examples](https://numpde.github.io/pay-to-play-wire/) ([source](docs/index.md)). This README describes how to develop, test and publish the repository.

## Development

Run `make help` to list supported commands. It needs no Docker image or installed Python dependencies. All project Python, lint, tests and packaging run inside the maintained containers. The host runs Make, shell commands, Docker and Git.

The supported environment is Linux amd64 with a local Docker engine at `unix:///var/run/docker.sock`, BuildKit and container-init support. Run as a user whose UID and GID are both nonzero. The exact Python base image pinned in [the Dockerfile](containers/wire/Dockerfile) must already be present in that engine. If it is missing, acquire that exact image through your explicit image-acquisition workflow before continuing; these Make commands do not pull it.

Prepare dependencies and the development image in separate steps:

```sh
make prerequisites/check
# Review the exact package versions in requirements/wire.lock for advisories.
# Replace eth0 with an existing interface; Make requires this argument explicitly.
make dependencies/download NETWORK_INTERFACE=eth0
make dependencies/check
make build/image
make build/verify
```

| Step | What it establishes |
| --- | --- |
| `prerequisites/check` | Required host tools, selected engine and pinned base image are available |
| `dependencies/download` | Locked dependency wheels and the declared Make package are acquired into an owned staging directory |
| `dependencies/check` | The current downloaded files match their recorded hashes, checked offline |
| `build/image` | The copied build inputs and dependency bytes produce the development image offline |
| `build/verify` | The prepared image runs with the expected user, mounts, network and resource restrictions |

Review advisories before installing package versions into an image or environment; a matching hash proves which bytes were obtained, not that they have no vulnerabilities. The runtime dependency lock is [requirements/runtime.lock](requirements/runtime.lock); the development image also includes test and build tools listed in [requirements/wire.lock](requirements/wire.lock).

Ordinary checks use the prepared image without network access. They never download dependencies, rebuild images or update locks implicitly. Source and root filesystems are read-only; tests run as the calling user, with no effective Linux capabilities, no new privileges and bounded resources. Credentials, private checkout state and engine sockets are excluded. These containers share the host kernel; their restrictions are checked by the repository tests.

## Build and check a candidate

```sh
make package/build
make test
```

`package/build` writes one wheel, one source distribution, `source.json` and `sha256.json` into `.work/dist/`. That directory must be empty before a build. Retain or move earlier output explicitly before rebuilding.

`make test` runs lint, repository checks, invoice, voucher and acceptance tests, and installed-package checks. It consumes the previously built artifacts. Focused commands are:

```sh
make lint/check
make test/repository
make test/invoice/normative
make test/invoice/adversarial
make test/invoice/integration
make test/voucher
make test/acceptance
make test/package
make vectors/show
```

The protocol tests exercise valid messages and distinct rejection cases. The repository tests check the actual Make workflows and run every Python example in the user guide, in order. `vectors/show` prints invoice and acceptance inputs and expectations for inspection; it does not rewrite fixtures.

`test/package` checks the built distributions without mounting the source package. It verifies their bytes, rebuilds a wheel from the source distribution offline, then installs each wheel in a separate fresh environment. Each installation must supply all three formats and their Pydantic adapters using the ordinary `wire` requirement, without extras. Checks cover dependencies, import locations, metadata, installed test vectors, signing, verification and serialization. A separate process blocks Ethereum imports while parsing vouchers and acceptances and verifying acceptance signatures. The complete installation still includes the Ethereum dependencies; only voucher cryptographic operations load them.

`source.json` records the paths and hashes copied before the build backend runs. Distribution contents are compared against that record: omitting the same file from both archives cannot pass merely because the two archives agree. `sha256.json` records hashes of the wheel, source distribution and source inventory.

Repository checks also validate the historical `notes/*_release_v*.md` records. Each paragraph or list item in those files stays on one source line, with blank lines separating blocks. Code fences retain their own line breaks.

## Publish a release or the documentation

These are separate operations. Both require a clean checkout and use the GitHub repository named by `origin`'s sole push URL. Git URL rewrite rules that could redirect that destination are rejected. GitHub authentication stays in host orchestration and never enters package containers.

### Package release

Set the next version in `pyproject.toml` and commit the candidate. Supply its matching tag explicitly; the following uses a placeholder that must be replaced:

```sh
make publish/release TAG=vX.Y.Z
```

The publisher captures committed `HEAD`, builds the distributions and runs all checks against that frozen source. It then pushes the matching tag, uploads a draft release, downloads every artifact and qualification log, and compares the downloaded bytes with the checked files. Only a matching draft is made public.

An existing release is rejected and published assets are never replaced. A release tag alone does not prove byte identity; consumers should retain the source revision and verify the actual wheel hash. The release includes the artifacts and logs needed to inspect those identities.

### GitHub Pages

Commit documentation changes on `main`, then run:

```sh
make publish/pages
```

This pushes `HEAD`, configures Pages for `main/docs` and waits for the live HTTPS page to report that exact source revision. A changed source or configuration triggers a build; an unchanged publication requests a rebuild. The wait has a ten-minute deadline, and individual API requests have shorter deadlines. A queued build or request timeout does not establish that the new guide is live.

If either publisher fails, it reports retained inputs, logs and API receipts under `.work/publication.*`. Inspect those records and confirm process/container cleanup before retrying. Some external steps may already have completed; failure is not permission to overwrite an existing release or discard uncertain state.

## Source and historical evidence

[AGENTS.md](AGENTS.md) defines repository responsibilities and working rules. [The consolidation record](notes/010_wire_consolidation.txt) identifies copied implementations, donor revisions and adaptations. [The default-installation record](notes/014_complete_default_installation.txt) records the complete package decision. [The acceptance v2 release record](notes/018_release_v0.8.0.md) describes the authenticated signer field and the incompatible profile change. Earlier notes describe their own revisions and historical releases; they do not establish that a consumer has adopted or deployed the current package.
