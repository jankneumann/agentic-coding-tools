# A Code Atlas for Agentic Development

## Executive synthesis

Your core premise is correct: in an agentic workflow, the limiting factor is shifting from *generation* to *navigation, review, and architectural judgment*. Recent work on code-focused deep research agents, persistent code graphs, semantic diff visualization, and multi-scale software visualization all point in the same direction: the next useful layer is not “more autocomplete” or “more chat,” but a persistent, queryable, multi-scale **code atlas** that lets humans move fluidly between architecture, modules, symbols, tests, services, commits, worktrees, and agent-produced artifacts. Your own repository is already unusually well positioned for this because it already produces structured architecture artifacts, work-package/review schemas, worktree-based variants, and coordinator-side memory/audit/handoff primitives that can become first-class visual objects rather than hidden implementation details. citeturn4search2turn33view0turn34view0turn13view0turn14view0turn18view0turn19view0

The right product decision is therefore **not** to replace VS Code, IntelliJ, or Visual Studio navigation. It is to build a **graph-backed augmentation layer** on top of them: a local MCP-powered system that continuously derives structural, semantic-diff, runtime-evidence, and agent-provenance artifacts; exposes them as tools/resources/apps; and renders them in linked views with semantic zoom, blast-radius analysis, version scrubbing, and direct jump-back to code. The best current evidence supports a hybrid approach: use 2D as the default interaction surface for precision and readability, use 3D selectively for orientation or large-landscape overviews, and use AI primarily as a *navigation and interrogation copilot* for operating the atlas rather than as a replacement for it. citeturn38view1turn35view0turn26view2turn26view3turn36view0turn36view1

## What existing tools already cover

You should explicitly build *on top of* the baseline that modern IDEs already provide. VS Code already has file and symbol navigation, breadcrumbs, go-to-definition, go-to-implementation, cross-file symbol search, inline peek views, inline reference information, test discovery and coverage, built-in worktree support, agent sessions/handoffs, MCP server support, and interactive MCP apps. Visual Studio already includes code maps and dependency diagrams. IntelliJ already provides class/method/call hierarchies and module dependency diagrams. Rebuilding those primitives from scratch would be a poor use of time unless you need substantially different semantics or scale. citeturn27view0turn27view2turn27view3turn31view0turn32view0turn26view2turn26view4turn30view6turn30view7turn30view8

What those tools *do not* yet give you, at least not in a unified way, is a persistent repo-scale model that ties together **code structure, semantic changes, tests, runtime evidence, deployment/service topology, worktrees, commits, and agent artifacts** into one navigable system. VS Code’s minimap, breadcrumbs, and peek are excellent local navigational affordances, but they are file-centric; Visual Studio code maps and IntelliJ diagrams help with specific relationship classes, but they are not a unified, version-aware, agent-aware substrate for reviewing multi-file autonomous changes at scale. That gap is exactly where a custom atlas adds value. citeturn28search8turn30view6turn30view7turn30view8turn18view0turn13view0turn14view0

Your repository also already has the right architectural direction for such an augmentation. The documented workflow calls for `/refresh-architecture` and already produces structured machine artifacts such as `architecture.summary.json`, `architecture.graph.json`, `architecture.diagnostics.json`, `parallel_zones.json`, `architecture.report.md`, and Mermaid views. The implementation-review skill already consumes `work-packages.yaml`, contract artifacts, git diffs, and work-queue result JSON, and emits findings against a structured schema. The coordinator adds session handoffs, episodic memory, audit trail, discovery, and MCP integration. In other words, the repo already treats execution as *artifact-producing*, which is precisely what an atlas needs. citeturn4search2turn29search0turn33view0turn34view0

## The custom UX worth building

The best custom UX is a **linked set of views** rather than a single grand visualization. Recent systems that succeeded in practice did so by giving users a high-level overview *plus* on-demand drilldown, not by forcing everything through one representation. Helveg explicitly centers interactive diagrams as documentation/navigation aids. Microservice treemap work emphasizes holistic overview plus fine-grained inspection. ChangePrism combines a general overview of commits with a detailed code view. The common pattern is “overview first, filter and zoom, then details on demand.” citeturn30view0turn16view2turn37view3turn18view0

I would build five primary views.

