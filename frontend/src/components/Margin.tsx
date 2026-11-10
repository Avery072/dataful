import { useMemo, useState } from "react";
import type { Decision, Issue, Severity } from "../api";
import { sortIssues, SEVERITY_LABEL } from "../format";
import { Chat } from "./Chat";
import { DecisionList } from "./DecisionList";
import { Icon, SeverityMark } from "./Glyphs";
import { IssueNote } from "./IssueNote";

type Tab = "all" | Severity;

interface Props {
  datasetId: string;
  issues: Issue[] | undefined;
  decisions: Decision[];
  loading: boolean;
  error?: string;
  focusedId: string | null;
  onFocus: (id: string | null) => void;
  onClose?: () => void;
  onApplied: (issueId: string, message: string) => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  aiEnabled?: boolean;
}

export function Margin({ datasetId, issues, decisions, loading, error, focusedId, onFocus, onClose, onApplied, collapsed = false, onToggleCollapsed, aiEnabled = false }: Props) {
  const [tab, setTab] = useState<Tab>("all");
  const [mode, setMode] = useState<"notes" | "chat">("notes");
  const sorted = useMemo(() => sortIssues(issues ?? []), [issues]);
  const counts = useMemo(() => {
    const c: Record<Severity, number> = { numbers: 0, missing: 0, format: 0 };
    sorted.forEach((i) => (i.status === "open" || i.status === "skipped") && i.severity in c && c[i.severity]++);
    return c;
  }, [sorted]);
  const shown = tab === "all" ? sorted : sorted.filter((i) => i.severity === tab);
  const openCount = counts.numbers + counts.missing + counts.format;

  // The "current" question: the focused one if it's an open question, else the first open question.
  const focused = sorted.find((i) => i.id === focusedId);
  const current =
    focused && focused.kind === "question" && focused.status === "open"
      ? focused
      : sorted.find((i) => i.kind === "question" && i.status === "open");
  const questionsLeft = sorted.filter((i) => i.kind === "question" && i.status === "open").length;

  if (collapsed) {
    return (
      <aside className="margin margin-rail" aria-label="Margin notes (collapsed)">
        <button className="rail-btn" onClick={onToggleCollapsed} aria-label={`Show notes${openCount ? ` (${openCount} open)` : ""}`} title="Show notes">
          <Icon name="expand" />
          <span className="rail-label serif">Notes</span>
          {openCount > 0 && <span className="count">{openCount}</span>}
        </button>
      </aside>
    );
  }

  return (
    <aside className="margin" aria-label="Margin notes">
      <div className="margin-head">
        <h2 className="serif margin-modes" role="tablist" aria-label="Notes or chat">
          <button role="tab" aria-selected={mode === "notes"} className={mode === "notes" ? "on" : ""} onClick={() => setMode("notes")}>
            Notes <span className="dim">{openCount > 0 ? `· ${openCount} open` : ""}</span>
          </button>
          <button role="tab" aria-selected={mode === "chat"} className={mode === "chat" ? "on" : ""} onClick={() => setMode("chat")}>
            Ask Dataful
          </button>
        </h2>
        {onToggleCollapsed && (
          <button className="icon-btn" onClick={onToggleCollapsed} aria-label="Hide notes to make room for the table" title="Hide notes">
            <Icon name="collapse" />
          </button>
        )}
        {onClose && (
          <button className="icon-btn" onClick={onClose} aria-label="Close notes">
            <Icon name="close" />
          </button>
        )}
      </div>
      {mode === "chat" ? (
        <Chat
          datasetId={datasetId}
          aiEnabled={aiEnabled}
          issues={issues ?? []}
          onShowIssue={(id) => {
            setMode("notes");
            setTab("all");
            onFocus(id);
          }}
        />
      ) : (
      <>
      <div className="tabs" role="tablist" aria-label="Filter notes by kind">
        <button role="tab" aria-selected={tab === "all"} className={tab === "all" ? "on" : ""} onClick={() => setTab("all")}>
          All
        </button>
        {(["numbers", "missing", "format"] as Severity[]).map((s) => (
          <button key={s} role="tab" aria-selected={tab === s} className={tab === s ? "on" : ""} onClick={() => setTab(s)}>
            <SeverityMark severity={s} /> {SEVERITY_LABEL[s]} <span className="count">{counts[s]}</span>
          </button>
        ))}
      </div>
      {questionsLeft > 0 && <p className="q-progress small">{questionsLeft === 1 ? "1 question needs your judgment" : `${questionsLeft} questions need your judgment`}</p>}

      <div className="notes">
        {loading && !issues && [0, 1, 2].map((i) => <div key={i} className="note-skel"><span className="skeleton" style={{ width: "70%" }} /><span className="skeleton" style={{ width: "90%" }} /><span className="skeleton" style={{ width: "40%" }} /></div>)}
        {error && <p className="error small">Couldn't load notes: {error}</p>}
        {issues && shown.length === 0 && <p className="dim small empty-notes">{tab === "all" ? "Nothing suspicious found. This data looks clean." : "Nothing in this category."}</p>}
        {shown.map((i) => (
          <IssueNote
            key={i.id}
            datasetId={datasetId}
            issue={i}
            focused={focusedId === i.id}
            current={current?.id === i.id}
            onFocus={() => onFocus(focusedId === i.id ? null : i.id)}
            onApplied={(msg) => onApplied(i.id, msg)}
          />
        ))}
      </div>

      <DecisionList datasetId={datasetId} decisions={decisions} onFocusIssue={(id) => onFocus(id)} />
      </>
      )}
    </aside>
  );
}
