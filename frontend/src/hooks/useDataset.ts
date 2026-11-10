import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Op, type View } from "../api";

export const qk = {
  health: ["health"] as const,
  datasets: ["datasets"] as const,
  profile: (id: string, view: View) => ["ds", id, "profile", view] as const,
  issues: (id: string) => ["ds", id, "issues"] as const,
  decisions: (id: string) => ["ds", id, "decisions"] as const,
  rows: (id: string, key: string, page: number) => ["ds", id, "rows", key, page] as const,
  group: (id: string, key: string) => ["ds", id, "group", key] as const,
  chat: (id: string) => ["ds", id, "chat"] as const,
};

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: api.health, staleTime: 60_000, retry: 1 });
}

export function useDatasets() {
  return useQuery({ queryKey: qk.datasets, queryFn: api.datasets });
}

export function useProfile(id: string, view: View) {
  return useQuery({ queryKey: qk.profile(id, view), queryFn: () => api.profile(id, view), placeholderData: (prev) => prev });
}
export function useIssues(id: string) {
  return useQuery({ queryKey: qk.issues(id), queryFn: () => api.issues(id) });
}
export function useDecisions(id: string) {
  return useQuery({ queryKey: qk.decisions(id), queryFn: () => api.decisions(id) });
}

/** After any decision change everything derived from the view is stale. */
export function useRefreshDataset(id: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["ds", id] });
    qc.invalidateQueries({ queryKey: qk.datasets });
  };
}

export function useDecisionMutations(id: string) {
  const refresh = useRefreshDataset(id);
  const add = useMutation({
    mutationFn: (b: { op: Op | null; issue_id?: string; reason?: string }) => api.addDecision(id, b),
    onSuccess: refresh,
  });
  const toggle = useMutation({
    mutationFn: (b: { did: string; enabled: boolean }) => api.toggleDecision(id, b.did, b.enabled),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: (did: string) => api.removeDecision(id, did), onSuccess: refresh });
  const skip = useMutation({ mutationFn: (iid: string) => api.skip(id, iid), onSuccess: refresh });
  return { add, toggle, remove, skip };
}
