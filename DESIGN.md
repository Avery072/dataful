# Dataful — Design

> Working design doc. Items marked **(stretch)** are planned only if time allows.

## The user & the problem

Smart, non-technical business users (marketing analyst, sales ops, small-business owner) who get a spreadsheet export and are stuck at three moments:

1. **"Where do I even look?"** — too many fields, unclear what a row is, unclear how sheets relate.
2. **"Can I trust this?"** — the dangerous problems are invisible: what a blank means, what one row represents (double counting), IDs that aren't unique. They find out in the meeting.
3. **"I have to redo this every month."** — cleanup is manual and unrepeatable.

These users live in Excel / Google Sheets. **The grid is their mental model, and they trust what they can see.** So the product keeps the data visible at all times and adds the smart features *onto* the grid rather than hiding rows behind cards and charts.

Many fixes need business context only the user has (does blank Discount mean 0?). So:

> **Principle: the tool finds the questions; the user answers them. The AI suggests, code changes the data, the user decides.**

## Make data beautiful

Golden's promise is data that's "easy, powerful, and beautiful." Beautiful here means calm and legible, not decorated:

- **Color only carries meaning.** A neutral base; color reserved for health states (healthy / gaps / trap) and previewed changes. No rainbow charts.
- **Numbers that read well.** Tabular, right-aligned figures; thousands separators; compact units (271k, $1.2M); dates shown one consistent way.
- **Typography does the hierarchy.** One clean sans-serif, a few sizes, plenty of whitespace; column group bands and header profiles instead of borders everywhere.
- **Small charts everywhere, big charts rarely.** Header histograms and inline bars make the shape of the data visible without leaving the grid.
- **Motion explains change.** Previewed fixes animate old → new so the user sees exactly what a decision does.
- **Light and dark themes**, accessible contrast, and a polished empty/loading state (the first screen sells it).

### Visual direction — warm, editorial, Notes-app feel

The dataset reads like a **note you're annotating**, not a BI console.

```
┌──────────────┬──────────────────────────────────────────────┬────────────────────┐
│ Datasets     │  Olympic athletes                    (serif) │  Margin notes      │
│              │  Each row is one athlete in one event,       │                    │
│ ● Olympics   │  1896–2016. 271,116 rows · 15 columns.       │  ▲ Team golds are  │
│   Employees  │  ─────────────────────────────────────────── │    counted once    │
│   Bookshop   │   WHO              WHERE       RESULT        │    per player.     │
│   MovieLens  │   Name   Sex  Age  Team  NOC   Medal         │    How should we   │
│              │   ▁▃█▅   ▆▃   ▂▆█  ...   ...   ...           │    count them?     │
│ + Add file   │   A Dijiang  M  24  China CHN  —             │    [Once] [Each]   │
│              │   ...                                        │                    │
└──────────────┴──────────────────────────────────────────────┴────────────────────┘
```

- **Paper, not chrome:** warm off-white page (dark mode: warm charcoal), thin hairline rules, almost no boxes or shadows.
- **Type:** serif for titles and the orientation sentence (editorial voice); clean sans for UI; tabular figures in the grid.
- **One warm accent** (Notes-style amber) for focus and the current question; muted terracotta for traps, ochre for gaps, sage for healthy/applied.
- **Sidebar like Notes:** datasets (and later, sheets) as a simple list.
- **Issues as margin notes:** annotations beside the data, like an editor's notes on a draft, rather than an alert panel. Questions are answered right in the margin.

## Built around trust

- **Read-only source.** The original file is never modified. Decisions are a layer on top that can be turned off, reordered, or removed at any time.
- **Confidence on every finding.** Each issue or hypothesis shows how sure the tool is (e.g. "certain: 24 cells are the text 'N/A'" vs "likely: blank Discount means 0"). Low-confidence findings are always asked as questions, never auto-fixed.
- **Every number is traceable** to the rows behind it and the decisions applied.
- **Per-org isolation (future):** each company gets its own data store / environment.

## Layout — one grid, side panels

```
┌─ athlete_events.csv · 271,116 rows · "each row = one athlete in one event" ────────┐
│                                                         ┌─ ISSUES (11) ───────────┐ │
│  ┌── Who ─────────────┐┌── Where ──┐┌── Result ┐         │ ▲ Team golds counted    │ │
│  Name   Sex  Age  Height Team   NOC  Medal               │   once per player       │ │
│  ▁▃█▅▂  ██▃  ▂▆█▃  ▃█▆▂ ▲1184  ●230 ◐85% NA              │ ◐ Height missing 22%    │ │
│  ──────────────────────────────────────────────          │ ▲ Team has 1,184 values │ │
│  A Dijiang  M  24   180  China  CHN  ░NA░                │ ...                     │ │
│  A Lamusi   M  23   170  China  CHN  ░NA░                ├─ QUESTION 1 of 4 ───────┤ │
│  Aaby       M  24  ░NA░  Denmark DEN ░NA░                │ "Should a team win      │ │
│  ...                                                     │  count once?"           │ │
│  [Group by ▾]  [Count: rows ▾]  [Filter: Medal = Gold ×] │ [Once] [Per athlete]    │ │
└──────────────────────────────────────────────────────────┴─────────────────────────┘
```