**The atlas view** should be the default landing surface. It should answer “what exists here?” at repository, service, package, module, file, and symbol scales. This is where you show ownership, import/call/test relations, generated contracts, and dominant architectural regions. For codebases dominated by internal structure, use a node-link or treemap presentation first; for service- and deployment-heavy systems, layer in service and infrastructure topology. Helveg’s interactive code diagrams, the microservice treemap work, and KubeDiagrams all reinforce that architecture comprehension improves when the visual overview is generated automatically from source/manifests and stays synchronized with reality. citeturn30view0turn37view3turn37view4

**The change lens** should answer “what changed, semantically, and why should I care?” This should not be a prettier line diff. It should classify changes into additions, removals, modifications, refactorings, micro-changes, contract changes, test-impact changes, and runtime-risk changes, then rank what deserves attention. ChangePrism shows the value of separating a commit overview from exact source detail and of tagging change types beyond green/red hunks. ReviewVis shows that graph-based review views help reviewers navigate and understand multi-entity change sets. MICROSCOPE shows that language-agnostic impact analysis can reduce downstream test scope dramatically in microservices, which is exactly the sort of “blast radius” UX you want before merges and validations. citeturn18view0turn30view2turn30view4turn30view3

**The version and variant view** should answer “how did this area evolve across commits, branches, worktrees, and prototype variants?” Your workflow already has variant generation and convergence, and VS Code already supports worktrees. What is missing is a visual lane view where a user can compare alternative branches and agent-generated prototypes at the level of symbols, files, architectural regions, and validation outcomes. EvoScat is relevant here because it focuses on global, scalable views of long software histories rather than only one diff at a time. citeturn25view0turn32view0turn22search3

**The evidence view** should answer “what validates or contradicts this code?” This is where tests, coverage, runtime traces, service endpoints, deployment manifests, and validation outputs need to be linked back to the structural graph. VS Code already gives local test discovery, debugging, and coverage overlays, but research in ExplorViz, microservice treemaps, and KubeDiagrams shows that comprehension improves when runtime or environment evidence is placed alongside structural views instead of living in separate silos. citeturn31view0turn7search2turn37view3turn37view4

**The agent provenance view** should answer “which agent or workflow artifact caused this state?” This is especially important in your repo because the coordinator already models handoffs, memory, discovery, audit, and queue state, and the skills workflow already models parallel prototypes and parallel review. Those should become visible timelines and lineage graphs: commits, branches, worktrees, work packages, review findings, validations, and memories should be explorable as first-class objects. Code Researcher’s structured memory and multi-phase workflow, combined with your coordinator’s handoff/audit/memory system, strongly support making agent reasoning *inspectable* rather than ephemeral. citeturn13view0turn34view0turn25view0

Across all of these views, the central interaction pattern should be **semantic zoom**. The most useful recent evidence in software-city research is not “3D is amazing,” but that semantic zoom and mini-maps reduce complexity and are especially helpful for larger landscapes and collaborative exploration. At the same time, Helveg is a strong reminder that overly clever visualization fails if navigation, filtering, and detail access are not intuitive. In practice, that means zoom should change representation, not just scale pixels: repository → subsystem → package → module → file → symbol → hunk → line → linked tests/evidence. citeturn19view0turn37view2turn16view3

## The artifacts to generate

The most important implementation decision is to make the atlas **artifact-first**. Markdown reports are useful, but machine-friendly artifacts must become the source of truth. Codebase-Memory is the clearest current evidence for this direction: it constructs a persistent Tree-Sitter knowledge graph via MCP, parses 66 languages, and reports 83% answer quality versus 92% for a file-exploration agent while using ten times fewer tokens and 2.1 times fewer tool calls. That is exactly the kind of tradeoff you want for frequent repo-scale interrogation. citeturn14view0turn14view1turn14view2

I would generate four artifact families and keep a canonical copy in a local database such as SQLite, plus JSON exports for rendering.

| Artifact family | Purpose | Minimum contents |
|---|---|---|
| **Structural graph** | Stable topology of the codebase | nodes for repo/service/package/module/file/symbol/test/contract/spec; edges for imports, defines, calls, implements, tests, covers, owns |
| **Semantic change graph** | Meaningful review context for diffs and versions | changed entities, change kinds, refactorings, micro-changes, impacted tests, risk tags, before/after snapshots |
| **Evidence graph** | Validation and runtime grounding | test results, coverage, logs, traces, build outputs, deployment manifests, service endpoints, contract checks |
| **Provenance graph** | Explain how artifacts came to exist | commits, branches, worktrees, agent sessions, handoffs, review findings, workflow steps, approvals, merges |

