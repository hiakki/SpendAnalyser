# Spend Analyser

A local-first personal finance app. Drop in bank or credit-card statements (PDF / XLS / XLSX / CSV),
get them parsed, auto-categorized (rules + optional LLM), and explore via dashboards,
budgets, recurring-subscription detection, and anomaly flags.

```
spendAnalyser/
├── backend/     FastAPI + SQLite + pdfplumber + pandas
└── frontend/    Next.js 16 + React 18 + Tailwind + Recharts
```

## Quick start

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The DB and uploads land in `backend/data/`. On first run, a set of seed
categories and ~120 rules covering common Indian merchants are loaded.

Optional LLM fallback — review the privacy section before opting in. Copy
`.env.example` to `.env` and set:

```ini
SPENDA_LLM_ENABLED=true
SPENDA_LLM_PROVIDER=openai           # or gemini
SPENDA_OPENAI_API_KEY=sk-...
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

The Next.js dev server proxies `/api/*` to `http://127.0.0.1:8000` — no CORS pain.

### 3. Try it out

Open <http://localhost:3000> and either:

- **Settings → Generate 6 months of demo data** for an instant dashboard, OR
- **Upload** → create an account (e.g. "HDFC Savings", "ICICI Amazon Pay CC") → drop a PDF/XLS/CSV statement.

## What's included

| Page         | What it does |
|--------------|--------------|
| **Dashboard**    | KPIs (spend / income / net / #tx), monthly trend, category pie, top merchants, recent activity |
| **Transactions** | Filterable table (search, account, category, direction, date range), inline category edit, CSV export |
| **Upload**       | Drag-drop PDF/XLS/CSV per account. Deduped by `(account, date, amount, description)` fingerprint |
| **Budgets**      | Per-category monthly budgets with progress bars; `*` for "recurring every month" |
| **Recurring**    | Detects subscriptions: similar merchant + monthly cadence + stable amount |
| **Anomalies**    | Per-category z-score flags for unusually large spend |
| **Settings**     | Manage accounts, rules (substring/regex → category), re-categorize all, seed demo, reset DB |

## How the parser works

Complementary strategies inside `backend/app/parsers`:

1. **Table extraction** — `pdfplumber.extract_tables()` for PDF, `pandas.read_excel`/`read_csv` for spreadsheets.
   For each table we auto-detect a header row containing tokens like `Date`, `Description`, `Debit`,
   `Credit`, `Amount`, then map columns to a common shape.
2. **Positioned columns** — bank PDFs with a bordered heading and borderless rows use the
   heading's date, description, withdrawal, and deposit column bounds. Wrapped descriptions
   are preserved, and running balances are excluded from transaction amounts.
3. **Text fallback** — for credit-card PDFs without proper tables, we regex over each line:
   `DD MMM/MM/YYYY` + free text + `amount` + optional `CR`/`DR`.

Excel readers detect the workbook contents: `xlrd` handles legacy XLS and `openpyxl`
handles XLSX, including files with a mismatched extension. Both are runtime dependencies.
Image-only scanned PDFs still require OCR, which is not included. An unsupported text
layout is reported separately from a PDF with no readable text.

ICICI UPI, IMPS, and NEFT remarks are extracted separately from counterparties,
bank-routing fields, and reference IDs. Imports and both recategorization actions
use the same label-first classifier. Unrecognized explicit notes stay in Other
with a **Needs review** source instead of being overridden by a merchant guess.

Confirmed meanings can be saved through `GET/POST /rules/labels` and
`DELETE /rules/labels/{id}`. POST accepts `account_id`, `label`, `direction`
(`debit` or `credit`), and `category_id`; it updates an existing mapping for the
same account, normalized label, and direction. These mappings take precedence
over general rules, including for bank-generated notes, and stay in the local
database. Personal names and meanings should not be hardcoded into source.

After confirming mappings, use `POST /admin/reparse-merchants?account_id=ID`
to repair extracted notes, counterparties, and automatic categories for that
account. It preserves manual classifications and existing notes, and does not
change dates, amounts, descriptions, or import fingerprints. Ordinary
`POST /rules/recategorize?account_id=ID` also respects labels and manual choices.
Both actions apply to all accounts when `account_id` is omitted.

Built-in keyword rules match word boundaries; custom substring and regex rules
retain their configured behavior. Auto-generated merchant rules respect payment
direction. Legacy built-in rules that equated a bare loan reference or person
name with lending are ignored; borrowing and repayment require confirmation.

Parsed transactions carry a fingerprint based on their account, date, amount,
and normalized description so overlapping statement imports can be identified.
Every parsed row gets:

- a 32-char `fingerprint` so re-uploads of overlapping months don't duplicate
- a `merchant` guess (UPI refs / numeric IDs stripped out)
- a category from the **rules** layer (fast, deterministic) or, if enabled and unmatched,
  the **LLM** layer (cached per merchant in `llm_cache`).

## Financial interpretation and current limits

Use this version for INR statements. Reports add stored amounts without exchange
rate conversion or grouping by currency: ₹100 and US$100 would produce a misleading
combined total of 200. Generic CSV/table imports currently default to INR even
when the selected account has another currency. Foreign-currency reporting is
not supported.

Dashboard inflows and outflows describe cash movement, not verified income and
consumption. Transfers, credit-card repayments, investments, and refunds need
review before drawing spending conclusions. An unfamiliar one-off merchant or
person stays in Other; a name alone is not evidence of a loan. Existing records
previously assigned by the old name heuristic are not rewritten automatically.

Duplicate imports preserve previously inserted rows. Whole-statement atomicity
is not guaranteed when optional LLM categorization is enabled: its cache writes
currently commit through the upload's database session. LLM fallback remains
disabled by default. Identical payments within one statement retain their
occurrence counts, but indistinguishable payments split across partial statements
can require manual reconciliation.

## Adding your bank

If a particular statement extracts 0 rows or misses columns:

1. Check the **Upload page** — each statement row stores `parse_log` and warnings (see API `/upload/statements`).
2. Add a substring rule under **Settings → Rules** to categorize a recurring merchant.
3. If columns are non-standard, extend `backend/app/parsers/table.py` (the `DATE_COLS`, `DEBIT_COLS`, etc.
   sets) — it's a single source of truth used by both PDF tables and XLS/CSV.

## API

All routes live under `/api/*` (proxied by Next.js to FastAPI). Explore the live OpenAPI docs at
<http://127.0.0.1:8000/docs>.

Notable endpoints:

- `POST /upload` (multipart: `file`, `account_id`) → parse + categorize + insert
- `GET /transactions?start&end&account_id&category_id&direction&q`
- `PATCH /transactions/{id}` `{ category_id, note, merchant }`
- `GET /analytics/{summary,by-category,by-month,top-merchants,by-account}`
- `GET /budgets/status?month=YYYY-MM`
- `GET /recurring`
- `GET /anomalies?z_threshold=2.5&min_amount=500`
- `GET /export/csv`
- `POST /admin/{reset,seed-mock,seed-categories}`
- `POST /rules/recategorize?only_uncategorized&overwrite_user`

## Privacy

PDFs, parsed rows, and the SQLite database are stored in `backend/data/` by
default. LLM fallback is off by default. If enabled, it sends categorization text
to the configured provider; this can include the merchant, transaction description,
and UPI label, rather than only a cleaned merchant name. Keep it disabled when
those details must remain local.

Private data, sample statements, environment files, generated graphs, dependencies,
and browser/runtime artifacts are excluded from Git and codebase-memory indexing.
Use synthetic fixtures for tests and screenshots. Local ignore rules protect
normal staging; they do not prevent deliberate `git add -f` or copying data elsewhere.

## AI development tools

`AGENTS.md` documents the architecture, financial invariants, privacy rules, and
verification workflow; `CLAUDE.md` points Claude Code at the same rules.

Graft uses the globally installed `graft` CLI. Its deterministic source index is
already initialized; refresh and inspect it from the repository root:

```bash
export DO_NOT_TRACK=1
graft build --only-dir backend/app --only-dir backend/tests --only-dir frontend/app --only-dir frontend/components --only-dir frontend/lib
graft check
graft map
graft ask "How are transactions categorized?" --source
```

The explicit source directories keep financial data outside the index; retain
these flags when rebuilding. `--deep` is optional and uses an external LLM;
it is not needed for normal graph lookup and is not enabled here. The index is a
local ignored cache, so each checkout builds its own copy. Graft MCP registration
is project-local in `.mcp.json` (Claude), `.codex/config.toml` (Codex), and
`opencode.json`; a new trusted project session is needed for an agent to load it.
Claude's generated hooks refresh context after edits. No global agent settings
were changed.

gstack is configured in optional team mode, reusing the installed global skills
instead of copying a second distribution into this repository:

```bash
bash scripts/gstack.sh doctor
bash scripts/gstack.sh browse help
```

The wrapper resolves the installed tool and puts its state and temporary files in
ignored `.gstack/`. Defaults in `scripts/gstack-config.yaml` disable telemetry,
artifact sync, and update checks. It also supports `start`, `end`, and `learn`
for skill lifecycle commands. Read the applicable skill before running it.

## Verification without disturbing a running app

```bash
cd backend
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
cd ../frontend
npm run lint
SPENDA_NEXT_DIST_DIR=.next-qa npm run build
```

The backend suite generates real XLS, XLSX, and multi-page PDF fixtures and checks
multipart uploads, debit/credit amounts, wrapped descriptions, and duplicate reimports.
Development dependencies add fixture writers; production only needs `requirements.txt`.

`SPENDA_NEXT_DIST_DIR` selects a separate Next.js output directory. For full QA,
use a synthetic database under ignored `output/`, override `SPENDA_DB_URL` and
`SPENDA_UPLOAD_DIR`, and run separate backend/frontend ports (for example
8107/3107). Set `NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8107` for both the QA
frontend build and runtime. Existing servers must not be restarted without
explicit authorization. The older `scripts/server.sh test` reads a private
sample statement; prefer the synthetic regression suite above.
