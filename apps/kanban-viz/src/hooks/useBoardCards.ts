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
  MultiSourceProposalListResponse,
  PRCard,
  PRListResponse,
  ProposalCard,
  SourceWarning,
} from "../lib/coordinator-types";
import { getClusterKey, deriveIssueRepo } from "../lib/coordinator-types";

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
 * 1. Groups cards by a namespaced cluster key.
 * 2. Annotates each card with cluster_count (>1 means it has cross-row siblings).
 * 3. Returns the cluster Map and the annotated array.
 *
 * Cluster key resolution (D3 + R1-005):
 *   - When a card has repo != null: key = `<repo>/<change_id>` (namespaced)
 *   - When ALL cards in a candidate change_id group have repo == null:
 *     key = bare change_id (back-compat for pre-multi-repo data)
 *   - Mixed-null groups SPLIT: repo-null cards form their own bare-key group
 *     while repo-set cards form per-repo namespaced groups. The groups never
 *     mix because a cluster cannot contain both repo=null and repo="x/y" cards.
 *
 * Cards with change_id=null receive cluster_count=null and are excluded from clusters.
 * Cards that are the only card for a given effective key also receive cluster_count=null.
 */
export function clusterBoardCards(
  cards: readonly BoardCard[],
  clusterKeyOverride?: (card: BoardCard) => string | null,
): ClusterResult {
  const resolveKey = clusterKeyOverride ?? getClusterKey;

  // First pass: for each bare change_id, collect all cards and determine
  // whether ALL have null repo (i.e., the bare-fallback case).
  const byChangeId = new Map<string, BoardCard[]>();
  for (const card of cards) {
    if (card.change_id == null) continue;
    const group = byChangeId.get(card.change_id) ?? [];
    group.push(card);
    byChangeId.set(card.change_id, group);
  }

  // Compute the effective cluster key for each card.
  //
  // Mixed-null split rule (D3, spec "Namespaced Cluster Key Resolution"):
  //   - A cluster cannot mix repo=null and repo="x/y" members.
  //   - If ALL members of a bare change_id group have repo=null → bare key (back-compat).
  //   - If SOME members have repo=null (mixed group):
  //       * The repo-null cards use the bare change_id as their key
  //         (they cluster ONLY with other repo-null cards sharing the same change_id).
  //       * The repo-set cards use their namespaced key (`<repo>/<change_id>`).
  //   - If ALL members have repo set → namespaced keys (no bare fallback).
  const effectiveKey = (card: BoardCard): string | null => {
    if (card.change_id == null) return null;
    const group = byChangeId.get(card.change_id) ?? [];
    const allNull = group.every((c) => (c.repo ?? null) == null);
    if (allNull) {
      // Back-compat fallback: all members have null repo → use bare change_id
      return card.change_id;
    }
    // Mixed or all-repo case:
    if ((card.repo ?? null) == null) {
      // This card has no repo — give it the bare change_id key so it can
      // cluster with other null-repo cards (split from the namespaced group).
      return card.change_id;
    }
    // Card has repo set → namespaced key
    return resolveKey(card);
  };

  // Second pass: group by effective key
  const byEffectiveKey = new Map<string, BoardCard[]>();
  for (const card of cards) {
    const key = effectiveKey(card);
    if (key == null) continue;
    const group = byEffectiveKey.get(key) ?? [];
    group.push(card);
    byEffectiveKey.set(key, group);
  }

  // Only include clusters with >1 card
  const clusters = new Map<string, BoardCard[]>();
  for (const [key, group] of byEffectiveKey) {
    if (group.length > 1) {
      clusters.set(key, group);
    }
  }

  // Annotate: find which cluster (if any) a card belongs to
  const annotated: AnnotatedCard[] = cards.map((card) => {
    const key = effectiveKey(card);
    const clusterSize = key != null ? (clusters.get(key)?.length ?? null) : null;
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
  /**
   * Per-source failures from GET /openspec/proposals _warnings field.
   * Non-empty when at least one configured source failed on the last fetch.
   * Reset to [] on each refresh so warnings never persist across refreshes.
   */
  proposalsWarnings: readonly SourceWarning[];
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

async function fetchProposals(
  apiUrl: string,
  apiKey: string,
  bust = false,
): Promise<{ proposals: ProposalCard[]; warnings: readonly SourceWarning[] }> {
  const url = new URL(`${apiUrl}/openspec/proposals`);
  if (bust) url.searchParams.set("refresh", "true");
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
  if (!res.ok) throw new Error(`GET /openspec/proposals: ${res.status}`);
  // Cast to MultiSourceProposalListResponse so _warnings are preserved.
  // Wire-compatible with PR #211's ProposalListResponse (adds optional _warnings,
  // widens source enum to include "mixed").
  const data = (await res.json()) as MultiSourceProposalListResponse;
  return {
    proposals: Array.from(data.proposals),
    warnings: data._warnings ?? [],
  };
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
  // Per-source warnings from the last /openspec/proposals response.
  // Reset to [] on each refresh so warnings never persist across refreshes (D6).
  const [proposalsWarnings, setProposalsWarnings] = useState<readonly SourceWarning[]>([]);

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
        // Derive repo from labels client-side (D4 — label convention)
        const issuesWithRepo = issueResult.value.map((issue) => ({
          ...issue,
          repo: deriveIssueRepo(issue.labels),
        }));
        setIssueRow({ cards: issuesWithRepo, loading: false, error: null });
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
        setProposalRow({ cards: proposalResult.value.proposals, loading: false, error: null });
        setProposalsWarnings(proposalResult.value.warnings);
      } else {
        setProposalRow((prev) => ({
          ...prev,
          loading: false,
          error: String(proposalResult.reason),
        }));
        setProposalsWarnings([]);
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
    // Reset loading state and clear stale warnings so the chip disappears
    // while the next refresh is in-flight (D6: only latest-refresh warnings shown).
    setIssueRow((prev) => ({ ...prev, loading: true }));
    setPrRow((prev) => ({ ...prev, loading: true }));
    setProposalRow((prev) => ({ ...prev, loading: true }));
    setProposalsWarnings([]);
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
    proposalsWarnings,
  };
}
