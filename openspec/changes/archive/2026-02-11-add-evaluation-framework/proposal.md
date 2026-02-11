# Change: Add Evaluation Framework for Agent Coordination Benchmarking

## Why

The agent-coordinator system has grown to include file locking, work queues, memory (episodic/working/procedural), session management, handoffs, agent discovery, verification tiers, and Task()-based parallelization — but we have no way to measure whether these mechanisms actually help. Key unanswered questions:

1. **Parallelization ROI**: Does Task() parallelization produce faster/better results than sequential execution? What is the coordination overhead?
2. **Agent comparison**: How do different backend agents (Claude Code, Codex, Gemini/Jules, Aider) compare on identical tasks when orchestrated through our coordination layer?
3. **Coordination mechanism value**: Which primitives (locking, memory, handoffs, work queue) provide the most benefit? What happens when they are ablated?
4. **Memory effectiveness**: Does episodic/procedural memory improve task success rates over time? How much context is optimal?
5. **Scaling behavior**: How does performance change as agent count increases?

Without an evaluation framework, we are building coordination capabilities based on intuition rather than evidence. An evaluation framework enables data-driven prioritization of future work.

## What Changes

- **New `evaluation-framework` capability** with scenario-driven benchmarking infrastructure
- **Task suite**: A curated set of reproducible coding tasks with known solutions, difficulty levels, and parallelizability characteristics
- **Metrics collection**: Instrumented harness that captures timing, token usage, coordination overhead, task success, and merge conflict rates
- **Comparison harness**: Run identical tasks across different agent backends and coordination configurations (with/without locking, memory, parallelization)
- **Ablation support**: Toggle coordination mechanisms on/off to measure their individual contribution
- **External benchmark adapters**: Adapters for SWE-bench Verified (500 real GitHub issues), MultiAgentBench (MARBLE coordination topologies), and Context-Bench (long-horizon memory evaluation)
- **Reporting**: Generate structured evaluation reports with statistical significance testing

## Impact

- Affected specs: None modified — this is a new capability
- New spec: `evaluation-framework`
- Affected code:
  - New `agent-coordinator/evaluation/` module
  - New `agent-coordinator/evaluation/tasks/` task suite directory
  - New `agent-coordinator/evaluation/harness.py` execution engine
  - New `agent-coordinator/evaluation/metrics.py` collection and aggregation
  - New `agent-coordinator/evaluation/adapters/` external benchmark adapters
  - New `agent-coordinator/evaluation/reports/` output directory
  - Integration with existing `agent-coordinator/src/` coordination primitives
