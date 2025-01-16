ifneq ("$(wildcard .env)","")
  include .env
  export $(shell sed 's/=.*//' .env)
endif

.PHONY: test
test:
	@poetry run pytest tests

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
	@rm -f poetry.lock
	@poetry install --with dev
	@poetry export --without-hashes -f requirements.txt -o requirements.txt

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
	@if [ -z "$$VERSION" ]; then \
	    echo "no VERSION provided, auto-incrementing patch version..."; \
	    OLD_VERSION=$$(poetry version | awk '{print $$2}'); \
	    MAJOR=$$(echo $$OLD_VERSION | cut -d. -f1); \
	    MINOR=$$(echo $$OLD_VERSION | cut -d. -f2); \
	    PATCH=$$(echo $$OLD_VERSION | cut -d. -f3); \
	    VERSION=$$MAJOR.$$MINOR.$$((PATCH + 1)); \
	    echo "auto-incremented version to $$VERSION"; \
	    poetry version $$VERSION; \
		echo "creating and pushing git tag..."; \
		git add pyproject.toml poetry.lock requirements.txt; \
		git commit -m "release version v$$VERSION"; \
		git tag -a v$$VERSION -m "Release version v$$VERSION"; \
		git push origin main ; \
		git push origin v$$VERSION; \
	else \
	    echo "updating version to $$VERSION..."; \
	    poetry version $$VERSION; \
		echo "creating and pushing git tag..."; \
		git add pyproject.toml poetry.lock requirements.txt; \
		git commit -m "release version v$$VERSION"; \
		git tag -a v$$VERSION -m "Release version v$$VERSION"; \
		git push origin main ; \
		git push origin v$$VERSION; \
	fi
