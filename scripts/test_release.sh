#!/bin/bash
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

# Copy the auth-vault-agent file to the test_release directory
cp examples/readme_agent.py ../test_release/agent.py

echo "Successfully copied auth-vault-agent/agent.py to ../test_release/agent.py"
cd ../test_release
# Create .env file with the NOTTE_API_KEY
echo "NOTTE_API_KEY=$NOTTE_RELEASE_TEST_API_KEY" > .env

echo "Successfully copied auth-vault-agent/agent.py to ../test_release/agent.py"
echo "Created .env file with NOTTE_API_KEY in ../test_release/"

rm -rf .venv
uv venv --python 3.11
source .venv/bin/activate
uv pip install --upgrade notte-sdk
uv run python agent.py
