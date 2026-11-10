# Dataful frontend — dev notes

Vite + React + TypeScript. TanStack Table (column model, resizing) + TanStack Virtual (row virtualization) + React Query (fetch cache). Plain CSS with tokens; no component library.

## Run

```bash
# backend (port 8000)
cd backend && uv run uvicorn app.main:app --port 8000

# frontend (port 5173, proxies /api → :8000; override with DATAFUL_API=http://localhost:8001)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. `npm run build` type-checks and builds to `dist/`.

**Mock mode (no backend):** `VITE_MOCK=1 npm run dev` serves a small in-memory imitation of the Olympics demo from `src/mock/`. It is lazy-loaded and never used unless that flag is set.

## Structure

```
src/
  api.ts                 typed client mirroring API.md (+ USE_MOCK switch)
  format.ts              number/percent/cell formatting, issue sorting
  hooks/
    useDataset.ts        React Query hooks, query keys, decision mutations (invalidate ["ds", id])
    useRowPages.ts       on-demand paging (200 rows/page) for the virtual grid
  components/
    Sidebar.tsx          Notes-style dataset list, Excel sheets nested by workbook, upload
    EmptyState.tsx       first screen
    Workspace.tsx        page header, lede, AI review line, toolbar, grid/group area, margin
    Grid.tsx             virtualized grid, group bands, flagged cells
    HeaderProfile.tsx    header: role glyph, mini chart, missing %, health marker
    ColumnCard.tsx       header popover (top values → filter, sort, group by)
    CellTooltip.tsx      spell-check style explanation for flagged cells
    charts.tsx           MiniHistogram, TopValues (hand-made SVG)
    GroupView.tsx        group-by controls + table with inline bars and count-unit toggle
    Margin.tsx           issues as margin notes, severity tabs; collapsible to a rail (remembered per browser)
    IssueNote.tsx        one note: evidence, Fix it / question → preview → Yes
    DecisionList.tsx     decisions with enable toggle + remove; `broken` decisions show their error + Remove
    ErrorBoundary.tsx    region error boundaries + calm error card (Reload / Reset dataset with in-app confirm)
    Glyphs.tsx, Num.tsx  health/role glyphs (+ plain-words legend), icons, animated numbers
  mock/mockApi.ts        DEV-ONLY fixtures
```

Data flow: every decision mutation invalidates all `["ds", id, …]` queries (profile, issues, rows pages, group), so the grid, headers and notes refresh together. Nothing is sent to the AI until "Ask Dataful to review" is clicked.

## Robustness (v2)

- Decisions may have `op: null` ("keep as is") or be `broken`; always read the op kind via `opKind(d)` from `api.ts`, never `d.op.op`.
- The workspace, the grid/group area and the margin each sit in an `ErrorBoundary`; one failing region shows an error card instead of blanking the app. "Reset this dataset" calls `POST /reset`.
- v2 fields (`rows_current`, `row_numbers`, `total_unfiltered`, `excluded_rows`, `caveats`, `broken`) are optional in the types; the UI falls back when a v1 server omits them.
- Question options are cleaned client-side (`cleanOptions` in IssueNote): invalid entries dropped, near-duplicate labels merged, and exactly one "Not sure — decide later" (= skip) is rendered by the note itself.
