import type { Column, Confidence, Issue, Severity } from "./api";

const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const nfPlain = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, useGrouping: false });
const cf = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export const fmtInt = (n: number | null | undefined) => (n == null ? "—" : nf.format(n));
export const fmtCompact = (n: number) => (Math.abs(n) < 10000 ? nf.format(n) : cf.format(n).toLowerCase());
export function fmtPct(p: number): string {
  if (p === 0) return "0%";
  if (p < 0.001) return "<0.1%";
  if (p < 0.1) return (p * 100).toFixed(1).replace(/\.0$/, "") + "%";
  return Math.round(p * 100) + "%";
}

export const isMissing = (v: unknown) => v === null || v === undefined || v === "";

/** Format a grid cell. IDs and years keep plain digits (no "1,992"). */
export function fmtCell(v: unknown, col?: Column): string {
  if (isMissing(v)) return "—";
  if (typeof v === "number") {
    if (col && (col.role === "identifier" || col.role === "time")) return nfPlain.format(v);
    return nf.format(v);
  }
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

export const isNumericCol = (c?: Column) => !!c && (c.type === "integer" || c.type === "decimal");

export function fmtRange(c: Column): string | null {
  if (c.min == null && c.max == null) return null;
  const f = (v: string | number | null) => (typeof v === "number" ? fmtCell(v, c) : v ?? "—");
  return `${f(c.min)} – ${f(c.max)}`;
}

export const SEVERITY_ORDER: Record<Severity, number> = { numbers: 0, missing: 1, format: 2 };
export const CONFIDENCE_ORDER: Record<Confidence, number> = { certain: 0, likely: 1, guess: 2 };
export const SEVERITY_LABEL: Record<Severity, string> = {
  numbers: "Changes your numbers",
  missing: "Missing data",
  format: "Formatting",
};

export function sortIssues(issues: Issue[]): Issue[] {
  const done = (i: Issue) => (i.status === "open" || i.status === "skipped" ? 0 : 1);
  return [...issues].sort(
    (a, b) =>
      done(a) - done(b) ||
      SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] ||
      CONFIDENCE_ORDER[a.confidence] - CONFIDENCE_ORDER[b.confidence] ||
      b.affected_rows - a.affected_rows,
  );
}

export function plural(n: number, one: string, many = one + "s") {
  return `${fmtInt(n)} ${n === 1 ? one : many}`;
}
