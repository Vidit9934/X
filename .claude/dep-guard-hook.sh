#!/bin/bash
# Fires on PreToolUse/Bash — blocks git commit/push when critical dependencies change.
# Critical packages: alembic (migration lethal), celery, duckdb, psycopg/asyncpg (postgres), redis, kombu, speed*

input=$(cat)

# Extract command (use python3 for reliable JSON parsing, fallback to grep)
cmd=$(echo "$input" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null || \
      echo "$input" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')

# Only intercept git commit or git push
if [[ ! "$cmd" =~ ^git[[:space:]]+(commit|push) ]]; then
  exit 0
fi

# Extract working directory where the git command would run
cwd=$(echo "$input" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('cwd',''))" 2>/dev/null || echo "")

if [[ -n "$cwd" ]] && [[ -d "$cwd" ]]; then
  cd "$cwd" || exit 0
fi

# Find staged dependency files
DEP_FILES=$(git diff --cached --name-only 2>/dev/null | \
  grep -iE '(requirements[^/]*\.txt|pyproject\.toml|setup\.(py|cfg)|Pipfile(\.lock)?|alembic\.ini|poetry\.lock)' | \
  tr '\n' ' ')

if [[ -z "$DEP_FILES" ]]; then
  exit 0
fi

# Critical packages to guard
CRITICAL="alembic|celery|duckdb|psycopg|asyncpg|sqlalchemy|redis|kombu|speed"

# Get changed lines touching critical packages (+ additions, - removals)
CHANGES=$(git diff --cached -- $DEP_FILES 2>/dev/null | \
  grep -E "^[+-].*(${CRITICAL})" | \
  grep -v "^[+-]{3}")

if [[ -z "$CHANGES" ]]; then
  exit 0
fi

# Export for Python (avoids all bash/JSON quoting hazards)
export GUARD_FILES="$DEP_FILES"
export GUARD_CHANGES="$CHANGES"

python3 -c "
import json, os
files = os.environ.get('GUARD_FILES', '').strip()
changes = os.environ.get('GUARD_CHANGES', '')

reason = (
    '⚠️  CRITICAL DEPENDENCY CHANGES DETECTED\n\n'
    'Dependency files in this commit:\n  ' + '\n  '.join(files.split()) + '\n\n'
    'Lines touching critical packages:\n' + changes + '\n\n'
    '🔴 ALEMBIC DOWNGRADE = LETHAL\n'
    '   Silently corrupts migration history. Every future alembic upgrade/downgrade\n'
    '   will fail or produce wrong schema. This has happened before in this repo.\n\n'
    '⚠️  CELERY / DUCKDB / POSTGRESQL DRIVER (psycopg / asyncpg)\n'
    '   Version mismatches break workers, connection pools, and data reads without\n'
    '   obvious error messages at deploy time.\n\n'
    'Before approving:\n'
    '  1. Is this version change intentional (not an accidental downgrade)?\n'
    '  2. Have you tested the migration path (alembic upgrade head) locally?\n'
    '  3. Is the change reflected in all environments (dev, staging, prod)?\n\n'
    'Approve only if 100% certain. Deny to abort the commit.'
)

print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'ask',
        'permissionDecisionReason': reason
    }
}))
"
