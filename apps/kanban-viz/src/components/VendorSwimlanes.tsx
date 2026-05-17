/**
 * VendorSwimlanes — renders per-vendor swim lanes for in-flight cards.
 *
 * Design D4: vendor extracted from agent_id suffix after `--`.
 * E.g. "wp-backend--claude" → vendor "claude".
 *
 * When only one vendor is present, the lane header is collapsed into a single
 * label (no extra visual weight for single-vendor cards).
 *
 * When a work package is completed, the lanes collapse to a consensus indicator
 * (check or cross) derived from the outcome field.
 */

export interface AgentActivity {
  agent_id: string;
  /** ISO timestamp of latest audit event for this agent */
  last_event_at: string | null;
  /** Outcome signal: "success" | "failure" | null (in-flight) */
  outcome: "success" | "failure" | null;
}

interface Props {
  agents: AgentActivity[];
  /** If true, the work package is complete — collapse to consensus indicator */
  completed?: boolean;
}

/** Extract vendor short-name from agent_id using -- delimiter (D4). */
export function extractVendor(agent_id: string): string {
  const parts = agent_id.split("--");
  return parts.length >= 2 ? parts[parts.length - 1]! : agent_id;
}

/** Format relative time string from ISO timestamp. */
function relativeTime(isoStr: string | null): string {
  if (!isoStr) return "";
  const diffMs = Date.now() - new Date(isoStr).getTime();
  const s = Math.floor(diffMs / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

/** Group agents by vendor and pick the most recent event per vendor. */
function groupByVendor(
  agents: AgentActivity[],
): Map<string, AgentActivity[]> {
  const map = new Map<string, AgentActivity[]>();
  for (const agent of agents) {
    const vendor = extractVendor(agent.agent_id);
    const list = map.get(vendor) ?? [];
    list.push(agent);
    map.set(vendor, list);
  }
  return map;
}

/** Determine consensus from completed agents. True = all success, False = any failure. */
function determineConsensus(agents: AgentActivity[]): boolean {
  return agents.every((a) => a.outcome === "success");
}

export function VendorSwimlanes({ agents, completed = false }: Props) {
  if (agents.length === 0) {
    return null;
  }

  // Consensus indicator for completed work-packages
  if (completed) {
    const consensus = determineConsensus(agents);
    return (
      <div
        data-testid="consensus-indicator"
        data-consensus={consensus ? "pass" : "fail"}
        aria-label={consensus ? "Consensus: pass" : "Consensus: fail"}
        style={{
          fontSize: 18,
          fontWeight: 700,
          color: consensus ? "#22a06b" : "#de350b",
          padding: "2px 4px",
        }}
      >
        {consensus ? "✓" : "✗"}
      </div>
    );
  }

  const byVendor = groupByVendor(agents);
  const vendorsSorted = Array.from(byVendor.keys()).sort();
  const singleVendor = vendorsSorted.length === 1;

  return (
    <div data-testid="vendor-swimlanes" style={{ marginTop: 4 }}>
      {vendorsSorted.map((vendor) => {
        const vendorAgents = byVendor.get(vendor)!;
        const mostRecentAgent = vendorAgents.reduce((a, b) => {
          if (!a.last_event_at) return b;
          if (!b.last_event_at) return a;
          return a.last_event_at > b.last_event_at ? a : b;
        });

        return (
          <div
            key={vendor}
            data-testid={`swimlane-${vendor}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "2px 0",
              borderTop: singleVendor ? "none" : "1px solid #f0f0f0",
            }}
          >
            <span
              data-testid={`swimlane-vendor-label-${vendor}`}
              style={{
                fontSize: 11,
                color: "#555",
                fontWeight: 600,
                minWidth: 48,
              }}
            >
              {vendor}
            </span>
            {mostRecentAgent.last_event_at && (
              <span
                data-testid={`swimlane-activity-${vendor}`}
                style={{ fontSize: 11, color: "#999" }}
              >
                {relativeTime(mostRecentAgent.last_event_at)}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