This design is not speculative in a vacuum. Your repo already emits architecture JSON, work-package/review artifacts, and coordinator audit/memory/handoff state; ChangePrism provides a clear model for semantic diff views; MICROSCOPE provides a clear model for change-impact data; and KubeDiagrams and the microservice treemap work demonstrate the value of deriving architectural artifacts directly from code/manifests rather than hand-maintaining them. citeturn4search2turn33view0turn34view0turn18view0turn30view3turn37view3turn37view4

A practical schema design would use **stable symbol IDs** and **snapshot IDs**. Stable symbol IDs let you track a function or class across file moves and refactors; snapshot IDs let every node/edge be queried “as of” a commit, branch head, or worktree. That is what makes version scrubbing, branch comparison, and blast-radius previews feel instantaneous rather than recomputed from scratch. The research support here is indirect but strong: Code Researcher emphasizes commit-history-aware structured memory; Codebase-Memory emphasizes persistent graph-native queries; EvoScat emphasizes temporally scalable views of very large histories. citeturn13view0turn14view0turn22search3

A concrete node/edge vocabulary for your project could look like this:

```json
{
  "nodeKinds": [
    "repository", "service", "package", "module", "file", "symbol",
    "test", "contract", "spec", "task", "commit", "branch", "worktree",
    "agent_session", "review_finding", "validation_run", "runtime_trace"
  ],
  "edgeKinds": [
    "contains", "imports", "defines", "calls", "implements",
    "tests", "covers", "owns", "changed_in", "derived_from",
    "validated_by", "reviewed_by", "explains", "deployed_as"
  ]
}
```

For your repository specifically, I would extend `/refresh-architecture` so it still writes human-facing report files, but also writes:

```json
{
  "graph.sqlite": "canonical local graph store",
  "symbols.jsonl": "signature/skeleton view of all symbols",
  "snapshots/<sha>.json": "aggregated export for a specific commit",
  "changes/<base>..<head>.json": "semantic diff + impacted entities",
  "blast-radius/<sha>/<symbol>.json": "ranked downstream impact",
  "evidence/<sha>.json": "tests, coverage, traces, validations",
  "provenance/<run-id>.json": "agent sessions, handoffs, findings, approvals"
}
```

That extension aligns directly with what the repo already documents: architecture refresh before planning, diff-oriented architecture refresh before validation, structured review findings, work-package definitions, result JSON, and coordinator audit/memory/handoff tools. citeturn4search2turn25view0turn33view0turn34view0

## Rendering and integration architecture

If by “3d.js” you meant **D3.js**, then the short answer is: use **D3 for precision 2D interaction**, not for true 3D. D3 is designed for bespoke dynamic data visualization, with strong support for selections, scales, shapes, panning, zooming, dragging, and force-based layouts. Three.js, by contrast, is the right choice for true 3D scenes and scene-graph-based spatial metaphors. citeturn36view0turn36view2turn36view1turn36view3

The recommendation I would make is a consciously **hybrid stack**:

| Layer | Recommended default | Why |
|---|---|---|
| Precision architecture map | D3 + Canvas/WebGL-backed 2D | Best for node-link diagrams, treemaps, timelines, semantic filtering, and accurate edge reading citeturn36view0turn36view2turn38view1 |
| Large-landscape overview | Three.js | Best for optional software-city overviews, spatial orientation, collaborative/immersive modes, and large 3D scenes citeturn36view1turn36view3turn19view0 |
| Editor integration | VS Code webview and/or MCP App | Lets the same atlas render inside the IDE and inside the agent conversation, with secure sandboxing and bidirectional tool calls citeturn26view0turn26view2turn35view0 |
| Transport | MCP | Standardized tools/resources/apps model; already supported in VS Code and aligned with your coordinator direction citeturn26view2turn26view3turn35view1turn34view0 |

The default interaction surface should still be **2D**, not 3D. Helveg’s background discussion is unusually useful here because it states the tradeoff directly: software-city metaphors are intuitive, but they often omit relationships and suffer from occlusion and perspective distortion; the Helveg authors therefore explicitly rejected 3D as the default in favor of simpler and more effective 2D diagrams for code navigation. That matches broader visualization guidance: use 3D only where spatiality adds real information, not because it looks modern. citeturn38view1turn38view2

