#!/bin/bash

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

# uvx --from=toml-cli toml set --toml-path=pyproject.toml project.version $version
echo "Building root notte package version==$version"
sed -i '' "s/0.0.dev/$version/g" pyproject.toml
uv build
for package in $(ls packages); do
    echo "Building $package==$version"
    cd packages/$package
    sed -i '' "s/0.0.dev/$version/g" pyproject.toml
    uv build
    cd ../../
done

publish=$2
if [ "$publish" == "publish" ]; then
    echo "Publishing packages"
    uv run twine upload --skip-existing --repository pypi dist/* -u __token__ -p $UV_PUBLISH_TOKEN
fi
