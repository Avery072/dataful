// DEV-ONLY mock of the Dataful API, used only when VITE_MOCK=1.
// A tiny in-memory imitation of the Olympics demo so the UI can be built
// before the backend exists. Not used by default builds.
import type { Api, Column, Dataset, Decision, Issue, Op, Profile, RowsPage, View } from "../api";

const COLS = ["ID", "Name", "Sex", "Age", "Height", "Weight", "Team", "NOC", "Games", "Year", "Season", "City", "Sport", "Event", "Medal"];
const TOTAL = 271116;
const NAMES = ["A Dijiang", "A Lamusi", "Gunnar Aaby", "Edgar Aabye", "Christine Aaftink", "Per Knut Aaland", "John Aalberg", "Cornelia Aalten", "Pepijn Aardewijn", "Jan-Erik Aarberg"];
const TEAMS: [string, string][] = [["United States", "USA"], ["China", "CHN"], ["Denmark", "DEN"], ["Netherlands", "NED"], ["Norway", "NOR"], ["France", "FRA"], ["Great Britain", "GBR"], ["Germany", "GER"]];
const GAMES: [number, string, string][] = [[1992, "Summer", "Barcelona"], [2012, "Summer", "London"], [1920, "Summer", "Antwerpen"], [1900, "Summer", "Paris"], [1988, "Winter", "Calgary"], [1994, "Winter", "Lillehammer"], [2016, "Summer", "Rio de Janeiro"]];
const SPORTS: [string, string][] = [["Basketball", "Basketball Men's Basketball"], ["Judo", "Judo Men's Extra-Lightweight"], ["Football", "Football Men's Football"], ["Tug-Of-War", "Tug-Of-War Men's Tug-Of-War"], ["Speed Skating", "Speed Skating Women's 500 metres"], ["Cross Country Skiing", "Cross Country Skiing Men's 10 kilometres"], ["Swimming", "Swimming Men's 100 metres Freestyle"]];
const MEDALS = ["NA", "NA", "NA", "NA", "NA", "NA", "Gold", "Silver", "Bronze", "NA"];

const rnd = (i: number, salt: number) => {
  let x = (i * 2654435761 + salt * 40503) >>> 0;
  x ^= x >>> 13; x = Math.imul(x, 0x5bd1e995) >>> 0; x ^= x >>> 15;
  return (x >>> 0) / 4294967296;
};

let decisions: Decision[] = [];
const skipped = new Set<string>();

function row(i: number, view: View): unknown[] {
  const t = TEAMS[Math.floor(rnd(i, 1) * TEAMS.length)];
  const g = GAMES[Math.floor(rnd(i, 2) * GAMES.length)];
  const s = SPORTS[Math.floor(rnd(i, 3) * SPORTS.length)];
  const naMissing = view === "decisions" && decisions.some((d) => d.enabled && d.op?.op === "mark_missing");
  let medal: string | null = MEDALS[Math.floor(rnd(i, 4) * MEDALS.length)];
  if (medal === "NA" && naMissing) medal = null;
  const h = rnd(i, 5) < 0.22 ? null : Math.round(150 + rnd(i, 6) * 50);
  return [i + 1, NAMES[i % NAMES.length], rnd(i, 7) < 0.72 ? "M" : "F", rnd(i, 8) < 0.03 ? null : Math.round(16 + rnd(i, 9) * 20), h,
    h === null ? null : Math.round(h - 105 + rnd(i, 10) * 20), t[0], t[1], `${g[0]} ${g[1]}`, g[0], g[1], g[2], s[0], s[1], medal];
}

const hist = (lo: number, hi: number, peak: number) =>
  Array.from({ length: 12 }, (_, k) => {
    const start = lo + ((hi - lo) / 12) * k;
    const d = (k - peak) / 3;
    return { start, end: start + (hi - lo) / 12, count: Math.round(40000 * Math.exp(-d * d)) + 200 };
  });

