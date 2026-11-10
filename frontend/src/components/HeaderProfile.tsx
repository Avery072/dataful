import type { Column } from "../api";
import { fmtCompact, fmtPct, isNumericCol } from "../format";
import { MiniHistogram, TopValues } from "./charts";
import { HealthMark, Icon, RoleGlyph } from "./Glyphs";
import { Num } from "./Num";

interface Props {
  col: Column;
  width: number;
  total: number;
  sort: "asc" | "desc" | null;
  highlighted: boolean;
  open: boolean;
  onOpen: (rect: DOMRect) => void;
  onSort: () => void;
  resizeHandler: (e: unknown) => void;
  resizing: boolean;
}

export function HeaderProfile({ col, width, total, sort, highlighted, open, onOpen, onSort, resizeHandler, resizing }: Props) {
  const inner = Math.max(40, width - 20);
  const showHist = !!col.histogram?.length && (isNumericCol(col) || col.type === "date" || col.role === "time");
  return (
    <div
      className={"hp" + (highlighted ? " col-hl" : "") + (open ? " open" : "") + (isNumericCol(col) ? " num" : "")}
      style={{ width }}
      role="columnheader"
      aria-sort={sort === "asc" ? "ascending" : sort === "desc" ? "descending" : "none"}
    >
      <div className="hp-top">
        <button
          className="hp-name"
          onClick={(e) => onOpen((e.currentTarget.parentElement!.parentElement as HTMLElement).getBoundingClientRect())}
          aria-haspopup="dialog"
          aria-expanded={open}
          title={`${col.name} — click for details`}
        >
          <RoleGlyph role={col.role} />
          <span className="hp-label">{col.name}</span>
        </button>
        <button className={"hp-sort" + (sort ? " on" : "")} onClick={onSort} aria-label={`Sort by ${col.name}${sort ? ` (currently ${sort})` : ""}`}>
          <Icon name={sort === "asc" ? "sort-asc" : sort === "desc" ? "sort-desc" : "sort"} size={12} />
        </button>
      </div>
      <div className="hp-chart" onClick={(e) => onOpen((e.currentTarget.parentElement as HTMLElement).getBoundingClientRect())}>
        {showHist ? (
          <MiniHistogram col={col} width={inner} height={30} />
        ) : col.top_values?.length ? (
          <TopValues col={col} total={total} width={inner} />
        ) : (
          <div className="mini-caption id-caption">
            {fmtCompact(col.distinct)} distinct
            {col.distinct < total && col.role === "identifier" ? ` · repeats` : ""}
          </div>
        )}
      </div>
      <div className="hp-foot">
        <HealthMark health={col.health} />
        <span className={col.missing_pct > 0 ? "hp-missing has" : "hp-missing"}>
          {col.missing_pct > 0 ? (
            <>
              <Num value={col.missing_pct} format={fmtPct} /> missing
            </>
          ) : (
            "complete"
          )}
        </span>
        {!showHist && (col.role === "category" || col.role === "geo") && col.distinct > 3 && <span className="hp-distinct">{fmtCompact(col.distinct)} values</span>}
      </div>
      <div
        className={"resizer" + (resizing ? " active" : "")}
        onMouseDown={resizeHandler}
        onTouchStart={resizeHandler}
        onClick={(e) => e.stopPropagation()}
        role="separator"
        aria-label={`Resize ${col.name}`}
      />
    </div>
  );
}
