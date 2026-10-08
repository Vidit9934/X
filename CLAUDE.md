# AI Twitter Growth Copilot — Backend

This repo is backend-only (FastAPI + Supabase + DeepSeek). The Android
frontend lives elsewhere and is intentionally not part of this repo.
See `requirements.txt` for the full app plan and `plan.txt` for the
staged build checklist (work top to bottom, cross off each stage's
items — including its tests — before starting the next).

## Layout
- `backend/app/main.py` — FastAPI app, mounts routers, `/health`, `/health/db`
  (trivial Supabase query, hit by the keepalive workflow).
- `backend/app/routers/` — HTTP endpoints.
  - `trend.py` (`POST /trend-scan`, manual paste) — `summarize_tweets()` is
    shared with `automation.py`'s real scrape-backed version.
  - `drafts.py` (`POST /drafts/generate`, `GET /drafts/today`).
  - `automation.py` (`POST /automation/trend-scan`, `POST
    /automation/style-profile-refresh`, `POST /automation/reply-target-scan`)
    — the Stage 2 scrape-backed endpoints the GitHub Actions workflows call.
    `reply-target-scan` is a **Stage 2 stub**: it scrapes
    `WATCHLIST_CREATOR_HANDLES` and returns raw posts with no scoring — Stage
    3 adds engagement-velocity scoring on top of this data, doesn't replace it.
  - `checkin.py` (`POST /checkin`, `GET /checkin/today`) — morning check-in
    intake; a null/blank `text` is a valid "no answer" signal, not an error.
- `backend/app/repositories/` — thin CRUD wrappers around the Supabase
  client, one per table (`drafts_repo.py`, `style_repo.py`, `leads_repo.py`,
  `reader_accounts_repo.py`, `check_ins_repo.py`). Endpoints depend on repos
  via FastAPI `Depends`, not on the Supabase client directly — keeps
  endpoints testable with fakes (see `backend/tests/fakes.py`).
- `backend/app/services/openrouter.py` — `OpenRouterClient.chat(system, user)`
  wrapper; raises `OpenRouterError` on transport/shape failures, logs token
  usage (never prompt/response content). Hits OpenRouter's OpenAI-compatible
  `/chat/completions` endpoint, defaulting to `settings.llm_model`
  (`deepseek/deepseek-v4-flash`) — the app's LLM is DeepSeek, but it is
  accessed via OpenRouter, not DeepSeek's own API.
- `backend/app/services/scraper.py` — `Scraper` Protocol (unchanged since
  Stage 1); `backend/app/services/twscrape_scraper.py`'s `TwscrapeScraper` is
  the Stage 2 implementation.
- `backend/app/services/twscrape_scraper.py` — `TwscrapeScraper`, twscrape-backed.
  twscrape is async-only; every public method wraps its async internals in
  `asyncio.run` so the rest of the codebase (routers, `ReaderPoolManager`)
  stays synchronous — **never call two of its methods from within the same
  outer `asyncio.run`**, or you'll hit `RuntimeError: asyncio.run() cannot be
  called from a running event loop` (this bit the first draft: `_get_pool`
  called `asyncio.run` a second time from inside an already-running one —
  fixed by making the pool-loading path a plain `async def` awaited by
  whichever public method is already inside `asyncio.run`). Reader-account
  X login credentials come from `READER_ACCOUNTS_JSON` and are loaded into
  twscrape's own local sqlite pool (`TWSCRAPE_DB_PATH`) — never into
  Supabase or git.
- `backend/app/services/reader_pool.py` — `ReaderPoolManager` wraps
  `TwscrapeScraper` + `ReaderAccountsRepo`. twscrape's `AccountsPool` already
  does account rotation internally; this class's job is only health
  monitoring — `sync_health()` reads twscrape's per-account
  active/inactive status and calls `mark_retired` on our `reader_accounts`
  row for any account twscrape reports as failed, per requirements.txt's
  "retire on first failure, never retry harder."
- `backend/app/schema.sql` — Supabase Postgres DDL for `style_profiles`,
  `drafts`, `leads`, `reader_accounts`, `check_ins`. Run manually against the
  Supabase project; there is no migration tool wired up yet.
- **No embeddings/vector search anywhere in this project, by design.**
  Trend scanning, draft generation, and (Stage 3) reply-target scoring all
  pass raw text straight into the LLM prompt rather than chunk-and-retrieve
  — the volume (15-30 creators, a handful of posts/day) fits in context.
  Don't add pgvector/embeddings speculatively; only reconsider if a future
  feature genuinely needs similarity search over a large corpus (e.g.
  deduping generated drafts against post history).

## Env vars (`backend/.env`, see `.env.example`)
- `SUPABASE_URL`, `SUPABASE_KEY` — `SUPABASE_KEY` must be the **service_role**
  key, not the anon/publishable key. The backend is server-only (never
  exposed to a browser), and all tables have Supabase's default
  Row-Level-Security enabled with no policies, so anon-key inserts are
  rejected with `42501 new row violates row-level security policy`. Using
  service_role (which bypasses RLS by design) is correct here — never send
  this key to a client.
- `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` (defaults to `https://openrouter.ai/api/v1`)
- `LLM_MODEL` (defaults to `deepseek/deepseek-v4-flash`)
- `TWSCRAPE_DB_PATH` (defaults to `twscrape_accounts.db`) — twscrape's own
  local sqlite account pool, separate from Supabase's `reader_accounts` table
  (which only tracks handle/status/health, never credentials).
