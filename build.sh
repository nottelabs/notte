#!/bin/bash

# Updates the package version in pyproject.toml files
update_package_version() {
    local version="$1"
    local file="$2"

    if [[ ! -f "$file" ]]; then
        echo "Error: File $file not found"
        exit 1
    fi

    # Use Perl and capture how many substitutions happened
    local replacements
    replacements=$(perl -i -pe '
        BEGIN { our $count = 0 }
        $count += s/[0-9]+\.[0-9]+\.[0-9]+\.dev/'"$version"'/g;
        END { print STDERR "$count\n" }
    ' "$file" 2>&1 >/dev/null)

    if [[ "$replacements" -eq 0 ]]; then
        echo "Error: No occurrences of version pattern found in $file"
        exit 1
    fi
}

# usage: bash build.sh <version>
# Or with publish if you want to publish to pypi directly
# usage: bash build.sh <version> publish
version=$1
if [ -z "$version" ]; then
    echo "Usage: $0 <version> (e.g. last 1.3.5)"
    exit 1
fi

echo "Cleaning dist..."
rm -rf dist

echo "Building root notte package version==$version"
update_package_version "$version" pyproject.toml
uv build
for package in $(ls packages); do
    # skip notte-bua
    if [ "$package" == "notte-bua" ]; then
        continue
    fi

    echo "Building $package==$version"
    cd packages/$package
    update_package_version "$version" pyproject.toml
    uv build
    cd ../../
done

publish=$2
if [ "$publish" == "publish" ]; then
    echo "Publishing packages"
    uv run twine upload --skip-existing --repository pypi dist/* -u __token__ -p $UV_PUBLISH_TOKEN
fi
