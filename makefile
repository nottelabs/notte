ifneq ("$(wildcard .env)","")
  include .env
  export $(shell sed 's/=.*//' .env)
endif

.PHONY: test
test:
	@uv run pytest tests

.PHONY: test-cicd
test-cicd:
	uv run pytest tests --ignore=tests/integration/test_webvoyager_resolution.py --ignore=tests/integration/test_e2e.py --ignore=tests/integration/test_webvoyager_scripts.py --ignore=tests/examples/test_examples.py --ignore=tests/examples/test_readme.py --durations=10

.PHONY: test-sdk
test-sdk:
	uv run pytest tests/sdk
	uv run pytest tests/integration/sdk

.PHONY: test-docs
test-docs:
	uv run pytest tests/docs

.PHONY: test-agent
test-agent:
	uv run pytest tests/agent
	uv run pytest tests/integration/sdk/test_vault.py

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

.PHONY: benchmark
benchmark:
	cat benchmarks/benchmark_config.toml | uv run python -m notte_eval.run

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


.PHONY: mcp
mcp:
	uv run python -m notte_mcp.server

.PHONY: mcp-install-claude
mcp-install-claude:
	uv run fastmcp install packages/notte-mcp/src/notte_mcp/server.py -f .env

.PHONY: profile-imports
profile-imports:
	uv run python profiling/profile_imports.py


.PHONY: docs-sdk
docs-sdk:
	cd docs && uv run sphinx-build -b mdx sphinx _build


.PHONY: docs
docs:
	cd docs/src && mint dev


.PHONY: docs-test
docs-test:
	cd docs/src && sh test.sh
