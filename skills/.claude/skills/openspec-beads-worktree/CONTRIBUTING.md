# Contributing to OpenSpec + Beads + Worktree Skill

Thank you for your interest in improving this skill! This guide covers how to customize, extend, and contribute to the skill.

## Quick Customization

### Change Worktree Location

Edit `SKILL.md`, Phase 3.2:

```bash
# From:
worktree_path="../worktrees/${PROPOSAL_NAME}-${task_num}"

# To:
worktree_path="/custom/path/${PROPOSAL_NAME}-${task_num}"
```

### Change Parallel Execution Limits

Edit `SKILL.md`, Phase 4.1:

```bash
# From:
parallel)
  cat "$MAP_FILE" | parallel -j 3 --colsep '|' execute_task {1} {2} {3}
  ;;

# To:
parallel)
  cat "$MAP_FILE" | parallel -j 5 --colsep '|' execute_task {1} {2} {3}
  ;;
```

### Add Project-Specific Rules

Create `.claude/commands/project-rules.md`:

```markdown
---
name: project-rules
description: Apply project-specific conventions
---

Before implementing any task:

1. Check coding standards in CONTRIBUTING.md
2. Use project linter: `npm run lint:fix`
3. Run type checker: `npm run type-check`
4. Follow naming conventions:
   - Components: PascalCase
   - Files: kebab-case
   - Functions: camelCase
```

Then reference in worktree CLAUDE.md:

```markdown
## Project Standards

Before starting, review: .claude/commands/project-rules.md
```

## Advanced Customization

### Add Custom Beads Labels

Edit Phase 2.3 to add custom labels:

```bash
# Add company-specific labels
issue_id=$(bd create "$task_title" \
  --type task \
  --priority $priority \
  --parent $epic_id \
  --label "openspec,$proposal,task-$task_num,team:backend,sprint:current" \
  --description "$description" \
  --json | jq -r '.id')
```

### Custom Dependency Types

Beads supports multiple dependency types:

```bash
# Standard dependencies
bd dep add $task_id $dep_id --type blocks

# Custom relationships
bd dep add $task_id $dep_id --type discovered-from
bd dep add $task_id $dep_id --type related-to
bd dep add $task_id $dep_id --type supersedes
```

### Add Slack Notifications

Create notification hook in Phase 4.1:

```bash
execute_task() {
  local task_id=$1
  local worktree_path=$2
  local branch=$3
  
  # Notify start
  curl -X POST $SLACK_WEBHOOK_URL \
    -H 'Content-Type: application/json' \
    -d "{\"text\":\"🚀 Starting task: $task_id\"}"
  
  cd "$worktree_path"
  bd update $task_id --status in_progress --assignee "@claude-$(hostname)"
  claude -p "Review CLAUDE.md and implement this task."
  
  # Notify completion
  curl -X POST $SLACK_WEBHOOK_URL \
    -H 'Content-Type: application/json' \
    -d "{\"text\":\"✅ Completed task: $task_id\"}"
  
  cd - > /dev/null
}
```

### Add GitHub Integration

Create GitHub issue on task creation:

```bash
create_github_issue() {
  local task_id=$1
  local task_title=$2
  local task_desc=$3
  
  gh issue create \
    --title "$task_title" \
    --body "$task_desc

Beads ID: $task_id
OpenSpec: $PROPOSAL_NAME" \
    --label "openspec" \
    --label "automated"
}
```

## Contributing New Features

### Feature Request Process

1. Open a GitHub Issue describing the feature
2. Explain the use case
3. Provide example usage
4. Wait for maintainer feedback

### Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes to `SKILL.md`
4. Update `README.md` with new features
5. Add examples to `EXAMPLE.md` if applicable
6. Test thoroughly
7. Submit PR with clear description

### Testing Your Changes

```bash
# 1. Install your modified skill
cp SKILL.md ~/.claude/skills/openspec-beads-worktree/

# 2. Test with example proposal
cd /tmp/test-project
git init
bd init
cp -r ~/.claude/skills/openspec-beads-worktree/example-openspec openspec/changes/

# 3. Invoke in Claude Code
claude
# > "Implement the add-user-authentication OpenSpec proposal"

# 4. Verify all phases work
./monitor_add-user-authentication.sh
./execute_add-user-authentication.sh
```

## Skill Architecture

### File Structure

```
SKILL.md          # Main skill logic (read by Claude)
README.md         # User documentation
EXAMPLE.md        # Walkthrough example
install.sh        # Installation script
example-openspec/ # Sample OpenSpec files
```

### Skill Phases

The skill executes in 6 phases:

```
Phase 1: Review         Read OpenSpec proposal
Phase 2: Convert        Create Beads issues
Phase 3: Setup          Create git worktrees
Phase 4: Execute        Run parallel agents
Phase 5: Integrate      Merge work back
Phase 6: Archive        Clean up and document
```

### Key Functions

**Essential Functions:**
- `create_beads_from_tasks()` - Parse tasks.md
- `link_dependencies()` - Create Beads deps
- `create_task_worktree()` - Setup worktree
- `execute_task()` - Run agent in worktree
- `merge_worktrees()` - Integrate work

**Extension Points:**
Add custom logic at these points:

```bash
# After task creation (Phase 2.3)
# → Add custom labels, GitHub issues, notifications

# Before worktree creation (Phase 3.1)
# → Custom validation, approval gates

# Before execution (Phase 4.1)
# → Resource allocation, environment setup

# After task completion (Phase 4.1)
# → Quality gates, automated testing

# After integration (Phase 5.1)
# → Deployment triggers, documentation
```