function columns(view: View): Column[] {
  const naFixed = view === "decisions" && decisions.some((d) => d.enabled && d.op?.op === "mark_missing");
  const c = (name: string, o: Partial<Column>): Column => ({
    name, type: "text", role: "category", missing: 0, missing_pct: 0, distinct: 10, top_values: [], histogram: null,
    min: null, max: null, health: "healthy", issue_ids: [], ...o,
  });
  return [
    c("ID", { type: "integer", role: "identifier", distinct: 135571, min: 1, max: 135571, health: "trap", issue_ids: ["dup-rows"] }),
    c("Name", { role: "text", distinct: 134732, top_values: [{ value: "Robert Tait McKenzie", count: 58 }] }),
    c("Sex", { distinct: 2, top_values: [{ value: "M", count: 196594 }, { value: "F", count: 74522 }] }),
    c("Age", { type: "integer", role: "measure", missing: 9474, missing_pct: 0.035, distinct: 74, min: 10, max: 97, histogram: hist(10, 97, 3), health: "gaps" }),
    c("Height", { type: "integer", role: "measure", missing: 60171, missing_pct: 0.222, distinct: 95, min: 127, max: 226, histogram: hist(127, 226, 5), health: "gaps" }),
    c("Weight", { type: "decimal", role: "measure", missing: 62875, missing_pct: 0.232, distinct: 220, min: 25, max: 214, histogram: hist(25, 214, 3), health: "gaps" }),
    c("Team", { distinct: 1184, top_values: [{ value: "United States", count: 17847 }, { value: "France", count: 11988 }, { value: "Great Britain", count: 11404 }, { value: "Italy", count: 10260 }, { value: "Germany", count: 9326 }], health: "trap", issue_ids: ["team-variants"] }),
    c("NOC", { role: "geo", distinct: 230, top_values: [{ value: "USA", count: 18853 }, { value: "FRA", count: 12758 }, { value: "GBR", count: 12256 }] }),
    c("Games", { distinct: 51, top_values: [{ value: "2000 Summer", count: 13821 }, { value: "1996 Summer", count: 13780 }] }),
    c("Year", { type: "integer", role: "time", distinct: 35, min: 1896, max: 2016, histogram: hist(1896, 2016, 9) }),
    c("Season", { distinct: 2, top_values: [{ value: "Summer", count: 222552 }, { value: "Winter", count: 48564 }] }),
    c("City", { role: "geo", distinct: 42, top_values: [{ value: "London", count: 22426 }, { value: "Athina", count: 15556 }] }),
    c("Sport", { distinct: 66, top_values: [{ value: "Athletics", count: 38624 }, { value: "Gymnastics", count: 26707 }, { value: "Swimming", count: 23195 }] }),
    c("Event", { role: "text", distinct: 765, top_values: [{ value: "Football Men's Football", count: 5733 }] }),
    c("Medal", {
      distinct: 4, missing: naFixed ? 231333 : 0, missing_pct: naFixed ? 0.853 : 0,
      top_values: naFixed ? [{ value: "Gold", count: 13372 }, { value: "Bronze", count: 13295 }, { value: "Silver", count: 13116 }]
        : [{ value: "NA", count: 231333 }, { value: "Gold", count: 13372 }, { value: "Bronze", count: 13295 }, { value: "Silver", count: 13116 }],
      health: naFixed ? "trap" : "trap", issue_ids: ["medal-na", "team-golds"],
    }),
  ];
}

const DATASETS: Dataset[] = [
  { id: "olympics-athlete-events", name: "Olympic athletes", file: "athlete_events.csv", sheet: null, rows: TOTAL, columns: 15, demo: true },
  { id: "employees", name: "Messy employees", file: "Messy_Employee_dataset.csv", sheet: null, rows: 1020, columns: 12, demo: true },
  { id: "bookshop-sales-q1", name: "Bookshop · Sales Q1", file: "Bookshop.xlsx", sheet: "Sales Q1", rows: 1200, columns: 6, demo: true },
  { id: "bookshop-books", name: "Bookshop · Books", file: "Bookshop.xlsx", sheet: "Books", rows: 340, columns: 8, demo: true },
];

const markNa: Op = { op: "mark_missing", column: "Medal", values: ["NA"] };
const unit: Op = { op: "set_count_unit", columns: ["Games", "Event", "Team", "Medal"], label: "medals" };

