#!/bin/sh
set -eu

command -v sbx >/dev/null 2>&1 || { echo 'Install Docker Sandboxes sbx first' >&2; exit 1; }

sbx mcp add notte --url https://api.notte.cc/mcp \
  --header 'Authorization: Bearer ${api-key}'
sbx secret set mcp:notte:api-key
exec sbx run "${1:-claude}" --name "${2:-notte-browser}" --static-mcp notte
