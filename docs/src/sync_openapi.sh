#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
curl -fsSL "https://api.notte.cc/openapi.json" -o "${ROOT_DIR}/openapi.json"