Where 3D *does* make sense is in a selective “overview mode”: city/island/grouping views for very large repo landscapes, collaborative exploration, or temporal “flying through” branch histories. The most persuasive recent support for this is not the city metaphor alone, but the addition of semantic zoom and mini-maps in ExplorViz. The studies there found those features useful, especially in larger software landscapes and collaborative exploration, with 15 of 16 participants preferring the semantic-zoom version for interaction and mini-maps being perceived as more helpful in larger landscapes. citeturn19view0

The integration point with agents should be **MCP Apps**, not a disconnected dashboard. MCP Apps are designed specifically for interactive dashboards, visualizations, and multi-step workflows rendered inside the conversation, with sandboxed iframes, bidirectional communication, and the ability to call MCP tools. That matters because your desired UX is not just “show me a graph,” but “let AI help me navigate and interrogate the graph *in context*.” citeturn26view0turn35view0

## The research most worth adopting

The strongest current research and tool ideas break down into “adopt now,” “adapt selectively,” and “watch closely.”

| Work | What to take from it | Recommendation |
|---|---|---|
| **Codebase-Memory** | Persistent Tree-Sitter knowledge graph via MCP; 66 languages; strong graph-native query support; 10× fewer tokens than file-by-file exploration with competitive answer quality citeturn14view0turn14view1turn14view2 | **Adopt now as the backbone** for structural storage and MCP exposure |
| **Code Researcher** | Analysis → synthesis → validation loop with structured memory and explicit commit-history exploration; average 10 files explored per trajectory vs 1.33 for SWE-agent; 58% crash-resolution on kBenchSyz vs 37.5% for SWE-agent citeturn13view0 | **Adopt as a reasoning pattern** for history-aware multi-file research and evidence capture |
| **Helveg** | Interactive code diagrams as documentation; filtering, tree view, side panel, code preview; second study showed improved intuitiveness, interactivity, and UI, while still highlighting scalability limits and the need for careful filtering citeturn16view1turn16view2turn16view3 | **Adopt as a UX pattern library** for overview + filter + inspect |
| **MICROSCOPE** | Language-agnostic change-impact analysis for microservices using relational Datalog rules; in industrial evaluation over 112 commits it reduced interfaces to test by 97% and testing time by 73% citeturn13view3turn30view3 | **Adopt conceptually now** for blast-radius and impacted-test ranking |
| **ChangePrism** | Semantic diff visualization with general view, commit insight view, and code detail view; distinguishes refactorings and micro-changes from ordinary edits citeturn18view0turn30view2 | **Adopt now** for diff review UX |
| **ReviewVis** | Graph-based merge-request visualization helped developers navigate and understand review change-sets citeturn30view4 | **Adapt selectively** for PR review mode |
| **Semantic Zoom and Mini-Maps for Software Cities** | Semantic zoom and mini-maps were useful additions, especially for large landscapes and collaborative exploration; positive preference results despite implementation caveats citeturn19view0turn37view2 | **Adopt now** as interaction mechanics, not necessarily as your primary rendering metaphor |
| **Interactive treemaps for microservices** | Holistic + drilldown view was effective across 10 real architectures; developers highlighted navigation from macro to micro levels and strong usefulness on large systems citeturn37view3 | **Adopt for service/repo/package overviews** |
| **KubeDiagrams** | Continuously generated architecture diagrams from manifests/cluster state keep documentation aligned with deployment reality citeturn37view4 | **Adopt for deployment/infra overlays** |
| **EvoScat** | Scalable temporal visualization for millions of software-history events via interactive density scatterplots citeturn22search3 | **Adapt for commit-history and repository-evolution views** |
| **LLMs as Visualization Agents** | Interesting early evidence that LLMs can generate task-aligned visualizations, but output quality varies widely and the paper frames this as an open question rather than a solved capability citeturn20search0turn20search5 | **Watch, do not anchor the product on this yet** |

One important caution: some of the most exciting papers in this space are still preprints or have small-sample user studies. Code Researcher is explicitly labeled a preprint under review. Codebase-Memory is a recent arXiv preprint. The semantic-zoom and mini-map studies are promising, but not large-scale industrial validation. So the right posture is not “copy the papers literally,” but “use them as validated design signals and test them in your own workflow.” citeturn13view0turn14view0turn19view0turn16view1

