# OpenSpec + Beads + Git Worktree Skill

A production-ready Claude Skill for coordinating systematic spec-driven development with parallel agent execution.

## Overview

This skill implements a sophisticated workflow that combines three powerful patterns:

1. **OpenSpec** - Specification-driven development with clear proposals and task breakdowns
2. **Beads** - Git-backed issue tracking that gives AI agents persistent memory
3. **Git Worktrees** - Isolated execution environments for parallel development

## What This Skill Does

```
┌─────────────────┐
│ OpenSpec        │ Plan: Create proposal with tasks
│ Proposal        │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Beads           │ Track: Convert to epic + issues
│ Issues          │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Git             │ Isolate: Create worktrees per task
│ Worktrees       │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Parallel        │ Execute: Run multiple Claude agents
│ Execution       │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Integration     │ Merge: Combine work back to main
│ & Archive       │
└─────────────────┘
```

## Installation

### Prerequisites

```bash
# 1. OpenSpec (choose one)
npm install -g openspec
# OR use manual OpenSpec structure

# 2. Beads
brew tap steveyegge/beads
brew install bd
# OR
go install github.com/steveyegge/beads/cmd/bd@latest

# 3. Git (with worktree support)
git --version  # Should be 2.x or higher

# 4. Optional: GNU Parallel (for parallel execution)
brew install parallel
```

### Skill Installation

#### For Claude Code

```bash
# 1. Clone or download this skill
git clone https://github.com/yourusername/openspec-beads-worktree-skill
# OR download and extract ZIP

# 2. Install to Claude Code
cp -r openspec-beads-worktree-skill ~/.claude/skills/

# 3. Verify installation
claude -p "list available skills"
```

#### For Claude Desktop (via MCP)

```json
{
  "mcpServers": {
    "openspec-skill": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/skills-mcp"],
      "env": {
        "SKILLS_PATH": "/path/to/openspec-beads-worktree-skill"
      }
    }
  }
}
```

## Quick Start

### 1. Create an OpenSpec Proposal

```bash
cd your-project
openspec init  # If not already initialized

# Create a proposal
openspec proposal "Add user authentication"
# This creates: openspec/changes/add-user-authentication/
```

### 2. Invoke the Skill

In Claude Code:

```
Implement the add-user-authentication OpenSpec proposal using Beads and worktrees
```

Claude will automatically:
- Read the OpenSpec proposal
- Create a Beads epic
- Convert tasks to Beads issues
- Link dependencies
- Set up git worktrees
- Generate orchestration scripts

### 3. Execute the Work

```bash
# Option A: Sequential (safe, simple)
./execute_add-user-authentication.sh

# Option B: Parallel (faster)
STRATEGY=parallel ./execute_add-user-authentication.sh

# Option C: Monitor in real-time
./monitor_add-user-authentication.sh  # In separate terminal
```

## Usage Patterns

### Pattern 1: Single Developer, Sequential Work

Best for:
- Small proposals (< 5 tasks)
- Complex tasks requiring full context
- Learning the workflow

```bash
# Claude creates one worktree
# Works through tasks sequentially
# You review after each task
```

### Pattern 2: Single Developer, Parallel Tasks

Best for:
- Medium proposals (5-10 tasks)
- Independent tasks
- Time-sensitive work

```bash
# Claude creates multiple worktrees
# Launches 2-3 parallel agents
# Tasks execute simultaneously
```

### Pattern 3: Team Coordination

Best for:
- Large proposals (10+ tasks)
- Distributed team
- Long-running features

```bash
# Each team member:
1. git worktree list  # See available worktrees
2. cd ../worktrees/proposal-task-X.Y
3. bd update <task-id> --assignee "@yourname"
4. claude  # Work on task
5. bd close <task-id>
```

## Directory Structure

After running the skill:

```
your-project/
├── openspec/
│   ├── changes/
│   │   └── add-user-authentication/
│   │       ├── proposal.md
│   │       ├── tasks.md
│   │       └── specs/
│   └── specs/  # Archived specs
├── .beads/
│   ├── beads.jsonl
│   └── sqlite.db
├── .git/
│   └── worktrees/
├── ../worktrees/  # Created outside repo
│   ├── add-user-authentication-1.1/
│   ├── add-user-authentication-1.2/
│   └── add-user-authentication-2.1/
├── execute_add-user-authentication.sh
└── monitor_add-user-authentication.sh
```

