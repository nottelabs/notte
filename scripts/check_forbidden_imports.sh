#!/bin/bash

# Check for forbidden imports in notte packages
# Core packages should not depend on other notte packages to avoid circular dependencies

# Packages to check for forbidden imports
packages_to_check=("notte-core" "notte-sdk")

# Forbidden packages that should not be imported
forbidden_packages=("notte_browser" "notte_agent")

found_violations=false

for package_dir in "${packages_to_check[@]}"; do
    for forbidden_package in "${forbidden_packages[@]}"; do
        # Check for actual import statements, not just string occurrences
        # Look for: import forbidden_package, from forbidden_package import, import forbidden_package.something
        if grep -r -E "^[[:space:]]*(import[[:space:]]+${forbidden_package}([[:space:]]*$|[[:space:]]*\.|[[:space:]]*,)|from[[:space:]]+${forbidden_package}([[:space:]]*$|[[:space:]]*\.|[[:space:]]+import))" "packages/$package_dir/" --include="*.py" --include="*.pyi"; then
            echo "ERROR: $forbidden_package imports found in $package_dir"
            found_violations=true
        fi
    done
done

if [ "$found_violations" = true ]; then
    echo "This creates dependency issues. Please remove these imports."
    exit 1
fi

echo "✓ No forbidden imports found in checked packages"
exit 0