function issues(): Issue[] {
  const base: Issue[] = [
    { id: "team-golds", family: "double_counting", title: "Team golds are counted once per player", detail: "A basketball gold appears 12 times — once for each athlete. Counting rows inflates medal totals (USA: 2,638 rows vs ≈1,131 medals).", severity: "numbers", confidence: "likely", columns: ["Games", "Event", "Team", "Medal"], affected_rows: 39783, evidence: { for: ["Same Games + Event + Team + Medal repeats up to 12 times", "Repeats happen only in team sports"], against: ["Some events legitimately award tied medals"] }, kind: "question", question: "Should a team win count once, or once per athlete?", options: [{ label: "Once per team", op: unit, description: "Count medals, not medal rows" }, { label: "Once per athlete", op: null, description: "Keep counting rows" }], status: "open", decision_id: null, source: "rules" },
    { id: "dup-rows", family: "duplicate_rows", title: "1,385 rows are exact copies", detail: "Identical rows inflate every count. Keeping one copy is safe.", severity: "numbers", confidence: "certain", columns: [], affected_rows: 1385, evidence: { for: ["All 15 columns identical"], against: [] }, kind: "fix", question: null, options: [{ label: "Fix it", op: { op: "remove_duplicates", columns: null } }], status: "open", decision_id: null, source: "rules" },
    { id: "team-variants", family: "inconsistent_categories", title: "Team has 1,184 values — many are variants", detail: "'United States-1' and 'United States-2' are boat crews of United States.", severity: "numbers", confidence: "guess", columns: ["Team"], affected_rows: 6421, evidence: { for: ["Suffix '-1', '-2' pattern on 312 values"], against: ["NOC already identifies the country"] }, kind: "question", question: "Merge numbered crews into their country?", options: [{ label: "Merge them", op: { op: "merge_values", column: "Team", from: ["United States-1", "United States-2"], to: "United States" } }, { label: "Keep separate", op: { op: "keep_separate", column: "Team", values: ["United States-1", "United States-2"] } }], status: "open", decision_id: null, source: "rules" },
    { id: "medal-na", family: "disguised_missing", title: "231,333 Medal cells are the text 'NA'", detail: "'NA' is text, so it's counted as a medal type. It means no medal.", severity: "missing", confidence: "certain", columns: ["Medal"], affected_rows: 231333, evidence: { for: ["'NA' is a known placeholder"], against: [] }, kind: "fix", question: null, options: [{ label: "Fix it", op: markNa }], status: "open", decision_id: null, source: "rules" },
    { id: "height-gaps", family: "default_values", title: "Height is missing for 22% of athletes", detail: "Mostly before 1960 — averages skew towards modern athletes.", severity: "missing", confidence: "likely", columns: ["Height", "Weight"], affected_rows: 60171, evidence: { for: ["Missing rate 71% before 1960, 6% after"], against: [] }, kind: "question", question: "Leave missing heights out of averages?", options: [{ label: "Leave them out", op: null }, { label: "Drop those rows", op: { op: "drop_rows", where: [{ column: "Height", op: "is_missing" }] } }], status: "open", decision_id: null, source: "rules" },
    { id: "games-combined", family: "combined_field", title: "Games repeats Year + Season", detail: "'1992 Summer' is just Year and Season joined.", severity: "format", confidence: "certain", columns: ["Games"], affected_rows: 0, evidence: { for: ["Matches Year + ' ' + Season on every row"], against: [] }, kind: "fix", question: null, options: [{ label: "Fix it", op: { op: "split_column", column: "Games", sep: " ", into: ["Games year", "Games season"] } }], status: "open", decision_id: null, source: "rules" },
  ];
  return base.map((i) => {
    const d = decisions.find((x) => x.issue_id === i.id);
    if (d) return { ...i, status: d.op?.op === "keep_separate" ? "kept" : "resolved", decision_id: d.id };
    if (skipped.has(i.id)) return { ...i, status: "skipped" };
    return i;
  });
}

const wait = <T,>(v: T, ms = 120) => new Promise<T>((r) => setTimeout(() => r(structuredClone(v)), ms));

