# Newsletter System: Multi-Agent Architecture with Verification Gateway

## Overview

This document describes how to integrate the Verification Gateway into your newsletter
processing system, coordinating Claude Code, Codex, and Gemini Jules across local and
cloud environments.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              GOVERNANCE LAYER                                        │
│                         (Weekly Review / Leadership)                                 │
│                                                                                      │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                     │
│   │ Agent Metrics   │  │ Verification    │  │ Cost/Token      │                     │
│   │ Dashboard       │  │ Success Rates   │  │ Analysis        │                     │
│   │ (Supabase)      │  │ (Supabase)      │  │ (Supabase)      │                     │
│   └─────────────────┘  └─────────────────┘  └─────────────────┘                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                TRUST LAYER                                           │
│                          (Per-Sprint / Daily)                                        │
│                                                                                      │
│   ┌────────────────────────────────────────────────────────────────────────────┐    │
│   │                      VERIFICATION GATEWAY                                   │    │
│   │                      (FastAPI + Supabase)                                   │    │
│   │                                                                             │    │
│   │   Webhook ──→ Policy ──→ Route ──→ Execute ──→ Collect ──→ Report         │    │
│   │   Receiver    Engine     Decision   Dispatch   Results     Status          │    │
│   │                                                                             │    │
│   │   Policies:                                                                 │    │
│   │   • python-static  → Inline (ruff, mypy)                                   │    │
│   │   • typescript-*   → Inline (tsc) or GitHub Actions                        │    │
│   │   • supabase-*     → Local NTM (needs Supabase CLI)                        │    │
│   │   • gmail-api-*    → Local NTM (needs credentials)                         │    │
│   │   • claude-api-*   → E2B Sandbox (safe API testing)                        │    │
│   │   • security-*     → Human Review Queue                                     │    │
│   └────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│   ┌─────────────────┐                              ┌─────────────────┐              │
│   │ Approval Queue  │◄──── Human Approves ────────►│ BV (Dependency  │              │
│   │ (Slack/Discord) │      High-Risk Changes       │ Graph/Priority) │              │
│   └─────────────────┘                              └─────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            COORDINATION LAYER                                        │
│                             (Per-Task)                                               │
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                          SHARED STATE                                        │   │
│   │                                                                              │   │
│   │   Supabase Tables:                                                          │   │
│   │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │   │
│   │   │ changesets   │  │ verification │  │ agent_       │  │ approval_    │   │   │
│   │   │              │  │ _results     │  │ sessions     │  │ queue        │   │   │
│   │   └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │   │
│   │                                                                              │   │
│   │   Agent Coordination:                                                        │   │
│   │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │   │
│   │   │ Agent Mail   │  │ File Locks   │  │ CASS         │                      │   │
│   │   │ (Messages)   │  │ (Supabase)   │  │ (History)    │                      │   │
│   │   └──────────────┘  └──────────────┘  └──────────────┘                      │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                ┌───────────────────────┼───────────────────────┐
                ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                             EXECUTION LAYER                                          │
│                              (Continuous)                                            │
│                                                                                      │
│   ┌─────────────────────────────┐       ┌─────────────────────────────┐             │
│   │      LOCAL CLUSTER          │       │      CLOUD CLUSTER          │             │
│   │   (Your Machine / NTM)      │       │   (Parallel Generation)     │             │
│   │                             │       │                             │             │
│   │   Newsletter Components:    │       │   Newsletter Components:    │             │
│   │                             │       │                             │             │
│   │   ┌───────────────────┐    │       │   ┌───────────────────┐     │             │
│   │   │ Claude Code       │    │       │   │ Claude API        │     │             │
│   │   │ (Integration)     │    │       │   │ (Haiku/Sonnet)    │     │             │
│   │   │ • Gmail fetch     │    │       │   │ • Summarization   │     │             │
│   │   │ • Supabase writes │    │       │   │ • Weekly synthesis│     │             │
│   │   │ • Full pipeline   │    │       │   │ • Content gen     │     │             │
│   │   └───────────────────┘    │       │   └───────────────────┘     │             │
│   │                             │       │                             │             │
│   │   ┌───────────────────┐    │       │   ┌───────────────────┐     │             │
│   │   │ Codex (Local)     │    │       │   │ Codex (Cloud)     │     │             │
│   │   │ • Refactoring     │    │       │   │ • New features    │     │             │
│   │   │ • Test writing    │    │       │   │ • Documentation   │     │             │
│   │   └───────────────────┘    │       │   └───────────────────┘     │             │
│   │                             │       │                             │             │
│   │   ┌───────────────────┐    │       │   ┌───────────────────┐     │             │
│   │   │ Verifier Agents   │    │       │   │ Gemini Jules      │     │             │
│   │   │ • Run tests       │    │       │   │ • Exploration     │     │             │
│   │   │ • Check types     │    │       │   │ • Prototyping     │     │             │
│   │   │ • Validate        │    │       │   └───────────────────┘     │             │
│   │   └───────────────────┘    │       │                             │             │
│   │                             │       │                             │             │
│   │   Full Env Access:         │       │   Sandboxed/Limited:        │             │
│   │   ✓ Supabase CLI           │       │   ✓ Stateless generation    │             │
│   │   ✓ Gmail credentials      │       │   ✓ API calls (rate-limited)│             │
│   │   ✓ Docker Compose         │       │   ✓ E2B sandbox available   │             │
│   │   ✓ VPN/internal access    │       │   ✗ No persistent state     │             │
│   └─────────────────────────────┘       └─────────────────────────────┘             │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Newsletter-Specific Agent Responsibilities

