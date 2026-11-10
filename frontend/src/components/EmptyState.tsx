import type { Dataset } from "../api";
import { fmtInt } from "../format";
import { Icon } from "./Glyphs";

export function EmptyState({ datasets, onSelect, onPickFile }: { datasets: Dataset[]; onSelect: (id: string) => void; onPickFile: () => void }) {
  const demos = datasets.filter((d) => d.demo).slice(0, 6);
  return (
    <main className="page empty">
      <div className="empty-inner">
        <p className="eyebrow">Dataful</p>
        <h1 className="serif">Know what your spreadsheet is saying — and whether to trust it.</h1>
        <p className="lede serif">
          Drop in an export. Dataful reads every row, marks what could quietly change your numbers, and asks you the questions only you can answer. Your original file is never changed.
        </p>
        <div className="empty-actions">
          <button className="btn primary" onClick={onPickFile}>
            <Icon name="plus" /> Open a file
          </button>
          <span className="dim small">.csv, .tsv or .xlsx — or drag it onto this page</span>
        </div>
        {demos.length > 0 && (
          <>
            <h2 className="small-caps">Or start with an example</h2>
            <ul className="demo-cards">
              {demos.map((d) => (
                <li key={d.id}>
                  <button onClick={() => onSelect(d.id)}>
                    <span className="serif demo-name">{d.name}</span>
                    <span className="dim small">
                      {fmtInt(d.rows)} rows · {d.columns} columns
                    </span>
                    <span className="dim small file">
                      {d.file}
                      {d.sheet ? ` › ${d.sheet}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </main>
  );
}
