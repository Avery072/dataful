import { useEffect, useRef } from "react";
import type { Issue } from "../api";
import { fmtCell } from "../format";
import { SeverityMark } from "./Glyphs";

export interface TipState {
  issueId: string;
  column: string;
  value: unknown;
  rect: DOMRect;
  pinned: boolean;
  closing?: boolean;
}

/** Spell-check style explanation for a flagged cell. */
export function CellTooltip({ tip, issue, onClose, onKeep, onOpenNote }: { tip: TipState; issue?: Issue; onClose: () => void; onKeep: () => void; onOpenNote: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!tip.closing) return;
    const t = setTimeout(onClose, 220);
    return () => clearTimeout(t);
  }, [tip.closing, onClose]);
  useEffect(() => {
    if (!tip.pinned) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && onClose();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const t = setTimeout(() => window.addEventListener("mousedown", onDown), 0);
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [tip.pinned, onClose]);

  const left = Math.min(tip.rect.left, window.innerWidth - 300);
  const below = tip.rect.bottom + 140 < window.innerHeight;
  const style = below ? { left, top: tip.rect.bottom + 4 } : { left, bottom: window.innerHeight - tip.rect.top + 4 };
  return (
    <div className="popover cell-tip" ref={ref} style={style} role="tooltip" onMouseEnter={onKeep} onMouseLeave={() => !tip.pinned && onClose()}>
      {issue ? (
        <>
          <p className="ct-title serif">
            <SeverityMark severity={issue.severity} /> {issue.title}
          </p>
          <p className="ct-detail">
            <span className="mono">{tip.column}</span> = <span className="mono">{fmtCell(tip.value)}</span>. {issue.detail}
          </p>
          <button className="link-btn" onClick={onOpenNote}>
            Open the note →
          </button>
        </>
      ) : (
        <p className="ct-detail">This cell is flagged ({tip.issueId}).</p>
      )}
    </div>
  );
}
