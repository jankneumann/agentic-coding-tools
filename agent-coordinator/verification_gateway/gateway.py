"""
Verification Gateway - Routes agent-generated changes to appropriate verification tiers.

This is a thin routing layer that:
1. Receives webhooks from git pushes or agent completions
2. Analyzes changes to determine verification requirements
3. Routes to appropriate executor (cloud CI, local cluster, E2B sandbox)
4. Collects results and reports back

Designed for: Python/TypeScript/Supabase newsletter processing system
"""

import asyncio
import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
import subprocess
import httpx


class VerificationTier(Enum):
    """Verification tiers ordered by increasing complexity/resource requirements"""
    STATIC = 0      # Linting, type checking - instant, no execution
    UNIT = 1        # Unit tests - isolated, no external deps
    INTEGRATION = 2 # Integration tests - requires services (DB, APIs)
    SYSTEM = 3      # Full system tests - requires complete environment
    MANUAL = 4      # Requires human review


class Executor(Enum):
    """Where verification runs"""
    INLINE = "inline"           # Run immediately in this process
    GITHUB_ACTIONS = "github"   # Trigger GitHub Actions workflow
    LOCAL_NTM = "ntm"          # Dispatch to NTM-managed local agent
    E2B_SANDBOX = "e2b"        # Spin up E2B sandbox
    HUMAN = "human"            # Queue for human review


@dataclass
class VerificationPolicy:
    """A rule that maps change patterns to verification requirements"""
    name: str
    tier: VerificationTier
    executor: Executor
    patterns: list[str]              # File patterns that trigger this policy
    exclude_patterns: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)  # Env vars needed
    timeout_seconds: int = 300
    requires_approval: bool = False


