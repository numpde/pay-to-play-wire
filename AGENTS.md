# pay-to-play-wire

Own invoice and purchase-acceptance JWS and fixed PayToPlay/2 voucher wire profiles, their parsing,
signing, verification and installed interoperability vectors. Applications own
payment-route qualification, key trust and registered signer authorization, product
schemas, persistence, consent, admission, fulfillment and settlement.

Copy established owners from the recorded source repositories before inventing replacements.
Record the source revision and deliberate adaptations. Preserve original bytes
and distinct rejection scenarios. Require the fixed Ed25519 JWS protected profile;
applications supply trusted provider keys and own their authorization. Preserve
carried segments and hash the complete compact signed artifact. No legacy domains.
Voucher verification requires a caller-supplied trusted deployment domain and
signer. Preserve the EIP-712 ordered schema, digest and contract signature rules.
No RPC, key registry, secret custody or purchase policy belongs in this package.
Acceptance v2 carries exactly signer, the full signed voucher and acceptedAt signing Unix seconds.
signer is the canonical raw32 Ed25519 public key encoded as unpadded base64url.
Signing requires equality with the private key's public key; verification requires
equality with the caller-supplied trusted key. Carry identity on wire rather than
requiring a separate saved key or database lookup; trust remains application-owned.
No opaque signer selector or acceptance hash. Reject the old acceptance profile.
Structural voucher parsing must not import Ethereum backends. Applications own
historical voucher-signer authority, fulfillment and all later status policy.

Make is the supported interface; help is the default and needs no prerequisites.
Run all project Python, lint, tests, builds and packaging inside the maintained
containers. The host edits by hand and orchestrates shell/engine/Git operations.
No host venv, pip, unittest, Ruff or build fallback and no fake container marker.
Tests never acquire dependencies, build images or update locks implicitly.

Publish GitHub releases and Pages through their separate Make targets. Release
qualification runs against a frozen committed source snapshot; verify downloaded
draft assets before making a release public and never replace published assets.
Pages publication must verify the live source revision. Keep GitHub credentials
in host orchestration, outside source snapshots and package containers.

Keep acquisition, offline verification, image builds, package builds and tests
explicit. Downloads require a command-line NETWORK_INTERFACE. Review exact package
advisories before installation; verify actual locked bytes offline. Ordinary
lanes use immutable prepared images, no network, nonroot caller identity,
read-only exact inputs/root, dropped capabilities, no new privileges and bounded
resources. Do not mount credentials, engine sockets, private checkout state or
devices. Validate paths/ownership and retain evidence when cleanup is uncertain.

Use src/wire/invoice, src/wire/voucher and src/wire/acceptance; their matching tests directories hold normative/adversarial/integration
campaigns, tests/repository for actual workflow policy and tests/helpers for
reusable setup. Add categories only when populated. Shared interoperability
vectors are package data under src/wire/vectors so installed consumers
can read the same authoritative files without copying fixtures.

Write design and working notes as .txt files under notes/.

Use unittest and assertEqual(expected, observed). Prove both successful reachability
and each distinct unsafe input rejection. Source and recorded argv are separate
from live posture and installed-artifact proof. Consumer compatibility requires
declared immutable inputs; source inspection is not runtime or deployment proof.

Keep errors direct and safe: InvoiceError for invoice, AcceptanceError for acceptance and
ValueError for voucher protocol failures; preserve the qualified TypeError API
contracts and deliberate backend failure translations. Preserve unrelated
work. Edit by hand with patches; do not run ad hoc file-rewriting scripts.
Commit coherent slices with explicit paths after --. Never edit consumer repos
without their own authorization. No empty targets, skips or expected failures
that conceal missing proof.
