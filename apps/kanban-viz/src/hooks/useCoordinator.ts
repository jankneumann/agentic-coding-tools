/**
 * useCoordinator hook — fetches work queue issues from the coordinator API,
 * mints an SSE token, subscribes to GET /events/work, and falls back to
 * polling when EventSource fails.
 *
 * Design D2: SSE primary, polling fallback.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  ActiveWorktree,
  Issue,
  SnapshotPayload,
  TransitionPayload,
  AuditPayload,
} from "../lib/coordinator-types";
import type { AgentActivity } from "../components/VendorSwimlanes";

export interface UseCoordinatorOptions {
  /** API base URL, defaults to http://localhost:8081 */
  apiUrl?: string;
  /** API key for Authorization: Bearer header */
  apiKey: string;
  /** Change IDs to subscribe to */
  changeIds: string[];
  /** Polling interval in ms (used on SSE failure). Default: 5000 */
  pollIntervalMs?: number;
}

export interface UseCoordinatorResult {
  issues: Issue[];
  loading: boolean;
  error: string | null;
  /** True while using SSE; false = polling fallback is active */
  streamConnected: boolean;
  /**
   * Recent audit events (most-recent-first, capped at 20). Surfaced from the
   * SSE 'audit' stream so consumers can display an audit feed without
   * re-fetching from /audit. Empty array when SSE is not connected.
   */
  recentAuditEvents: AuditPayload[];
  /**
   * Active worktree registry projected from the snapshot. Empty when not
   * connected or no active agents.
   */
  activeAgents: ActiveWorktree[];
  /**
   * Per-issue agent activity projection (IMPL_REVIEW F2): for each in-flight
   * issue with a `claimed_by` value, the matching active worktree's heartbeat
   * is exposed so VendorSwimlanes can render per-vendor lanes without each
   * consumer re-deriving the projection.
   */
  agentsByIssueId: Map<string, AgentActivity[]>;
}

interface EventsAuthResponse {
  token: string;
  expires_at: string;
  aud: string;
  change_ids: string[];
}

async function fetchIssuesForSingleChange(
  apiUrl: string,
  apiKey: string,
  changeId: string,
): Promise<Issue[]> {
  const res = await fetch(`${apiUrl}/issues/list`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ labels: [`change:${changeId}`] }),
  });
  if (!res.ok) throw new Error(`fetchIssues: ${res.status}`);
  const data = (await res.json()) as { issues?: Issue[]; items?: Issue[] };
  return data.issues ?? data.items ?? [];
}

async function fetchIssues(
  apiUrl: string,
  apiKey: string,
  changeIds: string[],
): Promise<Issue[]> {
  // Multi-change boards require UNION semantics, but POST /issues/list applies
  // AND across labels (issue_service.py:277-280). A single call with
  // labels=[change:a, change:b] would return the intersection — empty for any
  // issue labelled with only one change_id, which is the typical case.
  // Iterate per-change-id, run in parallel, dedupe by id.
  if (changeIds.length === 0) return [];
  const perChange = await Promise.all(
    changeIds.map((id) => fetchIssuesForSingleChange(apiUrl, apiKey, id)),
  );
  const merged = new Map<string, Issue>();
  for (const batch of perChange) {
    for (const issue of batch) {
      if (!merged.has(issue.id)) merged.set(issue.id, issue);
    }
  }
  return Array.from(merged.values());
}

async function mintEventsToken(
  apiUrl: string,
  apiKey: string,
  changeIds: string[],
): Promise<string> {
  const res = await fetch(`${apiUrl}/events/auth`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ change_ids: changeIds }),
  });
  if (!res.ok) throw new Error(`mintEventsToken: ${res.status}`);
  const data = (await res.json()) as EventsAuthResponse;
  return data.token;
}

