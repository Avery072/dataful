import { useState } from "react";
import type { Column } from "../api";
import { fmtCell, fmtInt, fmtPct } from "../format";

/** Mini column histogram for numeric/date columns. Single neutral series; hover shows the bin. */
export function MiniHistogram({ col, width = 100, height = 30 }: { col: Column; width?: number; height?: number }) {
  const bins = col.histogram ?? [];
  const [hover, setHover] = useState<number | null>(null);
  if (!bins.length) return <div className="mini-empty" style={{ height }} />;
  const max = Math.max(...bins.map((b) => b.count), 1);
  const gap = 1.5;
  const bw = Math.max(1, (width - gap * (bins.length - 1)) / bins.length);
  const fmt = (v: number) => (col.type === "date" ? new Date(v).getFullYear().toString() : fmtCell(Math.round(v * 100) / 100, col));
  const h = hover != null ? bins[hover] : null;
  return (
    <div className="mini-chart" onMouseLeave={() => setHover(null)}>
      <svg width={width} height={height} role="img" aria-label={`Distribution of ${col.name}`}>
        {bins.map((b, i) => {
          const bh = b.count === 0 ? 0 : Math.max(1.5, (b.count / max) * (height - 1));
          const x = i * (bw + gap);
          return (
            <g key={i} onMouseEnter={() => setHover(i)}>
              <rect x={x} y={0} width={bw + gap} height={height} fill="transparent" />
              <path className={hover === i ? "mark mark-hover" : "mark"} d={roundTop(x, height - bh, bw, bh, Math.min(2, bw / 2))} />
            </g>
          );
        })}
        <line x1={0} x2={width} y1={height - 0.5} y2={height - 0.5} className="baseline" />
      </svg>
      <div className="mini-caption">
        {h ? (
          <span>
            {fmt(h.start)}–{fmt(h.end)} · <b>{fmtInt(h.count)}</b>
          </span>
        ) : (
          <span>
            {fmt(bins[0].start)} <span className="dim">to</span> {fmt(bins[bins.length - 1].end)}
          </span>
        )}
      </div>
    </div>
  );
}

/** Top-value bars for categories: up to 3 thin horizontal bars + share. */
export function TopValues({ col, total, n = 3, width = 100 }: { col: Column; total: number; n?: number; width?: number }) {
  const vals = (col.top_values ?? []).slice(0, n);
  if (!vals.length) return <div className="mini-empty" />;
  const max = Math.max(...vals.map((v) => v.count), 1);
  return (
    <div className="top-values" style={{ width }}>
      {vals.map((v) => (
        <div className="tv-row" key={v.value} title={`${v.value}: ${fmtInt(v.count)} rows (${fmtPct(v.count / Math.max(total, 1))})`}>
          <span className="tv-label">{v.value === "" ? "(blank)" : v.value}</span>
          <span className="tv-bar">
            <span style={{ width: `${(v.count / max) * 100}%` }} />
          </span>
        </div>
      ))}
    </div>
  );
}

/** Path for a bar with rounded top (data end) and square baseline. */
export function roundTop(x: number, y: number, w: number, h: number, r: number) {
  if (h <= 0) return "";
  r = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}
