echo "Building root notte package"
uv build
for package in $(ls packages); do
    echo "Building $package"
    cd packages/$package
    uv build
    cd ../../
done
