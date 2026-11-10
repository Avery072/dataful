import { useQuery } from "@tanstack/react-query";
import { api, type Agg, type Column, type Filter, type View } from "../api";
import { fmtCell, fmtInt, isMissing, isNumericCol } from "../format";
import { qk } from "../hooks/useDataset";

export interface GroupState {
  by: string;
  agg: Agg;
  measure: string | null;
  useUnit: boolean;
}

const AGG_LABEL: Record<Agg, string> = { count: "Count", sum: "Sum of", avg: "Average", count_distinct: "Distinct" };

interface Props {
  datasetId: string;
  columns: Column[];
  view: View;
  filters: Filter[];
  group: GroupState;
  countUnit: string | null; // label from an enabled set_count_unit decision
  countUnitPlain?: string | null; // plain words for that unit, e.g. "a shared team win counted once"
  onChange: (g: GroupState) => void;
  onPick: (key: unknown) => void;
  onClose: () => void;
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function GroupControls({ columns, group, countUnit, countUnitPlain, onChange, onClose }: Pick<Props, "columns" | "group" | "countUnit" | "countUnitPlain" | "onChange" | "onClose">) {
  const measures = columns.filter((c) => (group.agg === "count_distinct" ? c.name !== group.by : isNumericCol(c) && c.role !== "identifier"));
  const setAgg = (agg: Agg) => {
    let measure = group.measure;
    if (agg === "count") measure = null;
    else if (!measure || !columns.find((c) => c.name === measure && (agg === "count_distinct" || isNumericCol(c)))) {
      measure = (agg === "count_distinct" ? columns.find((c) => c.role === "identifier") ?? columns[0] : columns.find((c) => isNumericCol(c) && c.role === "measure"))?.name ?? null;
    }
    onChange({ ...group, agg, measure });
  };
  return (
    <div className="group-controls">
      <label>
        <span>Group by</span>
        <select value={group.by} onChange={(e) => onChange({ ...group, by: e.target.value })}>
          {columns.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Show</span>
        <select value={group.agg} onChange={(e) => setAgg(e.target.value as Agg)}>
          <option value="count">count</option>
          <option value="sum">sum</option>
          <option value="avg">average</option>
          <option value="count_distinct">count distinct</option>
        </select>
      </label>
      {group.agg !== "count" && (
        <label>
          <span>of</span>
          <select value={group.measure ?? ""} onChange={(e) => onChange({ ...group, measure: e.target.value })}>
            {measures.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {group.agg === "count" && countUnit && (
        <div className="unit-toggle">
          <div className="seg" role="radiogroup" aria-label="What to count">
            <span className="seg-label">Count</span>
            <button role="radio" aria-checked={!group.useUnit} className={!group.useUnit ? "on" : ""} onClick={() => onChange({ ...group, useUnit: false })} title="Every line in the file counts once">
              Rows
            </button>
            <button role="radio" aria-checked={group.useUnit} className={group.useUnit ? "on" : ""} onClick={() => onChange({ ...group, useUnit: true })} title={cap(countUnitPlain ?? `each ${countUnit} counted once`)}>
              {cap(countUnit)}
            </button>
          </div>
          <span className="unit-hint small dim">
            {group.useUnit ? (
              <>
                <b>{cap(countUnit)}</b> — {countUnitPlain ?? `each ${countUnit.replace(/s$/, "")} counted once`}
              </>
            ) : (
              <>
                <b>Rows</b> — every line in the file
              </>
            )}
          </span>
        </div>
      )}
      <button className="link-btn" onClick={onClose}>
        Back to rows
      </button>
    </div>
  );
}

export function GroupView({ datasetId, columns, view, filters, group, countUnit, countUnitPlain, onPick }: Props) {
  const params = { by: group.by, agg: group.agg, measure: group.agg === "count" ? null : group.measure, use_count_unit: group.useUnit && !!countUnit, view, filters };
  const q = useQuery({
    queryKey: qk.group(datasetId, JSON.stringify(params)),
    queryFn: () => api.group(datasetId, params),
    placeholderData: (prev) => prev,
    enabled: group.agg === "count" || !!group.measure,
  });
  const byCol = columns.find((c) => c.name === group.by);
  const data = q.data;
  const groups = Array.isArray(data?.groups) ? data.groups : [];
  const max = Math.max(...groups.map((g) => Math.abs(Number(g.value) || 0)), 1);
  const fmtV = (v: number) => (group.agg === "avg" ? fmtInt(Math.round(v * 100) / 100) : fmtInt(v));
  // Never show raw tuples: the server's count_unit should be a label, but fall back to ours if it isn't.
  const rawUnit = data?.count_unit;
  const unitShown = rawUnit ? (/[(),]/.test(rawUnit) ? countUnit ?? "records" : rawUnit) : null;
  const valueLabel = group.agg === "count" ? (unitShown ? `${unitShown}` : "rows") : `${AGG_LABEL[group.agg].toLowerCase()} ${group.measure ?? ""}`;
  const showRowsCol = !(group.agg === "count" && !unitShown);
  const caveats = (Array.isArray(data?.caveats) ? data.caveats : []).filter((c) => typeof c === "string" && c.trim());
  const excluded = typeof data?.excluded_rows === "number" ? data.excluded_rows : 0;
  const excludedText =
    excluded > 0 && !caveats.some((c) => /not counted|left out|excluded|skipped/i.test(c))
      ? `${fmtInt(excluded)} ${excluded === 1 ? "row is" : "rows are"} not counted because ${group.agg === "count" || !group.measure ? group.by : `${group.by} or ${group.measure}`} is missing.`
      : null;

  return (
    <div className={"group-view" + (q.isFetching ? " refreshing" : "")}>
      {q.error && <p className="error">Couldn't group: {(q.error as Error).message}</p>}
      {!data && q.isLoading && (
        <div className="group-skel">
          {Array.from({ length: 8 }, (_, i) => (
            <span key={i} className="skeleton" style={{ width: `${85 - i * 9}%` }} />
          ))}
        </div>
      )}
      {data && (
        <>
          <p className="group-caption small">
            {groups.length >= 50 ? "Top 50 groups" : `${groups.length} ${groups.length === 1 ? "group" : "groups"}`} by <b>{data.by}</b>, showing {valueLabel}
            {unitShown && <> — {countUnitPlain ?? `each ${unitShown.replace(/s$/, "")} counted once`}</>}. Click a group to see its rows.
          </p>
          {(excludedText || caveats.length > 0) && (
            <ul className="caveats" aria-label="Things to know about these numbers">
              {excludedText && (
                <li>
                  <span className="caveat-mark" aria-hidden>◐</span> {excludedText}
                </li>
              )}
              {caveats.map((c, i) => (
                <li key={i}>
                  <span className="caveat-mark" aria-hidden>▲</span> {c}
                </li>
              ))}
            </ul>
          )}
          <table className="group-table">
            <thead>
              <tr>
                <th scope="col">{data.by}</th>
                <th scope="col" className="num">
                  {valueLabel}
                </th>
                <th scope="col" className="bar-col">
                  <span className="sr-only">bar</span>
                </th>
                {showRowsCol && (
                  <th scope="col" className="num dim">
                    rows
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {groups.map((g, i) => (
                <tr key={i} tabIndex={0} onClick={() => onPick(g.key)} onKeyDown={(e) => e.key === "Enter" && onPick(g.key)} title={`Show the ${fmtInt(g.rows)} rows where ${data.by} = ${fmtCell(g.key)}`}>
                  <th scope="row" className={isMissing(g.key) ? "missing" : ""}>
                    {isMissing(g.key) ? "— missing" : fmtCell(g.key, byCol)}
                  </th>
                  <td className="num value">{fmtV(g.value)}</td>
                  <td className="bar-col">
                    <span className="gbar" style={{ width: `${(Math.abs(Number(g.value) || 0) / max) * 100}%` }} />
                  </td>
                  {showRowsCol && <td className="num dim">{fmtInt(g.rows)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