### Agent Assignment Matrix

| Component | Primary Agent | Verification | Rationale |
|-----------|---------------|--------------|-----------|
| **Gmail Ingestion** | Claude Code (local) | Local NTM | Needs OAuth credentials |
| **Newsletter Parsing** | Codex (cloud) | GitHub Actions | Stateless text processing |
| **Haiku Summarization** | Claude API (cloud) | E2B Sandbox | Safe to test API calls |
| **Supabase Storage** | Claude Code (local) | Local NTM | Needs Supabase CLI |
| **Weekly Synthesis** | Claude API (Sonnet) | E2B Sandbox | Complex but stateless |
| **Frontend UI** | Gemini Jules (cloud) | GitHub Actions | TypeScript static analysis |
| **Auth/Security** | Claude Code (local) | Human + Local | High-risk changes |

### Workflow: Processing 100 Newsletters/Week

```
Monday-Friday (Automated):
┌────────────────────────────────────────────────────────────────────────┐
│  6:00 AM - Gmail Fetch (Local Claude Code)                             │
│  ├── Fetches new newsletters via Gmail API                             │
│  ├── Stores raw content in Supabase (newsletters table)                │
│  └── Triggers: verification_gateway/webhook/agent                      │
│                                                                         │
│  6:15 AM - Haiku Processing (Cloud - Parallel)                         │
│  ├── Cloud agents process each newsletter in parallel                  │
│  ├── ~100 newsletters × 280 tokens = ~28K tokens/day                   │
│  ├── Stores summaries in Supabase (daily_summaries table)              │
│  └── Triggers: verification_gateway (E2B for API validation)           │
└────────────────────────────────────────────────────────────────────────┘

Saturday (Automated with Human Checkpoint):
┌────────────────────────────────────────────────────────────────────────┐
│  8:00 AM - Sonnet Synthesis (Cloud)                                    │
│  ├── Aggregates week's summaries                                       │
│  ├── Generates strategic insights for leadership                       │
│  └── Stores in weekly_reports table                                    │
│                                                                         │
│  9:00 AM - Human Review (Approval Queue)                               │
│  ├── You review synthesized report                                     │
│  ├── Approve/edit before distribution                                  │
│  └── Report distributed to CTO, CDO                                    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Steps

### Phase 1: Foundation (Week 1)

1. **Deploy Verification Gateway**
   ```bash
   # Create Supabase tables
   supabase db push --db-url $SUPABASE_DB_URL < supabase_schema.sql
   
   # Deploy gateway
   docker build -t verification-gateway .
   docker run -d -p 8080:8080 \
     -e SUPABASE_URL=$SUPABASE_URL \
     -e SUPABASE_KEY=$SUPABASE_SERVICE_KEY \
     verification-gateway
   ```

2. **Configure GitHub Webhook**
   - Settings → Webhooks → Add webhook
   - Payload URL: `https://your-gateway/webhook/github`
   - Events: Push events, Pull requests

3. **Set Up Local NTM Session for Verification**
   ```bash
   # Create dedicated verification session
   ntm spawn newsletter-verify --cc=2 --tag=verifier
   
   # Configure agents to listen for verification requests
   ntm --robot-send --tag verifier --message '{"action": "configure", "role": "verifier"}'
   ```

### Phase 2: Agent Integration (Week 2)

1. **Instrument Agents to Report Changes**
   
   Add to each agent's completion hook:
   ```python
   async def report_completion(agent_id: str, changed_files: list[str], branch: str):
       async with httpx.AsyncClient() as client:
           await client.post(
               "http://localhost:8080/webhook/agent",
               json={
                   "agent_id": agent_id,
                   "agent_type": "claude_code",  # or codex, gemini_jules
                   "branch": branch,
                   "changed_files": changed_files,
               }
           )
   ```

