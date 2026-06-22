/**
 * Tests for getClusterKey + clusterBoardCards multi-repo scenarios — task 7.3
 *
 * Spec scenarios covered:
 *   - Same-repo cluster uses namespaced key (<repo>/<change_id>)
 *   - Cross-repo same change_id does NOT cluster (different namespaced keys)
 *   - All-null-repo falls back to bare change_id (back-compat)
 *   - Mixed null/non-null splits: repo-null group + per-distinct-repo groups
 */
import { describe, it, expect } from "vitest";
import { getClusterKey } from "../coordinator-types";
import { clusterBoardCards } from "../../hooks/useBoardCards";
import type { IssueCard, PRCard, ProposalCard } from "../coordinator-types";

// ─────────────────────────────────────────────────────────────────────────────
// Fixtures

function makeIssue(id: string, changeId: string | null, repo?: string | null): IssueCard {
  return {
    kind: "issue",
    id,
    title: `Issue ${id}`,
    body: null,
    status: "pending",
    priority: 1,
    labels: [],
    assignee: null,
    claimed_by: null,
    claimed_at: null,
    completed_at: null,
    created_at: new Date().toISOString(),
    updated_at: null,
    change_id: changeId,
    task_key: null,
    repo: repo ?? null,
  };
}

function makePR(id: string, changeId: string | null, repo: string): PRCard {
  return {
    kind: "pr",
    id,
    change_id: changeId,
    repo,
    number: 1,
    title: `PR ${id}`,
    author: "alice",
    head_branch: `openspec/${changeId}`,
    base_branch: "main",
    origin: "openspec",
    status: "open",
    review_summary: { state: "none", reviewer_count: 0, last_reviewed_at_iso: null },
    is_draft: false,
    url: `https://github.com/${repo}/pull/1`,
    created_at_iso: new Date().toISOString(),
    updated_at_iso: new Date().toISOString(),
  };
}