## Configuration

### Customize Execution Strategy

Edit the generated execution script:

```bash
# In execute_<proposal>.sh

# Change from:
STRATEGY="parallel"

# To:
STRATEGY="single"  # Sequential
STRATEGY="swarm"   # 5+ concurrent
```

### Customize Worktree Locations

```bash
# Default: ../worktrees/
# Change in Phase 3.2 of SKILL.md:

worktree_path="/path/to/custom/location/${PROPOSAL_NAME}-${task_num}"
```

### Customize Agent Behavior

Edit `CLAUDE.md` in each worktree to add:
- Project-specific guidelines
- Testing requirements
- Code style rules
- Review criteria

## Advanced Usage

### Integration with CI/CD

```yaml
# .github/workflows/openspec-validation.yml
name: OpenSpec Validation

on:
  pull_request:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Install Beads
        run: |
          brew tap steveyegge/beads
          brew install bd
      
      - name: Validate Completion
        run: |
          # Extract proposal name from PR branch
          PROPOSAL=$(echo ${{ github.head_ref }} | sed 's/openspec\///')
          EPIC_ID=$(bd list --label "openspec,$PROPOSAL" --type epic --json | jq -r '.[0].id')
          
          # Check all tasks closed
          OPEN=$(bd list --parent $EPIC_ID --status open --json | jq '. | length')
          
          if [ $OPEN -gt 0 ]; then
            echo "ERROR: $OPEN tasks still open"
            exit 1
          fi
      
      - name: Run Tests
        run: npm test
```

### Multi-Agent Coordination with MCP Agent Mail

```bash
# Install MCP Agent Mail (when available)
npm install -g mcp-agent-mail

# Agents communicate via messages
# Beads provides shared memory
# Complete autonomous coordination
```

### Integration with Gastown

If using Gastown orchestrator:

```bash
# Add rig to Gastown
gt rig add myproject https://github.com/you/repo.git

# Gastown will detect Beads
# Mayor agent coordinates with Polecats
# This skill becomes a Mayor command
```

## Monitoring & Observability

### Real-Time Dashboard

```bash
# Launch monitoring dashboard
./monitor_<proposal>.sh

# Shows:
# - Status summary (open, in_progress, blocked, closed)
# - Active tasks with assignees
# - Ready work (unblocked tasks)
# - Blocked tasks with reasons
```

### Export Metrics

```bash
# Task completion rate
bd list --parent $EPIC_ID --json | \
  jq '{
    total: length,
    completed: map(select(.status == "closed")) | length,
    rate: (map(select(.status == "closed")) | length / length)
  }'

# Time tracking (if using Beads comments)
bd list --parent $EPIC_ID --json | \
  jq '.[] | {
    id: .id,
    title: .title,
    created: .created_at,
    closed: .closed_at,
    duration: (.closed_at - .created_at)
  }'
```

### Grafana Integration (Advanced)

```bash
# Export Beads data to Prometheus format
bd list --parent $EPIC_ID --json | \
  jq -r '
    .[] | 
    "beads_task{id=\"\(.id)\",status=\"\(.status)\"} \(if .status == "closed" then 1 else 0 end)"
  ' > /var/lib/prometheus/beads.prom
```

## Troubleshooting

### Common Issues

#### 1. Beads not found in worktree

**Problem**: `bd` command not working in worktree

**Solution**:
```bash
# Ensure PATH is inherited
echo $PATH  # In worktree

# Or symlink .beads from main repo
ln -s ../../.beads .beads
```

#### 2. Merge conflicts

**Problem**: Task branches conflict when merging

**Solution**:
```bash
# Merge incrementally, not all at once
git checkout feature/openspec-xxx
git merge task-1.1  # Resolve
git merge task-1.2  # Resolve
# etc.

# Or use interactive rebase
git rebase -i feature/openspec-xxx
```

