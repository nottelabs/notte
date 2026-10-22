ifneq ("$(wildcard .env)","")
  include .env
  export $(shell sed 's/=.*//' .env)
endif

# The test selections below are the single source of truth: .github/workflows/test-cicd.yml runs
# `make test-cicd` (the offline unit gate) and `make test-live` (Notte API + third-party sites).
# Markers are declared in pyproject.toml; tests/integration/conftest.py marks that directory by path.
# The README and examples suites run nightly (nightly-examples.yml), never in these targets.
PYTEST_IGNORE := --ignore=tests/examples/test_examples.py --ignore=tests/examples/test_readme.py
PYTEST_UNIT := uv run pytest -n logical tests -m "not staging and not live" $(PYTEST_IGNORE)
PYTEST_LIVE := uv run pytest -n logical tests -m "staging or live" $(PYTEST_IGNORE)

# Offline: needs a local browser, no secrets and no network beyond localhost.
.PHONY: test
test:
	$(PYTEST_UNIT)

.PHONY: test-cicd
test-cicd:
	$(PYTEST_UNIT) --durations=10 --junitxml=pytest.xml --cov-report=term-missing:skip-covered --cov=packages

# Needs NOTTE_API_KEY (and NOTTE_API_URL for staging) plus internet access. Live sites are flaky by
# nature, so failures are retried; tests with their own @pytest.mark.flaky keep their own count.
.PHONY: test-live
test-live:
	$(PYTEST_LIVE) --reruns 2 --reruns-delay 5 --durations=10

.PHONY: test-sdk
test-sdk:
	uv run pytest -n 3 tests/integration/sdk
	uv run pytest -n logical tests/sdk

.PHONY: test-docs
test-docs:
	uv run pytest -n logical tests/docs

.PHONY: test-sdk-staging
test-sdk-staging:
	@echo "Testing SDK with staging API..."
	$(eval ORIGINAL_NOTTE_API_URL := $(shell grep '^NOTTE_API_URL=' .env 2>/dev/null | cut -d '=' -f2))
	@if grep -q "^NOTTE_API_URL=" .env; then \
		sed -i '' 's|^NOTTE_API_URL=.*|NOTTE_API_URL=https://staging.notte.cc|' .env; \
	else \
		echo "NOTTE_API_URL=https://staging.notte.cc" >> .env; \
	fi
	@echo "Set NOTTE_API_URL=$(NOTTE_API_URL)"
	@$(SHELL) -c "source .env"
	uv run pytest tests/sdk
	uv run pytest tests/integration/sdk
	@if [ -n "$(ORIGINAL_NOTTE_API_URL)" ]; then \
		sed -i '' 's|^NOTTE_API_URL=.*|NOTTE_API_URL=$(ORIGINAL_NOTTE_API_URL)|' .env; \
	else \
		sed -i '' '/^NOTTE_API_URL=/d' .env; \
	fi
	@echo "Restored NOTTE_API_URL=$(ORIGINAL_NOTTE_API_URL)"
	@$(SHELL) -c "source .env"

.PHONY: test-readme
test-readme:
	uv run pytest tests/examples/test_readme.py -k "test_readme_python_code"

.PHONY: test-release
test-release:
	sh scripts/test_release.sh

.PHONY: test-examples
test-examples:
	uv run pytest tests/examples/test_examples.py

.PHONY: pre-commit-run
pre-commit-run:
	uv run --active pre-commit run --all-files

.PHONY: clean
clean:
	@find . -name "*.pyc" -exec rm -f {} \;
	@find . -name "__pycache__" -exec rm -rf {} \; 2> /dev/null
	@find . -name ".pytest_cache" -exec rm -rf {} \; 2> /dev/null
	@find . -name ".mypy_cache" -exec rm -rf {} \; 2> /dev/null
	@find . -name ".ruff_cache" -exec rm -rf {} \; 2> /dev/null
	@find . -name ".DS_Store" -exec rm -f {} \; 2> /dev/null
	@find . -type d -empty -delete

.PHONY: install
install:
	@rm -f uv.lock
	@uv sync --dev --all-extras
	@uv export > requirements.txt

