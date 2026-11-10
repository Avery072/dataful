import {
  createColumnHelper,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnSizingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Column, Issue, Profile } from "../api";
import { fmtCell, isMissing, isNumericCol } from "../format";
import { PAGE_SIZE, useRowPages, type RowQuery } from "../hooks/useRowPages";
import { ColumnCard } from "./ColumnCard";
import { HeaderProfile } from "./HeaderProfile";
import { CellTooltip, type TipState } from "./CellTooltip";

const ROW_H = 32;
const GUTTER = 64;

type RowShape = Record<string, unknown>;

/** Room the header needs so the name isn't cut: padding + role glyph + name (13px semibold) + sort button. */
export function headerWidth(c: Column): number {
  return Math.round(Math.min(260, 20 + 17 + 12 + c.name.length * 8.6 + 24));
}

export function widthFor(c: Column): number {
  const head = headerWidth(c);
  if (isNumericCol(c) || c.role === "time") return Math.round(Math.min(180, Math.max(96, head)));
  const longest = Math.max(0, ...(c.top_values ?? []).map((v) => String(v.value).length));
  const body = longest * 7 + 24;
  const max = c.role === "text" ? 280 : 220;
  return Math.round(Math.min(Math.max(max, head), Math.max(88, head, body)));
}

export interface GridProps {
  datasetId: string;
  profile: Profile;
  issues: Map<string, Issue>;
  query: RowQuery;
  highlight: Set<string>;
  onSort: (column: string, dir: "asc" | "desc" | null) => void;
  onFilter: (f: import("../api").Filter) => void;
  onFocusIssue: (id: string) => void;
  onGroupBy: (column: string) => void;
  /** True while a typed search hasn't been sent yet: show "Searching…", never a stale empty state. */
  pending?: boolean;
  /** Used for "X of Y rows" when the server doesn't send total_unfiltered. */
  fallbackTotal?: number;
  onCounts?: (c: { shown: number; total: number } | null) => void;
}