- `READER_ACCOUNTS_JSON` — JSON array of `{handle, username, password, email,
  email_password}` for the 2-3 reader accounts. Real X login credentials —
  never commit a filled-in value, never store these in Supabase.
- `STUDY_CREATOR_HANDLES`, `WATCHLIST_CREATOR_HANDLES` — comma-separated
  creator lists (style-study vs. reply-target watchlist per
  requirements.txt section 2). Deliberately env vars, not a Supabase table
  — simple to edit without a migration, and the volume (15-30 handles) is
  small.
- `SCRAPE_POSTS_PER_HANDLE` (defaults to 5), `SCRAPE_PACING_SECONDS`
  (defaults to 2.0) — pacing between handles in `TwscrapeScraper`, so scrapes
  never burst.

## Gotchas
- **Python version:** use 3.13, not 3.14 — `pydantic-core` has no prebuilt
  wheel for cp314 on Windows yet and building from source needs a Rust/MSVC
  toolchain that isn't set up here. Venv at `backend/.venv` was created with
  `py -3.13 -m venv .venv`.
- **`supabase` pin: must be >=2.31.0** (bumped from an initial `2.11.0`).
  Older `supabase-py` validates the key against a strict JWT-shaped regex
  client-side and raises `SupabaseException("Invalid API key")` for
  Supabase's newer `sb_publishable_...`/`sb_secret_...` key formats before
  ever making a network call — 2.31.0 dropped that check. If you ever see
  "Invalid API key" with a key that looks right, this is almost certainly
  the cause, not a bad credential.
