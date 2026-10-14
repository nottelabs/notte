#!/usr/bin/env bash
# Wait until $API_URL/health is healthy N times in a row with a stable version.
#
# A single 200 is not enough: the API can answer /health while it is scaling up
# or mid-rollout, then fail or change version on the next call. A poll counts
# toward the streak only when it returns HTTP 200 with status "healthy" and the
# same version as the previous healthy poll. Any failure resets the streak and
# backs off exponentially (capped) until the overall deadline.
set -uo pipefail

: "${API_URL:?API_URL is required}"
CONSECUTIVE="${CONSECUTIVE:-3}"
INTERVAL="${INTERVAL:-5}"
MAX_BACKOFF="${MAX_BACKOFF:-60}"
TIMEOUT="${TIMEOUT:-900}"

url="${API_URL%/}/health"
deadline=$((SECONDS + TIMEOUT))
streak=0
version=""
backoff="$INTERVAL"
body_file="$(mktemp)"
trap 'rm -f "$body_file"' EXIT

while :; do
  code="$(curl -s -o "$body_file" --max-time 20 -w '%{http_code}' "$url" || true)"
  status=""
  current=""
  if [ "$code" = "200" ]; then
    # Print "<status> <version>"; empty when the body is not the expected JSON.
    read -r status current < <(python3 -c '
import json, sys
try:
    data = json.load(open(sys.argv[1]))
    print(data.get("status", ""), data.get("version", "") or "-")
except Exception:
    print("", "")
' "$body_file") || true
  fi

  if [ "$code" = "200" ] && [ "$status" = "healthy" ]; then
    if [ "$streak" -gt 0 ] && [ "$current" != "$version" ]; then
      echo "Version changed from $version to $current; restarting the streak."
      streak=0
    fi
    version="$current"
    streak=$((streak + 1))
    backoff="$INTERVAL"
    echo "Healthy ($streak/$CONSECUTIVE), version $version"
    if [ "$streak" -ge "$CONSECUTIVE" ]; then
      echo "API is ready at $API_URL (version $version)."
      exit 0
    fi
    delay="$INTERVAL"
  else
    [ "$streak" -gt 0 ] && echo "Streak broken after $streak healthy responses."
    streak=0
    echo "Not ready yet (HTTP ${code:-none}${status:+, status $status}); retrying in ${backoff}s."
    delay="$backoff"
    backoff=$((backoff * 2))
    [ "$backoff" -le "$MAX_BACKOFF" ] || backoff="$MAX_BACKOFF"
  fi

  if [ $((SECONDS + delay)) -ge "$deadline" ]; then
    echo "::error::API at $API_URL was not ready within ${TIMEOUT}s."
    exit 1
  fi
  sleep "$delay"
done
