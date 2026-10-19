# signed-invoice

Own the shared invoice wire grammar, exact-byte hash/signature/envelope
rules and pure payment-route comparison. Applications own key trust, product
schemas, persistence, consent, admission, fulfillment and settlement.

Copy established owners from the recorded source repositories before inventing replacements.
Record the source revision and deliberate adaptations. Preserve original bytes
and distinct rejection scenarios. Applications supply the trusted signing domain
explicitly; never add a branded default, infer it from an invoice or add delimiters.

Make is the supported interface; help is the default and needs no prerequisites.
Run all project Python, lint, tests, builds and packaging inside the maintained
containers. The host edits by hand and orchestrates shell/engine/Git operations.
No host venv, pip, unittest, Ruff or build fallback and no fake container marker.
Tests never acquire dependencies, build images or update locks implicitly.

Keep acquisition, offline verification, image builds, package builds and tests
explicit. Downloads require a command-line NETWORK_INTERFACE. Review exact package
advisories before installation; verify actual locked bytes offline. Ordinary
lanes use immutable prepared images, no network, nonroot caller identity,
read-only exact inputs/root, dropped capabilities, no new privileges and bounded
resources. Do not mount credentials, engine sockets, private checkout state or
devices. Validate paths/ownership and retain evidence when cleanup is uncertain.

Use src/signed_invoice; tests/invoice for normative/adversarial/integration
campaigns, tests/repository for actual workflow policy and tests/helpers for
reusable setup. Add categories only when populated. Shared interoperability
vectors are package data under src/signed_invoice/vectors so installed consumers
can read the same authoritative files without copying fixtures.

Use unittest and assertEqual(expected, observed). Prove both successful reachability
and each distinct unsafe input rejection. Source and recorded argv are separate
from live posture and installed-artifact proof. Consumer compatibility requires
declared immutable inputs; source inspection is not runtime or deployment proof.

Keep errors direct and safe: InvoiceError for protocol failures, TypeError for
wrong API argument types. Let key/backend failures propagate. Preserve unrelated
work. Edit by hand with patches; do not run ad hoc file-rewriting scripts.
Commit coherent slices with explicit paths after --. Never edit consumer repos
without their own authorization. No empty targets, skips or expected failures
that conceal missing proof.