## Recommended roadmap for agentic-coding-tools

The extension path for your repository should be incremental, because the repo already contains the seeds of the system you need.

First, extend **`/refresh-architecture`** from “architecture reports and Mermaid views” to “canonical graph snapshot generation.” Keep the current files for humans, but additionally emit a stable graph store, symbol skeleton exports, semantic diffs, and blast-radius artifacts keyed by commit/worktree. This is the lowest-risk step because it builds on a command your workflow already treats as central before planning and validation. citeturn4search2turn25view0

Second, create a dedicated **atlas MCP server**. It should expose tools such as `symbol_lookup`, `neighbors`, `blast_radius`, `compare_snapshots`, `tests_for_symbol`, `commits_touching_symbol`, `worktree_variants`, `review_findings_for_entity`, and `explain_lineage`. That fits your current direction because VS Code already supports MCP servers/resources/apps, your coordinator already has MCP integration, and MCP itself is explicitly designed to standardize tools, resources, and workflows for hosts and servers. citeturn26view2turn26view3turn35view1turn34view0

Third, build a **Code Atlas panel** as either a VS Code webview, an MCP App, or both. The minimum viable product should have four panes linked together: a map pane, a timeline pane, a detail pane, and an ask pane. Clicking a node in any pane should highlight corresponding entities in the others and offer deep links back to code, tests, contracts, spec tasks, review findings, and validation evidence. MCP Apps are especially attractive here because they let the visualization live inside the same conversational context where the agent is reasoning, rather than forcing a context switch to a separate tab. citeturn26view0turn35view0

Fourth, make your existing workflow artifacts visible. Your repo already has work-package definitions, review-finding schemas, result JSON, parallel prototype branches, and coordinator-side handoffs/memory/audit. Those should become explicit objects in the atlas. A reviewer should be able to click a function and immediately see not only callers, tests, and commits, but also which work package changed it, which prototype branch first introduced it, what review findings were attached to it, and which validation runs touched it. That is the shortest path to turning agent speed into something governable by humans. citeturn25view0turn33view0turn34view0

Fifth, add **runtime and environment overlays** only after the structural/change base is stable. For applications and services, that means coverage, key test traces, endpoint maps, deployment manifests, and service topology. For infrastructure-heavy repos, manifest-derived diagrams and environment drift indicators will add far more value than another static architecture document. The research on microservice treemaps and KubeDiagrams strongly suggests that these overlays are worth it, but only when they remain synchronized with reality. citeturn37view3turn37view4

A practical near-term product shape for this repository would therefore be:

```json
{
  "new_commands": [
    "/refresh-architecture --snapshot",
    "/refresh-architecture --diff <base-sha>",
    "/refresh-architecture --blast-radius <symbol>",
    "/query-architecture <question>"
  ],
  "new_runtime": [
    "code-atlas-mcp",
    "vscode-code-atlas-panel"
  ],
  "new_artifacts": [
    "graph.sqlite",
    "symbols.jsonl",
    "changes/*.json",
    "evidence/*.json",
    "provenance/*.json"
  ]
}
```

### Open questions and limitations

The biggest open engineering questions are stable symbol identity across renames/refactors, layout scalability once graphs reach very high node counts, the cost of collecting runtime evidence without slowing normal development, and how much of the atlas should be precomputed versus queried on demand. There is also a real trust-and-safety dimension: MCP is powerful precisely because it allows tools and data access, and the MCP specification explicitly emphasizes user consent, tool safety, and clear authorization flows. Your atlas should therefore prefer read-mostly interrogation by default and make state-changing actions explicit and reviewable. citeturn35view1

The strongest evidence base today supports the *direction* of this architecture more than any single exact implementation. The most reliable pattern across the literature is consistent: automatically generated structural artifacts, semantic-diff summaries, linked overview-plus-detail views, semantic zoom, and synchronized editor jump-backs are useful; flashy 3D-only experiences and purely chat-based representations are not enough on their own. That is why the best next step for your project is not another markdown format, but a local, persistent, MCP-exposed atlas that treats code, tests, services, commits, and agent artifacts as one navigable system. citeturn38view1turn19view0turn18view0turn37view3turn14view0turn13view0