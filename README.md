# signed-invoice

**[Documentation — GitHub Pages](https://numpde.github.io/signed-invoice/)** · [Documentation source](docs/index.md)

Development and operations for the Python merchant-invoice library. Protocol,
API and consumer guidance live in the documentation above.

## Development

Use `make help` for the maintained commands. It works without Docker or
dependencies. Project Python, lint, tests, image builds and packaging run in
containers; the host runs Make, shell orchestration and Git.

The supported engine is Docker on Linux amd64 at
`unix:///var/run/docker.sock`, with BuildKit and container-init support. Run as
a nonzero user and group. The digest-pinned base image must already be available
locally; these commands never pull an image implicitly.

```sh
make prerequisites/check
# Choose an existing network interface explicitly; eth0 is an example.
make dependencies/download NETWORK_INTERFACE=eth0
make dependencies/check
make build/image
make build/verify
make package/build
make test
```

Downloads receive the declared dependency inputs and an owned staging directory.
Verification hashes actual current files. Image builds capture the declared
inputs and dependencies, verify those captured bytes offline, then admit the
observed image ID and input label. Refresh dependencies and images explicitly;
ordinary checks never download, build or update locks.

Tests run without network, as the calling user, with read-only source/root,
dropped capabilities, no new privileges and bounded CPU, memory, processes and
temporary storage. Private checkout state, credentials and the engine socket
are excluded. These are ordinary containers sharing the host kernel.

## Focused checks

```sh
make lint/check
make test/repository
make test/invoice/normative
make test/invoice/adversarial
make test/invoice/integration
make test/package
```

`test/package` consumes previously built artifacts without mounting source. It
captures and verifies the artifact bytes, rebuilds a wheel from the sdist offline,
and checks both wheels in a fresh contained environment. The checks cover import
origin, metadata, dependencies, payload, resources and cryptographic operations.

## Artifacts and releases

`make package/build` writes one wheel, one sdist and `sha256.json` to
`.work/dist/`. It requires an empty output directory. Retain or move previous
artifacts explicitly before rebuilding. Failed operations report retained
evidence; confirm owned-process/container cleanup before retrying.

GitHub tags name releases. Consumers pin the source commit and verify the actual
wheel hash; a tag name alone does not make bytes immutable. Release assets allow
explicit acquisition followed by an offline, hash-locked installation.
Keep acquisition credentials out of dependency images, layers and runtime.

Pages content lives in `docs/`. Repository instructions are in `AGENTS.md`;
source provenance and validation records are in `notes/001_extraction.txt`.
