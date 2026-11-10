// Typed API client mirroring API.md. All calls go to the real `/api` unless
// VITE_MOCK=1 is set, in which case the isolated fixtures in ./mock are used.

export type Role = "identifier" | "category" | "measure" | "time" | "text" | "geo" | "boolean";
export type Health = "healthy" | "gaps" | "trap";
export type Confidence = "certain" | "likely" | "guess";
export type Severity = "numbers" | "missing" | "format";
export type IssueStatus = "open" | "resolved" | "kept" | "flagged" | "skipped";
export type View = "original" | "decisions";

export interface Dataset {
  id: string;
  name: string;
  file: string;
  sheet: string | null;
  rows: number;
  /** v2: rows after enabled decisions. Fall back to `rows` when missing. */
  rows_current?: number;
  columns: number;
  demo: boolean;
}

export interface Column {
  name: string;
  type: "integer" | "decimal" | "text" | "date" | "boolean";
  role: Role;
  missing: number;
  missing_pct: number;
  distinct: number;
  top_values: { value: string; count: number }[];
  histogram: { start: number; end: number; count: number }[] | null;
  min: string | number | null;
  max: string | number | null;
  health: Health;
  issue_ids: string[];
}

export interface Orientation {
  row_meaning: string;
  summary: string;
  groups: { name: string; columns: string[] }[];
  source: "ai" | "rules";
}

export interface Profile {
  dataset: Dataset;
  columns: Column[];
  orientation: Orientation;
  ai_reviewed: boolean;
}

export interface Evidence {
  for: string[];
  against: string[];
}

export interface Option {
  label: string;
  op: Op | null;
  description?: string;
}

export interface Issue {
  id: string;
  family: string;
  title: string;
  detail: string;
  severity: Severity;
  confidence: Confidence;
  columns: string[];
  affected_rows: number;
  evidence: Evidence;
  kind: "fix" | "question";
  question: string | null;
  options: Option[];
  status: IssueStatus;
  decision_id: string | null;
  source: "rules" | "ai";
}

export type FilterOp = "=" | "!=" | "<" | ">" | "is_missing" | "not_missing" | "contains" | "in";
export interface Filter {
  column: string;
  op: FilterOp;
  value?: unknown;
}

export type Op =
  | { op: "mark_missing"; column: string; values: string[] }
  | { op: "fill_blank"; column: string; value: string | number }
  | { op: "change_type"; column: string; to: "text" | "integer" | "decimal" | "date" }
  | { op: "split_column"; column: string; sep: string; into: [string, string] }
  | { op: "merge_values"; column: string; from: string[]; to: string }
  | { op: "recode_values"; column: string; mapping: Record<string, string> }
  | { op: "combine_columns"; columns: string[]; sep: string; into: string }
  | { op: "set_count_unit"; columns: string[]; label: string }
  | { op: "drop_rows"; where: Filter[] }
  | { op: "flag_rows"; where: Filter[]; label: string }
  | { op: "remove_duplicates"; columns: string[] | null }
  | { op: "merge_records"; key: string[]; keep: "first" | "last" }
  | { op: "keep_separate"; column: string; values: string[] }
  | { op: "flag_duplicates"; key: string[]; label: string };

export interface ChatEntry {
  role: "user" | "assistant";
  text: string;
  /** Notes Claude added to the margin during this reply. */
  issues?: string[];
}
export interface ChatResult {
  log: ChatEntry[];
  added: string[];
  issues: Issue[];
}

export interface Decision {
  id: string;
  /** null = "keep as is" (an answer that changes nothing). */
  op: Op | null;
  plain: string;
  issue_id: string | null;
  reason: string | null;
  enabled: boolean;
  created_at: string;
  /** v2: saved decision that no longer applies to the current data. */
  broken?: boolean;
  error?: string;
}

export interface Health_ {
  ok: boolean;
  ai_enabled: boolean;
  model: string | null;
}

export interface RowsPage {
  total: number;
  /** v2: rows in the view before filters/search/note filter. */
  total_unfiltered?: number;
  columns: string[];
  /** v2: typed values (numbers, booleans, ISO dates, null for missing). */
  rows: unknown[][];
  /** v2: absolute row number for each returned row. */
  row_numbers?: number[];
  flags: Record<string, Record<string, string>>;
}

export interface RowsParams {
  offset: number;
  limit: number;
  sort?: string | null;
  dir?: "asc" | "desc";
  filters?: Filter[];
  search?: string;
  issue_id?: string | null;
  view?: View;
}

export interface Preview {
  affected_rows: number;
  impact: string;
  changes: { column: string; before: unknown; after: unknown; count: number }[];
  rows_before: number;
  rows_after: number;
}

export type Agg = "count" | "sum" | "avg" | "count_distinct";
export interface GroupParams {
  by: string;
  measure?: string | null;
  agg: Agg;
  use_count_unit: boolean;
  view: View;
  filters?: Filter[];
}
export interface GroupResult {
  by: string;
  agg: Agg;
  measure: string | null;
  count_unit: string | null;
  groups: { key: unknown; value: number; rows: number }[];
  /** v2: rows skipped because the group key or measure is missing. */
  excluded_rows?: number;
  /** v2: plain-English warnings about the grouped numbers. */
  caveats?: string[];
}

