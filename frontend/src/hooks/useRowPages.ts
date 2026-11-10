import { useQueries } from "@tanstack/react-query";
import { useMemo, useRef } from "react";
import { absoluteFlags, api, type RowsPage, type RowsParams } from "../api";
import { qk } from "./useDataset";

export const PAGE_SIZE = 200;

export type RowQuery = Omit<RowsParams, "offset" | "limit">;

export interface LoadedRow {
  values: unknown[];
  /** 1-based absolute row number (from the server's row_numbers when available). */
  rowNumber?: number;
  flags?: Record<string, string>;
}

/**
 * Server-side paging for the virtualized grid. Only the pages that cover the
 * visible window are requested; React Query keeps the page cache and refetches
 * them when the dataset is invalidated (e.g. after a decision).
 */
export function useRowPages(datasetId: string, params: RowQuery, visible: { start: number; end: number }) {
  const key = JSON.stringify(params);
  const first = Math.floor(visible.start / PAGE_SIZE);
  const last = Math.max(first, Math.floor(Math.max(visible.end, 0) / PAGE_SIZE));
  const pages: number[] = [];
  for (let p = first; p <= last; p++) pages.push(p);

  const results = useQueries({
    queries: pages.map((p) => ({
      queryKey: qk.rows(datasetId, key, p),
      queryFn: () => api.rows(datasetId, { ...params, offset: p * PAGE_SIZE, limit: PAGE_SIZE }),
      staleTime: 60_000,
    })),
  });

  // Remember the last known total for this query so the scroll height doesn't collapse while loading.
  const totals = useRef(new Map<string, number>());
  const unfiltered = useRef<number | undefined>(undefined);
  const loaded = new Map<number, RowsPage>();
  results.forEach((r, i) => {
    if (r.data) {
      loaded.set(pages[i], r.data);
      if (typeof r.data.total === "number") totals.current.set(key, r.data.total);
      if (typeof r.data.total_unfiltered === "number") unfiltered.current = r.data.total_unfiltered;
    }
  });
  const known = totals.current.get(key);
  const lastTotal = useRef<number | undefined>(undefined);
  if (known !== undefined) lastTotal.current = known;

  const error = results.find((r) => r.error)?.error as Error | undefined;
  const columns = [...loaded.values()][0]?.columns;

  const flagMaps = useMemo(() => {
    const m = new Map<number, Map<number, Record<string, string>>>();
    loaded.forEach((pg, p) => m.set(p, absoluteFlags(pg, p * PAGE_SIZE)));
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results.map((r) => r.dataUpdatedAt).join(",")]);

  const getRow = (i: number): LoadedRow | undefined => {
    const p = Math.floor(i / PAGE_SIZE);
    const pg = loaded.get(p);
    if (!pg) return undefined;
    const j = i - p * PAGE_SIZE;
    const values = Array.isArray(pg.rows) ? pg.rows[j] : undefined;
    if (!Array.isArray(values)) return undefined;
    return { values, rowNumber: rowNumberOf(pg, j), flags: flagMaps.get(p)?.get(i) };
  };

  return {
    totalUnfiltered: unfiltered.current,
    total: known ?? lastTotal.current ?? 0,
    totalKnown: known !== undefined,
    fetching: results.some((r) => r.isFetching),
    columns,
    error,
    getRow,
  };
}

/** Absolute 1-based row number from the server's `row_numbers` (1-based, as in the file). */
function rowNumberOf(pg: RowsPage, j: number): number | undefined {
  const nums = pg.row_numbers;
  if (!Array.isArray(nums) || typeof nums[j] !== "number") return undefined;
  return nums[j];
}
