/**
 * SyncPointBanner — shows sync-point blocking status at the top of the board.
 * Design D5: polls GET /sync-points/status every 5s; also updated on SSE events.
 *
 * When all sync-points are clear: single-line green status.
 * When any sync-point is blocked: one row per blocked skill with blocker count,
 * last heartbeat age, and "Kick <agent_id>" action buttons.
 *
 * Clicking "Kick" surfaces a ConsentPrompt before calling POST /agents/{id}/kick.
 * Audit events emitted regardless of confirm/decline outcome.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { SyncPointStatus } from "../lib/coordinator-types";
import { ConsentPrompt } from "./ConsentPrompt";

interface Props {
  apiUrl?: string;
  apiKey: string;
  /** Optional SSE-driven updates injected from the parent */
  lastUpdateAt?: string;
  onAuditEmit?: (eventData: Record<string, unknown>) => void;
}

async function fetchSyncStatus(
  apiUrl: string,
  apiKey: string,
): Promise<SyncPointStatus[]> {
  const res = await fetch(`${apiUrl}/sync-points/status`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
  if (!res.ok) throw new Error(`fetchSyncStatus: ${res.status}`);
  return (await res.json()) as SyncPointStatus[];
}

function relativeTime(isoStr: string): string {
  const diffMs = Date.now() - new Date(isoStr).getTime();
  const m = Math.floor(diffMs / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

export function SyncPointBanner({
  apiUrl = "http://localhost:8081",
  apiKey,
  lastUpdateAt,
  onAuditEmit,
}: Props) {
  const [statuses, setStatuses] = useState<SyncPointStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingKick, setPendingKick] = useState<{
    /** May be null for single-agent worktrees keyed only on change_id. */
    agentId: string | null;
    changeId: string;
    skill: string;
  } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchSyncStatus(apiUrl, apiKey);
      setStatuses(data);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, [apiUrl, apiKey]);

  useEffect(() => {
    void refresh();
    pollRef.current = setInterval(() => void refresh(), 5000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [refresh]);

  // Refresh when SSE delivers an update
  useEffect(() => {
    if (lastUpdateAt) void refresh();
  }, [lastUpdateAt, refresh]);

  const handleKickClick = (
    agentId: string | null,
    changeId: string | null,
    skill: string,
  ) => {
    // IMPL_REVIEW F5: changeId must NEVER be the literal "unknown" (prior bug).
    // If the blocker row genuinely has no change_id, the kick action is not
    // actionable and the button should be disabled (handled in render below).
    if (!changeId) return;
    setPendingKick({ agentId, changeId, skill });
    // Emit audit regardless of outcome (decline = audit.outcome=cancelled)
    onAuditEmit?.({
      action: "kick-agent-initiated",
      agent_id: agentId,
      change_id: changeId,
      skill,
      outcome: "pending",
    });
  };

  const handleConfirm = async () => {
    if (!pendingKick) return;
    const { agentId, changeId, skill } = pendingKick;
    // IMPL_REVIEW claude#16: when the registry entry has no agent_id
    // (single-agent worktree), the kick endpoint must omit --agent-id from
    // the worktree.py teardown invocation. Signal that via skip_agent_id.
    const skipAgentId = !agentId;
    // URL path requires SOMETHING for agent_id; the backend ignores it when
    // skip_agent_id is true. Convention: "_none".
    const urlAgentId = agentId ?? "_none";
    let outcome: "success" | "failure" = "failure";
    let failureReason: string | undefined;
    try {
      const res = await fetch(`${apiUrl}/agents/${urlAgentId}/kick`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          change_id: changeId,
          ...(skipAgentId ? { skip_agent_id: true } : {}),
        }),
      });
      // IMPL_REVIEW claude#6 (high): the prior implementation treated any
      // awaited fetch as success — never inspecting res.ok or the response
      // body's `kicked` field. Now we validate both.
      if (!res.ok) {
        failureReason = `HTTP ${res.status}`;
      } else {
        const body = (await res.json().catch(() => ({}))) as {
          kicked?: boolean;
          registry_cleared?: boolean;
          errors?: string[];
        };
        if (body.kicked === true || body.registry_cleared === true) {
          outcome = "success";
        } else {
          failureReason = body.errors?.join("; ") ?? "kicked=false";
        }
      }
    } catch (e) {
      failureReason = String(e);
    }
    onAuditEmit?.({
      action: "kick-agent",
      agent_id: agentId,
      change_id: changeId,
      skill,
      outcome,
      ...(failureReason && outcome === "failure"
        ? { failure_reason: failureReason }
        : {}),
    });
    setPendingKick(null);
    void refresh();
  };

  const handleDecline = () => {
    if (pendingKick) {
      onAuditEmit?.({
        action: "kick-agent-declined",
        agent_id: pendingKick.agentId,
        skill: pendingKick.skill,
        outcome: "cancelled",
      });
    }
    setPendingKick(null);
  };

  const anyBlocked = statuses.some((s) => s.blocked);

  if (error) {
    return (
      <div data-testid="sync-banner-error" style={{ color: "#de350b", padding: 8 }}>
        Sync-point status unavailable: {error}
      </div>
    );
  }

  return (
    <>
      <div
        data-testid="sync-banner"
        data-blocked={anyBlocked ? "true" : "false"}
        style={{
          padding: "6px 16px",
          background: anyBlocked ? "#fff0eb" : "#e3fcef",
          borderBottom: "1px solid",
          borderColor: anyBlocked ? "#ffbdad" : "#abf5d1",
          fontSize: 13,
        }}
      >
        {!anyBlocked ? (
          <span
            data-testid="sync-banner-clear"
            style={{ color: "#006644", fontWeight: 600 }}
          >
            All sync-points clear
          </span>
        ) : (
          <div>
            {statuses
              .filter((s) => s.blocked)
              .map((s) => (
                <div
                  key={s.skill}
                  data-testid={`sync-banner-row-${s.skill}`}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "4px 0",
                  }}
                >
                  <span
                    data-testid={`sync-banner-skill-${s.skill}`}
                    style={{ fontWeight: 600, color: "#bf2600", minWidth: 120 }}
                  >
                    {s.skill}
                  </span>
                  <span
                    data-testid={`sync-banner-blocker-count-${s.skill}`}
                    style={{ color: "#555" }}
                  >
                    {s.blockers.length} blocker
                    {s.blockers.length !== 1 ? "s" : ""}
                  </span>
                  {s.blockers.map((b) => {
                    // IMPL_REVIEW F5: render uses the blocker's real change_id
                    // and agent_id (no more 'unknown' literal). Stable react
                    // key prefers change_id (always populated in active
                    // worktrees) and falls back to agent_id; both may not be
                    // simultaneously null in a real registry entry.
                    const reactKey = b.change_id ?? b.agent_id ?? "blocker";
                    const buttonLabel = b.agent_id
                      ? `Kick ${b.agent_id}`
                      : `Kick worktree ${b.change_id ?? ""}`.trim();
                    // testid: agent_id when present, else change_id-prefixed.
                    const testIdSuffix = b.agent_id ?? `change-${b.change_id}`;
                    const canKick = Boolean(b.change_id);
                    return (
                      <div key={reactKey} style={{ display: "flex", gap: 6 }}>
                        <span
                          data-testid={`sync-banner-heartbeat-${testIdSuffix}`}
                          style={{ color: "#999", fontSize: 11 }}
                        >
                          {relativeTime(b.last_heartbeat_iso)}
                        </span>
                        <button
                          data-testid={`sync-banner-kick-${testIdSuffix}`}
                          disabled={!canKick}
                          title={
                            canKick
                              ? undefined
                              : "Cannot kick: blocker missing change_id"
                          }
                          onClick={() =>
                            handleKickClick(b.agent_id, b.change_id, s.skill)
                          }
                          style={{
                            fontSize: 11,
                            padding: "1px 8px",
                            background: canKick ? "#de350b" : "#999",
                            color: "#fff",
                            border: "none",
                            borderRadius: 3,
                            cursor: canKick ? "pointer" : "not-allowed",
                          }}
                        >
                          {buttonLabel}
                        </button>
                      </div>
                    );
                  })}
                </div>
              ))}
          </div>
        )}
      </div>
      {pendingKick && (
        <ConsentPrompt
          message={
            pendingKick.agentId
              ? `Are you sure you want to kick agent "${pendingKick.agentId}" (change ${pendingKick.changeId}) blocking ${pendingKick.skill}?`
              : `Are you sure you want to tear down worktree "${pendingKick.changeId}" blocking ${pendingKick.skill}?`
          }
          onConfirm={() => void handleConfirm()}
          onDecline={handleDecline}
        />
      )}
    </>
  );
}