export const mockApi: Api = {
  health: () => wait({ ok: true, ai_enabled: false, model: null }),
  datasets: () => wait(DATASETS),
  upload: async (file) => wait([{ id: "up-" + file.name, name: file.name.replace(/\.\w+$/, ""), file: file.name, sheet: null, rows: 100, columns: 5, demo: false }], 600),
  profile: (id, view) => {
    const ds = DATASETS.find((d) => d.id === id) ?? DATASETS[0];
    const p: Profile = {
      dataset: { ...ds, rows: view === "decisions" && decisions.some((d) => d.enabled && d.op?.op === "remove_duplicates") ? TOTAL - 1385 : TOTAL },
      columns: columns(view),
      orientation: {
        row_meaning: "Each row is one athlete competing in one event at one Games.",
        summary: "120 years of Olympics, 1896–2016, across 51 Games and 230 nations.",
        groups: [
          { name: "Who", columns: ["ID", "Name", "Sex", "Age", "Height", "Weight"] },
          { name: "Where", columns: ["Team", "NOC", "City"] },
          { name: "When", columns: ["Games", "Year", "Season"] },
          { name: "What", columns: ["Sport", "Event", "Medal"] },
        ],
        source: "rules",
      },
      ai_reviewed: false,
    };
    return wait(p);
  },
  issues: () => wait(issues()),
  rows: (_id, p) => {
    const view = p.view ?? "decisions";
    let total = TOTAL;
    let map = (i: number) => i;
    if (p.issue_id === "medal-na" || p.issue_id === "team-golds") { total = Math.floor(TOTAL * 0.4); map = (i) => i * 2; }
    const rows: unknown[][] = [];
    const flags: RowsPage["flags"] = {};
    for (let k = p.offset; k < Math.min(total, p.offset + p.limit); k++) {
      const r = row(map(k), view);
      rows.push(r);
      if (r[14] === "NA") flags[k] = { Medal: "medal-na" };
      if (r[4] === null) flags[k] = { ...(flags[k] ?? {}), Height: "height-gaps" };
    }
    return wait({ total, columns: COLS, rows, flags }, 80);
  },
  preview: (_id, op) =>
    wait({
      affected_rows: op.op === "mark_missing" ? 231333 : 1385,
      impact: op.op === "set_count_unit" ? "USA golds: 2,638 rows → 1,131 medals" : op.op === "mark_missing" ? "Medal types: 4 → 3; 'NA' becomes blank" : "Rows: 271,116 → 269,731",
      changes: op.op === "mark_missing" ? [{ column: "Medal", before: "NA", after: null, count: 231333 }]
        : op.op === "set_count_unit" ? [{ column: "count", before: 2638, after: 1131, count: 1 }]
        : [{ column: "Name", before: "John Smith (×2)", after: "John Smith", count: 1385 }],
      rows_before: TOTAL,
      rows_after: op.op === "remove_duplicates" ? TOTAL - 1385 : TOTAL,
    }, 300),
  decisions: () => wait(decisions),
  addDecision: (_id, body) => {
    const plain: Record<string, string> = {
      mark_missing: "Treat 'NA' in Medal as missing", remove_duplicates: "Keep one copy of identical rows",
      set_count_unit: "Count a team win once (Games, Event, Team, Medal)", split_column: "Split Games into year and season",
      merge_values: "Merge numbered crews into their country", keep_separate: "Keep numbered crews separate", drop_rows: "Exclude rows with no Height",
    };
    const d: Decision = { id: "d" + Date.now(), op: body.op, plain: body.op ? plain[body.op.op] ?? body.op.op : "Keep as is", issue_id: body.issue_id ?? null, reason: body.reason ?? null, enabled: true, created_at: new Date().toISOString() };
    decisions = [...decisions, d];
    if (body.issue_id) skipped.delete(body.issue_id);
    return wait(d);
  },
  toggleDecision: (_id, did, enabled) => {
    decisions = decisions.map((d) => (d.id === did ? { ...d, enabled } : d));
    return wait(decisions.find((d) => d.id === did)!);
  },
  removeDecision: (_id, did) => {
    decisions = decisions.filter((d) => d.id !== did);
    return wait({ ok: true as const });
  },
  skip: (_id, iid) => {
    skipped.add(iid);
    return wait(issues().find((i) => i.id === iid)!);
  },
  reset: () => {
    decisions = [];
    skipped.clear();
    return wait({ ok: true as const });
  },
  review: () => Promise.reject(new Error("No API key (mock)")),
  chatHistory: () => Promise.resolve({ log: [] }),
  chatSend: () => Promise.reject(new Error("No API key (mock)")),
  chatReset: () => Promise.resolve({ log: [] }),
  group: (_id, p) => {
    const unitOn = p.use_count_unit && decisions.some((d) => d.enabled && d.op?.op === "set_count_unit");
    const keys = p.by === "Medal" ? ["Gold", "Bronze", "Silver"] : p.by === "NOC" || p.by === "Team" ? ["USA", "URS", "GER", "GBR", "FRA", "ITA", "SWE", "CAN"] : ["Athletics", "Gymnastics", "Swimming", "Shooting", "Cycling"];
    const base = p.by === "Medal" ? [13372, 13295, 13116] : [5637, 2503, 2165, 2068, 1777, 1637, 1536, 1352];
    return wait({
      by: p.by, agg: p.agg, measure: p.measure ?? null, count_unit: unitOn ? "medals" : null,
      groups: keys.map((k, i) => ({ key: k, value: Math.round((base[i] ?? 900) * (unitOn ? 0.43 : 1)), rows: base[i] ?? 900 })),
    });
  },
  exportCsvUrl: () => "#",
  decisionsJsonUrl: () => "#",
};
