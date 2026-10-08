#!/bin/bash
# push-gate-hook.sh — fires on PreToolUse/Bash when Claude attempts git push.
#
# Behaviour:
#   - ALWAYS requires user approval (permissionDecision: ask)
#   - Calls EPAM Dial AI to classify stakes (HIGH / LOW) and summarise the push
#   - HIGH-stakes pushes display a prominent warning; LOW get a neutral prompt
#
# Pattern: stdin captured before heredoc → temp file → Python reads via env var.
# (The heredoc consumes Python's stdin, so hook JSON must be pre-staged to disk.)

PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)

if [[ -z "$PYTHON" ]]; then
  exit 0
fi

input=$(cat)

# fail-open: if /tmp is full let the push through rather than block forever
TMPINPUT=$(mktemp /tmp/push_gate_XXXXXX.json) || exit 0
printf '%s' "$input" > "$TMPINPUT"
trap "rm -f '$TMPINPUT'" EXIT

export HOOK_INPUT_FILE="$TMPINPUT"
export PG_DIAL_KEY="dial-wueusale2qsd6n2vmkzwj373lme"
export PG_DIAL_BASE="https://ai-proxy.lab.epam.com"
export PG_DIAL_MODEL="gpt-4o"

"$PYTHON" - <<'PYEOF'
import sys, json, os, subprocess, urllib.request, re, glob

DIAL_KEY   = os.environ.get("PG_DIAL_KEY", "")
DIAL_BASE  = os.environ.get("PG_DIAL_BASE", "").rstrip("/")
DIAL_MODEL = os.environ.get("PG_DIAL_MODEL", "gpt-4o")

# ── 1. Load hook input ───────────────────────────────────────────────────────

try:
    with open(os.environ.get("HOOK_INPUT_FILE", ""), "r") as fh:
        data = json.load(fh)
except Exception:
    data = {}

cmd = data.get("tool_input", {}).get("command", "")
cwd = data.get("tool_input", {}).get("cwd", "")

# Only intercept git push — ignore commit, log, status, etc.
if not re.search(r'\bgit\b.*\bpush\b', cmd):
    sys.exit(0)

# ── 2. Normalise cwd (Windows path → POSIX) ─────────────────────────────────

orig_cwd = cwd   # keep Windows-format as fallback for os.path.isdir on native Windows Python

