#!/bin/bash
# Quickstart script for Notte SDK
# Usage: source this script or run directly (will create venv, install SDK, and run a Python example)

set -e

# Step 1: Create virtual environment with Python 3.11

# Check if 'uv' is installed
if ! command -v uv &> /dev/null; then
  echo "[INFO] 'uv' is not installed. Attempting to install with Homebrew..."
  if ! command -v brew &> /dev/null; then
    echo "[ERROR] Homebrew is not installed. Please install Homebrew first: https://brew.sh/"
    exit 1
  fi
  brew install uv || { echo "[ERROR] Failed to install 'uv' with Homebrew."; exit 1; }
fi

# Check for existing virtual environment and create if none available

# Create virtual environment
if type deactivate >/dev/null 2>&1; then
    echo "[INFO] Venv already active. Attempting to deactivate it."
    deactivate
fi

echo -e "\n[INFO] Creating virtual environment at: .venv_notte_quickstart"
uv venv --python 3.11 ".venv_notte_quickstart" &> /dev/null

# Step 2: Activate the virtual environment
source .venv_notte_quickstart/bin/activate

# Autoload environment variables from .env if present
if [ -f .env ]; then
  set -o allexport
  source .env
  set +o allexport
fi


# Step 3: Install packages
uv pip install rich &> /dev/null
uv pip install textual textual-dev &> /dev/null
uv pip install notte-sdk &> /dev/null


# Step 4: Run the Python quickstart example
if [ -z "$NOTTE_API_KEY" ]; then
  echo "[ERROR] NOTTE_API_KEY environment variable is not set."
  echo "You must set this variable to use the Notte SDK. Sign up at https://console.notte.cc for a free API key."
  echo "To set it on Unix/Linux/macOS (bash/zsh):"
  echo "  export NOTTE_API_KEY=your-key-here"
  echo "To set it on Windows (cmd):"
  echo "  set NOTTE_API_KEY=your-key-here"
  echo "To set it on Windows (PowerShell):"
  echo "  $env:NOTTE_API_KEY=\"your-key-here\""
  exit 1
fi

# Pull and run the latest quickstart_launcher.py from GitHub
curl -s https://raw.githubusercontent.com/nottelabs/notte/branding/examples/quickstart_launcher.py -o examples/quickstart_launcher.py
python examples/quickstart_launcher.py
