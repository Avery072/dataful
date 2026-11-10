import { useRef } from "react";
import { currentRows, type Dataset } from "../api";
import { fmtCompact, fmtInt } from "../format";
import { Icon } from "./Glyphs";

interface Props {
  datasets: Dataset[] | undefined;
  loading: boolean;
  error?: string;
  selected: string | null;
  onSelect: (id: string) => void;
  onUpload: (f: File) => void;
  uploading: boolean;
  uploadError?: string;
  theme: "light" | "dark";
  onToggleTheme: () => void;
}

interface FileGroup {
  file: string;
  items: Dataset[];
}

function groupByFile(ds: Dataset[]): FileGroup[] {
  const m = new Map<string, Dataset[]>();
  for (const d of ds) {
    const k = d.sheet ? d.file : `${d.file}\u0000${d.id}`;
    m.set(k, [...(m.get(k) ?? []), d]);
  }
  return [...m.entries()].map(([k, items]) => ({ file: k.split("\u0000")[0], items }));
}

export const ACCEPT = ".csv,.tsv,.xlsx";

export function Sidebar({ datasets, loading, error, selected, onSelect, onUpload, uploading, uploadError, theme, onToggleTheme }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const demos = groupByFile((datasets ?? []).filter((d) => d.demo));
  const mine = groupByFile((datasets ?? []).filter((d) => !d.demo));

  const item = (d: Dataset, nested = false) => {
    const n = currentRows(d);
    const changed = n !== d.rows;
    const name = (nested ? d.sheet : d.name) ?? d.name;
    return (
      <li key={d.id}>
        <button
          className={"ds-item" + (selected === d.id ? " on" : "") + (nested ? " nested" : "")}
          onClick={() => onSelect(d.id)}
          aria-current={selected === d.id ? "page" : undefined}
          aria-label={`Open ${name}${nested ? ` (${d.file})` : ""}, ${fmtInt(n)} rows${changed ? ` after your decisions (${fmtInt(d.rows)} in the file)` : ""}`}
          title={changed ? `${fmtInt(n)} rows after your decisions · ${fmtInt(d.rows)} in the file` : `${fmtInt(n)} rows`}
        >
          <span className="ds-name">{name}</span>
          <span className={"ds-rows" + (changed ? " changed" : "")}>{fmtCompact(n)}</span>
        </button>
      </li>
    );
  };

  const section = (title: string, groups: FileGroup[]) =>
    groups.length > 0 && (
      <section>
        <h2>{title}</h2>
        <ul>
          {groups.map((g) =>
            g.items.length === 1 && !g.items[0].sheet ? (
              item(g.items[0])
            ) : (
              <li key={g.file} className="ds-file">
                <span className="ds-file-name">
                  <Icon name="sheet" size={12} /> {g.file}
                </span>
                <ul>{g.items.map((d) => item(d, true))}</ul>
              </li>
            ),
          )}
        </ul>
      </section>
    );

  return (
    <nav className="sidebar" aria-label="Datasets">
      <div className="brand">
        <span className="logo" aria-hidden>
          <svg width="18" height="18" viewBox="0 0 32 32">
            <rect x="7" y="17" width="4" height="8" rx="1.5" fill="currentColor" />
            <rect x="14" y="11" width="4" height="14" rx="1.5" fill="currentColor" />
            <rect x="21" y="7" width="4" height="18" rx="1.5" className="logo-accent" />
          </svg>
        </span>
        <span className="serif brand-name">Dataful</span>
        <button className="icon-btn theme-btn" onClick={onToggleTheme} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}>
          <Icon name={theme === "dark" ? "sun" : "moon"} />
        </button>
      </div>

      <div className="ds-list">
        {loading && [0, 1, 2, 3].map((i) => <span key={i} className="skeleton" style={{ width: `${70 - i * 8}%`, margin: "10px 12px" }} />)}
        {error && <p className="error small pad">{error}</p>}
        {section("Your files", mine)}
        {section("Examples", demos)}
      </div>

      <div className="add-file">
        <input
          ref={input}
          type="file"
          accept={ACCEPT}
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onUpload(f);
            e.target.value = "";
          }}
        />
        <button className="btn ghost wide" onClick={() => input.current?.click()} disabled={uploading} aria-label="Add a file (.csv, .tsv or .xlsx)">
          <Icon name="plus" /> {uploading ? "Reading file…" : "Add file"}
        </button>
        <p className="small dim">or drop a .csv, .tsv or .xlsx anywhere</p>
        {uploadError && <p className="error small">{uploadError}</p>}
      </div>
    </nav>
  );
}
