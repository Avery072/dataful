import { useQueryClient } from "@tanstack/react-query";
import { Component, useState, type ErrorInfo, type ReactNode } from "react";
import { api } from "../api";
import { qk } from "../hooks/useDataset";

interface BoundaryProps {
  /** Shown instead of the children after a render error. */
  fallback: (error: Error, retry: () => void) => ReactNode;
  /** Changing this clears a caught error (e.g. switching datasets). */
  resetKey?: unknown;
  children: ReactNode;
}

interface BoundaryState {
  error: Error | null;
  key: unknown;
}

/** Catches render errors in one region so the rest of the app keeps working. */
export class ErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null, key: this.props.resetKey };

  static getDerivedStateFromError(error: Error): Partial<BoundaryState> {
    return { error };
  }

  static getDerivedStateFromProps(props: BoundaryProps, state: BoundaryState): Partial<BoundaryState> | null {
    return props.resetKey !== state.key ? { error: null, key: props.resetKey } : null;
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Dataful: a part of the page failed to render", error, info.componentStack);
  }

  retry = () => this.setState({ error: null });

  render() {
    return this.state.error ? this.props.fallback(this.state.error, this.retry) : this.props.children;
  }
}

/**
 * Calm error card for a dataset region: reload the dataset's data, or reset it
 * (clears saved decisions on the server) with an in-app confirmation.
 */
export function DatasetErrorCard({ datasetId, error, retry, compact = false, what = "this part of the page" }: { datasetId: string; error: Error; retry: () => void; compact?: boolean; what?: string }) {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  const reload = async () => {
    qc.removeQueries({ queryKey: ["ds", datasetId] });
    qc.invalidateQueries({ queryKey: qk.datasets });
    retry();
  };

  const reset = async () => {
    setBusy(true);
    setResetError(null);
    try {
      await api.reset(datasetId);
      setConfirming(false);
      await reload();
    } catch (e) {
      setResetError((e as Error).message || "The reset didn't go through.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={"error-card" + (compact ? " compact" : "")} role="alert">
      <p className="eyebrow">Something went wrong</p>
      <h2 className="serif">We couldn't show {what}.</h2>
      <p className="dim">
        Your original file is untouched. Reloading usually fixes it. If it keeps happening, one of your saved decisions may no longer fit
        this data — resetting clears them.
      </p>
      <details className="error-detail small dim">
        <summary>Technical detail</summary>
        <code>{error.message || String(error)}</code>
      </details>
      {!confirming ? (
        <div className="error-actions">
          <button className="btn primary" onClick={reload}>
            Reload this dataset
          </button>
          <button className="btn ghost" onClick={() => setConfirming(true)}>
            Reset this dataset…
          </button>
        </div>
      ) : (
        <div className="confirm-box" role="group" aria-label="Confirm reset">
          <p className="serif">Clear every decision for this dataset?</p>
          <p className="small dim">
            All fixes and answers you've saved here are removed and the data goes back to how it looks in the file. The file itself is
            never changed. This can't be undone.
          </p>
          <div className="error-actions">
            <button className="btn danger" onClick={reset} disabled={busy}>
              {busy ? "Resetting…" : "Yes, clear my decisions"}
            </button>
            <button className="btn ghost" onClick={() => setConfirming(false)} disabled={busy}>
              Keep them
            </button>
          </div>
        </div>
      )}
      {resetError && <p className="error small">Couldn't reset: {resetError}</p>}
    </div>
  );
}