.PHONY: release-cleanup
release-clean:
	@rm -rf dist
	@rm -rf build
	@rm -rf *.egg-info
	@rm -rf .ruff_cache
	@rm -rf .mypy_cache
	@rm -rf .pytest_cache
	@git checkout pyproject.toml uv.lock packages/*/pyproject.toml

.PHONY: profile-imports
profile-imports:
	uv run python profiling/profile_imports.py


.PHONY: docs-sdk
docs-sdk: docs-llms
	cd docs && uv run sphinx-build -b mdx sphinx _build
	rm -rf docs/src/sdk-reference/baseaction
	cd docs/src && uv run python scripts/apply_agent_md_notice.py


.PHONY: docs-llms
docs-llms:
	cd docs/src && uv run python scripts/generate_llms.py

# Rebuild the API section of llms.txt from the live OpenAPI spec. Only the
# refresh-llms workflow should need this; docs-llms reuses the committed section.
.PHONY: docs-llms-refresh
docs-llms-refresh:
	cd docs/src && uv run python scripts/generate_llms.py --refresh-openapi


.PHONY: docs-agent-notice
docs-agent-notice:
	cd docs/src && uv run python scripts/apply_agent_md_notice.py


.PHONY: docs-check
docs-check:
	@if ! git diff HEAD --quiet -- docs || [ -n "$$(git ls-files --others --exclude-standard -- docs)" ]; then \
		echo "\033[0;31mError: docs/ has uncommitted changes or untracked files. Commit or stash them before running docs-check (it would overwrite them).\033[0m"; \
		git --no-pager diff HEAD --stat -- docs; \
		git ls-files --others --exclude-standard -- docs; \
		exit 1; \
	fi
	@$(MAKE) --no-print-directory docs-sdk
	@if ! git diff HEAD --quiet -- docs || [ -n "$$(git ls-files --others --exclude-standard -- docs)" ]; then \
		echo "\033[0;31mError: docs generation produced changes. Run 'make docs-sdk docs-agent-notice' locally and commit the result.\033[0m"; \
		git --no-pager diff HEAD --stat -- docs; \
		git ls-files --others --exclude-standard -- docs; \
		exit 1; \
	fi
	@echo "\033[0;32mdocs are up to date\033[0m"


.PHONY: docs
docs:
	cd docs/src && mint dev


.PHONY: docs-tests
docs-tests:
	cd docs/src && sh tests.sh


# Generate all snippets from testers
.PHONY: sniptest
sniptest:
	cd docs/src && uv run python sniptest/generate.py

# Generate snippets and remove orphans
.PHONY: sniptest-clean
sniptest-clean:
	cd docs/src && uv run python sniptest/generate.py --clean


%:
	@:

.PHONY: release
release:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
			echo "\033[0;31mError: No word specified. Usage: make release <release_tag>\033[0m"; \
			echo "Example: make release 1.6.6"; \
			exit 1; \
	fi
	@echo "\033[0;35mBuilding version: $(filter-out $@,$(MAKECMDGOALS))\033[0m"
	python3 scripts/build_release.py $(filter-out $@,$(MAKECMDGOALS))

# The wire models in notte_core.types are the source of truth; openapi/openapi.json is the API's
# rendering of them. See docs/design/openapi-contract.md.
.PHONY: openapi-check
openapi-check:
	uv run --no-sync python scripts/openapi_contract.py --check

# Refresh the snapshot from staging (override with OPENAPI_URL=https://api.notte.cc).
OPENAPI_URL ?= https://us-staging.notte.cc
.PHONY: openapi-fetch
openapi-fetch:
	uv run --no-sync python scripts/openapi_contract.py --fetch --url $(OPENAPI_URL)

# Release gate: production must serve the wire models we are about to publish, and every
# operation the Python SDK calls (method, path, parameters, models) as the snapshot describes it.
.PHONY: openapi-check-prod
openapi-check-prod:
	uv run --no-sync python scripts/openapi_contract.py --check --against https://api.notte.cc
	uv run --no-sync python scripts/generate_sdk_endpoints.py --check --against https://api.notte.cc

# The Python SDK's endpoint layer (notte_sdk/_generated/endpoints.py) is generated from the
# snapshot. See docs/design/sdk-generated-endpoints.md.
.PHONY: sdk-endpoints
sdk-endpoints:
	uv run --no-sync python scripts/generate_sdk_endpoints.py

.PHONY: sdk-endpoints-check
sdk-endpoints-check:
	uv run --no-sync python scripts/generate_sdk_endpoints.py --check

# SDK-owned models, side by side with the existing public API during migration.
.PHONY: sdk-codegen sdk-codegen-check
sdk-codegen:
	uv run --no-sync python scripts/generate_sdk_models.py
	uv run --no-sync python scripts/generate_sdk_endpoints.py

sdk-codegen-check:
	uv run --no-sync python scripts/generate_sdk_models.py --check
	uv run --no-sync python scripts/generate_sdk_endpoints.py --check

# One reviewed contract update for both SDKs. Install uv and npm dependencies first.
.PHONY: openapi-refresh sdk-generate-all node-sdk-codegen
openapi-refresh:
	$(MAKE) openapi-fetch
	$(MAKE) -k sdk-generate-all

# Keep independent generators running even if one reports an incompatible contract;
# make still exits non-zero if any of them failed. sdk-codegen includes sdk-endpoints.
sdk-generate-all: sdk-codegen node-sdk-codegen

node-sdk-codegen:
	cd node-sdk && npm run generate && npm run docs:generate
