import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type ChatEntry, type Issue } from "../api";
import { qk } from "../hooks/useDataset";
import { Icon } from "./Glyphs";

const EXAMPLES = [
  "Some ages look wrong to me",
  "Are there customers entered twice?",
  "Gender still has too many values",
];

interface Props {
  datasetId: string;
  aiEnabled: boolean;
  issues: Issue[];
  onShowIssue: (id: string) => void;
}

/** Tell Dataful what looks off; Claude looks it up in the data and may add a note to the margin. */
export function Chat({ datasetId, aiEnabled, issues, onShowIssue }: Props) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const history = useQuery({ queryKey: qk.chat(datasetId), queryFn: () => api.chatHistory(datasetId), enabled: aiEnabled });
  const log: ChatEntry[] = history.data?.log ?? [];

  const send = useMutation({
    mutationFn: (message: string) => api.chatSend(datasetId, message),
    onMutate: (message) => setPending(message),
    onSuccess: (res) => {
      qc.setQueryData(qk.chat(datasetId), { log: res.log });
      qc.setQueryData(qk.issues(datasetId), res.issues);
      setDraft("");
    },
    onSettled: () => setPending(null),
  });
  const reset = useMutation({
    mutationFn: () => api.chatReset(datasetId),
    onSuccess: (res) => qc.setQueryData(qk.chat(datasetId), res),
  });

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [log.length, pending]);

  if (!aiEnabled) {
    return (
      <div className="chat">
        <p className="dim small">Chat needs an Anthropic API key. Everything else works without it.</p>
      </div>
    );
  }

  const title = (id: string) => issues.find((i) => i.id === id)?.title ?? "a new note";
  const submit = (text: string) => {
    const t = text.trim();
    if (t && !send.isPending) send.mutate(t);
  };

  return (
    <div className="chat">
      <div className="chat-log" aria-live="polite">
        {log.length === 0 && !pending && (
          <div className="chat-empty">
            <p className="serif">Spotted something odd?</p>
            <p className="dim small">
              Tell Dataful in your own words. It looks it up in your data and, if it's a real problem, adds a note you can preview and say Yes to. It never changes the data by itself.
            </p>
            <div className="chat-examples">
              {EXAMPLES.map((e) => (
                <button key={e} className="opt" onClick={() => submit(e)}>
                  {e}
                </button>
              ))}
            </div>
          </div>
        )}
        {log.map((m, i) => (
          <div key={i} className={`bubble bubble-${m.role}`}>
            <p>{m.text}</p>
            {(m.issues ?? []).map((id) => (
              <button key={id} className="link-btn chat-note" onClick={() => onShowIssue(id)}>
                <Icon name="notes" size={12} /> Added note: {title(id)}
              </button>
            ))}
          </div>
        ))}
        {pending && (
          <>
            <div className="bubble bubble-user">
              <p>{pending}</p>
            </div>
            <div className="bubble bubble-assistant thinking">
              <p className="dim">Looking at your data…</p>
            </div>
          </>
        )}
        {send.error && <p className="error small">{(send.error as Error).message}</p>}
        <div ref={end} />
      </div>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          submit(draft);
        }}
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(draft);
            }
          }}
          placeholder="What looks wrong to you?"
          rows={2}
          aria-label="Message to Dataful"
          disabled={send.isPending}
        />
        <div className="chat-actions">
          {log.length > 0 && (
            <button type="button" className="link-btn muted tiny" onClick={() => reset.mutate()} disabled={reset.isPending || send.isPending}>
              Start over
            </button>
          )}
          <button type="submit" className="btn accent" disabled={!draft.trim() || send.isPending}>
            <Icon name="sparkle" size={12} /> {send.isPending ? "Looking…" : "Ask"}
          </button>
        </div>
      </form>
    </div>
  );
}
