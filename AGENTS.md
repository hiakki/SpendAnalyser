# Spend Analyser agent guide

## Scope and working agreement

- Work only within this repository. Preserve user changes and private statement data.
- Read the relevant implementation before editing. Use `apply_patch` for manual edits.
- Never restart an existing local or production server without explicit authorization.
- Verify runtime changes using an isolated database and separate ports, or an explicitly authorized reload. State any verification gaps.
- Do not commit or push unless requested. Include ready-to-run `git add .`, `git commit`, and `git push` commands after changes; explain if no remote exists.

## Architecture and checks

- `backend/app`: FastAPI, SQLAlchemy/SQLite, statement parsers, categorization, analytics.
- `frontend/app`: Next.js App Router pages; `frontend/components`: shared UI; `frontend/lib`: API client and formatting.
- `scripts/server.sh`: existing lifecycle commands. `deploy`, `quick`, and `restart` restart services; do not invoke implicitly.
- Type check: `cd frontend && npm run lint`.
- Production build: `cd frontend && SPENDA_NEXT_DIST_DIR=.next-qa npm run build` (keeps an existing `.next` build intact).
- Backend regression tests: `cd backend && .venv/bin/python -m unittest discover -s tests -v`.
- Use synthetic test fixtures. The legacy `scripts/server.sh test` reads a private sample PDF and is not the default agent check.
- For isolated QA use `SPENDA_DB_URL` pointing inside ignored `output/`, backend port 8107, frontend port 3107, and `NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8107` when building/running the QA frontend.

## Financial correctness and privacy

- Monetary values and debit/credit direction must survive parsing without guessing away uncertainty. Preserve original descriptions and parse warnings.
- Keep actual spending separate from transfers, investments, loan movements, and credit-card repayments. Do not double-count repayments as purchases.
- Do not collapse unrelated purchases merely because they share a date and amount. Reimports must be idempotent, and user categorization must survive automatic recategorization unless explicitly overridden.
- Do not enable LLM categorization, send transaction data to external services, seed demo data into the user's database, or reset their database without a specific request.
- Never index or include `backend/data`, `backend/samples`, uploads, financial exports, `.env`, secrets, browser session files, or test runtime data in commits, prompts, screenshots, or external requests. `.gitignore` and `.cbmignore` record the exclusions.
- Document known limitations rather than presenting classifications, refunds, or transfers as more certain than the implementation supports.

## Code discovery

Set `DO_NOT_TRACK=1` for Graft CLI calls. Project MCP registrations and Claude
hook settings already disable its telemetry through this environment variable.

Prefer the existing codebase-memory MCP graph when available: confirm project/generation, search/trace, read exact snippets, then check coverage for all evidence paths. Use Verify tier by default. For stale, partial, excluded, or unknown coverage, inspect the relevant source ranges. Use `rg` for literals, configuration, non-code files, or graph gaps. Graft provides an additional local structural index; its generated guidance below does not override coverage checks or privacy constraints.

## Skill routing

Use the globally installed gstack skills for relevant tasks: `/gstack-review` for review, `/gstack-investigate` for debugging, `/gstack-qa` for browser verification, and `/gstack-design-review` for visual QA. Read the selected skill before using it. Use relevant frontend and security skills when their scope matches the change; do not run every workflow indiscriminately.

This repository uses gstack team mode with the existing global installation. `bash scripts/gstack.sh doctor` checks availability. Run supported gstack commands through the wrapper so state stays in ignored `.gstack/`, with telemetry, artifact sync, and update checks disabled locally. Respect the project boundary if any skill requests machine-wide changes. Do not run upgrade/setup or external review agents implicitly.

<!-- graft:start -->
## Graft — repo context graph

This repo is indexed in `graft/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `graft map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `graft ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `graft grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `graft skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `graft callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `graft/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `graft ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `graft build` (deterministic,
no API key, $0).
<!-- graft:end -->
