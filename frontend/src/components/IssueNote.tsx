import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, foundByAI, type Issue, type Option, type Preview } from "../api";
import { fmtCell, fmtInt, plural } from "../format";
import { useDecisionMutations } from "../hooks/useDataset";
import { SeverityMark } from "./Glyphs";

const CONF_LABEL = { certain: "certain", likely: "likely", guess: "a guess" } as const;
const STATUS_LABEL: Record<string, string> = { resolved: "applied", kept: "kept as is", flagged: "flagged", skipped: "unresolved" };

interface Props {
  datasetId: string;
  issue: Issue;
  focused: boolean;
  current: boolean;
  onFocus: () => void;
  onApplied?: (message: string) => void;
}

const NOT_SURE = /^(not sure|unsure|skip|decide later|i don.?t know)|decide later|skip for now/i;
const norm = (s: string) => s.toLowerCase().replace(/[—–-]/g, " ").replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").trim();

/** Valid, de-duplicated answer options. "Not sure" variants are dropped — the note renders exactly one itself. */
export function cleanOptions(options: unknown): { options: Option[]; hadNotSure: boolean } {
  const seen = new Set<string>();
  const out: Option[] = [];
  let hadNotSure = false;
  for (const o of Array.isArray(options) ? options : []) {
    if (!o || typeof o !== "object" || typeof (o as Option).label !== "string") continue;
    const opt = o as Option;
    if (!opt.op && NOT_SURE.test(opt.label)) {
      hadNotSure = true;
      continue;
    }
    const k = norm(opt.label);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push({ ...opt, op: opt.op && typeof opt.op === "object" ? opt.op : null });
  }
  return { options: out, hadNotSure };
}

/** Short confirmation after a decision is applied. */
function appliedMessage(issue: Issue, option: Option, p: Preview | undefined): string {
  if (!option.op) return "Noted — nothing in the data changed";
  const kind = option.op.op;
  const n = p?.affected_rows ?? 0;
  if (p && p.rows_before !== p.rows_after) {
    const gone = p.rows_before - p.rows_after;
    return `Done — ${plural(Math.abs(gone), "row")} ${gone > 0 ? "removed" : "added"} · ${fmtInt(p.rows_after)} left`;
  }
  if (kind === "flag_rows" || kind === "flag_duplicates") return n > 0 ? `Flagged — ${plural(n, "row")} marked` : "Flagged";
  if (kind === "keep_separate" || kind === "set_count_unit") return "Saved — your answer is remembered";
  if (n > 0) return `Fixed — ${plural(n, "row")} updated`;
  return issue.kind === "fix" ? "Fixed" : "Saved";
}

