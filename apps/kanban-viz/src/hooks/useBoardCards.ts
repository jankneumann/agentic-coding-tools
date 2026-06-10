/**
 * useBoardCards — fetches all three card sources (issues, PRs, proposals) in
 * parallel and provides a unified BoardCard array with cluster annotations.
 *
 * Design decisions:
 * - Issues: per-change-id fetch with union semantics (see fetchIssuesUnioned).
 *   A single batched POST to /issues/list returns the INTERSECTION (AND),
 *   which is empty for any issue labelled with only one change_id.
 * - PRs: single-shot GET /github/prs (not per-change partitioned).
 * - Proposals: single-shot GET /openspec/proposals.
 * - refreshGeneration: bumped on each manual refresh; SSE event handlers
 *   should check this counter and ignore events from prior generations.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchIssuesUnioned } from "./useCoordinator";
import type {
  BoardCard,
  IssueCard,
  PRCard,
  PRListResponse,
  ProposalCard,
  ProposalListResponse,
} from "../lib/coordinator-types";

// ─────────────────────────────────────────────────────────────────────────────
// Pure utility: cluster computation

export type AnnotatedCard = BoardCard & {
  /** Number of cards sharing this change_id across all rows. null when no cluster. */
  cluster_count: number | null;
};

export interface ClusterResult {
  clusters: Map<string, BoardCard[]>;
  annotated: AnnotatedCard[];
}

/**
 * clusterBoardCards — pure function that:
 * 1. Groups cards by change_id (excluding nulls).
 * 2. Annotates each card with cluster_count (>1 means it has cross-row siblings).
 * 3. Returns the cluster Map and the annotated array.
 *
 * Cards with change_id=null receive cluster_count=null and are excluded from clusters.
 * Cards that are the only card for a given change_id also receive cluster_count=null.
 */
export function clusterBoardCards(cards: readonly BoardCard[]): ClusterResult {
  // Group by change_id
  const byChangeId = new Map<string, BoardCard[]>();
  for (const card of cards) {
    const cid = card.change_id;
    if (cid == null) continue;
    const list = byChangeId.get(cid) ?? [];
    list.push(card);
    byChangeId.set(cid, list);
  }

  // Only include clusters with >1 card
  const clusters = new Map<string, BoardCard[]>();
  for (const [cid, group] of byChangeId) {
    if (group.length > 1) {
      clusters.set(cid, group);
    }
  }

  // Annotate
  const annotated: AnnotatedCard[] = cards.map((card) => {
    const cid = card.change_id;
    const clusterSize = cid != null ? (clusters.get(cid)?.length ?? null) : null;
    return { ...card, cluster_count: clusterSize } as AnnotatedCard;
  });

  return { clusters, annotated };
}

// ─────────────────────────────────────────────────────────────────────────────
// Row-level state

export interface RowState<T extends BoardCard = BoardCard> {
  cards: T[];
  loading: boolean;
  error: string | null;
}

export interface UseBoardCardsOptions {
  apiUrl?: string;
  apiKey: string;
  changeIds: string[];
}

export interface UseBoardCardsResult {
  /** Flat union of all card kinds — ready for rendering. */
  cards: BoardCard[];
  byRow: {
    issues: RowState<IssueCard>;
    prs: RowState<PRCard>;
    proposals: RowState<ProposalCard>;
  };
  /** Cluster map keyed by change_id (only clusters with >1 card). */
  clusters: Map<string, BoardCard[]>;
  loading: boolean;
  /** Generation counter — bump on each manual refresh. SSE handlers fence on this. */
  refreshGeneration: number;
  /** Trigger a parallel refetch of all three sources with ?refresh=true. */
  refresh: () => Promise<void>;
}

async function fetchPRs(apiUrl: string, apiKey: string, bust = false): Promise<PRCard[]> {
  const url = new URL(`${apiUrl}/github/prs`);
  if (bust) url.searchParams.set("refresh", "true");
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
  if (!res.ok) throw new Error(`GET /github/prs: ${res.status}`);
  const data = (await res.json()) as PRListResponse;
  return Array.from(data.prs);
}

