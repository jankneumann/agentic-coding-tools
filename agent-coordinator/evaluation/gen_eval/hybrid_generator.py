"""Hybrid scenario generator.

Composes TemplateGenerator + CLIGenerator + SDKGenerator with
AdaptiveBackend. AdaptiveBackend detects rate limiting and falls
back CLI -> SDK transparently.
"""

from __future__ import annotations

import logging

from .cli_generator import CLIBackend, CLIBackendError, CLIGenerator
from .config import GenEvalConfig
from .descriptor import InterfaceDescriptor
from .generator import TemplateGenerator
from .models import EvalFeedback, Scenario
from .sdk_generator import SDKBackend, SDKBackendError, SDKGenerator

logger = logging.getLogger(__name__)


class AdaptiveBackend:
    """Tries CLI first, falls back to SDK on rate limits.

    Rate limiting is detected by checking: non-zero exit code + stderr
    matching configurable patterns ("rate limit", "too many requests",
    "quota exceeded", HTTP 429).
    """

    def __init__(
        self,
        cli: CLIBackend,
        sdk: SDKBackend | None = None,
        rate_limit_patterns: list[str] | None = None,
    ) -> None:
        self.cli = cli
        self.sdk = sdk
        self._rate_limit_patterns = rate_limit_patterns or [
            "rate limit",
            "too many requests",
            "quota exceeded",
            "429",
        ]
        self._cli_available = True

    @property
    def name(self) -> str:
        if self._cli_available:
            return self.cli.name
        return self.sdk.name if self.sdk else self.cli.name

    @property
    def is_subscription_covered(self) -> bool:
        return self._cli_available and self.cli.is_subscription_covered

    async def is_available(self) -> bool:
        """Check if at least one backend is available."""
        if await self.cli.is_available():
            return True
        if self.sdk and await self.sdk.is_available():
            return True
        return False

    async def run(self, prompt: str, system: str | None = None) -> str:
        """Run prompt through CLI, falling back to SDK on rate limit."""
        if self._cli_available:
            try:
                return await self.cli.run(prompt, system=system)
            except CLIBackendError as e:
                if self._is_rate_limited(e):
                    logger.warning(
                        "CLI rate limited (exit=%d), falling back to SDK",
                        e.exit_code,
                    )
                    self._cli_available = False
                else:
                    raise

        if self.sdk is None:
            raise CLIBackendError(
                "CLI rate limited and no SDK backend configured",
                exit_code=-1,
                stderr="no fallback",
            )

        try:
            return await self.sdk.run(prompt, system=system)
        except SDKBackendError:
            raise

    def _is_rate_limited(self, error: CLIBackendError) -> bool:
        """Check if a CLI error indicates rate limiting."""
        if error.exit_code == 0:
            return False
        stderr_lower = error.stderr.lower()
        return any(pattern.lower() in stderr_lower for pattern in self._rate_limit_patterns)

    def reset(self) -> None:
        """Reset CLI availability (e.g., after a backoff period)."""
        self._cli_available = True


class HybridGenerator:
    """Composes template + LLM generators for comprehensive coverage.

    Produces scenarios from templates first (free, deterministic), then
    augments with LLM-generated scenarios via AdaptiveBackend (CLI first,
    SDK fallback). The adaptive backend handles rate limiting transparently.

    Implements the ScenarioGenerator protocol.
    """

    def __init__(
        self,
        descriptor: InterfaceDescriptor,
        config: GenEvalConfig,
        feedback: EvalFeedback | None = None,
        template_generator: TemplateGenerator | None = None,
        cli_generator: CLIGenerator | None = None,
        sdk_generator: SDKGenerator | None = None,
        adaptive_backend: AdaptiveBackend | None = None,
    ) -> None:
        self.descriptor = descriptor
        self.config = config
        self.feedback = feedback

        self.template_generator = template_generator or TemplateGenerator(
            descriptor=descriptor, config=config, feedback=feedback
        )

        # Build adaptive backend if not provided
        if adaptive_backend is None:
            cli_backend = CLIBackend(
                command=config.cli_command,
                args=config.cli_args,
            )
            sdk_backend: SDKBackend | None = None
            if config.auto_fallback_to_sdk:
                sdk_backend = SDKBackend(
                    provider=config.sdk_provider,  # type: ignore[arg-type]
                    model=config.sdk_model,
                    api_key_env=config.sdk_api_key_env,
                )
            adaptive_backend = AdaptiveBackend(
                cli=cli_backend,
                sdk=sdk_backend,
                rate_limit_patterns=config.rate_limit_patterns,
            )

        self.adaptive_backend = adaptive_backend

        # Wire generators with the adaptive backend's sub-backends
        self.cli_generator = cli_generator or CLIGenerator(
            descriptor=descriptor,
            config=config,
            backend=adaptive_backend.cli,
            feedback=feedback,
        )
        self.sdk_generator = sdk_generator or SDKGenerator(
            descriptor=descriptor,
            config=config,
            backend=adaptive_backend.sdk or SDKBackend(),
            feedback=feedback,
        )

    async def generate(
        self,
        focus_areas: list[str] | None = None,
        count: int = 10,
    ) -> list[Scenario]:
        """Generate scenarios from templates, then augment with LLM.

        Template scenarios are generated first (free). If the template
        count is below the requested count, LLM scenarios fill the gap
        using the adaptive backend (CLI -> SDK fallback).
        """
        # Phase 1: Template scenarios (free, deterministic)
        template_scenarios = await self.template_generator.generate(
            focus_areas=focus_areas, count=count
        )
        logger.info("Template generator produced %d scenarios", len(template_scenarios))

        if len(template_scenarios) >= count:
            return template_scenarios[:count]

        # Phase 2: LLM-augmented scenarios
        remaining = count - len(template_scenarios)
        llm_scenarios = await self._generate_llm(focus_areas, remaining)
        logger.info("LLM generator produced %d scenarios", len(llm_scenarios))

        # Deduplicate by ID
        seen_ids = {s.id for s in template_scenarios}
        unique_llm = [s for s in llm_scenarios if s.id not in seen_ids]

        combined = template_scenarios + unique_llm
        return combined[:count]

    async def _generate_llm(
        self,
        focus_areas: list[str] | None,
        count: int,
    ) -> list[Scenario]:
        """Generate LLM scenarios via adaptive backend."""
        if self.config.mode == "template-only":
            return []

        # Use CLI generator with adaptive backend's run method
        try:
            prompt = self.cli_generator._build_prompt(focus_areas, count)
            system = self.cli_generator._build_system_prompt()
            raw = await self.adaptive_backend.run(prompt, system=system)
            return self.cli_generator._parse_output(raw)
        except (CLIBackendError, SDKBackendError) as e:
            logger.warning("LLM generation failed: %s", e)
            return []
