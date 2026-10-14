#!/bin/bash
# Tests scripts/stale_pr_nudge.sh against a fake `gh` with canned pull requests.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
fake=$(mktemp -d)
trap 'rm -rf "$fake"' EXIT

cat > "$fake/gh" <<'GH'
#!/bin/bash
# Fake gh: PR list and timelines from fixtures, filtered with jq like --jq does.
jqexpr="${*: -1}"
if [ "$1 $2" = "pr list" ]; then
  cat <<'JSON' | jq -r "$jqexpr"
[
  {"number": 1, "isDraft": false, "updatedAt": "2026-01-01T00:00:00Z", "author": {"login": "idle", "is_bot": false}},
  {"number": 2, "isDraft": false, "updatedAt": "2026-01-01T00:00:00Z", "author": {"login": "pinged", "is_bot": false}},
  {"number": 3, "isDraft": true, "updatedAt": "2026-01-01T00:00:00Z", "author": {"login": "draft", "is_bot": false}},
  {"number": 4, "isDraft": false, "updatedAt": "2026-01-01T00:00:00Z", "author": {"login": "dependabot", "is_bot": true}},
  {"number": 5, "isDraft": false, "updatedAt": "2999-01-01T00:00:00Z", "author": {"login": "active", "is_bot": false}},
  {"number": 6, "isDraft": false, "updatedAt": "2026-01-01T00:00:00Z", "author": {"login": "replied", "is_bot": false}}
]
JSON
elif [ "$1" = "api" ]; then
  ping='{"event": "commented", "body": "x\n\n<!-- stale-pr-nudge -->", "actor": {"type": "Bot"}}'
  case "$3" in
    # Pinged, then only the notification events the ping itself caused.
    */2/timeline) echo "[{\"event\": \"committed\"}, $ping, {\"event\": \"mentioned\", \"actor\": {\"type\": \"User\"}}, {\"event\": \"subscribed\", \"actor\": {\"type\": \"User\"}}]" ;;
    # Pinged, then the author replied seconds later.
    */6/timeline) echo "[$ping, {\"event\": \"commented\", \"body\": \"on it\", \"actor\": {\"type\": \"User\"}}]" ;;
    *) echo '[{"event": "committed"}]' ;;
  esac | jq -r "$jqexpr"
elif [ "$1 $2" = "pr comment" ]; then
  echo "COMMENT #$3 $(printf '%s' "${*: -1}" | tr '\n' ' ')"
fi
GH
chmod +x "$fake/gh"

run() {
  PATH="$fake:$PATH" REPO=owner/repo STALE_DAYS=7 MARKER='<!-- stale-pr-nudge -->' DRY_RUN="$1" \
    bash "$here/stale_pr_nudge.sh"
}

fail() { echo "FAIL: $1"; echo "$output"; exit 1; }

output=$(run false)
grep -q '^COMMENT #1 @idle .*<!-- stale-pr-nudge -->$' <<<"$output" || fail "idle PR is pinged with the marker"
grep -q '^#2: already pinged' <<<"$output" || fail "a PR whose latest activity is the ping is skipped"
grep -q '^COMMENT #6 @replied' <<<"$output" || fail "a reply after the ping makes the PR eligible again"
for n in 3 4 5; do
  ! grep -q "#$n" <<<"$output" || fail "PR #$n (draft, bot or recently active) is left alone"
done

output=$(run true)
! grep -q '^COMMENT' <<<"$output" || fail "a dry run does not comment"
grep -q '^#1: would ping @idle' <<<"$output" || fail "a dry run lists the PRs it would ping"

echo "stale_pr_nudge: all tests passed"
