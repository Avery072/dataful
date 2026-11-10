# Dataful API contract (MVP)

Backend: FastAPI on `http://localhost:8000`, all routes under `/api`. Frontend (Vite, port 5173) proxies `/api` → 8000.
All JSON. Errors: `{"detail": "message"}` with a 4xx/5xx status.

## Types

```ts
type Role = "identifier" | "category" | "measure" | "time" | "text" | "geo" | "boolean";
type Health = "healthy" | "gaps" | "trap";
type Confidence = "certain" | "likely" | "guess";
type Severity = "numbers" | "missing" | "format";   // sort order: numbers → missing → format
type IssueStatus = "open" | "resolved" | "kept" | "flagged" | "skipped";

interface Dataset {
  id: string;            // slug, e.g. "olympics-athlete-events" or "bookshop-sales-q1"
  name: string;          // human title, e.g. "Olympic athletes"
  file: string;          // original file name
  sheet: string | null;  // Excel sheet name, null for CSV
  rows: number;
  columns: number;
  demo: boolean;         // bundled demo vs uploaded
}

interface Column {
  name: string;
  type: "integer" | "decimal" | "text" | "date" | "boolean";
  role: Role;
  missing: number;           // count of missing (incl. disguised: "NA", "N/A", "", "-", "TBD"...)
  missing_pct: number;       // 0..1
  distinct: number;
  top_values: { value: string; count: number }[];        // up to 8
  histogram: { start: number; end: number; count: number }[] | null;  // numeric/date, ~12 bins
  min: string | number | null;
  max: string | number | null;
  health: Health;
  issue_ids: string[];
}

interface Orientation {
  row_meaning: string;                 // "Each row is one athlete competing in one event at one Games."
  summary: string;                     // one editorial sentence: span, coverage
  groups: { name: string; columns: string[] }[];   // Who / Where / When / What / Measures ...
  source: "ai" | "rules";
}

interface Profile {
  dataset: Dataset;
  columns: Column[];
  orientation: Orientation;            // rules-based until AI review runs
  ai_reviewed: boolean;
}

interface Evidence { for: string[]; against: string[] }

interface Option { label: string; op: Op | null; description?: string }   // op null = "keep as is"

interface Issue {
  id: string;
  family: string;            // "duplicate_rows" | "duplicate_records" | "double_counting" | "inconsistent_categories"
                             // | "disguised_missing" | "default_values" | "format_damage" | "impossible_values"
                             // | "fake_unique_id" | "combined_field" | "outliers" | "constant_column" | ...
  title: string;             // short, plain English: "1,385 rows are exact copies"
  detail: string;            // 1–2 sentences, why it matters
  severity: Severity;
  confidence: Confidence;
  columns: string[];
  affected_rows: number;
  evidence: Evidence;
  kind: "fix" | "question";  // fix = one-click fact; question = needs the user's judgment
  question: string | null;   // for kind=question: "Should a team win count once, or once per athlete?"
  options: Option[];         // fix: [{label:"Fix it", op}], question: 2–4 options
  status: IssueStatus;
  decision_id: string | null;
  source: "rules" | "ai";
}
```

## Operations (fixed vocabulary)

```ts
type Op =
  | { op: "mark_missing"; column: string; values: string[] }
  | { op: "fill_blank"; column: string; value: string | number }
  | { op: "change_type"; column: string; to: "text" | "integer" | "decimal" | "date" }
  | { op: "split_column"; column: string; sep: string; into: [string, string] }
  | { op: "merge_values"; column: string; from: string[]; to: string }
  | { op: "combine_columns"; columns: string[]; sep: string; into: string }
  | { op: "set_count_unit"; columns: string[]; label: string }      // dedupe key used by Group-by "count"
  | { op: "drop_rows"; where: Filter[] }
  | { op: "flag_rows"; where: Filter[]; label: string }
  | { op: "remove_duplicates"; columns: string[] | null }            // null = all columns
  | { op: "merge_records"; key: string[]; keep: "first" | "last" }
  | { op: "keep_separate"; column: string; values: string[] }        // no data change; remembered
  | { op: "flag_duplicates"; key: string[]; label: string };

type Filter = { column: string; op: "=" | "!=" | "<" | ">" | "is_missing" | "not_missing" | "contains" | "in"; value?: any };

interface Decision {
  id: string;
  op: Op;
  plain: string;             // "Treat 'N/A' in Salary as missing"
  issue_id: string | null;
  reason: string | null;     // user's chosen option label
  enabled: boolean;
  created_at: string;
}
```

Every op compiles to SQL over the previous view. The source table is **never modified**: view_n = op_n(view_{n-1}), starting from the raw table.