- `POST /drafts/generate` expects the LLM response to be a JSON array
  of exactly 5 `{body, image_idea, source_link}` objects (optionally wrapped
  in a ` ```json ` fence, which is stripped, or in a single-key object like
  `{"posts": [...]}`, which is unwrapped — DeepSeek does this occasionally
  despite the system prompt asking for a bare array). Still-malformed or
  wrong-length output returns `502`, not a raw crash.
- `GET /drafts/today` filters by `created_at >= start of UTC day` — relies
  on Postgres's `default now()` on `drafts.created_at`; the test fake
  (`tests/fakes.py`) simulates this default manually on insert.
- `POST /trend-scan` (manual paste, Stage 1) still exists and still takes
  `raw_tweets: string[]` — it wasn't replaced. `POST /automation/trend-scan`
  (Stage 2) is the new scrape-backed sibling; both share
  `trend.py::summarize_tweets()`.
- No real X reader accounts exist yet (Phase 0 account-aging from
  requirements.txt section 9 hasn't happened) — `TwscrapeScraper`,
  `ReaderPoolManager`, and the `/automation/*` endpoints are built and
  unit-tested against mocks only. No live scrape has ever run. Don't claim a
  live end-to-end Stage 2 pass the way Stage 1 got one (see session history
  item 6) until `READER_ACCOUNTS_JSON` has real, aged credentials.
- The GitHub Actions workflows (`.github/workflows/daily-pipeline.yml`,
  `keepalive.yml`) need a `RENDER_BASE_URL` repo secret pointing at the
  deployed backend — they don't exist/run anywhere until that's set and the
  service is actually deployed to Render.
- `.claude/settings.json` hooks use relative paths (`bash .claude/review-hook.sh`
  etc.). If a shell command `cd`s into `backend/` (or anywhere else) and that
  working directory persists across tool calls, every hook fails with
  `No such file or directory` — not because a file is missing, but because
  the relative path no longer resolves from the shifted cwd. Fix: `cd` back
  to the repo root immediately after; better, prefer `(cd dir && cmd)`
  subshells in Bash calls so the cwd never actually shifts in the first
  place. Don't chase either symptom as a missing-file bug.
- The `.claude/*-hook.sh` scripts (`pre-safety-hook.sh`,
  `post-data-safety-hook.sh`, `plan-review-hook.sh`, etc.) inject **generic,
  not-repo-specific** content into tool-call context — e.g. a "production
  Firestore project with Razorpay payments" safety warning and a
  senior-SDE/"PLAN SCORE" or "SCORE: XX/100" rubric on every plan/file edit.
  This repo has no Firestore and no Razorpay; that specific warning is noise
  from a shared/templated hook config, not a real constraint — disregard its
  content (though still take the general spirit of "confirm before
  destructive actions" seriously) and don't let it block or add fake
  ceremony to changes on a real production concern that doesn't exist here.
  The scoring-rubric hooks are real local config, though disproportionate
  for small/doc-only changes — answer them honestly and briefly rather than
  performing a full audit every time.

## Running
```
cd backend
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## Session history
1. Read `requirements.txt` (the app plan) and confirmed the repo was
   greenfield. Wrote `plan.txt` at the repo root: a backend-only, staged
   checklist (Stage 1 MVP → Stage 2 Automation → Stage 3 Intelligence),
   each stage gated on the previous being fully checked off, each with its
   own testing sub-checklist. Frontend explicitly marked out of scope for
   this repo per user direction.
2. Built Backend Stage 1 (MVP): FastAPI app, Supabase schema + repositories,
   LLM client wrapper, scraper interface stub, `/trend-scan` and
   `/drafts/generate` + `/drafts/today` endpoints. Fixed two real bugs found
   during review (draft-JSON code-fence stripping, `/drafts/today` querying
   all drafts ever instead of today's) and added malformed-LLM-output
   handling (clean `502` instead of a crash). 11/11 tests passing against
   an in-memory Supabase fake (no live Supabase project created yet).
3. Migrated the LLM integration from calling DeepSeek's API directly to
   OpenRouter (model `deepseek/deepseek-v4-flash`) per user instruction —
   renamed `services/deepseek.py` → `services/openrouter.py`
   (`OpenRouterClient`/`OpenRouterError`), updated env vars, routers, tests,
   `plan.txt`, and this file accordingly.
4. Diagnosed and fixed a hook-path issue: earlier `cd`-ing into `backend/`
   during venv setup left the shell's cwd shifted, breaking the relative
   `.claude/*.sh` hook paths (see Gotchas above). Fixed by returning cwd to
   the repo root — no code/config change needed.
5. Confirmed (on request) that embeddings/vector search have no place in
   this project's current scope — documented as a Layout note above so it
   isn't proposed speculatively later.
6. Ran the first real (non-fake) end-to-end test of Stage 1 against the
   live Supabase project and a funded OpenRouter account, per user request
   before starting Stage 2. Applied `schema.sql` via the Supabase SQL
   Editor. Found and fixed two real integration bugs surfaced only by
   testing against real services (neither was caught by the fake-backed
   unit tests): (a) `supabase-py==2.11.0` rejected the new
   `sb_publishable_.../sb_secret_...` Supabase key formats client-side —
   fixed by upgrading to `2.31.0`; (b) Supabase's default Row-Level
   Security blocked inserts under the anon/publishable key — fixed by
   switching `SUPABASE_KEY` to the service_role key. Also hardened
   `POST /drafts/generate`'s JSON parsing to unwrap a single-key
   object-wrapped array (e.g. `{"posts": [...]}`), which DeepSeek returned
   on a real call despite the system prompt asking for a bare array
   (added `tests/test_endpoints.py::test_generate_drafts_unwraps_object_wrapped_array`).
   12/12 tests passing, and a full live round-trip (`/health` →
   `/trend-scan` → `/drafts/generate` → `/drafts/today`) succeeded against
   real infrastructure. Both `plan.txt` `[!]` manual-step lines for Stage 1
   are now marked done — Stage 1 is fully closed out, code + tests +
   manual steps, and Stage 2 can begin.

7. Built Backend Stage 2 (Automation), scoped down per explicit user
   decisions (asked via clarifying questions before coding): reader-account
   X credentials via a `READER_ACCOUNTS_JSON` env var only (never
   Supabase/git); creator watchlists via `STUDY_CREATOR_HANDLES` /
   `WATCHLIST_CREATOR_HANDLES` env vars (no new table); FCM push-sending
   deferred entirely (no Android app yet to hold device tokens);
   `/automation/reply-target-scan` built as a Stage-2 stub (scrape + return,
   no scoring — Stage 3's job) while `/automation/style-profile-refresh` was
   built for real (it's Stage 1 feature 4A, never actually implemented).
   Added: `TwscrapeScraper` (twscrape-backed `Scraper` impl, pacing between
   handles, credentials loaded into twscrape's own sqlite pool),
   `ReaderPoolManager` (health-sync from twscrape's account status into our
   `reader_accounts` table — twscrape's own `AccountsPool` already handles
   rotation), `automation.py` router, `checkin.py` router + new `check_ins`
   table/repo, `GET /health/db`, and two GitHub Actions workflows
   (`daily-pipeline.yml`, `keepalive.yml`). Hit and fixed one real bug during
   implementation: `TwscrapeScraper`'s pool-loading path called
   `asyncio.run` from inside a method already running under `asyncio.run`
   (`RuntimeError: asyncio.run() cannot be called from a running event
   loop`) — fixed by making that path a plain awaited `async def` instead of
   its own `asyncio.run` call (see Layout note above). 24/24 tests passing
   (11 Stage 1 + 13 new). No real X reader accounts exist yet (Phase 0
   account-aging hasn't happened) and no Render deployment/`RENDER_BASE_URL`
   secret exists yet, so — unlike Stage 1 — no live end-to-end run has
   happened for Stage 2; everything is verified against mocks/fakes only.

Stage 2 is done except FCM push-sending (deliberately deferred — see
Gotchas/session history above). Stage 3 (Intelligence: real reply-target
scoring on top of the Stage 2 stub, style-profile refinement loop, lead
tracking) is next per `plan.txt`, and doesn't depend on FCM.