async function fetchProposals(apiUrl: string, apiKey: string, bust = false): Promise<ProposalCard[]> {
  const url = new URL(`${apiUrl}/openspec/proposals`);
  if (bust) url.searchParams.set("refresh", "true");
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
  if (!res.ok) throw new Error(`GET /openspec/proposals: ${res.status}`);
  const data = (await res.json()) as ProposalListResponse;
  return Array.from(data.proposals);
}

export function useBoardCards({
  apiUrl = "http://localhost:8081",
  apiKey,
  changeIds,
}: UseBoardCardsOptions): UseBoardCardsResult {
  const changeIdsKey = useMemo(() => [...changeIds].sort().join(","), [changeIds]);
  const stableChangeIds = useMemo(
    () => (changeIdsKey ? changeIdsKey.split(",") : []),
    [changeIdsKey],
  );

  const [issueRow, setIssueRow] = useState<RowState<IssueCard>>({
    cards: [],
    loading: true,
    error: null,
  });
  const [prRow, setPrRow] = useState<RowState<PRCard>>({
    cards: [],
    loading: true,
    error: null,
  });
  const [proposalRow, setProposalRow] = useState<RowState<ProposalCard>>({
    cards: [],
    loading: true,
    error: null,
  });
  const [refreshGeneration, setRefreshGeneration] = useState(0);

  const mountedRef = useRef(true);
  const currentGenRef = useRef(0);

  const fetchAll = useCallback(
    async (bust = false) => {
      const gen = currentGenRef.current;

      // Kick off all three fetches in parallel
      const [issueResult, prResult, proposalResult] = await Promise.allSettled([
        fetchIssuesUnioned(apiUrl, apiKey, stableChangeIds),
        fetchPRs(apiUrl, apiKey, bust),
        fetchProposals(apiUrl, apiKey, bust),
      ]);

      // Fence: ignore if a newer refresh has started
      if (!mountedRef.current || currentGenRef.current !== gen) return;

      if (issueResult.status === "fulfilled") {
        setIssueRow({ cards: issueResult.value, loading: false, error: null });
      } else {
        setIssueRow((prev) => ({
          ...prev,
          loading: false,
          error: String(issueResult.reason),
        }));
      }

      if (prResult.status === "fulfilled") {
        setPrRow({ cards: prResult.value, loading: false, error: null });
      } else {
        setPrRow((prev) => ({
          ...prev,
          loading: false,
          error: String(prResult.reason),
        }));
      }

      if (proposalResult.status === "fulfilled") {
        setProposalRow({ cards: proposalResult.value, loading: false, error: null });
      } else {
        setProposalRow((prev) => ({
          ...prev,
          loading: false,
          error: String(proposalResult.reason),
        }));
      }
    },
    [apiUrl, apiKey, stableChangeIds],
  );

  // Initial fetch
  useEffect(() => {
    mountedRef.current = true;
    currentGenRef.current = 0;
    void fetchAll(false);
    return () => {
      mountedRef.current = false;
    };
  }, [fetchAll]);

  const refresh = useCallback(async () => {
    currentGenRef.current += 1;
    setRefreshGeneration(currentGenRef.current);
    // Reset loading state
    setIssueRow((prev) => ({ ...prev, loading: true }));
    setPrRow((prev) => ({ ...prev, loading: true }));
    setProposalRow((prev) => ({ ...prev, loading: true }));
    await fetchAll(true);
  }, [fetchAll]);

  const cards = useMemo<BoardCard[]>(
    () => [...issueRow.cards, ...prRow.cards, ...proposalRow.cards],
    [issueRow.cards, prRow.cards, proposalRow.cards],
  );

  const { clusters } = useMemo(() => clusterBoardCards(cards), [cards]);

  const loading =
    issueRow.loading || prRow.loading || proposalRow.loading;

  return {
    cards,
    byRow: {
      issues: issueRow,
      prs: prRow,
      proposals: proposalRow,
    },
    clusters,
    loading,
    refreshGeneration,
    refresh,
  };
}