## Endpoints

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/health` | | `{ ok: true, ai_enabled: boolean, model: string \| null }` |
| GET | `/api/datasets` | | `Dataset[]` (demo datasets loaded at startup) |
| POST | `/api/datasets/upload` | multipart `file` (.csv, .tsv, .xlsx) | `Dataset[]` (one per Excel sheet) |
| GET | `/api/datasets/{id}/profile` | `?view=original\|decisions` (default decisions) | `Profile` |
| GET | `/api/datasets/{id}/issues` | | `Issue[]` sorted severity → confidence |
| GET | `/api/datasets/{id}/rows` | `offset, limit (≤500), sort, dir=asc\|desc, filters` (JSON `Filter[]`), `search`, `issue_id`, `view` | `{ total, columns: string[], rows: any[][], flags: { [rowOffset: number]: { [column: string]: string /*issue id*/ } } }` |
| POST | `/api/datasets/{id}/preview` | `{ op: Op }` | `{ affected_rows, impact: string, changes: { column, before, after, count }[] /*≤20*/, rows_before: number, rows_after: number }` |
| GET | `/api/datasets/{id}/decisions` | | `Decision[]` |
| POST | `/api/datasets/{id}/decisions` | `{ op: Op, issue_id?: string, reason?: string }` | `Decision` (issue status updated) |
| PATCH | `/api/datasets/{id}/decisions/{did}` | `{ enabled: boolean }` | `Decision` |
| DELETE | `/api/datasets/{id}/decisions/{did}` | | `{ ok: true }` (issue back to open) |
| POST | `/api/datasets/{id}/issues/{iid}/skip` | | `Issue` (status "skipped", stays unresolved) |
| POST | `/api/datasets/{id}/review` | | `{ orientation: Orientation, issues: Issue[] }` — **only AI call site**; 409 if no API key |
| GET | `/api/datasets/{id}/group` | `by, measure?, agg=count\|sum\|avg\|count_distinct, use_count_unit=true\|false, view, filters` | `{ by, agg, measure, count_unit: string \| null, groups: { key, value, rows }[] /*≤50, sorted desc*/ }` |
| GET | `/api/datasets/{id}/export.csv` | `view` | CSV file |
| GET | `/api/datasets/{id}/decisions.json` | | decision list file |

## AI rules
- Called only from `POST /review` (user clicks "Ask Dataful to review").
- Input: column profiles + ≤10 sample rows + ≤10 candidate groups per issue. Never the full table.
- Output via tool use / JSON schema; any proposed op is validated against the Op vocabulary and **re-checked with SQL** before it is shown. AI never applies anything; ops run only when the user posts a decision.
- No key → `/review` returns 409, the app works with rules-based wording.

## v2 changes (after first blind user test)

**Persistence**
- Decisions are saved to `backend/data/decisions/{dataset_id}.json` after every change and loaded at startup. Uploaded files are copied to `backend/data/uploads/` and re-registered at startup.
- Loading is defensive: a decision that fails validation or fails to compile against the current view is kept in the file but marked `enabled: false, broken: true` (with `error: string`) instead of breaking the dataset.
- New: `POST /api/datasets/{id}/reset` → clears all decisions for that dataset → `{ ok: true }`.

**Decisions**
- `Decision` gains `broken?: boolean`, `error?: string`.
- `POST /decisions` with an `issue_id` that already has a decision (enabled or not) **replaces** that decision (same position in the chain) instead of adding a second one. Re-answering a question is always safe.

**Issues are re-detected on the current view** (after enabled decisions), cached per decision version.
- Issue ids are **stable** (derived from family + columns + key values), so decisions keep pointing at their issue.
- Issues resolved by a decision stay listed with status `resolved` / `kept` / `flagged`; all counts (title, detail, affected_rows, evidence) come from the current view — the title and detail must use the same numbers.
- Options never reference columns that don't exist in the current view.
- Evidence text is generated from queried values only (no estimated ranges).

**Datasets / rows / group**
- `Dataset` gains `rows_current: number` (rows after enabled decisions). Sidebar shows `rows_current`.
- `/rows` returns **typed JSON values**: numbers as numbers, booleans as booleans, dates as ISO strings, missing (incl. disguised-missing that has been marked) as `null`. Response gains `total_unfiltered: number` and each row's absolute row number via `row_numbers: number[]`.
- `/group` response gains `excluded_rows: number` (rows skipped because the group key or measure is missing) and `caveats: string[]` (plain-English warnings, e.g. "211 rows with no Age are not counted", "Amount mixes USD and EUR — totals combine both currencies").
- Count-unit wording: a `set_count_unit` decision has a plain `label` (e.g. "medals") and `plain` text like "Count a shared team win once"; never expose raw column tuples in UI text.

**Wording**
- One "Not sure — decide later" option per question (= skip, stays unresolved). No near-duplicate options.
- Grammar-check generated text ("an Email", plural agreement).