## Common Extensions

### Add Database Migrations

```bash
# In Phase 4.1, before execution
execute_task() {
  local task_id=$1
  
  cd "$worktree_path"
  
  # Run pending migrations
  npm run migrate:up
  
  # Then execute task
  claude -p "Review CLAUDE.md..."
}
```

### Add Code Review Step

```bash
# In Phase 5.1, after merge
merge_worktrees() {
  # ... existing merge logic ...
  
  # Create review PR
  gh pr create \
    --base main \
    --head "$feature_branch" \
    --title "OpenSpec: $PROPOSAL_NAME" \
    --body "$(generate_pr_description)"
  
  echo "PR created for review"
}
```

### Add Deployment Integration

```bash
# In Phase 6.3, after archive
archive_openspec() {
  # ... existing archive logic ...
  
  # Trigger deployment
  gh workflow run deploy.yml \
    --ref "$feature_branch"
  
  echo "Deployment triggered"
}
```

## Integration with Other Tools

### Claude Flow Integration

If using Claude Flow:

```bash
# Phase 4.1 - Use hive-mind
execute_task() {
  cd "$worktree_path"
  
  npx claude-flow@alpha hive-mind spawn \
    "Implement Beads task $task_id" \
    --claude \
    --agents researcher,coder,tester
}
```

### Gastown Integration

If using Gastown:

```bash
# Convert Beads epic to Gastown rig
gt rig add $PROPOSAL_NAME $(git remote get-url origin)
gt crew add $(whoami) --rig $PROPOSAL_NAME

# Sling tasks to Gastown agents
bd list --parent $EPIC_ID --status open --json | \
  jq -r '.[] | .id' | \
  xargs -I {} gt sling {} $PROPOSAL_NAME
```

### CI/CD Integration

#### GitHub Actions

```yaml
# .github/workflows/openspec.yml
name: OpenSpec Validation

on:
  push:
    branches: [ 'openspec/*' ]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Install Dependencies
        run: |
          curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash
          npm install -g openspec
      
      - name: Validate Beads State
        run: |
          PROPOSAL=$(echo ${{ github.ref }} | cut -d/ -f4)
          EPIC_ID=$(bd list --label "openspec,$PROPOSAL" --type epic --json | jq -r '.[0].id')
          
          OPEN=$(bd list --parent $EPIC_ID --status open --json | jq '. | length')
          if [ $OPEN -gt 0 ]; then
            echo "::error::$OPEN tasks still open"
            exit 1
          fi
      
      - name: Run Tests
        run: npm test
```

## Performance Optimization

### Reduce Context Window Usage

```bash
# Use brief descriptions
bd update $task_id --description "$(echo "$description" | head -c 500)"

# Use Beads fields instead of description
bd update $task_id --custom-field "detailed_spec:path/to/spec.md"
```

### Optimize Git Operations

```bash
# Use shallow clones for worktrees
git worktree add --detach "$worktree_path"
git -C "$worktree_path" checkout -b "$branch" "$FEATURE_BRANCH"

# Clean up .git history in worktrees
git -C "$worktree_path" gc --aggressive --prune=all
```

### Parallel Execution Tuning

```bash
# Monitor system resources
case $(nproc) in
  [1-2])   MAX_PARALLEL=2 ;;
  [3-4])   MAX_PARALLEL=3 ;;
  [5-8])   MAX_PARALLEL=5 ;;
  *)       MAX_PARALLEL=8 ;;
esac

parallel -j $MAX_PARALLEL --colsep '|' execute_task {1} {2} {3}
```

## Debugging

### Enable Debug Mode

```bash
# In any phase
set -x  # Bash debug
export BEADS_DEBUG=1
export GIT_TRACE=1

# Then run skill
```

### Common Issues

**Issue**: "Beads not found in worktree"

```bash
# Solution: Symlink from main repo
cd "$worktree_path"
ln -s ../../.beads .beads
bd onboard
```

**Issue**: "Merge conflicts"

```bash
# Solution: Merge incrementally
for branch in $(git branch | grep "$FEATURE_BRANCH-task"); do
  git merge --no-ff "$branch" || {
    echo "Conflict in $branch"
    git merge --abort
  }
done
```

**Issue**: "Claude loses context"

```bash
# Solution: Add to CLAUDE.md
cat >> CLAUDE.md <<EOF

## Context Restoration
If you lose context, run:
1. cat CLAUDE.md
2. bd show $TASK_ID
3. git log --oneline -5
4. git status
EOF
```

## Documentation Standards

When contributing:

1. **Code Comments**: Explain why, not what
2. **Function Headers**: Document inputs, outputs, side effects
3. **Examples**: Include working code samples
4. **Error Messages**: Be specific and actionable

## Release Process

1. Update version in SKILL.md
2. Update CHANGELOG.md
3. Test with example project
4. Tag release: `git tag v1.1.0`
5. Push: `git push --tags`
6. Create GitHub release with notes

## Support

Questions? Issues? Ideas?

- GitHub Issues: Report bugs
- GitHub Discussions: Ask questions
- Pull Requests: Contribute code
- Discord: Real-time chat

## License

By contributing, you agree to license your contributions under the MIT License.

---

**Thank you for contributing!** 🎉
