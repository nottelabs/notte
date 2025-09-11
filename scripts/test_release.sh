#!/bin/bash
set -euo pipefail
export NOTTE_RELEASE_TEST_API_KEY_BKP=$NOTTE_RELEASE_TEST_API_KEY

# Unset all variables from current .env file if it exists
if [ -f .env ]; then
    while IFS= read -r line; do
        # Skip empty lines and comments
        if [[ ! -z "$line" && ! "$line" =~ ^[[:space:]]*# ]]; then
            # Extract variable name (everything before the first =)
            var_name=$(echo "$line" | cut -d'=' -f1)
            # Remove leading/trailing whitespace
            var_name=$(echo "$var_name" | xargs)
            # Unset the variable
            unset "$var_name"
        fi
    done < .env
fi

# Create the test_release directory if it doesn't exist
mkdir -p ../test_release

# Extract the second Python code block from README.md and save it to examples/readme_agent.py
awk '/^```python$/{count++; if(count==3){in_block=1; next}} /^```$/{if(in_block){in_block=0; exit}} in_block{print}' README.md > examples/readme_agent.py

# Copy the updated readme_agent.py file to the test_release directory
cp examples/readme_agent.py ../test_release/agent.py

echo "Successfully extracted second Python code block from README.md to examples/readme_agent.py"
echo "Successfully copied examples/readme_agent.py to ../test_release/agent.py"
cd ../test_release
# Create .env file with the NOTTE_API_KEY
export NOTTE_API_KEY=$NOTTE_RELEASE_TEST_API_KEY_BKP

echo "Successfully exported NOTTE_API_KEY to .env"

rm -rf .venv
uv venv --python 3.11
source .venv/bin/activate
uv pip install --upgrade notte-sdk

# Capture the output and exit status of the test
if output=$(uv run python agent.py 2>&1); then
    echo "Test completed successfully"
    {
      echo 'TEST_OUTPUT<<__GHA_EOF__'
      echo 'Test passed successfully'
      echo '__GHA_EOF__'
    } >> "$GITHUB_ENV"
    exit 0
else
    exit_code=$?
    echo "Test failed with exit code: $exit_code"
    {
      echo 'TEST_OUTPUT<<__GHA_EOF__'
      echo "Test failed with exit code ${exit_code}"
      echo
      printf '%s\n' "$output"
      echo '__GHA_EOF__'
    } >> "$GITHUB_ENV"
    exit "$exit_code"
fi
