import type { Decision } from "../api";
import { api } from "../api";
import { useDecisionMutations } from "../hooks/useDataset";
import { Icon } from "./Glyphs";

export function DecisionList({ datasetId, decisions, onFocusIssue }: { datasetId: string; decisions: Decision[]; onFocusIssue: (id: string) => void }) {
  const { toggle, remove } = useDecisionMutations(datasetId);
  const busy = toggle.isPending || remove.isPending;
  const err = (toggle.error ?? remove.error) as Error | null;
  return (
    <section className="decisions" aria-labelledby="dec-h">
      <div className="section-head">
        <h2 id="dec-h">Your decisions</h2>
        {decisions.length > 0 && (
          <a className="link-btn small" href={api.decisionsJsonUrl(datasetId)} download>
            <Icon name="download" size={12} /> JSON
          </a>
        )}
      </div>
      {decisions.length === 0 ? (
        <p className="dim small empty-dec">Nothing changed yet. Every fix you approve lands here — readable, reversible, and replayable next month.</p>
      ) : (
        <ol>
          {decisions.map((d, i) => {
            const id = typeof d.id === "string" && d.id ? d.id : null;
            const plain = d.plain || "A saved decision";
            if (d.broken) {
              return (
                <li key={id ?? `broken-${i}`} className="broken">
                  <span className="dec-n">{i + 1}</span>
                  <div className="dec-body">
                    <span className="dec-plain">{plain}</span>
                    <span className="dec-error small">
                      <span aria-hidden>▲</span> No longer fits this data{d.error ? ` — ${d.error}` : ""}. It's switched off.
                    </span>
                  </div>
                  {id && (
                    <button className="link-btn tiny" onClick={() => remove.mutate(id)} disabled={busy} aria-label={`Remove broken decision: ${plain}`}>
                      Remove
                    </button>
                  )}
                </li>
              );
            }
            return (
              <li key={id ?? `d-${i}`} className={d.enabled ? "" : "off"}>
                <span className="dec-n">{i + 1}</span>
                <div className="dec-body">
                  <span className="dec-plain">{plain}</span>
                  {d.reason && d.reason !== plain && <span className="dec-reason">“{d.reason}”</span>}
                  {d.issue_id && (
                    <button className="link-btn tiny" onClick={() => onFocusIssue(d.issue_id!)}>
                      see note
                    </button>
                  )}
                </div>
                <label className="switch" title={d.enabled ? "On — click to turn off" : "Off — click to turn on"}>
                  <input
                    type="checkbox"
                    checked={!!d.enabled}
                    disabled={busy || !id}
                    onChange={(e) => id && toggle.mutate({ did: id, enabled: e.target.checked })}
                    aria-label={`${d.enabled ? "Turn off" : "Turn on"}: ${plain}`}
                  />
                  <span aria-hidden />
                </label>
                <button className="icon-btn" onClick={() => id && remove.mutate(id)} disabled={busy || !id} aria-label={`Remove decision: ${plain}`}>
                  <Icon name="close" size={12} />
                </button>
              </li>
            );
          })}
        </ol>
      )}
      {err && <p className="error small">Couldn't update that decision: {err.message}</p>}
    </section>
  );
}