### See the data
- **The whole dataset is scrollable** — virtualized grid, server-side paging through DuckDB; spreadsheet-style sort, filter, search.
- **Profile in the column headers** — mini histogram / top values + a health marker (● healthy, ◐ gaps, ▲ trap).
- **Column group bands** (Who / Where / When / What / Measures) above the headers — the field map, built into the grid. AI suggests the groups.
- **One-line orientation** in the title bar: what one row represents.
- **Row detail panel** — click a row to see the full record vertically (for wide tables). **(stretch)**

### Find problems
- **Issues panel** — every detected issue at once, ranked by impact: *changes your numbers* → *missing data* → *formatting*.
- **Highlighted cells** — like spell-check underlines: `NA`-as-text shaded, outliers marked, near-duplicates underlined. Clicking one explains it and jumps to its question.
- **Clicking an issue filters the grid** to the affected rows.

### Decide
- **Facts get one-click fixes** (e.g. `"NA"` is text → mark missing). **Judgment calls become questions**, asked one at a time, with "Not sure — explain more."
- **Live preview** — before you commit, changed cells show in green with the old value crossed out.
- **Editing a cell becomes a rule** — "Apply to all 3 rows like this?" → saved as `merge_values`. **(stretch)**
- Every answer is saved to the **decision list** (readable + JSON), which can be re-applied to next month's file.

### Explore
- **Group by** (pivot-table style): pick a column → grid collapses into groups with counts / sums.
- **Count-unit picker** — "count rows / distinct athletes / medals" puts the double-counting trap right in the controls. Uses the decisions automatically.
- **Chart button** — turn the current grouped view into a chart (type chosen from column roles); click a bar → back to its rows. **(stretch)**
- **Worth-a-look** — a short list in the side panel of the strongest relationships found by code (see below). **(stretch)**

### Export
Clean CSV + the decision list.

## Architecture

```
React + Vite (UI: grid, panels)
      │  JSON
FastAPI (Python)
  ├─ load/normalize  → DuckDB tables (CSV; Excel sheets via openpyxl)
  ├─ profile         → pure SQL: types, blanks, distinct, roles, issue detectors
  ├─ rows            → paged / sorted / filtered / grouped queries for the grid
  ├─ operations      → fixed vocabulary, each compiles to SQL; preview + apply
  ├─ relationships   → pure SQL/stats: ranked "worth a look" findings (stretch)
  └─ ai              → Claude: orientation, column groups, question wording (2–3 calls/dataset)
```

**No AI in the data path.** Every number on screen comes from a query the app ran. If the AI call fails, the app still works with plainer wording.

### Normalize
Fix encoding & line endings, sniff delimiter/header, each Excel sheet → one table.

### Profile (code only)
Per column: type, % missing, distinct count, top values, range, distribution.
Column **role** inferred by rules: `identifier` · `category` · `measure` · `time` · `text` · `geo`.

**Issue detectors (code)** — general families that work on any table, not dataset-specific rules:

| Family | Business / CRM example | How it's detected |
|---|---|---|
| Duplicate rows | Same record exported twice (Olympics: 1,385 exact copies) | Hash of all non-ID columns |
| Duplicate records | "Acme Inc" vs "ACME Corp."; same person with two IDs | Same email/phone/name+key fields after normalizing |
| Double counting | Deal repeated per contact / product line; team medals | Same outcome repeated across rows with different IDs |
| Inconsistent categories | "Closed Won" / "closed-won" / "Won"; US / USA | Group by case/punctuation/whitespace-normalized value |
| Missing in disguise | `NA`, `N/A`, `-`, `TBD`, `asdf`, `000-000-0000` | Known placeholder list + suspicious repeated values |
| Defaults posing as data | Lead Source = "Other" for 60%; everything on Jan 1 | One value far more common than expected; date/number spikes |
| Format damage | `$1,200` as text, lost leading zeros, `1.2E+15`, mixed dates | Type detection per column |
| Impossible / contradictory | Negative phone/age; open deal with past close date; won deal at $0 | Role-based rules |
| Fake unique IDs | Email used by many people | ID-looking column that repeats |
| Stale data | Last activity 3 years ago | Age of the newest "updated" date |
| Test / internal records | `@ourcompany.com`, "Test Account" | Pattern match → always a question |
| Mixed units | USD + EUR, `12%` vs `0.12` | Mixed formats within one column |

**Duplicate / entity matching is code, not AI.** Work on *distinct values*, not rows (271k rows → 1,184 distinct Team values). Normalize (case, punctuation, suffixes like Inc/Corp), group exact matches, then fuzzy-match only within blocks (same first letters / shared token) using DuckDB's built-in string similarity, which avoids comparing every value to every other. The AI may see at most the top ~10 candidate groups to word a question; the confirmed rule is applied to every row with SQL. Token cost is flat regardless of row count.

