#!/bin/bash
# PostToolUse hook — fires after Edit/Write on sensitive file types.
# Injects targeted safety instructions based on what was just changed:
#   • Firestore-touching code (Admin.jsx, BookSession.jsx, BuyNowButton.jsx, firebase.js)
#     → data-safety + Firestore security-rules gotcha checklist
#   • package.json / package-lock.json → dependency-downgrade guard
#   • App code (*.jsx / *.js) → existing-function regression check

input=$(cat)

tool=$(echo "$input" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')

if [[ "$tool" != "Edit" && "$tool" != "Write" ]]; then
  echo '{"continue": true}'
  exit 0
fi

file=$(echo "$input" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')

# ── Firestore-touching code ──────────────────────────────────────────────────
if echo "$file" | grep -qiE 'firebase\.js|Admin\.jsx|BookSession\.jsx|BuyNowButton\.jsx'; then
  cat <<'EOF'
{
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "FIRESTORE SAFETY CHECK (auto-triggered because a Firestore-touching file was just modified):\n\n1. NEW COLLECTIONS — If this change reads/writes a Firestore collection name that didn't exist before, remember: Security Rules live ONLY in the Firebase Console (project sharan-24586), not in this repo. A missing rule means every read/write silently fails with permission-denied — remind the user to add the rule in the console.\n2. SWALLOWED FAILURES — This codebase's existing pattern (BookSession.jsx / BuyNowButton.jsx) is to try/catch Firestore writes after a Razorpay success and show a success UI regardless of whether the write actually landed. Do not silently extend that pattern to new flows without flagging it — prefer surfacing the failure or at least logging in a way that's discoverable.\n3. NO REAL AUTH — Admin.jsx is gated by a hardcoded PIN in sessionStorage only, not Firebase Auth. Any new admin-only write path is exposed to the same anonymous client as the public site; do not assume server-side trust.\n4. EXISTING DATA — Any bulk write/delete/update must use the narrowest possible query/filter. Confirm it cannot overwrite or delete bookings/orders/gallery docs that already exist.\n\nIf any of these checks fail, fix it before moving on."
  }
}
EOF
  exit 0
fi

# ── Dependency files ─────────────────────────────────────────────────────────
if echo "$file" | grep -qiE '(package\.json|package-lock\.json)'; then
  cat <<'EOF'
{
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "DEPENDENCY SAFETY CHECK (auto-triggered because a dependency file was just modified):\n\n1. NO DOWNGRADES — Compare every changed package version against the previous value. A version change is only acceptable if it is an upgrade (higher semver) or a new package. Downgrading any existing package is BLOCKED unless the user explicitly requested it and confirmed the reason.\n2. COMPATIBILITY — If a package was upgraded by a major version (react, react-router-dom, vite), call out any known breaking-change surface and confirm nothing in this codebase relies on the removed/changed API.\n3. LOCK FILE SYNC — If package.json changed, package-lock.json must also be updated in the same commit.\n4. EXISTING FEATURES — Identify which pages/components exercise the changed dependency and confirm they still work.\n\nIf a downgrade is detected and was not explicitly requested, REVERT the change immediately."
  }
}
EOF
  exit 0
fi

# ── App source code (JS / JSX) ────────────────────────────────────────────────
if echo "$file" | grep -qiE '\.(js|jsx)$'; then
  cat <<'EOF'
{
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "EXISTING-FUNCTION REGRESSION CHECK (auto-triggered because app source was just modified):\n\n1. COMPONENT CONTRACTS — Did any exported component's props, return shape, or side-effects change? If yes, list every caller (App.jsx routes, other components) and confirm each one is compatible.\n2. EXISTING USER DATA — Does this change read from or write to Firestore in a new way? Confirm it cannot corrupt or silently overwrite existing bookings/orders/gallery docs.\n3. PAYMENT FLOW — If the changed code touches BookSession.jsx, BuyNowButton.jsx, or razorpay.js, confirm the checkout → write → UI-success sequence still behaves consistently and doesn't introduce a path where a customer is charged without a corresponding Firestore doc.\n4. ADMIN GATE — If the changed code touches Admin.jsx or the /secretadmin routing short-circuit in App.jsx, confirm no new bypass of the PIN gate was introduced.\n\nIf any regression risk is found, fix it before moving on."
  }
}
EOF
  exit 0
fi

echo '{"continue": true}'
