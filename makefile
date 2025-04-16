ifneq ("$(wildcard .env)","")
  include .env
  export $(shell sed 's/=.*//' .env)
endif

.PHONY: test
test:
	@uv run pytest tests

.PHONY: test-cicd
test-cicd:
	uv run pytest tests --ignore=tests/integration/test_resolution.py --ignore=tests/integration/test_webvoyager_resolution.py --ignore=tests/browser/test_pool.py --ignore=tests/integration/test_e2e.py --ignore=tests/integration/test_webvoyager_scripts.py --durations=10

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

.PHONY: release
release:
	@echo "resetting to latest remote..."
	@git pull && git reset --hard origin/main
	@echo "re-installing package..."
	@make install
	@echo "starting release process..."
	@if [ "$$(git symbolic-ref --short HEAD)" != "main" ]; then \
		echo "not on main branch, please switch to main first"; \
		exit 1; \
	fi
	@VERSION="$(wordlist 2,2,$(MAKECMDGOALS))" && if [ -z "$$VERSION" ]; then \
		echo "no VERSION provided, auto-incrementing patch version..."; \
		OLD_VERSION=$$(uv version | awk '{print $$2}'); \
		MAJOR=$$(echo $$OLD_VERSION | cut -d. -f1); \
		MINOR=$$(echo $$OLD_VERSION | cut -d. -f2); \
		PATCH=$$(echo $$OLD_VERSION | cut -d. -f3); \
		VERSION=$$MAJOR.$$MINOR.$$((PATCH + 1)); \
		echo "auto-incremented version to $$VERSION"; \
	else \
		echo "updating version to $$VERSION..."; \
	fi && \
	uv version $$VERSION && \
	echo "creating and pushing git tag..." && \
	git add pyproject.toml uv.lock requirements.txt && \
	git commit -m "release version v$$VERSION" && \
	git tag -a v$$VERSION -m "Release version v$$VERSION" && \
	git push origin main && git push origin v$$VERSION
