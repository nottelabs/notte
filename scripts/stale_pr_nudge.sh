#!/bin/bash
# Pings the author of each open, ready-for-review pull request with no activity
# for STALE_DAYS days. Run by .github/workflows/stale-pr-nudge.yml.
#
# A PR whose latest activity is already this script's comment is skipped, so
# it is pinged again only after new activity followed by another idle period.
#
# Environment: REPO (owner/name), STALE_DAYS, MARKER (hidden comment that
# identifies the ping), DRY_RUN ("true" to only print), GH_TOKEN.
set -euo pipefail

# Timeline events that follow a comment that mentions someone, not activity.
NOISE='["mentioned", "subscribed", "unsubscribed"]'

gh pr list --repo "$REPO" --state open --limit 500 \
  --json number,isDraft,updatedAt,author \
  --jq '.[]
    | select((.isDraft | not) and (.author.is_bot | not))
    | select(now - (.updatedAt | fromdateiso8601) > (env.STALE_DAYS | tonumber) * 86400)
    | [.number, .updatedAt, .author.login] | @tsv' |
while IFS=$'\t' read -r number updated author; do
  # The timeline API does not document an order: sort events by time.
  latest=$(gh api --paginate --slurp "repos/$REPO/issues/$number/timeline" | jq -r --argjson noise "$NOISE" '
    add
    | map(select(.event as $e | $noise | index($e) | not))
    | sort_by(.created_at // .submitted_at // .committer.date // "")
    | last // empty
    | [.event, ((.body // "") | contains(env.MARKER)), (.actor.type // .user.type // "")] | @tsv')
  if [ "$latest" = "commented	true	Bot" ]; then
    echo "#$number: already pinged, no activity since"
    continue
  fi
  if [ "$DRY_RUN" = "true" ]; then
    echo "#$number: would ping @$author (last activity $updated)"
    continue
  fi
  body="@$author this pull request has had no activity for $STALE_DAYS days. If it is still needed, push an update or ask a reviewer to take a look; otherwise consider closing it.

$MARKER"
  gh pr comment "$number" --repo "$REPO" --body "$body"
  echo "#$number: pinged @$author"
done
