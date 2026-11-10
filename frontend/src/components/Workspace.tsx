import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, opKind, type Decision, type Filter, type Issue, type View } from "../api";
import { fmtCell, fmtInt, isMissing } from "../format";
import { qk, useDecisions, useHealth, useIssues, useProfile } from "../hooks/useDataset";
import { Grid } from "./Grid";
import { GroupControls, GroupView, type GroupState } from "./GroupView";
import { Icon } from "./Glyphs";
import { DatasetErrorCard, ErrorBoundary } from "./ErrorBoundary";
import { Margin } from "./Margin";
import { Num } from "./Num";

const OP_LABEL: Record<string, string> = { "=": "is", "!=": "is not", "<": "<", ">": ">", contains: "contains", in: "in", is_missing: "is missing", not_missing: "is not missing" };

function useDebounced<T>(v: T, ms: number) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const t = setTimeout(() => setD(v), ms);
    return () => clearTimeout(t);
  }, [v, ms]);
  return d;
}

/** Plain wording for the count-unit toggle; never shows raw column tuples. */
export function countUnitText(d: Decision | undefined): { label: string; plain: string } | null {
  if (!d || !d.op || d.op.op !== "set_count_unit") return null;
  const label = (d.op.label || "records").trim();
  const raw = (d.plain || "").trim();
  const looksRaw = /\(|\bdistinct\b|\bonce per\b/i.test(raw) || raw.length === 0;
  const one = label.replace(/s$/i, "");
  const plain = looksRaw ? `a shared ${one} counted once` : raw.charAt(0).toLowerCase() + raw.slice(1);
  return { label, plain };
}

function readCollapsed(): boolean {
  try {
    return localStorage.getItem("dataful-margin") === "collapsed";
  } catch {
    return false;
  }
}

export function Workspace({ datasetId, narrow }: { datasetId: string; narrow: boolean }) {
  const [view, setView] = useState<View>("decisions");
  const [sort, setSort] = useState<{ column: string; dir: "asc" | "desc" } | null>(null);
  const [filters, setFilters] = useState<Filter[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const search = useDebounced(searchInput.trim(), 300);
  const [focused, setFocused] = useState<string | null>(null);
  const [group, setGroup] = useState<GroupState | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [toast, setToast] = useState<string | null>(null);
  const [counts, setCounts] = useState<{ shown: number; total: number } | null>(null);
  const searchPending = searchInput.trim() !== search;

  useEffect(() => {
    try {
      localStorage.setItem("dataful-margin", collapsed ? "collapsed" : "open");
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4200);
    return () => clearTimeout(t);
  }, [toast]);

  const profile = useProfile(datasetId, view);
  const issuesQ = useIssues(datasetId);
  const decisionsQ = useDecisions(datasetId);
  const health = useHealth();

  const decisions: Decision[] = useMemo(
    () => (Array.isArray(decisionsQ.data) ? decisionsQ.data.filter((d): d is Decision => !!d && typeof d === "object") : []),
    [decisionsQ.data],
  );
  const issueList: Issue[] = useMemo(
    () => (Array.isArray(issuesQ.data) ? issuesQ.data.filter((i): i is Issue => !!i && typeof i === "object" && typeof i.id === "string") : []),
    [issuesQ.data],
  );
  const issueMap = useMemo(() => new Map<string, Issue>(issueList.map((i) => [i.id, i])), [issueList]);
  const focusedIssue = focused ? issueMap.get(focused) : undefined;
  const highlight = useMemo(() => new Set(focusedIssue?.columns ?? []), [focusedIssue]);
  // Root cause of the v1 crash: "keep as is" answers have op === null, and this line read d.op.op.
  const unitDecision = [...decisions].reverse().find((d) => d.enabled && !d.broken && opKind(d) === "set_count_unit");
  const unit = countUnitText(unitDecision);
  const countUnit = unit?.label ?? null;
  const openIssues = issueList.filter((i) => i.status === "open" || i.status === "skipped").length;
  const filtering = !!focused || filters.length > 0 || !!search;

  const query = useMemo(
    () => ({ sort: sort?.column ?? null, dir: sort?.dir, filters, search, issue_id: focused, view }),
    [sort, filters, search, focused, view],
  );

  const qc = useQueryClient();
  const review = useMutation({
    mutationFn: () => api.review(datasetId),
    onSuccess: (res) => {
      qc.setQueryData(qk.issues(datasetId), res.issues);
      qc.invalidateQueries({ queryKey: ["ds", datasetId] });
    },
  });

  const focusIssue = (id: string | null) => {
    setFocused(id);
    if (id) {
      setGroup(null);
      if (narrow) setDrawer(true);
    }
  };

  const startGroup = (by: string) => {
    setFocused(null);
    setGroup({ by, agg: "count", measure: null, useUnit: true });
  };

  const addFilter = (f: Filter) => {
    setGroup(null);
    setFilters((fs) => [...fs.filter((x) => !(x.column === f.column && x.op === f.op)), f]);
  };

  const onApplied = (issueId: string, message: string) => {
    if (focused === issueId) setFocused(null);
    setToast(message);
  };

  if (profile.error && !profile.data) {
    return (
      <main className="page page-state">
        <DatasetErrorCard
          datasetId={datasetId}
          error={profile.error as Error}
          retry={() => profile.refetch()}
          what="this dataset"
        />
      </main>
    );
  }

  const p = profile.data;
  const aiEnabled = health.data?.ai_enabled ?? false;

  const margin = (
    <ErrorBoundary
      resetKey={datasetId}
      fallback={(error, retry) => (
        <aside className="margin">
          <DatasetErrorCard datasetId={datasetId} error={error} retry={retry} compact what="the notes" />
        </aside>
      )}
    >
    <Margin
      datasetId={datasetId}
      issues={issuesQ.data ? issueList : undefined}
      decisions={decisions}
      onApplied={onApplied}
      collapsed={!narrow && collapsed}
      onToggleCollapsed={narrow ? undefined : () => setCollapsed((c) => !c)}
      loading={issuesQ.isLoading}
      error={(issuesQ.error as Error | null)?.message}
      focusedId={focused}
      onFocus={focusIssue}
      onClose={narrow ? () => setDrawer(false) : undefined}
      aiEnabled={aiEnabled}
    />
    </ErrorBoundary>
  );

  return (
    <>
      <main className="page">
        <header className="page-head">
          {!p ? (
            <div className="head-skel">
              <span className="skeleton" style={{ width: 280, height: 34 }} />
              <span className="skeleton" style={{ width: "60%" }} />
              <span className="skeleton" style={{ width: "40%" }} />
            </div>
          ) : (
            <>
              <div className="title-row">
                <h1 className="serif">{p.dataset.name}</h1>
                {narrow && (
                  <button className="btn ghost notes-btn" onClick={() => setDrawer(true)}>
                    <Icon name="notes" /> Notes {openIssues > 0 && <span className="count">{openIssues}</span>}
                  </button>
                )}
              </div>
              <p className="lede serif">
                {p.orientation.row_meaning} {p.orientation.summary}
              </p>
              <p className="meta">
                <span>
                  <Num value={p.dataset.rows} /> {p.dataset.rows === 1 ? "row" : "rows"}
                </span>
                <span>{p.dataset.columns || p.columns.length} columns</span>
                <span className="file">
                  {p.dataset.file}
                  {p.dataset.sheet ? ` › ${p.dataset.sheet}` : ""}
                </span>
                {view === "decisions" && decisions.some((d) => d.enabled) && <span className="applied">with {decisions.filter((d) => d.enabled).length} of your decisions</span>}
              </p>
              <div className="ai-line">
                {aiEnabled ? (
                  <>
                    <span className="small dim">
                      {p.ai_reviewed ? (
                        <>
                          <Icon name="sparkle" size={12} /> Reviewed by Dataful. Wording, groups and notes marked "AI found" came from AI; every number is still computed from your data. Answer some notes, then review again to look at the cleaner data.
                        </>
                      ) : (
                        "The AI sees column summaries, the values of small columns and 50 sample rows — never the whole table, and nothing until you ask."
                      )}
                    </span>
                    <button className={p.ai_reviewed ? "btn ghost" : "btn accent"} onClick={() => review.mutate()} disabled={review.isPending}>
                      <Icon name="sparkle" size={13} /> {review.isPending ? "Reviewing…" : p.ai_reviewed ? "Review again" : "Ask Dataful to review"}
                    </button>
                  </>
                ) : (
                  <>
                    <span className="small dim">Add an Anthropic API key to enable AI review — everything else works without it.</span>
                    <button className="btn accent" disabled title="AI review needs an Anthropic API key">
                      <Icon name="sparkle" size={13} /> Ask Dataful to review
                    </button>
                  </>
                )}
                {review.error && <span className="error small">{(review.error as Error).message}</span>}
              </div>
            </>
          )}
        </header>

        {p && (
          <div className="toolbar" role="toolbar" aria-label="Grid tools">
            <label className="search">
              <Icon name="search" />
              <input type="search" placeholder="Search rows" value={searchInput} onChange={(e) => setSearchInput(e.target.value)} aria-label="Search rows" />
            </label>
            {filtering && !group && (
              <span className="row-count" aria-live="polite">
                {searchPending || !counts ? (
                  "Counting rows…"
                ) : (
                  <>
                    <b>{fmtInt(counts.shown)}</b> of {fmtInt(counts.total)} rows
                  </>
                )}
              </span>
            )}
            <div className="chips">
              {focused && (
                <span className="chip chip-issue">
                  Rows in note: {focusedIssue?.title ?? "this note"}
                  <button onClick={() => setFocused(null)} aria-label="Clear note filter">
                    <Icon name="close" size={11} />
                  </button>
                </span>
              )}
              {filters.map((f, i) => (
                <span className="chip" key={i}>
                  {f.column} {OP_LABEL[f.op]} {f.value !== undefined && <b>{fmtCell(f.value)}</b>}
                  <button onClick={() => setFilters((fs) => fs.filter((_, j) => j !== i))} aria-label={`Remove filter on ${f.column}`}>
                    <Icon name="close" size={11} />
                  </button>
                </span>
              ))}
              {sort && (
                <span className="chip chip-quiet">
                  sorted by {sort.column} {sort.dir === "asc" ? "↑" : "↓"}
                  <button onClick={() => setSort(null)} aria-label="Clear sort">
                    <Icon name="close" size={11} />
                  </button>
                </span>
              )}
            </div>
            <div className="tool-right">
              {!group && (
                <label className="select-btn">
                  <Icon name="group" />
                  <select
                    value=""
                    onChange={(e) => e.target.value && startGroup(e.target.value)}
                    aria-label="Group by column"
                  >
                    <option value="">Group by…</option>
                    {p.columns
                      .filter((c) => c.role !== "identifier" && c.role !== "text")
                      .map((c) => (
                        <option key={c.name} value={c.name}>
                          {c.name}
                        </option>
                      ))}
                  </select>
                </label>
              )}
              <div className="seg" role="radiogroup" aria-label="Which version of the data">
                <button role="radio" aria-checked={view === "original"} className={view === "original" ? "on" : ""} onClick={() => setView("original")}>
                  Original
                </button>
                <button role="radio" aria-checked={view === "decisions"} className={view === "decisions" ? "on" : ""} onClick={() => setView("decisions")}>
                  With my decisions
                </button>
              </div>
              <details className="menu">
                <summary className="btn ghost">
                  <Icon name="download" /> Export
                </summary>
                <div className="menu-pop">
                  <a href={api.exportCsvUrl(datasetId, "decisions")} download>
                    Clean CSV <span className="dim small">with your decisions</span>
                  </a>
                  <a href={api.exportCsvUrl(datasetId, "original")} download>
                    Original CSV
                  </a>
                  <a href={api.decisionsJsonUrl(datasetId)} download>
                    Decision list <span className="dim small">JSON</span>
                  </a>
                </div>
              </details>
            </div>
          </div>
        )}

        {p && group && (
          <GroupControls columns={p.columns} group={group} countUnit={countUnit} countUnitPlain={unit?.plain ?? null} onChange={setGroup} onClose={() => setGroup(null)} />
        )}

        <div className="grid-area">
          <ErrorBoundary
            resetKey={`${group ? "g" : "r"}:${view}`}
            fallback={(error, retry) => <DatasetErrorCard datasetId={datasetId} error={error} retry={retry} what={group ? "the grouped numbers" : "the table"} />}
          >
          {p && group ? (
            <GroupView
              datasetId={datasetId}
              columns={p.columns}
              view={view}
              filters={filters}
              group={group}
              countUnit={countUnit}
              countUnitPlain={unit?.plain ?? null}
              onChange={setGroup}
              onClose={() => setGroup(null)}
              onPick={(key) => addFilter(isMissing(key) ? { column: group.by, op: "is_missing" } : { column: group.by, op: "=", value: key })}
            />
          ) : p ? (
            <Grid
              datasetId={datasetId}
              profile={p}
              issues={issueMap}
              query={query}
              highlight={highlight}
              pending={searchPending}
              fallbackTotal={p.dataset.rows}
              onCounts={setCounts}
              onSort={(column, dir) => setSort(dir ? { column, dir } : null)}
              onFilter={addFilter}
              onFocusIssue={focusIssue}
              onGroupBy={startGroup}
            />
          ) : (
            <div className="grid-skel">
              {Array.from({ length: 14 }, (_, i) => (
                <span key={i} className="skeleton" style={{ width: `${92 - (i % 4) * 6}%` }} />
              ))}
            </div>
          )}
          </ErrorBoundary>
        </div>
      </main>
      {narrow ? (
        drawer && (
          <div className="drawer-scrim" onMouseDown={(e) => e.target === e.currentTarget && setDrawer(false)}>
            <div className="drawer">{margin}</div>
          </div>
        )
      ) : (
        margin
      )}
      {toast && (
        <div className="toast toast-ok" role="status">
          <span aria-hidden>✓</span> {toast}
        </div>
      )}
    </>
  );
}