2. **Configure Policy Routing**
   
   Update `NEWSLETTER_POLICIES` in gateway.py for your specific paths:
   ```python
   VerificationPolicy(
       name="newsletter-ingestion",
       tier=VerificationTier.INTEGRATION,
       executor=Executor.LOCAL_NTM,
       patterns=["src/ingestion/**/*.py"],
       required_env=["GMAIL_CLIENT_ID"],
   ),
   ```

### Phase 3: Observability (Week 3)

1. **Create Supabase Dashboard**
   - Real-time verification status
   - Agent success rates
   - Tier distribution metrics

2. **Set Up Alerts**
   ```sql
   -- Supabase Edge Function for Slack alerts
   CREATE FUNCTION notify_verification_failure()
   RETURNS TRIGGER AS $$
   BEGIN
       IF NEW.success = false THEN
           -- Call Slack webhook
           PERFORM net.http_post(
               'https://hooks.slack.com/services/...',
               '{"text": "Verification failed for ' || NEW.changeset_id || '"}'
           );
       END IF;
       RETURN NEW;
   END;
   $$ LANGUAGE plpgsql;
   
   CREATE TRIGGER on_verification_failure
   AFTER INSERT ON verification_results
   FOR EACH ROW EXECUTE FUNCTION notify_verification_failure();
   ```

---

## File Lock Coordination via Supabase

Since your system now uses Supabase, you can implement file locks there instead of
depending on the flywheel's Agent Mail:

```sql
-- File locks table
CREATE TABLE file_locks (
    file_path TEXT PRIMARY KEY,
    locked_by TEXT NOT NULL,  -- agent_id
    locked_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 minutes'),
    lock_reason TEXT
);

-- Acquire lock (atomic)
CREATE FUNCTION acquire_lock(
    p_file_path TEXT,
    p_agent_id TEXT,
    p_reason TEXT DEFAULT NULL
) RETURNS BOOLEAN AS $$
DECLARE
    v_acquired BOOLEAN;
BEGIN
    -- Delete expired locks first
    DELETE FROM file_locks WHERE expires_at < NOW();
    
    -- Try to insert (fails if lock exists)
    INSERT INTO file_locks (file_path, locked_by, lock_reason)
    VALUES (p_file_path, p_agent_id, p_reason)
    ON CONFLICT (file_path) DO NOTHING
    RETURNING TRUE INTO v_acquired;
    
    RETURN COALESCE(v_acquired, FALSE);
END;
$$ LANGUAGE plpgsql;

-- Release lock
CREATE FUNCTION release_lock(p_file_path TEXT, p_agent_id TEXT)
RETURNS BOOLEAN AS $$
BEGIN
    DELETE FROM file_locks 
    WHERE file_path = p_file_path AND locked_by = p_agent_id;
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;
```

---

## Cost Optimization

### Token Budget by Tier

| Tier | Typical Tokens | Cost Optimization |
|------|----------------|-------------------|
| Static (Tier 0) | 0 | Free - local tools |
| Unit (Tier 1) | ~500/run | Batch similar files |
| Integration (Tier 2) | ~2,000/run | Cache test fixtures |
| System (Tier 3) | ~5,000/run | Run only on main branch |
| Human (Tier 4) | 0 | No automation cost |

### Newsletter-Specific Budget

```
Daily (100 newsletters):
- Haiku summarization: 100 × 280 tokens = 28,000 input tokens
- Output summaries: 100 × ~150 tokens = 15,000 output tokens
- Verification (E2B): ~5 sandbox runs × $0.01 = $0.05/day

Weekly synthesis:
- Sonnet input: ~20,000 tokens (week's summaries)
- Sonnet output: ~2,000 tokens (strategic report)
- Total weekly: ~$2-3

Estimated monthly: $60-90 for full automation
```

---

## Summary: Your Stack

| Layer | Components | Data Store |
|-------|------------|------------|
| **Governance** | Metrics dashboards, weekly review | Supabase views |
| **Trust** | Verification Gateway, Approval Queue | Supabase + Slack |
| **Coordination** | File locks, agent sessions | Supabase realtime |
| **Execution (Local)** | Claude Code, NTM, Supabase CLI | Local filesystem |
| **Execution (Cloud)** | Claude API, Codex Cloud, E2B | Stateless |

The key insight: **Supabase becomes your coordination backbone**, replacing parts of
the flywheel (Mail, CASS state) while the Verification Gateway handles the routing
logic that doesn't exist elsewhere.