export interface ReviewResult {
  orientation: Orientation;
  issues: Issue[];
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface Api {
  health(): Promise<Health_>;
  datasets(): Promise<Dataset[]>;
  upload(file: File): Promise<Dataset[]>;
  profile(id: string, view: View): Promise<Profile>;
  issues(id: string): Promise<Issue[]>;
  rows(id: string, p: RowsParams): Promise<RowsPage>;
  preview(id: string, op: Op): Promise<Preview>;
  decisions(id: string): Promise<Decision[]>;
  addDecision(id: string, body: { op: Op | null; issue_id?: string; reason?: string }): Promise<Decision>;
  toggleDecision(id: string, did: string, enabled: boolean): Promise<Decision>;
  removeDecision(id: string, did: string): Promise<{ ok: true }>;
  skip(id: string, iid: string): Promise<Issue>;
  review(id: string): Promise<ReviewResult>;
  chatHistory(id: string): Promise<{ log: ChatEntry[] }>;
  chatSend(id: string, message: string): Promise<ChatResult>;
  chatReset(id: string): Promise<{ log: ChatEntry[] }>;
  group(id: string, p: GroupParams): Promise<GroupResult>;
  reset(id: string): Promise<{ ok: true }>;
  exportCsvUrl(id: string, view: View): string;
  decisionsJsonUrl(id: string): string;
}

const BASE = "/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, init);
  } catch {
    throw new ApiError(0, "Can't reach the Dataful server. Is the backend running on port 8000?");
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

function qs(params: Record<string, unknown>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) {
      if (v.length === 0) continue;
      u.set(k, JSON.stringify(v));
    } else u.set(k, String(v));
  }
  const s = u.toString();
  return s ? "?" + s : "";
}

const enc = encodeURIComponent;

export const httpApi: Api = {
  health: () => req("/health"),
  datasets: () => req("/datasets"),
  upload: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req("/datasets/upload", { method: "POST", body: fd });
  },
  profile: (id, view) => req(`/datasets/${enc(id)}/profile${qs({ view })}`),
  issues: (id) => req(`/datasets/${enc(id)}/issues`),
  rows: (id, p) => req(`/datasets/${enc(id)}/rows${qs({ ...p })}`),
  preview: (id, op) => req(`/datasets/${enc(id)}/preview`, json("POST", { op })),
  decisions: (id) => req(`/datasets/${enc(id)}/decisions`),
  addDecision: (id, body) => req(`/datasets/${enc(id)}/decisions`, json("POST", body)),
  toggleDecision: (id, did, enabled) => req(`/datasets/${enc(id)}/decisions/${enc(did)}`, json("PATCH", { enabled })),
  removeDecision: (id, did) => req(`/datasets/${enc(id)}/decisions/${enc(did)}`, { method: "DELETE" }),
  skip: (id, iid) => req(`/datasets/${enc(id)}/issues/${enc(iid)}/skip`, { method: "POST" }),
  review: (id) => req(`/datasets/${enc(id)}/review`, { method: "POST" }),
  chatHistory: (id) => req(`/datasets/${enc(id)}/chat`),
  chatSend: (id, message) => req(`/datasets/${enc(id)}/chat`, json("POST", { message })),
  chatReset: (id) => req(`/datasets/${enc(id)}/chat`, { method: "DELETE" }),
  group: (id, p) => req(`/datasets/${enc(id)}/group${qs({ ...p })}`),
  reset: (id) => req(`/datasets/${enc(id)}/reset`, { method: "POST" }),
  exportCsvUrl: (id, view) => `${BASE}/datasets/${enc(id)}/export.csv${qs({ view })}`,
  decisionsJsonUrl: (id) => `${BASE}/datasets/${enc(id)}/decisions.json`,
};

export const USE_MOCK = import.meta.env.VITE_MOCK === "1";

// Mock layer is loaded lazily and only when explicitly requested.
const mockLoader = () => import("./mock/mockApi").then((m) => m.mockApi);
const lazyMock = new Proxy({} as Api, {
  get(_t, key: keyof Api) {
    if (key === "exportCsvUrl" || key === "decisionsJsonUrl") return httpApi[key];
    return (...args: unknown[]) =>
      mockLoader().then((m) => (m[key] as (...a: unknown[]) => unknown)(...args));
  },
});

export const api: Api = USE_MOCK ? lazyMock : httpApi;

/** Flags keys may be absolute row offsets or page-relative; normalise to absolute. */
export function absoluteFlags(page: RowsPage, offset: number): Map<number, Record<string, string>> {
  const out = new Map<number, Record<string, string>>();
  const keys = Object.keys(page.flags ?? {}).map(Number);
  const relative = offset > 0 && keys.length > 0 && keys.every((k) => k < page.rows.length) && !keys.some((k) => k >= offset);
  for (const k of keys) out.set(relative ? offset + k : k, page.flags[String(k)]);
  return out;
}

/** The op kind of a decision, or null for "keep as is" / malformed decisions. */
/** Issues Claude found itself (review or chat), as opposed to rule issues it only reworded. */
export const foundByAI = (i: Pick<Issue, "family">) => typeof i.family === "string" && i.family.startsWith("ai_");

export const opKind = (d: { op?: Op | null } | null | undefined): Op["op"] | null =>
  d && d.op && typeof d.op === "object" && typeof d.op.op === "string" ? d.op.op : null;

/** Rows in the current view (after decisions), tolerant of v1 servers. */
export const currentRows = (d: Dataset) => (typeof d.rows_current === "number" ? d.rows_current : d.rows);