export function Grid({ datasetId, profile, issues, query, highlight, onSort, onFilter, onFocusIssue, onGroupBy, pending = false, fallbackTotal, onCounts }: GridProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState({ start: 0, end: 60 });
  const rows = useRowPages(datasetId, query, visible);
  const [openCard, setOpenCard] = useState<{ column: string; rect: DOMRect } | null>(null);
  const [tip, setTip] = useState<TipState | null>(null);

  const colByName = useMemo(() => new Map(profile.columns.map((c) => [c.name, c])), [profile.columns]);

  // Order columns by their group bands; ungrouped columns go last.
  const ordered = useMemo(() => {
    const seen = new Set<string>();
    const bands: { name: string; cols: Column[] }[] = [];
    for (const g of profile.orientation.groups ?? []) {
      const cols = g.columns.map((n) => colByName.get(n)).filter((c): c is Column => !!c && !seen.has(c.name));
      cols.forEach((c) => seen.add(c.name));
      if (cols.length) bands.push({ name: g.name, cols });
    }
    const rest = profile.columns.filter((c) => !seen.has(c.name));
    if (rest.length) bands.push({ name: bands.length ? "Other" : "", cols: rest });
    return bands;
  }, [profile.orientation.groups, profile.columns, colByName]);

  const columnDefs = useMemo<ColumnDef<RowShape, unknown>[]>(() => {
    const h = createColumnHelper<RowShape>();
    return ordered.map((b, i) =>
      h.group({
        id: `band:${i}:${b.name}`,
        header: b.name,
        columns: b.cols.map((c) => h.accessor((r) => r[c.name], { id: c.name, header: c.name, size: widthFor(c), minSize: Math.min(headerWidth(c), 120), maxSize: 600 })),
      }),
    );
  }, [ordered]);

  const [sizing, setSizing] = useState<ColumnSizingState>({});
  const table = useReactTable<RowShape>({
    data: [],
    columns: columnDefs,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: "onChange",
    state: { columnSizing: sizing },
    onColumnSizingChange: setSizing,
    manualSorting: true,
    manualFiltering: true,
    manualPagination: true,
  });
  const [bandGroup, leafGroup] = table.getHeaderGroups();
  const leafCols = table.getVisibleLeafColumns();
  const totalWidth = GUTTER + table.getTotalSize();

  // Server column order -> index map
  const serverIndex = useMemo(() => {
    const names = rows.columns ?? profile.columns.map((c) => c.name);
    return new Map(names.map((n, i) => [n, i]));
  }, [rows.columns, profile.columns]);

  const virtualizer = useVirtualizer({
    count: rows.total,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 24,
  });
  const items = virtualizer.getVirtualItems();
  const vStart = items[0]?.index ?? 0;
  const vEnd = items[items.length - 1]?.index ?? 0;

  useEffect(() => {
    const s = Math.floor(vStart / PAGE_SIZE);
    const e = Math.floor(vEnd / PAGE_SIZE);
    if (s !== Math.floor(visible.start / PAGE_SIZE) || e !== Math.floor(visible.end / PAGE_SIZE)) setVisible({ start: vStart, end: vEnd });
  }, [vStart, vEnd, visible.start, visible.end]);

  // New query -> back to the top.
  const qkey = JSON.stringify({ ...query, view: undefined });
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 });
    setVisible({ start: 0, end: 60 });
  }, [qkey]);

  const shownTotal = rows.totalKnown && !pending ? rows.total : null;
  const allTotal = rows.totalUnfiltered ?? fallbackTotal;
  useEffect(() => {
    onCounts?.(shownTotal != null && allTotal != null ? { shown: shownTotal, total: Math.max(allTotal, shownTotal) } : null);
  }, [shownTotal, allTotal, onCounts]);

  const sortDir = (name: string) => (query.sort === name ? (query.dir ?? "asc") : null);

  const openTip = (e: React.MouseEvent, issueId: string, column: string, value: unknown, pinned: boolean) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setTip({ issueId, column, value, rect: r, pinned });
  };

  const headerHeight = bandGroup ? 24 + 112 : 112;

  return (
    <div className="grid-wrap">
      <div className="grid-scroll" ref={scrollRef} role="grid" aria-rowcount={rows.total} aria-colcount={leafCols.length}>
        <div style={{ width: totalWidth, minWidth: "100%" }}>
          <div className="grid-head" style={{ height: headerHeight }}>
            {bandGroup && (
              <div className="band-row">
                <div className="gutter" style={{ width: GUTTER }} />
                {bandGroup.headers.map((h) => (
                  <div key={h.id} className="band" style={{ width: h.getSize() }}>
                    {!h.isPlaceholder && <span>{String(h.column.columnDef.header ?? "")}</span>}
                  </div>
                ))}
              </div>
            )}
            <div className="header-row" role="row">
              <div className="gutter" style={{ width: GUTTER }} aria-hidden />
              {leafGroup.headers.map((h) => {
                const col = colByName.get(h.column.id);
                if (!col) return null;
                return (
                  <HeaderProfile
                    key={h.id}
                    col={col}
                    width={h.getSize()}
                    total={profile.dataset.rows}
                    sort={sortDir(col.name)}
                    highlighted={highlight.has(col.name)}
                    open={openCard?.column === col.name}
                    onOpen={(rect) => setOpenCard(openCard?.column === col.name ? null : { column: col.name, rect })}
                    onSort={() => {
                      const d = sortDir(col.name);
                      onSort(col.name, d === null ? (isNumericCol(col) ? "desc" : "asc") : d === "asc" ? "desc" : null);
                    }}
                    resizeHandler={h.getResizeHandler()}
                    resizing={h.column.getIsResizing()}
                  />
                );
              })}
            </div>
          </div>

          <div className="grid-body" style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {items.map((vi) => {
              const r = rows.getRow(vi.index);
              return (
                <div
                  key={vi.key}
                  className={"grid-row" + (vi.index % 2 ? " odd" : "")}
                  role="row"
                  aria-rowindex={vi.index + 1}
                  style={{ transform: `translateY(${vi.start}px)`, height: ROW_H }}
                >
                  <div className="gutter cell-n" style={{ width: GUTTER }}>
                    {r?.rowNumber ?? vi.index + 1}
                  </div>
                  {leafCols.map((lc) => {
                    const col = colByName.get(lc.id);
                    if (!col) return null;
                    const w = lc.getSize();
                    const hl = highlight.has(col.name);
                    if (!r)
                      return (
                        <div key={lc.id} className={"cell" + (hl ? " col-hl" : "")} style={{ width: w }}>
                          <span className="skeleton" style={{ width: `${30 + ((vi.index * 7 + lc.getIndex() * 13) % 50)}%` }} />
                        </div>
                      );
                    const v = r.values[serverIndex.get(col.name) ?? -1];
                    const flag = r.flags?.[col.name];
                    const issue = flag ? issues.get(flag) : undefined;
                    const missing = isMissing(v);
                    const num = typeof v === "number" || (isNumericCol(col) && !missing && !isNaN(Number(v)));
                    const cls = [
                      "cell",
                      num ? "num" : "",
                      missing ? "missing" : "",
                      hl ? "col-hl" : "",
                      issue ? `flag flag-${issue.severity}` : flag ? "flag flag-format" : "",
                    ].join(" ");
                    const text = fmtCell(num && typeof v !== "number" ? Number(v) : v, col);
                    return (
                      <div
                        key={lc.id}
                        role="gridcell"
                        className={cls}
                        style={{ width: w }}
                        title={!flag && text.length > 14 ? text : undefined}
                        tabIndex={flag ? 0 : undefined}
                        onMouseEnter={flag ? (e) => openTip(e, flag, col.name, v, false) : undefined}
                        onMouseLeave={flag ? () => setTip((t) => (t && !t.pinned ? { ...t, closing: true } : t)) : undefined}
                        onClick={flag ? (e) => openTip(e, flag, col.name, v, true) : undefined}
                        onKeyDown={flag ? (e) => e.key === "Enter" && onFocusIssue(flag) : undefined}
                      >
                        <span>{text}</span>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      </div>
      {/* Overlays live outside the scroller so they stay centred when the grid is scrolled sideways. */}
      {!rows.error && (pending || (!rows.totalKnown && rows.fetching)) && rows.total === 0 && (
        <div className="grid-empty" aria-live="polite">
          <p className="serif dim">{pending || query.search ? "Searching…" : "Loading rows…"}</p>
        </div>
      )}
      {!rows.error && !pending && rows.totalKnown && !rows.fetching && rows.total === 0 && (
        <div className="grid-empty">
          <p className="serif">No rows match.</p>
          <p className="dim">Try clearing a filter or the search.</p>
        </div>
      )}
      {rows.error && (
        <div className="grid-empty">
          <p className="serif">Couldn't load rows.</p>
          <p className="dim">{rows.error.message}</p>
        </div>
      )}
      {(rows.fetching || pending) && <div className="grid-loading" aria-live="polite">{pending ? "Searching…" : "Loading rows…"}</div>}

      {openCard && colByName.get(openCard.column) && (
        <ColumnCard
          col={colByName.get(openCard.column)!}
          anchor={openCard.rect}
          total={profile.dataset.rows}
          issues={(colByName.get(openCard.column)!.issue_ids ?? []).map((id) => issues.get(id)).filter((i): i is Issue => !!i)}
          sort={sortDir(openCard.column)}
          onClose={() => setOpenCard(null)}
          onSort={(d) => onSort(openCard.column, d)}
          onFilter={(f) => {
            onFilter(f);
            setOpenCard(null);
          }}
          onGroupBy={() => {
            onGroupBy(openCard.column);
            setOpenCard(null);
          }}
          onFocusIssue={(id) => {
            onFocusIssue(id);
            setOpenCard(null);
          }}
        />
      )}
      {tip && (
        <CellTooltip
          tip={tip}
          issue={issues.get(tip.issueId)}
          onClose={() => setTip(null)}
          onKeep={() => setTip((t) => (t ? { ...t, closing: false } : t))}
          onOpenNote={() => {
            onFocusIssue(tip.issueId);
            setTip(null);
          }}
        />
      )}
    </div>
  );
}
