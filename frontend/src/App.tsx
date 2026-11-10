import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type Dataset } from "./api";
import { EmptyState } from "./components/EmptyState";
import { DatasetErrorCard, ErrorBoundary } from "./components/ErrorBoundary";
import { ACCEPT, Sidebar } from "./components/Sidebar";
import { Workspace } from "./components/Workspace";
import { qk, useDatasets } from "./hooks/useDataset";

type Theme = "light" | "dark";

function initialTheme(): Theme {
  try {
    const t = localStorage.getItem("dataful-theme");
    if (t === "light" || t === "dark") return t;
  } catch {
    /* storage unavailable */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function useNarrow(px: number) {
  const [n, setN] = useState(() => window.innerWidth < px);
  useEffect(() => {
    const on = () => setN(window.innerWidth < px);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, [px]);
  return n;
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [selected, setSelected] = useState<string | null>(() => decodeURIComponent(location.hash.slice(1)) || null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const narrow = useNarrow(1240);
  const qc = useQueryClient();
  const datasets = useDatasets();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("dataful-theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  useEffect(() => {
    history.replaceState(null, "", selected ? "#" + encodeURIComponent(selected) : location.pathname);
  }, [selected]);

  // Forget a stale selection (e.g. server restarted and the upload is gone).
  useEffect(() => {
    if (selected && datasets.data && !datasets.isFetching && !datasets.data.some((d) => d.id === selected)) setSelected(null);
  }, [selected, datasets.data, datasets.isFetching]);

  const upload = useMutation({
    mutationFn: (f: File) => api.upload(f),
    onSuccess: (res) => {
      qc.setQueryData<Dataset[]>(qk.datasets, (prev) => [...(prev ?? []).filter((d) => !res.some((r) => r.id === d.id)), ...res]);
      qc.invalidateQueries({ queryKey: qk.datasets });
      if (res[0]) setSelected(res[0].id);
    },
  });

  // Drop a file anywhere.
  useEffect(() => {
    let depth = 0;
    const hasFiles = (e: DragEvent) => !!e.dataTransfer?.types.includes("Files");
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth++;
      setDragging(true);
    };
    const leave = () => {
      depth = Math.max(0, depth - 1);
      if (!depth) setDragging(false);
    };
    const over = (e: DragEvent) => hasFiles(e) && e.preventDefault();
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDragging(false);
      const f = e.dataTransfer?.files?.[0];
      if (f) upload.mutate(f);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [upload]);

  return (
    <div className={"app" + (narrow ? " narrow" : "")}>
      <Sidebar
        datasets={datasets.data}
        loading={datasets.isLoading}
        error={(datasets.error as Error | null)?.message}
        selected={selected}
        onSelect={setSelected}
        onUpload={(f) => upload.mutate(f)}
        uploading={upload.isPending}
        uploadError={(upload.error as Error | null)?.message}
        theme={theme}
        onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")}
      />
      {selected ? (
        <ErrorBoundary
          resetKey={selected}
          fallback={(error, retry) => (
            <main className="page page-state">
              <DatasetErrorCard datasetId={selected} error={error} retry={retry} what="this dataset" />
            </main>
          )}
        >
          <Workspace key={selected} datasetId={selected} narrow={narrow} />
        </ErrorBoundary>
      ) : (
        <EmptyState datasets={datasets.data ?? []} onSelect={setSelected} onPickFile={() => fileInput.current?.click()} />
      )}
      <input
        ref={fileInput}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload.mutate(f);
          e.target.value = "";
        }}
      />
      {dragging && (
        <div className="drop-overlay" aria-hidden>
          <div>
            <p className="serif">Drop to open</p>
            <p className="small dim">.csv, .tsv or .xlsx — the original stays untouched</p>
          </div>
        </div>
      )}
      {upload.isPending && <div className="toast">Reading your file…</div>}
    </div>
  );
}