export function useCoordinator({
  apiUrl = "http://localhost:8081",
  apiKey,
  changeIds,
  pollIntervalMs = 5000,
}: UseCoordinatorOptions): UseCoordinatorResult {
  // Stabilize changeIds by content so consumers passing inline arrays
  // (`changeIds={["a","b"]}`) don't trigger token re-mint + re-fetch on every
  // parent render. Without this, useCallback deps churn drives an infinite
  // useEffect re-run loop in the polling-fallback path.
  const changeIdsKey = useMemo(
    () => [...changeIds].sort().join(","),
    [changeIds],
  );
  const stableChangeIds = useMemo(
    () => (changeIdsKey ? changeIdsKey.split(",") : []),
    [changeIdsKey],
  );

  const [issues, setIssues] = useState<Issue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [streamConnected, setStreamConnected] = useState(false);
  const [recentAuditEvents, setRecentAuditEvents] = useState<AuditPayload[]>([]);
  const [activeAgents, setActiveAgents] = useState<ActiveWorktree[]>([]);

  const esRef = useRef<EventSource | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  const applySnapshot = useCallback((payload: SnapshotPayload) => {
    if (mountedRef.current) {
      setIssues(payload.work_queue);
      setActiveAgents(payload.active_agents);
      setLoading(false);
    }
  }, []);

  // IMPL_REVIEW F2: project per-issue agent activity. For each in-flight
  // issue with claimed_by, find the matching active worktree and surface
  // its heartbeat + agent_id. Empty for non-in-flight issues or issues
  // whose claimed_by has no active worktree.
  const agentsByIssueId = useMemo(() => {
    const map = new Map<string, AgentActivity[]>();
    const worktreesByAgent = new Map<string, ActiveWorktree>();
    for (const wt of activeAgents) {
      if (wt.agent_id) worktreesByAgent.set(wt.agent_id, wt);
    }
    for (const issue of issues) {
      const isInFlight =
        issue.status === "claimed" || issue.status === "running";
      if (!isInFlight || !issue.claimed_by) continue;
      const wt = worktreesByAgent.get(issue.claimed_by);
      map.set(issue.id, [
        {
          agent_id: issue.claimed_by,
          last_event_at: wt?.last_heartbeat_iso ?? null,
          outcome: null,
        },
      ]);
    }
    return map;
  }, [issues, activeAgents]);

  const startPolling = useCallback(() => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    setStreamConnected(false);

    const poll = async () => {
      try {
        const fetched = await fetchIssues(apiUrl, apiKey, stableChangeIds);
        if (mountedRef.current) {
          setIssues(fetched);
          setLoading(false);
          setError(null);
        }
      } catch (e) {
        if (mountedRef.current) setError(String(e));
      }
    };

    void poll();
    pollTimerRef.current = setInterval(() => void poll(), pollIntervalMs);
  }, [apiUrl, apiKey, stableChangeIds, pollIntervalMs]);

  const startSSE = useCallback(
    async (token: string) => {
      const url = new URL(`${apiUrl}/events/work`);
      url.searchParams.set("change_ids", stableChangeIds.join(","));
      url.searchParams.set("token", token);

      const es = new EventSource(url.toString());
      esRef.current = es;

      es.addEventListener("snapshot", (e) => {
        try {
          const payload = JSON.parse(e.data) as SnapshotPayload;
          applySnapshot(payload);
          setStreamConnected(true);
          // Stop polling if it was active
          if (pollTimerRef.current) {
            clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
          }
        } catch {
          // ignore parse errors
        }
      });

      es.addEventListener("transition", (e) => {
        try {
          const payload = JSON.parse(e.data) as TransitionPayload;
          // IMPL_REVIEW claude#4/gemini#1: the prior implementation called
          // applyTransition(payload, current) — itself a setIssues — INSIDE
          // another setIssues functional update. That triggered two state
          // updates and could read stale state. Single functional update is
          // the canonical React pattern.
          setIssues((current) =>
            current.map((iss) =>
              iss.id === payload.work_queue_id
                ? { ...iss, status: payload.to as Issue["status"] }
                : iss,
            ),
          );
        } catch {
          // ignore parse errors
        }
      });

      es.addEventListener("audit", (e: MessageEvent<string>) => {
        // IMPL_REVIEW claude#13: prior code parsed then discarded the payload
        // with `void _payload`. Audit events are informational but useful for
        // operator visibility — buffer the most-recent 20 events and surface
        // them through UseCoordinatorResult so consumers can render an audit
        // feed without re-fetching /audit.
        try {
          const payload = JSON.parse(e.data) as AuditPayload;
          if (mountedRef.current) {
            setRecentAuditEvents((prev) => [payload, ...prev].slice(0, 20));
          }
        } catch {
          // ignore parse errors — audit events are non-critical
        }
      });

      es.onerror = () => {
        es.close();
        esRef.current = null;
        setStreamConnected(false);
        // Fall back to polling
        startPolling();
      };
    },
    [apiUrl, stableChangeIds, applySnapshot, startPolling],
  );

  useEffect(() => {
    mountedRef.current = true;

    const init = async () => {
      try {
        const token = await mintEventsToken(apiUrl, apiKey, stableChangeIds);
        await startSSE(token);
      } catch {
        // SSE unavailable (key not configured, network error): fall back
        startPolling();
      }
    };

    void init();

    return () => {
      mountedRef.current = false;
      esRef.current?.close();
      esRef.current = null;
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    };
  }, [apiUrl, apiKey, stableChangeIds, startSSE, startPolling]);

  return {
    issues,
    loading,
    error,
    streamConnected,
    recentAuditEvents,
    activeAgents,
    agentsByIssueId,
  };
}
