#!/bin/bash
set -euo pipefail

# usage: bash build.sh <version>
# Or with publish if you want to publish to pypi directly
# usage: bash build.sh <version> publish
version=${1:-}
if [ -z "$version" ]; then
    echo "Usage: $0 <version> (e.g. last 1.3.5)"
    exit 1
fi

# Validate every package before modifying files or building any distributions.
python3 scripts/release_version.py release "$version"
version=${version#v}

echo "Cleaning dist..."
rm -rf dist

echo "Building root notte package version==$version"
uv build
for package in packages/*; do
    echo "Building $package==$version"
    cd "$package"
    uv build
    cd ../../
done

publish=${2:-}
if [ "$publish" == "publish" ]; then
    echo "Publishing packages"
    uv publish \
        --check-url https://pypi.org/simple \
        dist/*
fi