@dataclass
class ChangeSet:
    """Represents a set of changes from an agent"""
    id: str
    branch: str
    agent_id: str
    agent_type: str  # "claude_code", "codex", "gemini_jules"
    changed_files: list[str]
    commit_sha: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Result of a verification run"""
    changeset_id: str
    tier: VerificationTier
    executor: Executor
    success: bool
    duration_seconds: float
    output: str
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


# =============================================================================
# NEWSLETTER PROJECT SPECIFIC POLICIES
# =============================================================================

NEWSLETTER_POLICIES = [
    # Tier 0: Static analysis - runs instantly
    VerificationPolicy(
        name="python-static",
        tier=VerificationTier.STATIC,
        executor=Executor.INLINE,
        patterns=["**/*.py"],
        timeout_seconds=60,
    ),
    VerificationPolicy(
        name="typescript-static",
        tier=VerificationTier.STATIC,
        executor=Executor.INLINE,
        patterns=["**/*.ts", "**/*.tsx"],
        timeout_seconds=60,
    ),
    
    # Tier 1: Unit tests - isolated, fast
    VerificationPolicy(
        name="python-unit",
        tier=VerificationTier.UNIT,
        executor=Executor.GITHUB_ACTIONS,
        patterns=["src/**/*.py", "lib/**/*.py"],
        exclude_patterns=["**/test_integration_*.py"],
        timeout_seconds=180,
    ),
    VerificationPolicy(
        name="typescript-unit",
        tier=VerificationTier.UNIT,
        executor=Executor.GITHUB_ACTIONS,
        patterns=["src/**/*.ts", "lib/**/*.ts"],
        exclude_patterns=["**/*.integration.test.ts"],
        timeout_seconds=180,
    ),
    
    # Tier 2: Integration - needs Supabase, external APIs
    VerificationPolicy(
        name="supabase-integration",
        tier=VerificationTier.INTEGRATION,
        executor=Executor.LOCAL_NTM,  # Local has Supabase CLI
        patterns=[
            "**/supabase/**",
            "**/*.sql",
            "**/database/**",
            "**/migrations/**",
        ],
        required_env=["SUPABASE_URL", "SUPABASE_ANON_KEY"],
        timeout_seconds=300,
    ),
    VerificationPolicy(
        name="gmail-api-integration",
        tier=VerificationTier.INTEGRATION,
        executor=Executor.LOCAL_NTM,  # Local has Gmail credentials
        patterns=[
            "**/gmail/**",
            "**/email_fetcher/**",
            "**/newsletter_ingestion/**",
        ],
        required_env=["GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET"],
        timeout_seconds=300,
    ),
    VerificationPolicy(
        name="claude-api-integration",
        tier=VerificationTier.INTEGRATION,
        executor=Executor.E2B_SANDBOX,  # Safe to test API calls in sandbox
        patterns=[
            "**/summarizer/**",
            "**/haiku_processor/**",
            "**/sonnet_synthesis/**",
        ],
        required_env=["ANTHROPIC_API_KEY"],
        timeout_seconds=300,
    ),
    
    # Tier 3: System tests - full pipeline
    VerificationPolicy(
        name="full-pipeline",
        tier=VerificationTier.SYSTEM,
        executor=Executor.LOCAL_NTM,
        patterns=[
            "**/pipeline/**",
            "**/orchestrator/**",
            "docker-compose*.yml",
        ],
        required_env=["SUPABASE_URL", "ANTHROPIC_API_KEY", "GMAIL_CLIENT_ID"],
        timeout_seconds=600,
        requires_approval=True,  # Expensive - needs human OK
    ),
    
    # Tier 4: Manual review triggers
    VerificationPolicy(
        name="security-review",
        tier=VerificationTier.MANUAL,
        executor=Executor.HUMAN,
        patterns=[
            "**/auth/**",
            "**/credentials/**",
            "**/.env*",
            "**/secrets/**",
        ],
        requires_approval=True,
    ),
]


class VerificationGateway:
    """
    Routes changes to appropriate verification tier and executor.
    
    The gateway is the bridge between the fast inner loop (agent execution)
    and the trust-building outer loop (human oversight).
    """
    
    def __init__(
        self,
        policies: list[VerificationPolicy],
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ):
        self.policies = sorted(policies, key=lambda p: p.tier.value, reverse=True)
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self._http_client = httpx.AsyncClient()
    
    def match_policies(self, changeset: ChangeSet) -> list[VerificationPolicy]:
        """Find all policies that match the changed files"""
        from fnmatch import fnmatch
        
        matched = []
        for policy in self.policies:
            for changed_file in changeset.changed_files:
                # Check if file matches any pattern
                if any(fnmatch(changed_file, pat) for pat in policy.patterns):
                    # Check if file is excluded
                    if not any(fnmatch(changed_file, pat) for pat in policy.exclude_patterns):
                        matched.append(policy)
                        break  # Don't double-count same policy
        
        return matched
    
    def determine_verification_plan(self, changeset: ChangeSet) -> dict:
        """
        Analyze changeset and determine verification plan.
        
        Returns a plan with the highest required tier and all executors needed.
        """
        matched = self.match_policies(changeset)
        
        if not matched:
            # Default: at least run static analysis
            return {
                "tier": VerificationTier.STATIC,
                "executors": [Executor.INLINE],
                "policies": [],
                "requires_approval": False,
            }
        
        # Get highest tier needed
        max_tier = max(p.tier for p in matched)
        requires_approval = any(p.requires_approval for p in matched)
        
        # Collect all executors needed (may run multiple in parallel)
        executors = list(set(p.executor for p in matched))
        
        return {
            "tier": max_tier,
            "executors": executors,
            "policies": matched,
            "requires_approval": requires_approval,
        }
    
    async def execute_verification(
        self,
        changeset: ChangeSet,
        plan: dict,
    ) -> list[VerificationResult]:
        """
        Execute verification according to plan.
        
        Runs appropriate checks based on tier and executor.
        """
        results = []
        
        for policy in plan["policies"]:
            start_time = asyncio.get_event_loop().time()
            
            try:
                if policy.executor == Executor.INLINE:
                    result = await self._run_inline(changeset, policy)
                elif policy.executor == Executor.GITHUB_ACTIONS:
                    result = await self._trigger_github_actions(changeset, policy)
                elif policy.executor == Executor.LOCAL_NTM:
                    result = await self._dispatch_to_ntm(changeset, policy)
                elif policy.executor == Executor.E2B_SANDBOX:
                    result = await self._run_in_e2b(changeset, policy)
                elif policy.executor == Executor.HUMAN:
                    result = await self._queue_for_human(changeset, policy)
                else:
                    raise ValueError(f"Unknown executor: {policy.executor}")
                
                duration = asyncio.get_event_loop().time() - start_time
                result.duration_seconds = duration
                results.append(result)
                
            except Exception as e:
                results.append(VerificationResult(
                    changeset_id=changeset.id,
                    tier=policy.tier,
                    executor=policy.executor,
                    success=False,
                    duration_seconds=asyncio.get_event_loop().time() - start_time,
                    output="",
                    errors=[str(e)],
                ))
        
        # Store results in Supabase if configured
        if self.supabase_url:
            await self._store_results(changeset, results)
        
        return results
    
    async def _run_inline(
        self,
        changeset: ChangeSet,
        policy: VerificationPolicy,
    ) -> VerificationResult:
        """Run static analysis inline"""
        errors = []
        output_lines = []
        
        for file in changeset.changed_files:
            if file.endswith(".py"):
                # Run ruff (fast Python linter)
                proc = await asyncio.create_subprocess_exec(
                    "ruff", "check", file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    errors.append(f"ruff {file}: {stderr.decode()}")
                output_lines.append(stdout.decode())
                
                # Run mypy for type checking
                proc = await asyncio.create_subprocess_exec(
                    "mypy", "--ignore-missing-imports", file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    errors.append(f"mypy {file}: {stdout.decode()}")
                output_lines.append(stdout.decode())
                
            elif file.endswith((".ts", ".tsx")):
                # Run tsc for TypeScript
                proc = await asyncio.create_subprocess_exec(
                    "npx", "tsc", "--noEmit", file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    errors.append(f"tsc {file}: {stdout.decode()}")
                output_lines.append(stdout.decode())
        
        return VerificationResult(
            changeset_id=changeset.id,
            tier=policy.tier,
            executor=policy.executor,
            success=len(errors) == 0,
            duration_seconds=0,  # Will be set by caller
            output="\n".join(output_lines),
            errors=errors,
        )
    
    async def _trigger_github_actions(
        self,
        changeset: ChangeSet,
        policy: VerificationPolicy,
    ) -> VerificationResult:
        """Trigger GitHub Actions workflow and wait for result"""
        # This would use GitHub API to trigger workflow_dispatch
        # For now, return a placeholder
        
        # In production:
        # 1. POST to /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches
        # 2. Poll for workflow run completion
        # 3. Fetch workflow run logs
        
        return VerificationResult(
            changeset_id=changeset.id,
            tier=policy.tier,
            executor=policy.executor,
            success=True,  # Placeholder
            duration_seconds=0,
            output="GitHub Actions workflow triggered",
            errors=[],
        )
    
    async def _dispatch_to_ntm(
        self,
        changeset: ChangeSet,
        policy: VerificationPolicy,
    ) -> VerificationResult:
        """Dispatch verification to NTM-managed local agent"""
        
        # Use NTM's robot mode to dispatch
        cmd = [
            "ntm", "--robot-send",
            "--type", "claude_code",  # Or whichever agent type
            "--tag", "verifier",
            "--message", json.dumps({
                "action": "verify",
                "changeset_id": changeset.id,
                "branch": changeset.branch,
                "policy": policy.name,
                "files": changeset.changed_files,
            }),
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return VerificationResult(
                changeset_id=changeset.id,
                tier=policy.tier,
                executor=policy.executor,
                success=False,
                duration_seconds=0,
                output=stdout.decode(),
                errors=[stderr.decode()],
            )
        
        # In production, would poll for completion via Mail or CASS
        return VerificationResult(
            changeset_id=changeset.id,
            tier=policy.tier,
            executor=policy.executor,
            success=True,
            duration_seconds=0,
            output=stdout.decode(),
            errors=[],
        )
    
    async def _run_in_e2b(
        self,
        changeset: ChangeSet,
        policy: VerificationPolicy,
    ) -> VerificationResult:
        """Run verification in E2B sandbox"""
        
        # E2B integration example
        # Requires: pip install e2b
        
        try:
            from e2b import Sandbox
        except ImportError:
            return VerificationResult(
                changeset_id=changeset.id,
                tier=policy.tier,
                executor=policy.executor,
                success=False,
                duration_seconds=0,
                output="",
                errors=["E2B not installed: pip install e2b"],
            )
        
        async with Sandbox.create(template="python-dev") as sandbox:
            # Clone the repo at the specific commit
            await sandbox.process.start(
                f"git clone --depth 1 --branch {changeset.branch} "
                f"https://github.com/yourorg/newsletter-system.git /app"
            )
            
            # Install dependencies
            await sandbox.process.start("cd /app && pip install -r requirements.txt")
            
            # Run tests for changed files
            test_output = []
            for file in changeset.changed_files:
                if "test_" in file or "_test.py" in file:
                    result = await sandbox.process.start(f"cd /app && pytest {file} -v")
                    test_output.append(result.stdout)
            
            return VerificationResult(
                changeset_id=changeset.id,
                tier=policy.tier,
                executor=policy.executor,
                success=True,  # Would check actual test results
                duration_seconds=0,
                output="\n".join(test_output),
                errors=[],
            )
    
    async def _queue_for_human(
        self,
        changeset: ChangeSet,
        policy: VerificationPolicy,
    ) -> VerificationResult:
        """Queue changeset for human review"""
        
        # In production, this would:
        # 1. Create a Supabase record in a "pending_reviews" table
        # 2. Send notification (Slack, email, etc.)
        # 3. Return pending status
        
        return VerificationResult(
            changeset_id=changeset.id,
            tier=policy.tier,
            executor=policy.executor,
            success=True,  # Queued successfully
            duration_seconds=0,
            output="Queued for human review",
            errors=[],
        )
    
    async def _store_results(
        self,
        changeset: ChangeSet,
        results: list[VerificationResult],
    ):
        """Store verification results in Supabase"""
        if not self.supabase_url or not self.supabase_key:
            return
        
        for result in results:
            await self._http_client.post(
                f"{self.supabase_url}/rest/v1/verification_results",
                headers={
                    "apikey": self.supabase_key,
                    "Authorization": f"Bearer {self.supabase_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "changeset_id": result.changeset_id,
                    "tier": result.tier.name,
                    "executor": result.executor.value,
                    "success": result.success,
                    "duration_seconds": result.duration_seconds,
                    "output": result.output,
                    "errors": result.errors,
                    "timestamp": result.timestamp.isoformat(),
                },
            )


# =============================================================================
# FastAPI Application (Webhook Receiver)
# =============================================================================

def create_app():
    """Create FastAPI app for webhook handling"""
    from fastapi import FastAPI, Request, BackgroundTasks
    
    app = FastAPI(title="Verification Gateway")
    gateway = VerificationGateway(NEWSLETTER_POLICIES)
    
    @app.post("/webhook/github")
    async def github_webhook(request: Request, background_tasks: BackgroundTasks):
        """Handle GitHub push webhooks"""
        payload = await request.json()
        
        # Parse GitHub webhook payload
        changeset = ChangeSet(
            id=hashlib.sha256(
                f"{payload['after']}{datetime.utcnow().isoformat()}".encode()
            ).hexdigest()[:12],
            branch=payload["ref"].replace("refs/heads/", ""),
            agent_id=payload.get("pusher", {}).get("name", "unknown"),
            agent_type="github",  # Could be agent type from commit message
            changed_files=[
                f["filename"]
                for commit in payload.get("commits", [])
                for f in commit.get("added", []) + commit.get("modified", [])
            ],
            commit_sha=payload["after"],
        )
        
        # Determine verification plan
        plan = gateway.determine_verification_plan(changeset)
        
        # If requires approval, don't auto-execute
        if plan["requires_approval"]:
            return {
                "status": "pending_approval",
                "changeset_id": changeset.id,
                "tier": plan["tier"].name,
                "executors": [e.value for e in plan["executors"]],
            }
        
        # Execute verification in background
        background_tasks.add_task(
            gateway.execute_verification,
            changeset,
            plan,
        )
        
        return {
            "status": "verification_started",
            "changeset_id": changeset.id,
            "tier": plan["tier"].name,
            "executors": [e.value for e in plan["executors"]],
        }
    
    @app.post("/webhook/agent")
    async def agent_completion_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
    ):
        """Handle direct agent completion notifications"""
        payload = await request.json()
        
        changeset = ChangeSet(
            id=payload.get("task_id", hashlib.sha256(
                datetime.utcnow().isoformat().encode()
            ).hexdigest()[:12]),
            branch=payload["branch"],
            agent_id=payload["agent_id"],
            agent_type=payload["agent_type"],
            changed_files=payload["changed_files"],
            metadata=payload.get("metadata", {}),
        )
        
        plan = gateway.determine_verification_plan(changeset)
        
        background_tasks.add_task(
            gateway.execute_verification,
            changeset,
            plan,
        )
        
        return {
            "status": "verification_started",
            "changeset_id": changeset.id,
            "plan": {
                "tier": plan["tier"].name,
                "executors": [e.value for e in plan["executors"]],
                "requires_approval": plan["requires_approval"],
            },
        }
    
    @app.get("/status/{changeset_id}")
    async def get_status(changeset_id: str):
        """Get verification status for a changeset"""
        # Would query Supabase for results
        return {"changeset_id": changeset_id, "status": "not_implemented"}
    
    return app


if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8080)