if cwd and len(cwd) >= 2 and cwd[1] == ':':
    try:
        cwd = subprocess.check_output(
            ['cygpath', '-u', cwd], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        drive = cwd[0].lower()
        rest  = cwd[2:].replace('\\', '/')
        cwd   = f'/{drive}{rest}'

# POSIX form works for MSYS2-aware Python; Windows form works for native Windows Python
work_dir = (cwd      if (cwd      and os.path.isdir(cwd))      else
            orig_cwd if (orig_cwd and os.path.isdir(orig_cwd)) else None)

# ── 3. Gather push context via git ──────────────────────────────────────────

def git(*args):
    try:
        return subprocess.check_output(
            ['git'] + list(args), cwd=work_dir,
            stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return ""

branch     = git('rev-parse', '--abbrev-ref', 'HEAD') or "unknown"
remote_ref = f"origin/{branch}"

# Commits and files that would actually be pushed
# Fall back to last-5 / HEAD~1 when the remote ref doesn't exist yet
commits = (git('log', '--oneline', f'{remote_ref}..HEAD') or
           git('log', '--oneline', '-5'))
files   = (git('diff', '--name-only', f'{remote_ref}..HEAD') or
           git('diff', '--name-only', 'HEAD~1'))

# Last *non-empty* line of --stat is the "N files changed" summary
raw_stat   = git('diff', '--stat', f'{remote_ref}..HEAD')
stat_lines = [l for l in raw_stat.split('\n') if l.strip()]
stat       = stat_lines[-1] if stat_lines else ""

# ── 3b. Alembic integrity check ──────────────────────────────────────────────

def parse_alembic_heads(base_dir):
    """Parse migration files to find head revisions — no DB or alembic binary needed.
    A head is any revision that no other revision lists as its down_revision."""
    if not base_dir:
        return [], None
    for vdir in [
        os.path.join(base_dir, 'backend', 'alembic', 'versions'),
        os.path.join(base_dir, 'alembic', 'versions'),
        os.path.join(base_dir, 'migrations', 'versions'),
    ]:
        if os.path.isdir(vdir):
            break
    else:
        return [], None   # no versions dir found — not an alembic project

    revisions = {}   # rev_id -> set of its down_revision ids
    for path in glob.glob(os.path.join(vdir, '*.py')):
        try:
            with open(path, encoding='utf-8', errors='ignore') as fh:
                content = fh.read()
        except Exception:
            continue
        rev_m = re.search(r'^revision\s*=\s*[\'"]([a-f0-9]+)[\'"]', content, re.MULTILINE)
        if not rev_m:
            continue   # env.py, __init__.py, etc.
        rev_id = rev_m.group(1)
        down_m = re.search(r'^down_revision\s*=\s*(.+)$', content, re.MULTILINE)
        downs = set()
        if down_m:
            raw = down_m.group(1).strip()
            if raw.lower() not in ('none', "''", '""'):
                # handles string, tuple, and merge-migration list forms
                downs.update(re.findall(r"['\"]([a-f0-9]+)['\"]", raw))
        revisions[rev_id] = downs

    all_downs = set()
    for downs in revisions.values():
        all_downs.update(downs)
    heads = sorted(r for r in revisions if r not in all_downs)
    return heads, vdir

alembic_heads, alembic_vdir = parse_alembic_heads(work_dir)
alembic_issues = []

if alembic_vdir:
    n = len(alembic_heads)
    if n > 1:
        alembic_issues.append(
            f"MULTIPLE HEADS ({n}): " + ", ".join(alembic_heads)
            + "  — migration graph is BRANCHED; a merge migration is required"
        )

    # Flag migration files included in this push so user is aware
    pushed_migs = [
        f.strip() for f in (files or '').split('\n')
        if f.strip() and re.search(r'(alembic|migrations)[/\\]versions[/\\]', f)
    ]
    if pushed_migs:
        alembic_issues.append(
            f"Migration files in push ({len(pushed_migs)}): "
            + ", ".join(os.path.basename(p) for p in pushed_migs)
        )

# ── 4. Call EPAM Dial AI ─────────────────────────────────────────────────────

alembic_section = "\n".join(alembic_issues) if alembic_issues else "none"

prompt = (
    "You are a senior engineer reviewing a git push before it reaches the remote.\n\n"
    f"Branch: {branch}\n\n"
    f"Commits:\n{commits or '(none)'}\n\n"
    f"Files changed:\n{files or '(none)'}\n\n"
    f"Stat: {stat}\n\n"
    f"Alembic/migration checks:\n{alembic_section}\n\n"
    "Classify STAKES as HIGH or LOW:\n"
    "HIGH = DB migrations, auth/security code, CI/CD config, prod infra,\n"
    "       breaking API changes, pushing to main/master/UAT-1, secrets/env vars,\n"
    "       anything that could cause a production incident.\n"
    "LOW  = UI components, tests, docs, isolated feature work, frontend-only fixes.\n\n"
    "Return ONLY a JSON object with exactly these keys:\n"
    '  "stakes": "HIGH" or "LOW"\n'
    '  "reason": one concise sentence explaining your classification\n'
    '  "summary": 2-3 sentence plain-English summary of what this push contains\n'
    '  "warnings": array of specific concern strings (empty array if none)'
)

ai = {
    "stakes":   "LOW",
    "reason":   "Dial AI unreachable — defaulting to LOW",
    "summary":  "AI review skipped. Verify changes manually before approving.",
    "warnings": []
}

try:
    payload = json.dumps({
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  400,
        "temperature": 0.1
    }).encode()

    url = (f"{DIAL_BASE}/openai/deployments/{DIAL_MODEL}"
           "/chat/completions?api-version=2024-02-01")

    req = urllib.request.Request(url, data=payload, headers={
        "api-key":      DIAL_KEY,
        "Content-Type": "application/json"
    })

    with urllib.request.urlopen(req, timeout=15) as resp:
        body    = json.loads(resp.read().decode())
        content = body["choices"][0]["message"]["content"]
        # Direct parse first; regex-extract fallback for markdown-fenced responses
        try:
            ai = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            m = re.search(r'\{[\s\S]*\}', content)
            if m:
                ai = json.loads(m.group())

except Exception as exc:
    ai["reason"] = f"Dial AI error ({type(exc).__name__}) — defaulting to LOW"

stakes   = str(ai.get("stakes", "LOW")).upper()
reason   = ai.get("reason", "")
summary  = ai.get("summary", "")
warnings = ai.get("warnings") or []   # `or []` also handles null (None) from AI

# Guard: AI may return a string like "none" instead of an empty list
if not isinstance(warnings, list):
    warnings = [str(warnings)]

# Multiple Alembic heads overrides AI stakes — branched migration history is
# a production incident waiting to happen regardless of what else is in the push
if any("MULTIPLE HEADS" in issue for issue in alembic_issues):
    stakes = "HIGH"

# ── 5. Build approval message ────────────────────────────────────────────────

if stakes == "HIGH":
    header     = "HIGH-STAKES PUSH — REVIEW REQUIRED"
    stake_line = "Stakes:   HIGH  <-- do not approve without careful review"
else:
    header     = "PUSH APPROVAL REQUIRED"
    stake_line = "Stakes:   LOW"

warn_block = ""
if warnings:
    warn_block = "\n\nConcerns flagged:\n" + "\n".join(f"  * {w}" for w in warnings)

msg_parts = [
    header,
    "",
    "Claude cannot push to remote without your explicit approval.",
    "",
    f"Branch:   {branch}",
    f"Command:  {cmd}",
    f"Scope:    {stat or '(no diff vs remote)'}",
    "",
    "--- EPAM DIAL AI ASSESSMENT ---",
    stake_line,
    f"Why:      {reason}",
    "",
    summary + warn_block,
]

if alembic_issues:
    msg_parts += [
        "",
        "--- ALEMBIC INTEGRITY ---",
    ] + [f"  ! {issue}" for issue in alembic_issues]

msg_parts += [
    "",
    "--- COMMITS IN THIS PUSH ---",
    commits or "(none detected -- branch may already be up to date)",
    "",
    "Approve to proceed. Deny to abort.",
]

msg = "\n".join(msg_parts)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName":            "PreToolUse",
        "permissionDecision":       "ask",
        "permissionDecisionReason": msg
    }
}))
PYEOF
