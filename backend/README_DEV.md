# Dataful backend (dev notes)

## Run

```bash
cd backend
uv sync
uv run uvicorn app.main:app --port 8000      # API at http://localhost:8000/api
```

Demo datasets (Olympics, employees, CRM deals, MovieLens, both Bookshop workbooks) load at startup;
profiling + issue detection warm up in a background thread (Olympics ~3s).

Regenerate the synthetic CRM export: `uv run python scripts/make_crm_deals.py`.

## Environment

`backend/.env` (see `.env.example`; the repo-root `.env` is also read):

- `ANTHROPIC_API_KEY` — optional. Without it everything works with rules-based wording and
  `POST /api/datasets/{id}/review` returns 409. With it, review calls `claude-sonnet-5-5`.

## Module map

| Module | Role |
|---|---|
| `app/main.py` | FastAPI routes (thin), CORS, startup, error mapping (400 bad op, 404, 409 no key, 502 AI failure) |
| `app/service.py` | Use cases behind routes: profile JSON, decisions, rows + flags, review |
| `app/store.py` | In-memory dataset registry, decisions, the single locked DuckDB connection |
| `app/loader.py` | Normalize (encoding, CR/CRLF line endings) and load CSV/TSV; each Excel sheet → one table |
| `app/sql.py` | Quoting, literals, missing/junk tokens, number/date parsing expressions |
| `app/profile.py` | Per-column type, role, missing, distinct, top values, histograms (pure SQL) |
| `app/detectors/` | Issue families: `duplicates` (rows, records, double counting, fake IDs), `categories` (label variants), `values` (disguised missing, junk, defaults, impossible, outliers, gaps, constant), `formats` (text numbers/dates, epoch, whole decimals, combined/split fields), `business` (test records, currencies, contradictions, stale) |
| `app/issues.py` | Detection cache, issue status from decisions, grid cell flags |
| `app/ops.py` | Fixed op vocabulary: validation, plain English, op → SQL |
| `app/views.py` | Decision chain (view_n = op_n(view_{n-1})) materialized per version; rows, group, preview, export |
| `app/orientation.py` | Rules-based "each row is…", summary, column groups |
| `app/ai.py` | The only Claude call site; output schema-validated, ops re-validated and re-checked with SQL |

All source tables are stored as VARCHAR plus a hidden `__rid`; types are inferred, so messy cells
("NA", "$1,200") stay visible until the user decides. The source table is never modified.