export function IssueNote({ datasetId, issue, focused, current, onFocus, onApplied }: Props) {
  const [chosen, setChosen] = useState<number | null>(null);
  const [peek, setPeek] = useState(false);
  const { options } = cleanOptions(issue.options);
  const evFor = Array.isArray(issue.evidence?.for) ? issue.evidence.for : [];
  const evAgainst = Array.isArray(issue.evidence?.against) ? issue.evidence.against : [];
  const columns = Array.isArray(issue.columns) ? issue.columns : [];
  const ref = useRef<HTMLElement>(null);
  const { add, skip, remove } = useDecisionMutations(datasetId);
  const open = issue.status === "open" || issue.status === "skipped";
  const expanded = focused || (current && open) || peek || chosen != null;

  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focused]);
  useEffect(() => {
    if (!open) {
      setChosen(null);
      setPeek(false);
    }
  }, [open]);

  const option: Option | null = chosen != null ? options[chosen] ?? null : null;

  const confirm = async (preview?: Preview) => {
    if (!option) return;
    const reason = issue.kind === "question" ? option.label : undefined;
    try {
      // op null = "keep as is". Re-answering replaces the earlier decision for this issue (v2).
      await add.mutateAsync({ op: option.op ?? null, issue_id: issue.id, reason });
    } catch {
      return; // error is shown in the preview block
    }
    setChosen(null);
    setPeek(false);
    onApplied?.(appliedMessage(issue, option, preview));
  };

  const cls = [
    "note",
    `sev-${issue.severity}`,
    focused ? "focused" : "",
    current && open ? "current" : "",
    !open ? "done" : "",
    issue.status === "skipped" ? "skipped" : "",
  ].join(" ");

  return (
    <article className={cls} ref={ref} aria-current={current ? "true" : undefined}>
      <button
        className="note-head"
        onClick={() => {
          setPeek(false);
          onFocus();
        }}
        aria-expanded={expanded}
        title={focused ? "Click to stop showing only this note's rows" : "Click to show the rows this note is about"}
      >
        <SeverityMark severity={issue.severity} />
        <span className="note-title serif">{issue.title}</span>
      </button>
      <div className="note-meta">
        {CONF_LABEL[issue.confidence] && <span className={`conf conf-${issue.confidence}`}>{CONF_LABEL[issue.confidence]}</span>}
        {issue.affected_rows > 0 && <span>{plural(issue.affected_rows, "row")}</span>}
        {columns.length > 0 && <span className="note-cols" title={columns.join(", ")}>{columns.join(", ")}</span>}
        {foundByAI(issue) ? (
          <span className="ai-tag" title="Claude spotted this; every option was re-checked against your data">AI found</span>
        ) : issue.source === "ai" ? (
          <span className="ai-worded" title="Found by Dataful's rules; Claude only rewrote the wording">AI wording</span>
        ) : null}
        {issue.status !== "open" && <span className={`status status-${issue.status}`}>{STATUS_LABEL[issue.status] ?? issue.status}</span>}
        {!open && issue.decision_id && (
          <button className="link-btn tiny" onClick={() => remove.mutate(issue.decision_id!)} disabled={remove.isPending}>
            undo
          </button>
        )}
      </div>
      <p className="note-detail">{issue.detail}</p>

      {!expanded && open && (
        <div className="note-quick">
          {issue.kind === "fix" ? (
            <button className="btn primary small-btn" onClick={() => setChosen(0)} disabled={!options[0]}>
              Fix it
            </button>
          ) : (
            <button className="btn small-btn accent" onClick={() => setPeek(true)}>
              Answer the question
            </button>
          )}
        </div>
      )}

      {expanded && (
        <div className="note-body">
          {(evFor.length > 0 || evAgainst.length > 0) && (
            <ul className="evidence">
              {evFor.map((e, i) => (
                <li key={"f" + i} className="ev-for">
                  <span aria-label="supports">✓</span> {e}
                </li>
              ))}
              {evAgainst.map((e, i) => (
                <li key={"a" + i} className="ev-against">
                  <span aria-label="argues against">✗</span> {e}
                </li>
              ))}
            </ul>
          )}

          {open && issue.kind === "question" && (
            <div className="question">
              <p className="q-text serif">{issue.question}</p>
              <div className="q-options" role="group" aria-label="Answers">
                {options.map((o, i) => (
                  <button key={i} className={"opt" + (chosen === i ? " on" : "")} onClick={() => setChosen(chosen === i ? null : i)} aria-pressed={chosen === i}>
                    {o.label}
                  </button>
                ))}
              </div>
              {chosen == null && (
                <button className="link-btn muted" onClick={() => skip.mutate(issue.id, { onSuccess: () => setPeek(false) })} disabled={skip.isPending || issue.status === "skipped"}>
                  {issue.status === "skipped" ? "Left for later — pick an answer any time" : "Not sure — decide later"}
                </button>
              )}
            </div>
          )}

          {open && issue.kind === "fix" && chosen == null && (
            <div className="fix-row">
              <button className="btn primary" onClick={() => setChosen(0)} disabled={!options[0]}>
                Fix it
              </button>
              <span className="dim small">You'll see what changes first.</span>
            </div>
          )}

          {open && option && (
            <PreviewBlock
              datasetId={datasetId}
              option={option}
              busy={add.isPending || skip.isPending}
              error={(add.error as Error | null)?.message}
              onYes={confirm}
              onCancel={() => {
                setChosen(null);
                add.reset();
              }}
            />
          )}
        </div>
      )}
    </article>
  );
}

function PreviewBlock({ datasetId, option, busy, error, onYes, onCancel }: { datasetId: string; option: Option; busy: boolean; error?: string; onYes: (p?: Preview) => void; onCancel: () => void }) {
  const op = option.op;
  const preview = useQuery({
    queryKey: ["ds", datasetId, "preview", JSON.stringify(op)],
    queryFn: () => api.preview(datasetId, op!),
    enabled: !!op,
    staleTime: 30_000,
  });
  const p = preview.data;
  return (
    <div className="preview" aria-live="polite">
      {option.description && <p className="small dim">{option.description}</p>}
      {!op && <p className="impact">Nothing in the data changes. Your answer is remembered.</p>}
      {op && preview.isLoading && (
        <div className="preview-loading">
          <span className="skeleton" style={{ width: "80%" }} />
          <span className="skeleton" style={{ width: "55%" }} />
        </div>
      )}
      {op && preview.error && <p className="error small">Couldn't preview: {(preview.error as Error).message}</p>}
      {p && (
        <>
          <p className="impact serif">{p.impact}</p>
          <p className="small dim">
            {p.affected_rows > 0 ? `${plural(p.affected_rows, "row")} affected` : "No values change"}
            {p.rows_before !== p.rows_after && (
              <>
                {" "}
                · rows {fmtInt(p.rows_before)} → <span className="after">{fmtInt(p.rows_after)}</span>
              </>
            )}
          </p>
          {Array.isArray(p.changes) && p.changes.length > 0 && (
            <ul className="changes">
              {p.changes.slice(0, 5).map((c, i) => (
                <li key={i}>
                  <span className="ch-col">{c.column}</span>
                  <del>{fmtCell(c.before)}</del>
                  <span className="arrow" aria-hidden>
                    →
                  </span>
                  <ins>{c.after === null || c.after === undefined || c.after === "" ? "blank" : fmtCell(c.after)}</ins>
                  {c.count > 1 && <span className="ch-n">×{fmtInt(c.count)}</span>}
                </li>
              ))}
              {p.changes.length > 5 && <li className="dim small">+{p.changes.length - 5} more kinds of change</li>}
            </ul>
          )}
        </>
      )}
      {error && <p className="error small">{error}</p>}
      <div className="confirm-row">
        <button className="btn primary" onClick={() => onYes(p)} disabled={busy || (!!op && !p && !preview.error)}>
          {busy ? "Applying…" : op && preview.error ? "Apply without preview" : "Yes, apply"}
        </button>
        <button className="btn ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  );
}