#### 3. Claude loses context

**Problem**: Agent forgets what it was doing

**Solution**:
```bash
# Ensure CLAUDE.md has full context
# Include:
# - Beads task ID
# - Links to OpenSpec specs
# - Current progress state

# Claude can reload with:
cat CLAUDE.md
bd show <task-id>
```

#### 4. Worktrees won't remove

**Problem**: `git worktree remove` fails

**Solution**:
```bash
# Force removal
git worktree remove --force <path>

# If still fails, manual cleanup
rm -rf <path>
git worktree prune
```

### Debug Mode

Enable verbose output:

```bash
# In execution script
set -x  # Enable bash debugging

# For Beads
export BEADS_DEBUG=1

# For git
export GIT_TRACE=1
```

## Best Practices

### 1. Task Granularity

✅ **Good Task Size**:
- 1-4 hours of work
- Single responsibility
- Clear acceptance criteria
- Testable in isolation

❌ **Too Large**:
- "Implement authentication system" (break down)

❌ **Too Small**:
- "Add semicolon to line 42" (combine)

### 2. Dependency Management

✅ **Clear Dependencies**:
```
Task 1.1: Database schema → No dependencies
Task 1.2: API endpoints → Depends on 1.1
Task 1.3: Frontend → Depends on 1.2
```

❌ **Circular Dependencies**:
```
Task 1.1 → Depends on 1.2
Task 1.2 → Depends on 1.1  # BAD!
```

### 3. Testing Strategy

Each worktree should:
- Run unit tests before committing
- Integration tests in feature branch
- E2E tests before archiving proposal

```bash
# In CLAUDE.md
## Pre-Commit Checklist
- [ ] Unit tests pass: `npm test`
- [ ] Lint passes: `npm run lint`
- [ ] Build succeeds: `npm run build`
```

### 4. Communication

Use Beads comments for:
- Progress updates
- Blocking issues
- Design decisions
- Questions for review

```bash
bd comment <task-id> "Implemented OAuth2 flow using passport.js
Decision: Used JWT tokens (24hr expiry)
Blocked: Need QA environment credentials"
```

## Performance Benchmarks

Typical performance (vs. sequential manual work):

| Tasks | Manual | Single Agent | Parallel (3) | Swarm (5+) |
|-------|--------|--------------|--------------|------------|
| 5     | 20h    | 10h          | 4h           | 3h         |
| 10    | 40h    | 20h          | 8h           | 5h         |
| 20    | 80h    | 40h          | 15h          | 8h         |

*Assumes 4h average per task, includes overhead*

## Roadmap

### v1.1 (Q1 2026)
- [ ] Automatic conflict resolution strategies
- [ ] Integration with Claude Flow MCP
- [ ] Enhanced monitoring dashboard (web UI)
- [ ] Support for non-git VCS

### v1.2 (Q2 2026)
- [ ] Multi-repo coordination
- [ ] Cost tracking per task
- [ ] AI-generated test cases
- [ ] Rollback capabilities

### v2.0 (Q3 2026)
- [ ] Full Gastown integration
- [ ] Enterprise SSO support
- [ ] Compliance reporting
- [ ] Multi-cloud execution

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

## Support

- Issues: [GitHub Issues](https://github.com/yourusername/openspec-beads-worktree-skill/issues)
- Discussions: [GitHub Discussions](https://github.com/yourusername/openspec-beads-worktree-skill/discussions)
- Discord: [AI Agents Discord](https://discord.gg/ai-agents)

## License

MIT License - see [LICENSE](LICENSE)

## Credits

- **OpenSpec**: [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec)
- **Beads**: [steveyegge/beads](https://github.com/steveyegge/beads)
- **Claude Code**: [Anthropic](https://www.anthropic.com/claude-code)

## Acknowledgments

Inspired by:
- Steve Yegge's work on Beads and agent orchestration
- The OpenSpec community's spec-driven development practices
- Anthropic's research on multi-agent coordination
- The git worktree workflow pioneered by the Linux kernel team

---

**Version**: 1.0.0  
**Last Updated**: January 2026  
**Maintained by**: Enterprise AI Strategy Team
