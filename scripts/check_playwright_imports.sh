#!/bin/bash

# Check for playwright/patchright imports in notte packages
# Only playwright_async_api.py should import these packages to maintain separation

# Packages to check for forbidden playwright imports
packages_to_check=("notte-core" "notte-sdk")

# Forbidden import patterns
forbidden_patterns=("playwright" "patchright")

found_violations=false

for package_dir in "${packages_to_check[@]}"; do
    for forbidden_pattern in "${forbidden_patterns[@]}"; do
        # Check for imports, excluding playwright_async_api.py
        violations=$(grep -r "from $forbidden_pattern\|import $forbidden_pattern" "packages/$package_dir/" --include="*.py" --include="*.pyi" --exclude="playwright_async_api.py")
        if [ ! -z "$violations" ]; then
            echo "ERROR: $forbidden_pattern imports found in $package_dir:"
            echo "$violations"
            found_violations=true
        fi
    done
done

# Check that playwright/patchright imports only exist in playwright_async_api.py files
echo "Checking that playwright/patchright imports are only in playwright_async_api.py files..."

# Search for playwright/patchright imports in all notte packages
all_packages=("notte-core" "notte-sdk" "notte-browser" "notte-agent" "notte-integrations" "notte-eval" "notte-mcp")

for package_dir in "${all_packages[@]}"; do
    for forbidden_pattern in "${forbidden_patterns[@]}"; do
        # Find all python files with playwright/patchright imports
        files_with_imports=$(grep -r -l "from $forbidden_pattern\|import $forbidden_pattern" "packages/$package_dir/" --include="*.py" --include="*.pyi" 2>/dev/null || true)

        if [ ! -z "$files_with_imports" ]; then
            # Check if all files are playwright_async_api.py
            for file in $files_with_imports; do
                if [[ ! "$file" =~ playwright_async_api\.py$ ]]; then
                    echo "ERROR: $forbidden_pattern import found in non-playwright_async_api.py file: $file"
                    found_violations=true
                fi
            done
        fi
    done
done

if [ "$found_violations" = true ]; then
    echo ""
    echo "Playwright/patchright imports should only be used in playwright_async_api.py files."
    echo "This maintains separation between browser automation libraries and core packages."
    exit 1
fi

echo "✓ No forbidden playwright/patchright imports found"
exit 0
