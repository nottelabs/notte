# Notte SDK Makefile


.PHONY: install sdk generate release tests example check help

# Default target
help:
	@echo "Available commands:"
	@echo "  make install     - Install dependencies and generate SDK"
	@echo "  make sdk         - Generate SDK from OpenAPI spec (alias: make generate)"
	@echo "  make check       - Check if SDK is up to date with staging"
	@echo "  make release <version> - Dry-run a release build (publishing happens in CI on a vX.Y.Z tag)"
	@echo "  make tests       - Run all tests"
	@echo "  make example <filename> - Run example file (e.g., make example persona)"
	@echo ""
	@echo "Available examples:"
	@echo "  - agent"
	@echo "  - persona"
	@echo "  - vault"

# Install dependencies and generate SDK
install:
	@echo "Installing dependencies..."
	npm install
	@echo "Generating SDK..."
	npm run generate

# Generate SDK from OpenAPI specification
sdk generate:
	@echo "Generating SDK from OpenAPI spec..."
	npm run generate

# Check if SDK is up to date with staging
check:
	@echo "Checking if SDK is up to date with staging..."
	npm run check:staging

# Dry-run a release build at a given version, then restore the dev version.
# Publishing happens in CI (.github/workflows/node-sdk-publish.yml) when a
# vX.Y.Z tag is pushed, together with the Python packages.
release:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Error: No version specified. Usage: make release <version>"; \
		echo "Example: make release 1.9.0"; \
		exit 1; \
	fi
	@echo "Building notte-sdk version: $(filter-out $@,$(MAKECMDGOALS))"
	npm version "$(filter-out $@,$(MAKECMDGOALS))" --no-git-tag-version
	npm run build
	node scripts/check-package.js
	npm pack --dry-run
	@git checkout package.json package-lock.json

# Run all tests
tests:
	@echo "Running tests..."
	npm run test:unit -- --run

# Run example file
example:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make example <filename>"; \
		echo "Available examples: agent, persona, vault"; \
		exit 1; \
	fi
	@EXAMPLE_FILE="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -f "examples/$$EXAMPLE_FILE.ts" ]; then \
		echo "Error: examples/$$EXAMPLE_FILE.ts not found"; \
		echo "Available examples: agent, persona, vault"; \
		exit 1; \
	fi; \
	echo "Running example: $$EXAMPLE_FILE"; \
	npx tsx -r dotenv/config examples/$$EXAMPLE_FILE.ts

# Allow make to accept arguments for the example command
%:
	@:
