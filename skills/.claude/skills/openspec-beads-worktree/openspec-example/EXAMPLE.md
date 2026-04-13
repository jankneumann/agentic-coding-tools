# Example: User Authentication Feature

This directory demonstrates how the OpenSpec + Beads + Git Worktree skill works with a real proposal.

## Scenario

Your team needs to implement user authentication for a web application. You'll use OpenSpec to plan, Beads to track, and git worktrees for parallel execution.

## Directory Structure

```
example-project/
├── openspec/
│   ├── project.md
│   └── changes/
│       └── add-user-authentication/
│           ├── proposal.md
│           ├── tasks.md
│           └── specs/
│               ├── auth/
│               │   └── spec.md
│               └── users/
│                   └── spec.md
├── src/
│   ├── api/
│   ├── components/
│   └── lib/
└── .beads/  (created after skill runs)
```

## Step-by-Step Walkthrough

### Step 1: Create OpenSpec Proposal

```bash
# Initialize OpenSpec (if not done)
openspec init

# Create proposal
openspec proposal "Add user authentication"

# OR manually create structure:
mkdir -p openspec/changes/add-user-authentication/{specs/{auth,users}}
```

**Files created**:
- `proposal.md` - High-level description
- `tasks.md` - Broken down implementation tasks
- `specs/auth/spec.md` - Authentication system spec
- `specs/users/spec.md` - User management spec

### Step 2: Invoke Claude Skill

In Claude Code:

```
I want to implement the add-user-authentication OpenSpec proposal. 
Please use the openspec-beads-worktree skill to:
1. Convert tasks to Beads issues
2. Set up git worktrees for parallel work
3. Create orchestration scripts
4. Execute with 3 parallel agents
```

### Step 3: Claude's Execution

Claude will:

1. **Read proposal** → Understands requirements
2. **Create Beads epic** → `bd-a3f8` "OpenSpec: User Authentication"
3. **Convert tasks** → Creates child issues:
   - `bd-a3f8.1` - Database schema
   - `bd-a3f8.2` - API endpoints
   - `bd-a3f8.3` - Frontend components
   - `bd-a3f8.4` - Integration tests
4. **Link dependencies**:
   ```
   bd-a3f8.2 → blocks on → bd-a3f8.1
   bd-a3f8.3 → blocks on → bd-a3f8.2
   bd-a3f8.4 → blocks on → bd-a3f8.3
   ```
5. **Create worktrees**:
   ```
   ../worktrees/
   ├── add-user-authentication-1.1/  (database)
   ├── add-user-authentication-2.1/  (api - waits for 1.1)
   └── add-user-authentication-3.1/  (frontend - waits for 2.1)
   ```
6. **Generate scripts**:
   - `execute_add-user-authentication.sh`
   - `monitor_add-user-authentication.sh`

### Step 4: Execution

```bash
# Terminal 1: Monitor progress
./monitor_add-user-authentication.sh

# Terminal 2: Execute
STRATEGY=parallel ./execute_add-user-authentication.sh

# OR manually coordinate
cd ../worktrees/add-user-authentication-1.1
claude  # Implement database schema
```

### Step 5: What Happens in Each Worktree

**Worktree 1 (Database):**
```bash
# Claude reads CLAUDE.md
# Sees task: "Create user table with email, password hash, tokens"
# Implements:
#   - migrations/001_create_users.sql
#   - models/User.js
# Tests pass
# Updates: bd update bd-a3f8.1 --status in_progress
# Commits: git commit -m "Add user database schema"
# Closes: bd close bd-a3f8.1
```

**Worktree 2 (API - starts after Worktree 1):**
```bash
# Claude checks: bd show bd-a3f8.2
# Sees blockers resolved
# Implements:
#   - routes/auth.js (register, login, logout)
#   - middleware/auth.js (JWT validation)
#   - controllers/authController.js
# Updates Beads, commits, closes
```

**Worktree 3 (Frontend - starts after Worktree 2):**
```bash
# Implements:
#   - components/LoginForm.jsx
#   - components/RegisterForm.jsx
#   - hooks/useAuth.js
# Updates Beads, commits, closes
```

### Step 6: Integration

```bash
# All tasks complete, merge back
git checkout feature/openspec-add-user-authentication

# Merge task branches
git merge feature/openspec-add-user-authentication-task-1.1
git merge feature/openspec-add-user-authentication-task-2.1
git merge feature/openspec-add-user-authentication-task-3.1

# Run integration tests
npm test

# All pass? Push for review
git push origin feature/openspec-add-user-authentication
```

### Step 7: Archive

```bash
# Validate completion
bd list --parent bd-a3f8 --status open  # Should be empty

# Archive OpenSpec
openspec archive add-user-authentication --yes

# Close epic
bd close bd-a3f8 --reason "Feature complete and merged"

# Clean up worktrees
git worktree remove ../worktrees/add-user-authentication-1.1
git worktree remove ../worktrees/add-user-authentication-2.1
git worktree remove ../worktrees/add-user-authentication-3.1
```

## Timeline Example

| Time | Activity | Agent | Status |
|------|----------|-------|--------|
| T+0h | Skill invoked | Human | Planning |
| T+0.5h | Beads epic created | Claude | Setup |
| T+1h | Worktrees ready | Claude | Ready |
| T+1h | Database work starts | Agent 1 | In Progress |
| T+3h | Database complete | Agent 1 | Closed |
| T+3h | API work starts | Agent 2 | In Progress |
| T+5h | API complete | Agent 2 | Closed |
| T+5h | Frontend starts | Agent 3 | In Progress |
| T+7h | Frontend complete | Agent 3 | Closed |
| T+7.5h | Integration merge | Human | Review |
| T+8h | Tests pass | CI | Complete |
| T+8h | Archived | Human | Done |

**Total time**: 8 hours (vs. 20+ hours sequential)

## Beads State Throughout

### After Task Creation
```bash
$ bd list --parent bd-a3f8 --json | jq -r '.[] | "\(.id): \(.status)"'
bd-a3f8.1: open
bd-a3f8.2: open
bd-a3f8.3: open
bd-a3f8.4: open

$ bd ready --parent bd-a3f8 --json | jq -r '.[] | .id'
bd-a3f8.1  # Only unblocked task
```

### During Execution
```bash
$ bd list --parent bd-a3f8 --json | jq -r '.[] | "\(.id): \(.status)"'
bd-a3f8.1: closed
bd-a3f8.2: in_progress
bd-a3f8.3: open
bd-a3f8.4: open

$ bd ready --parent bd-a3f8 --json | jq -r '.[] | .id'
# Empty - bd-a3f8.3 blocked by bd-a3f8.2
```

### After Completion
```bash
$ bd list --parent bd-a3f8 --json | jq -r '.[] | "\(.id): \(.status)"'
bd-a3f8.1: closed
bd-a3f8.2: closed
bd-a3f8.3: closed
bd-a3f8.4: closed
```

## Git Branch Structure

```
main
└── feature/openspec-add-user-authentication
    ├── feature/openspec-add-user-authentication-task-1.1-database
    ├── feature/openspec-add-user-authentication-task-2.1-api
    └── feature/openspec-add-user-authentication-task-3.1-frontend
```

## File Changes Summary

**Task 1.1 (Database):**
```
+ migrations/001_create_users.sql
+ migrations/002_create_sessions.sql
+ models/User.js
+ tests/models/User.test.js
```

**Task 2.1 (API):**
```
+ routes/auth.js
+ controllers/authController.js
+ middleware/auth.js
+ services/tokenService.js
+ tests/routes/auth.test.js
```

**Task 3.1 (Frontend):**
```
+ components/LoginForm.jsx
+ components/RegisterForm.jsx
+ components/ProtectedRoute.jsx
+ hooks/useAuth.js
+ context/AuthContext.jsx
+ tests/components/LoginForm.test.jsx
```

## Benefits Demonstrated

### 1. Clear Planning (OpenSpec)
- All stakeholders review proposal
- Tasks are well-defined before coding
- Specs serve as documentation

### 2. Persistent Memory (Beads)
- Agents know what's done, what's next
- Dependencies prevent conflicts
- Progress tracked across sessions

### 3. Isolation (Git Worktrees)
- Each task has clean environment
- No interference between agents
- Easy to review individual changes

### 4. Parallelization
- Independent tasks run simultaneously
- 3x-4x faster than sequential
- Better resource utilization

### 5. Coordination
- Automatic dependency management
- Blocked tasks wait appropriately
- Natural merge order emerges

## Variations

### Variation 1: Add More Agents

```bash
# For larger proposals
STRATEGY=swarm ./execute_add-user-authentication.sh

# Runs 5+ agents concurrently
# Useful for 15+ independent tasks
```

### Variation 2: Manual Control

```bash
# Don't use execute script
# Manually assign tasks to team members

# Alice takes database
cd ../worktrees/add-user-authentication-1.1
bd update bd-a3f8.1 --assignee "@alice"

# Bob takes API (when unblocked)
cd ../worktrees/add-user-authentication-2.1
bd update bd-a3f8.2 --assignee "@bob"
```

### Variation 3: Iterative Refinement

```bash
# After first task, refine remaining tasks
bd show bd-a3f8.2
bd update bd-a3f8.2 --description "Updated requirements based on Task 1.1 implementation..."

# Or create new sub-tasks
bd create "Add OAuth2 support" --parent bd-a3f8 --priority 2
```

## Troubleshooting This Example

### Issue: API tests fail

**Root cause**: API expects database schema from Task 1.1

**Solution**:
```bash
# In API worktree
# Pull database changes
git merge feature/openspec-add-user-authentication-task-1.1

# Or wait for proper merge order
# Dependencies ensure this happens automatically
```

### Issue: Frontend can't connect to API

**Root cause**: Worktree isolation - API not running

**Solution**:
```bash
# In API worktree, start server
npm run dev  # Keep running

# In Frontend worktree, connect to localhost:3000
# Or use shared test environment
```

## Next Steps

Try this yourself:

1. Copy the example proposal files
2. Modify for your own project
3. Invoke the skill
4. Watch the coordination happen
5. Iterate and improve

## Questions?

See the main [README.md](../README.md) for full documentation.
