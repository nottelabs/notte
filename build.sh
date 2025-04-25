#!/bin/bash

# Updates the package version in pyproject.toml files
update_package_version() {
    local version=$1
    local file=$2
    local pattern="s/0.0.dev/$version/g"

    if [[ ! -f "$file" ]]; then
        echo "Error: File $file not found"
        exit 1
    fi

    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS (BSD) version
        sed -i '' "$pattern" "$file" || {
            echo "Error: Failed to update version in $file"
            exit 1
        }
    else
        # Linux/GNU version
        sed -i "$pattern" "$file" || {
            echo "Error: Failed to update version in $file"
            exit 1
        }
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
