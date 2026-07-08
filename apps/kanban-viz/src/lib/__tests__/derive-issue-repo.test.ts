/**
 * Tests for deriveIssueRepo — task 7.1
 *
 * Covers the 4 spec scenarios for repo label derivation:
 *   1. Matching label → derived value (stripped + lowercased)
 *   2. No match → null
 *   3. Multiple matches → first wins + console.warn
 *   4. Mixed case → lowercased
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { deriveIssueRepo } from "../coordinator-types";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("deriveIssueRepo", () => {
  it("returns null when labels array is empty", () => {
    expect(deriveIssueRepo([])).toBeNull();
  });

  it("returns null when no repo: labels are present", () => {
    expect(deriveIssueRepo(["change:some-feature", "priority:high"])).toBeNull();
  });

  it("returns null when repo label does not match <owner>/<repo> pattern", () => {
    expect(deriveIssueRepo(["repo:justowner"])).toBeNull();
    expect(deriveIssueRepo(["repo:"])).toBeNull();
    expect(deriveIssueRepo(["repo:owner/"])).toBeNull();
  });

  it("returns lowercased <owner>/<repo> for a valid matching label", () => {
    expect(deriveIssueRepo(["repo:owner/myrepo"])).toBe("owner/myrepo");
  });

  it("lowercases the matched label (mixed-case input)", () => {
    expect(deriveIssueRepo(["repo:Owner/MyRepo"])).toBe("owner/myrepo");
    expect(deriveIssueRepo(["repo:JanKneumann/Agentic-Assistant"])).toBe("jankneumann/agentic-assistant");
  });

  it("first match wins when multiple repo: labels are present + warns", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const result = deriveIssueRepo([
      "repo:owner-a/repo-a",
      "repo:owner-b/repo-b",
    ]);
    expect(result).toBe("owner-a/repo-a");
    expect(warnSpy).toHaveBeenCalledOnce();
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("multiple repo: labels"),
      expect.arrayContaining(["owner-a/repo-a", "owner-b/repo-b"]),
    );
  });

  it("does not warn when exactly one repo: label is present", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    deriveIssueRepo(["repo:owner/repo"]);
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("ignores non-repo labels mixed in with a valid repo label", () => {
    expect(
      deriveIssueRepo([
        "change:my-feature",
        "pending-approval",
        "repo:myorg/myrepo",
        "priority:low",
      ]),
    ).toBe("myorg/myrepo");
  });

  it("accepts labels with dots, dashes, underscores in owner/repo", () => {
    expect(deriveIssueRepo(["repo:my.org/my-repo_v2"])).toBe("my.org/my-repo_v2");
  });
});
