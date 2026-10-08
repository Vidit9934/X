#!/bin/bash
# PreToolUse production-safety reminder.
# - Always fires before Bash commands that look like they write to production
#   Firestore data or touch payment flow (the exact class of action that could
#   silently corrupt bookings/orders or double-charge a customer).
# - Fires before Edit/Write with a short cooldown so it stays a reminder, not spam.

input=$(cat)

tool=$(echo "$input" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')

emit() {
  cat <<'EOF'
{"continue": true, "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "PRE-TOOL PRODUCTION SAFETY CHECK: This project's ONLY data store is a live Firestore project (sharan-24586) with real bookings, orders, and gallery content, accessed directly from the client with no backend and no real auth. There may be NO backup to restore from. Before this action, confirm it cannot harm real users or data: do NOT run any bulk write, delete, or overwrite against Firestore collections (bookings, availability, bookOrders, gallery) outside of narrowly-targeted, explicitly-approved operations. Never touch Razorpay key/order logic in a way that could double-charge a customer or leave a payment write silently failing (writes here are caught in try/catch and swallowed into a fake success state today — see CLAUDE.md gotcha). State the exact blast radius (which collection/docs, how many) and get EXPLICIT user approval before any production write. If the action is destructive or irreversible and you are not certain it is safe, STOP and ask instead of proceeding."}}
EOF
}

if [[ "$tool" == "Bash" ]]; then
  # git push to main = production deploy on Vercel — always warn.
  if echo "$input" | grep -Eiq 'git\s+push'; then
    emit
    exit 0
  fi
  # Critical: command that can write/delete Firestore data or hit Razorpay directly.
  if echo "$input" | grep -Eiq 'firestore|firebase deploy|deleteDoc|setDoc|updateDoc|addDoc|writeBatch|razorpay'; then
    emit
    exit 0
  fi
  echo '{"continue": true}'
  exit 0
fi

if [[ "$tool" == "Edit" || "$tool" == "Write" ]]; then
  emit
  exit 0
fi

echo '{"continue": true}'
