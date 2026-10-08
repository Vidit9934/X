#!/bin/bash

input=$(cat)

tool=$(echo "$input" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')

if [[ "$tool" != "Edit" && "$tool" != "Write" ]]; then
  echo '{"continue": true}'
  exit 0
fi

COOLDOWN_FILE="/tmp/claude_frontend_review_cooldown"
COOLDOWN_SECONDS=30

# Plan files get their own dedicated hook (plan-review-hook.sh) — always
# exempt here, checked BEFORE the cooldown gate so a plan-file edit landing
# inside the cooldown window doesn't get miscast as a throttled code review.
# Cheap grep pre-filter avoids starting python3 for the vast majority of
# edits that obviously aren't under .claude/ at all; exits WITHOUT writing
# the cooldown timestamp so plan-file writes don't burn the slot and block
# the next real code-file review.
if echo "$input" | grep -q '\.claude'; then
  file_check=$(echo "$input" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    fp = data.get('tool_input', {}).get('file_path', '')
    print('plan' if '.claude/plans/' in fp.replace('\\\\', '/') else 'code')
except Exception:
    print('code')
")
  if [[ "$file_check" == "plan" ]]; then
    echo '{"continue": true}'
    exit 0
  fi
fi

if [[ -f "$COOLDOWN_FILE" ]]; then
  last_review=$(cat "$COOLDOWN_FILE")
  now=$(date +%s)
  elapsed=$(( now - ${last_review:-0} ))
  if [[ $elapsed -lt $COOLDOWN_SECONDS ]]; then
    # Throttled, but never silent: emit a cheap reminder (no python3, no
    # timestamp reset) instead of dropping this edit's review entirely, so
    # a fast burst of edits doesn't quietly end with no score ever given.
    cat <<'EOF'
{
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "REVIEW THROTTLED (cooldown active, <30s since last full review): this edit is part of an ongoing burst. Do not skip scoring — once the burst of edits settles, run the full PHASE 1-3 review (coding quality, multi-POV scoring, SCORE: XX/100, doc sync) against the FINAL state of the file(s) touched, not just the first edit."
  }
}
EOF
    exit 0
  fi
fi

date +%s > "$COOLDOWN_FILE"

file=$(echo "$input" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')

cat <<EOF
{
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "POST-HOOK REVIEW REQUIRED: The file $file was just modified.\n\n## PHASE 1 — Standard Review\nReview for:\n1. Coding best practices\n2. Optimization opportunities\n3. Code reuse (check if functionality already exists)\n4. Architecture quality (senior SDE perspective)\nIf issues found, automatically fix them.\n\n## PHASE 2 — Creative Multi-POV Scoring\nNow think creatively and critically from multiple perspectives:\n- Security engineer: are there any attack surfaces or unsafe assumptions?\n- Performance engineer: any bottlenecks, N+1s, or unnecessary work?\n- Junior dev onboarding: is this readable and maintainable?\n- Product/user lens: does this actually solve the right problem correctly?\n- Devil's advocate: what is the most likely way this breaks in production?\n\nBased on this multi-POV analysis, assign an IMPLEMENTATION SCORE out of 100.\n\nOutput the score clearly like: SCORE: XX/100\n\nIf SCORE < 85: you MUST stop, explain what dragged the score down, completely redo the implementation to address all identified flaws, and then run this same review again on the new version until the score is 85 or above. Do not move on until the score is >= 85.\n\n## PHASE 3 — Documentation sync\nIf this change introduced or altered anything durable that a future session would need — a new/changed API endpoint or route, env var, naming convention, cross-file invariant, or a non-obvious gotcha — update CLAUDE.md in the SAME turn to match. Skip trivial/local edits; only record architectural or contract-level facts. If nothing durable changed, say so explicitly and do not touch CLAUDE.md."
  }
}
EOF
