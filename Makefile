override SHELL := bash
override .SHELLFLAGS := -eu -o pipefail -c
override .DEFAULT_GOAL := help

unexport NETWORK_INTERFACE
override export NETWORK_INTERFACE_INPUT := $(if $(filter command line,$(origin NETWORK_INTERFACE)),$(value NETWORK_INTERFACE))
unexport TAG
override export PUBLISH_TAG_INPUT := $(if $(filter command line,$(origin TAG)),$(value TAG))

.PHONY: help prerequisites/check dependencies/download dependencies/check build/image build/verify package/build publish/release publish/pages test test/repository test/invoice test/invoice/normative test/invoice/adversarial test/invoice/integration test/package lint/check

help:
	@printf '%s\n' \
	  'prerequisites/check        Check host tools, identity and the selected Docker engine.' \
	  'dependencies/download    Acquire locked wheels; requires NETWORK_INTERFACE=<name>.' \
	  'dependencies/check       Verify current local wheel bytes offline.' \
	  'build/image              Build the tool image offline from captured inputs.' \
	  'build/verify             Verify the prepared image and live containment.' \
	  'package/build            Build wheel and sdist offline into .work/dist.' \
	  'publish/release          Qualify and publish a GitHub release; requires TAG=vX.Y.Z.' \
	  'publish/pages            Push main, deploy docs/ and verify the live source revision.' \
	  'test                     Run all self-contained checks using prepared inputs.' \
	  'test/repository          Check the actual repository workflows and containment.' \
	  'test/invoice             Run all invoice behavior campaigns.' \
	  'test/invoice/normative   Check valid invoices and exact asset routes.' \
	  'test/invoice/adversarial Check malformed documents and cryptographic rejection.' \
	  'test/invoice/integration Check detached signing and envelope composition.' \
	  'test/package             Check installed wheel/sdist artifacts without source mounts.' \
	  'lint/check               Check Python lint and formatting without writing.'

test: lint/check test/repository test/invoice test/package

test/repository test/invoice test/invoice/normative test/invoice/adversarial test/invoice/integration test/package lint/check prerequisites/check build/verify package/build:
	bash tools/ops/invoice.sh $@

dependencies/download:
	bash tools/ops/invoice.sh download

dependencies/check:
	bash tools/ops/invoice.sh check

build/image:
	bash tools/ops/invoice.sh build

publish/release publish/pages:
	bash tools/ops/publish.sh $@
