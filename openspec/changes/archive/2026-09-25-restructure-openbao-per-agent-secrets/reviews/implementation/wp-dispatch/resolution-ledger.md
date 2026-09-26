# wp-dispatch review disposition

Review target: `96827d55`; integrated tip: `60879fea`. Antigravity, Claude Code, and Grok produced schema-valid findings (3/4); Pi did not. The independent final audit found no blockers. The focused resolver/dispatcher suite passed 155 tests; the related dispatch suite passed 185.

| Consensus IDs | Disposition on integrated tip |
| --- | --- |
| 1 | Fixed in `ad466899`: direct `agents.yaml` loading calls canonical `project_principals()` and rejects unknown or keyless vendor grants. |
| 2 | Fixed in `60879fea`: Bao imports occur only on credential lookup. CLI-only dispatch works without the shared package; configured Bao fails closed if it is unavailable. |
| 13 | Fixed in `60879fea`: a non-Bao SDK lookup uses the selected agent's configured environment name, so agents sharing a vendor cannot overwrite each other's setting. |
| 4–9, 18–19 | Positive findings; no change requested. |
| 3, 16 | Accepted catalog coupling: the supported SDK package names are the same vendor IDs defined by this revision's registry catalog. Unknown grants are rejected by projection and lookup. A future SDK with a different package name needs an explicit catalog mapping. |
| 10 | Accepted fail-closed behavior: a metered endpoint without a projected principal cannot read Bao credentials. It must be registered with an API key principal before Bao mode is enabled. |
| 11 | Accepted contract encoding: projection and resolver both validate the canonical agent SPIFFE form and derive `agent-<name>`. A public role-name helper can be added if the encoding changes. |
| 12 | Canonical skill-workflow spec is stale; reconcile it in the post-implementation spec update. The approved pca-02 contract forbids Bao-to-environment fallback. |
| 14 | Reviewer environment limitation: the vendor sandbox could not run tests. The worker and independent auditor ran the focused suite. |
| 15 | CLI branch behavior is covered by the new no-package regression test; no further change requested. |
| 17 | Accepted existing non-Bao OpenAI-compatible behavior. Missing ambient keys remain an adapter-level failure; no Bao fallback occurs. |

No `context_impact` block is declared for this package; its context-impact status is **unmigrated**.
