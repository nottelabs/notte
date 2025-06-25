#!/bin/bash

# Ensure pipeline fails if any command fails
set -o pipefail

# Define output file
SUMMARY_FILE="pytest_summary.log"
FULL_LOG="pytest_full_output.log"

# Let the user know what's happening
echo "Running pytest and capturing output..."
echo "Full output will be saved to: $FULL_LOG"
echo "Summary will be saved to: $SUMMARY_FILE"
echo "-----------------------------------"

# Run the test command and save full output
uv run pytest tests/examples --durations 10 | tee "$FULL_LOG"
status=$?

# Now extract the summary portion
echo "Extracting test summary information..."
awk '/^=+ short test summary info =+$/,0' "$FULL_LOG" > "$SUMMARY_FILE"

# Let the user know we're done
echo "-----------------------------------"
echo "Done! Summary saved to $SUMMARY_FILE"
echo "Full output saved to $FULL_LOG"

# Display the summary for convenience
echo "-----------------------------------"
echo "Test Summary:"
echo "-----------------------------------"
cat "$SUMMARY_FILE"

ESCAPED_CONTENT=$(sed 's/\\/\\\\/g; s/"/\\"/g; s/$/\\n/g' "$SUMMARY_FILE" | tr -d '\n')

# try to keep the newlines
echo 'TEST_OUTPUT<<EOF' >> $GITHUB_ENV
echo $ESCAPED_CONTENT >> $GITHUB_ENV
echo 'EOF' >> $GITHUB_ENV

exit $status
