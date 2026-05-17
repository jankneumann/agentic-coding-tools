/**
 * useCoordinator hook — fetches work queue issues from the coordinator API,
 * mints an SSE token, subscribes to GET /events/work, and falls back to
 * polling when EventSource fails.
 *
 * Design D2: SSE primary, polling fallback.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type {
  Issue,
  SnapshotPayload,
  TransitionPayload,
  AuditPayload,
} from "../lib/coordinator-types";

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
}

interface EventsAuthResponse {
  token: string;
  expires_at: string;
  aud: string;
  change_ids: string[];
}

async function fetchIssues(
  apiUrl: string,
  apiKey: string,
  changeIds: string[],
): Promise<Issue[]> {
  const labels = changeIds.map((id) => `change:${id}`);
  const res = await fetch(`${apiUrl}/issues/list`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ labels }),
  });
  if (!res.ok) throw new Error(`fetchIssues: ${res.status}`);
  const data = (await res.json()) as { issues?: Issue[]; items?: Issue[] };
  return data.issues ?? data.items ?? [];
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
  const [issues, setIssues] = useState<Issue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [streamConnected, setStreamConnected] = useState(false);

  const esRef = useRef<EventSource | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  const applySnapshot = useCallback((payload: SnapshotPayload) => {
    if (mountedRef.current) {
      setIssues(payload.work_queue);
      setLoading(false);
    }
  }, []);

  const applyTransition = useCallback(
    (payload: TransitionPayload, currentIssues: Issue[]) => {
      if (!mountedRef.current) return;
      setIssues(
        currentIssues.map((iss) =>
          iss.id === payload.work_queue_id
            ? { ...iss, status: payload.to as Issue["status"] }
            : iss,
        ),
      );
    },
    [],
  );

  const startPolling = useCallback(() => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    setStreamConnected(false);

    const poll = async () => {
      try {
        const fetched = await fetchIssues(apiUrl, apiKey, changeIds);
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
  }, [apiUrl, apiKey, changeIds, pollIntervalMs]);

  const startSSE = useCallback(
    async (token: string) => {
      const url = new URL(`${apiUrl}/events/work`);
      url.searchParams.set("change_ids", changeIds.join(","));
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
          setIssues((current) => {
            applyTransition(payload, current);
            return current.map((iss) =>
              iss.id === payload.work_queue_id
                ? { ...iss, status: payload.to as Issue["status"] }
                : iss,
            );
          });
        } catch {
          // ignore parse errors
        }
      });

      es.addEventListener("audit", (_e: MessageEvent<string>) => {
        // audit events are informational; no state update needed in base hook
        const _payload = JSON.parse(_e.data) as AuditPayload;
        void _payload;
      });

      es.onerror = () => {
        es.close();
        esRef.current = null;
        setStreamConnected(false);
        // Fall back to polling
        startPolling();
      };
    },
    [apiUrl, changeIds, applySnapshot, applyTransition, startPolling],
  );

  useEffect(() => {
    mountedRef.current = true;

    const init = async () => {
      try {
        const token = await mintEventsToken(apiUrl, apiKey, changeIds);
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
  }, [apiUrl, apiKey, changeIds, startSSE, startPolling]);

  return { issues, loading, error, streamConnected };
}