**Guarding against wrong merges** (similar names ≠ same thing: two Springfields, John Smith Sr./Jr., Acme Seattle vs. Acme Portland):
- **Never auto-merge.** Fuzzy matches are at most *likely*; only identical rows can be *certain*, and even those wait for a click.
- **Show evidence both ways.** Each candidate group lists what agrees (same Library ID, same email) and what conflicts (different city, different department). Any conflict lowers confidence.
- **Pick members, not all-or-nothing.** The user can untick individual values in a group.
- **Show the impact first.** "Merging changes Acme's revenue from $40k to $95k · affects 37 rows."
- **Flag instead of merge** is always an option: mark as "possible duplicate" without changing any numbers.
- **"Keep separate" is remembered** as a decision too, so it isn't asked again next month.
- **Reversible.** The source is read-only; any merge can be toggled off or removed.
- Merging *labels* (category spellings) is lower risk than merging *records* (people/companies); record merges need a strong shared key (email, ID) to reach *likely*.

**Hypotheses (AI):** what one row represents, double-counting risk, what a blank likely means — always phrased as a question to the user and checked with a query.

### Operations (fixed vocabulary)

| op | example | plain English |
|---|---|---|
| `mark_missing` | Salary `["N/A"]` | Treat 'N/A' as missing |
| `fill_blank` | Discount → 0 | Blank discount means no discount |
| `change_type` | Phone → text | Phone is an identifier, not a number |
| `split_column` | Department_Region on `-` | Split into Department and Region |
| `merge_values` | "Idle Hour Library YYY" → "Idle Hour Library" | These are the same |
| `remove_duplicates` | 1,385 identical Olympics rows | Keep one copy of identical rows |
| `merge_records` | Same email under 2 Employee IDs → keep newest | These records are the same person/company |
| `keep_separate` | "Acme Seattle" ≠ "Acme Portland" | These look alike but are different (don't ask again) |
| `flag_duplicates` | 43 employees with same name+age+dept | Mark as possible duplicates; numbers unchanged |
| `combine_columns` | BookID1 + BookID2 | Rebuild the book ID |
| `set_count_unit` | (Games, Event, Medal) | Count a team win once |
| `drop_rows` / `flag_rows` | Age is blank | Exclude rows with no age |
| `stack_tables` | Sales Q1–Q4 | Combine the quarterly sheets |

Decision list = ordered JSON of these ops (+ the user's reason). Deterministic and replayable.

### Worth a look — relationship finder (stretch)

| pair of roles | statistic | example |
|---|---|---|
| category × measure | effect size (η²) | Salary differs most by Department |
| measure × measure | correlation | Height ↔ Weight |
| category × category | Cramér's V | Sport ↔ Sex |
| time × measure/count | trend / biggest change | Women's participation since 1960 |
| category alone | concentration (top-N share) | Top 5 books = 40% of sales |
| missingness × anything | missing-rate by group | Height is missing mostly before 1960 |

Guards: minimum group size, skip ID columns, "related ≠ caused." If nothing is strong, say so honestly ("no strong patterns — this data may be generated").

## Scope

| Tonight (MVP) | Stretch | README "more time" |
|---|---|---|
| CSV + Excel upload (each sheet = a table) + bundled demo datasets | Row detail panel | Auto-detect relationships between sheets |
| Messy CRM deals export in `dataset/extensions/` | | |
| Grid: paging, sort, filter, header profiles, group bands | Edit-a-cell → rule | Re-apply decisions to next month's upload |
| Issue detectors + issues panel + cell highlights | Chart button + drill-down | Collaboration / saved projects |
| AI orientation + column groups + questions | Worth-a-look list | Natural-language questions |
| Question flow with live preview → decision list | | |
| Group by + count-unit picker | | |
| Export CSV + decision list | | |

## Decisions

| Topic | Decision |
|---|---|
| Name | **Dataful** |
| Confidence | 3 levels: **certain / likely / guess** (no fake-precise %) |
| Grid view | Toggle **Original ↔ With my decisions** |
| Skipped questions | Stay **unresolved**; affected numbers are marked |
| AI permissions | AI only *proposes*; an operation runs **only when the user clicks Yes** |
| State | Decisions saved as local JSON files per dataset (`backend/data/decisions/`) + export as JSON; "Reset this dataset" clears them |
| Grid | TanStack Table + virtualization (full styling control) |
| Model | Claude Sonnet |
| API key | **Bring your own** (`backend/.env`); without a key the app runs in no-AI mode with template wording |
| Hosting | Local only |
| Excel | Each sheet loads as its own table (sidebar); linking sheets is future work |

## Later
- Video script / demo story (owner: me)
- Unit tests for detectors + operations
- Prompt-injection talking point: the fixed op list + schema validation + Yes-gate keep the AI from doing anything the user didn't approve