function makeProposal(
  id: string,
  changeId: string,
  repo: string | null,
): ProposalCard {
  return {
    kind: "proposal",
    id,
    change_id: changeId,
    title: `Proposal ${id}`,
    status: "drafted",
    created_at_iso: new Date().toISOString(),
    updated_at_iso: new Date().toISOString(),
    proposal_path: `openspec/changes/${changeId}/proposal.md`,
    has_tasks_md: false,
    has_design_md: false,
    has_spec_delta: false,
    has_branch: false,
    branch_name: null,
    code_changes_outside_proposal: 0,
    repo,
    change_id_namespaced: repo != null ? `${repo}/${changeId}` : null,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// getClusterKey unit tests

describe("getClusterKey", () => {
  it("returns null when card.repo is null (IssueCard)", () => {
    const card = makeIssue("i1", "fix-auth", null);
    expect(getClusterKey(card)).toBeNull();
  });

  it("returns null when card.repo is null (ProposalCard)", () => {
    const card = makeProposal("p1", "fix-auth", null);
    expect(getClusterKey(card)).toBeNull();
  });

  it("returns null when card.change_id is null (IssueCard with repo set)", () => {
    const card = makeIssue("i1", null, "owner/repo");
    expect(getClusterKey(card)).toBeNull();
  });

  it("returns <repo>/<change_id> for a card with both repo and change_id set", () => {
    const card = makeProposal("p1", "fix-auth", "owner/myrepo");
    expect(getClusterKey(card)).toBe("owner/myrepo/fix-auth");
  });

  it("returns <repo>/<change_id> for a PRCard (repo always set)", () => {
    const card = makePR("pr1", "fix-auth", "owner/myrepo");
    expect(getClusterKey(card)).toBe("owner/myrepo/fix-auth");
  });

  it("does NOT double-namespace: does not use change_id_namespaced in the key", () => {
    // ProposalCard has change_id_namespaced = "owner/repo/fix-auth"
    // getClusterKey should return "owner/repo/fix-auth" (repo + bare change_id)
    // NOT "owner/repo/owner/repo/fix-auth" (repo + change_id_namespaced)
    const card = makeProposal("p1", "fix-auth", "owner/repo");
    expect(card.change_id_namespaced).toBe("owner/repo/fix-auth");
    expect(getClusterKey(card)).toBe("owner/repo/fix-auth");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// clusterBoardCards multi-repo scenarios

describe("clusterBoardCards — namespaced cluster key", () => {
  it("same-repo cards cluster using <repo>/<change_id> key", () => {
    const issue = makeIssue("i1", "fix-auth", "owner/repo");
    const pr = makePR("pr1", "fix-auth", "owner/repo");
    const proposal = makeProposal("p1", "fix-auth", "owner/repo");

    const { clusters, annotated } = clusterBoardCards([issue, pr, proposal]);

    // All three should be in the same cluster
    expect(clusters.size).toBe(1);
    const clusterKey = [...clusters.keys()][0];
    expect(clusterKey).toBe("owner/repo/fix-auth");
    expect(clusters.get(clusterKey)).toHaveLength(3);

    for (const card of annotated) {
      expect(card.cluster_count).toBe(3);
    }
  });

  it("cross-repo same change_id does NOT cluster", () => {
    // Same bare change_id "fix-auth" but different repos → different namespaced keys
    const issueA = makeIssue("i1", "fix-auth", "owner/repo-a");
    const prB = makePR("pr1", "fix-auth", "owner/repo-b");

    const { clusters, annotated } = clusterBoardCards([issueA, prB]);

    // Should NOT cluster — each in separate "cluster" of size 1
    expect(clusters.size).toBe(0);
    for (const card of annotated) {
      expect(card.cluster_count).toBeNull();
    }
  });

  it("all-null-repo cards fall back to bare change_id clustering (back-compat)", () => {
    const issue = makeIssue("i1", "fix-auth", null);
    const pr = makePR("pr1", "fix-auth", null as unknown as string); // Force null for test
    // Actually PRCard.repo is string (non-null), so simulate with an issue
    const issue2 = makeIssue("i2", "fix-auth", null);

    const { clusters, annotated } = clusterBoardCards([issue, issue2]);

    // Both have repo=null → same change_id → should cluster under bare key
    expect(clusters.size).toBe(1);
    const clusterKey = [...clusters.keys()][0];
    expect(clusterKey).toBe("fix-auth"); // bare fallback
    expect(clusters.get(clusterKey)).toHaveLength(2);

    for (const card of annotated) {
      expect(card.cluster_count).toBe(2);
    }
  });

  it("mixed null/non-null repo with same change_id: splits into separate groups", () => {
    // One card with repo=null, one with repo="owner/repo" for same change_id
    // They must NOT cluster together
    const issueNull = makeIssue("i1", "fix-auth", null);
    const issueRepo = makeIssue("i2", "fix-auth", "owner/repo");

    const { clusters, annotated } = clusterBoardCards([issueNull, issueRepo]);

    // Both are alone in their respective group → no cluster (size 1 each)
    // The null-repo card uses bare "fix-auth" key, but only size 1 → no cluster
    // The repo card uses "owner/repo/fix-auth" key, but only size 1 → no cluster
    expect(clusters.size).toBe(0);
    for (const card of annotated) {
      expect(card.cluster_count).toBeNull();
    }
  });

  it("mixed null/non-null repo: each group clusters independently when multiple members", () => {
    // Two null-repo cards for fix-auth → cluster (bare key)
    // Two owner/repo cards for fix-auth → cluster (namespaced key)
    const nullIssue1 = makeIssue("i1", "fix-auth", null);
    const nullIssue2 = makeIssue("i2", "fix-auth", null);
    const repoIssue1 = makeIssue("i3", "fix-auth", "owner/repo");
    const repoProposal = makeProposal("p1", "fix-auth", "owner/repo");

    const { clusters } = clusterBoardCards([nullIssue1, nullIssue2, repoIssue1, repoProposal]);

    // Two clusters: bare "fix-auth" (2 cards) + namespaced "owner/repo/fix-auth" (2 cards)
    expect(clusters.size).toBe(2);
    expect(clusters.get("fix-auth")).toHaveLength(2);
    expect(clusters.get("owner/repo/fix-auth")).toHaveLength(2);
  });

  it("single-source mode (implicit local, all same repo): PR + Proposal cluster correctly", () => {
    // When OPENSPEC_SOURCES is unset, coordinator derives repo from origin
    // PRCard.repo and ProposalCard.repo both = "owner/agentic-coding-tools"
    const pr = makePR("pr1", "my-feature", "owner/agentic-coding-tools");
    const proposal = makeProposal("p1", "my-feature", "owner/agentic-coding-tools");

    const { clusters } = clusterBoardCards([pr, proposal]);

    expect(clusters.size).toBe(1);
    expect(clusters.get("owner/agentic-coding-tools/my-feature")).toHaveLength(2);
  });
});
