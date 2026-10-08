#!/bin/bash
# Fires on PreToolUse/Edit|Write — reminds about frontend<->backend integration
# conventions whenever a file under frontend/ is about to be created/edited.

input=$(cat)

parsed=$(echo "$input" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
print(d.get('tool_name', ''))
print(d.get('tool_input', {}).get('file_path', ''))
" 2>/dev/null)

if [[ -n "$parsed" ]]; then
  tool=$(echo "$parsed" | sed -n '1p')
  file=$(echo "$parsed" | sed -n '2p')
else
  tool=$(echo "$input" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')
  file=$(echo "$input" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')
fi

if [[ "$tool" != "Edit" && "$tool" != "Write" ]]; then
  exit 0
fi

norm=$(echo "$file" | tr '\\' '/')

if [[ "$norm" != *"/frontend/"* ]] || [[ "$norm" == *"/node_modules/"* ]]; then
  exit 0
fi

python3 -c "
import json
reason = '''FRONTEND<->BACKEND INTEGRATION CHECKLIST for this file:
1. API calls go through the service layer (lib/api.ts + services/*Api.ts) - no raw fetch/axios in components.
2. Backend base URL only via import.meta.env.VITE_API_BASE_URL - never hardcode, never put secrets in frontend .env.
3. Auth token handling stays centralized (API client attaches it); session/user state lives in AppContext, not per-page.
4. Components are UI-only - no fetch/localStorage/business logic inline; delegate to service functions.
5. Handle loading / error / empty / unauthorized states for every backend-connected view.
6. Match the backend real error/response shape (check backend/app schemas + routes) - do not invent your own.
7. If a backend Pydantic schema or migration changed, verify frontend types/services were updated to match.
8. Mirror backend validation client-side for UX, but never rely on frontend-only validation.
9. Browser calls http://localhost:8000 (VITE_API_BASE_URL); http://backend:8000 only works container-to-container.
10. Keep CLAUDE.md in sync if this touches a durable contract/convention (route, env var, schema).'''
print(json.dumps({
    'continue': True,
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'additionalContext': reason
    }
}))
"
