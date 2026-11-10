import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Column, Filter, Issue } from "../api";
import { fmtInt, fmtPct, fmtRange } from "../format";
import { HealthMark, Icon, RoleGlyph, RoleLegend, roleLabel, rolePlain, SeverityMark } from "./Glyphs";

interface Props {
  col: Column;
  anchor: DOMRect;
  total: number;
  issues: Issue[];
  sort: "asc" | "desc" | null;
  onClose: () => void;
  onSort: (d: "asc" | "desc" | null) => void;
  onFilter: (f: Filter) => void;
  onGroupBy: () => void;
  onFocusIssue: (id: string) => void;
}

export function ColumnCard({ col, anchor, total, issues, sort, onClose, onSort, onFilter, onGroupBy, onFocusIssue }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: anchor.left, top: anchor.bottom + 6 });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const w = el.offsetWidth;
    const left = Math.max(12, Math.min(anchor.left, window.innerWidth - w - 12));
    setPos({ left, top: Math.min(anchor.bottom + 6, window.innerHeight - el.offsetHeight - 12) });
  }, [anchor]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    const t = setTimeout(() => window.addEventListener("mousedown", onDown), 0);
    ref.current?.focus();
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
      clearTimeout(t);
    };
  }, [onClose]);

  const range = fmtRange(col);
  const top = col.top_values ?? [];
  const max = Math.max(...top.map((v) => v.count), 1);

  return (
    <div className="popover col-card" ref={ref} style={pos} role="dialog" aria-label={`${col.name} details`} tabIndex={-1}>
      <header>
        <h3 className="serif">{col.name}</h3>
        <button className="icon-btn" onClick={onClose} aria-label="Close">
          <Icon name="close" />
        </button>
      </header>
      <p className="cc-meta">
        <RoleGlyph role={col.role} /> {roleLabel(col.role)} ·  <HealthMark health={col.health} /> {col.health === "healthy" ? "healthy" : col.health === "gaps" ? "has gaps" : "possible trap"}
      </p>
      <p className="cc-role small">{rolePlain(col.role)}.</p>
      <dl className="cc-stats">
        <div>
          <dt>Distinct</dt>
          <dd>{fmtInt(col.distinct)}</dd>
        </div>
        <div>
          <dt>Missing</dt>
          <dd>
            {fmtInt(col.missing)} <span className="dim">({fmtPct(col.missing_pct)})</span>
          </dd>
        </div>
        {range && (
          <div>
            <dt>Range</dt>
            <dd>{range}</dd>
          </div>
        )}
      </dl>

      {top.length > 0 && (
        <div className="cc-section">
          <h4>Most common</h4>
          <ul className="cc-top">
            {top.slice(0, 8).map((v) => (
              <li key={String(v.value)}>
                <button onClick={() => onFilter({ column: col.name, op: "=", value: v.value })} title={`Show only rows where ${col.name} = ${v.value}`}>
                  <span className="cc-top-label">{v.value === "" ? "(blank)" : v.value}</span>
                  <span className="cc-top-bar">
                    <span style={{ width: `${(v.count / max) * 100}%` }} />
                  </span>
                  <span className="cc-top-n">{fmtInt(v.count)}</span>
                  <span className="cc-top-pct">{fmtPct(v.count / Math.max(total, 1))}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {issues.length > 0 && (
        <div className="cc-section">
          <h4>Notes on this column</h4>
          <ul className="cc-issues">
            {issues.map((i) => (
              <li key={i.id}>
                <button onClick={() => onFocusIssue(i.id)}>
                  <SeverityMark severity={i.severity} /> <span>{i.title}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <details className="cc-legend">
        <summary className="small">What do the symbols mean?</summary>
        <RoleLegend current={col.role} />
      </details>

      <div className="cc-actions">
        <button className={"chip-btn" + (sort === "asc" ? " on" : "")} onClick={() => onSort(sort === "asc" ? null : "asc")}>
          <Icon name="sort-asc" size={12} /> Sort ascending
        </button>
        <button className={"chip-btn" + (sort === "desc" ? " on" : "")} onClick={() => onSort(sort === "desc" ? null : "desc")}>
          <Icon name="sort-desc" size={12} /> Descending
        </button>
        {col.missing > 0 && (
          <button className="chip-btn" onClick={() => onFilter({ column: col.name, op: "is_missing" })}>
            Only missing
          </button>
        )}
        <button className="chip-btn" onClick={onGroupBy}>
          <Icon name="group" size={12} /> Group by
        </button>
      </div>
    </div>
  );
}
