"""Evaluator module: execute scenarios against live services and produce verdicts.

The Evaluator takes a scenario (an ordered list of action steps with
expectations), executes each step through the appropriate transport client,
compares actual results against expectations, captures variables for use
in subsequent steps, and produces structured verdicts.

Extended with side-effect verification (D2/D3), semantic evaluation (D4),
and formalized assertion types (D1/D5).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

from jsonpath_ng import parse as jsonpath_parse
from jsonpath_ng.exceptions import JsonPathParserError

from evaluation.gen_eval.clients.base import StepContext, StepResult, TransportClientRegistry
from evaluation.gen_eval.descriptor import InterfaceDescriptor
from evaluation.gen_eval.models import (
    ActionStep,
    ExpectBlock,
    Scenario,
    ScenarioVerdict,
    SemanticVerdict,
    SideEffectStep,
    SideEffectVerdict,
    StepVerdict,
)
from evaluation.gen_eval.semantic_judge import semantic_judge_evaluate

logger = logging.getLogger(__name__)

# Pattern for variable interpolation: {{ var_name }}
_VAR_PATTERN = re.compile(r"\{\{\s*([\w.\-]+)\s*\}\}")

# Default per-step timeout in seconds
_DEFAULT_TIMEOUT = 30.0


class Evaluator:
    """Execute scenarios against live services and judge results."""

    def __init__(
        self,
        descriptor: InterfaceDescriptor,
        clients: TransportClientRegistry,
        *,
        default_timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.descriptor = descriptor
        self.clients = clients
        self.default_timeout = default_timeout

    async def evaluate(self, scenario: Scenario) -> ScenarioVerdict:
        """Evaluate a single scenario step-by-step."""
        start = time.monotonic()
        step_verdicts: list[StepVerdict] = []
        captured_vars: dict[str, Any] = {}
        cleanup_warnings: list[str] = []
        scenario_failed = False
        prev_transport: str | None = None
        prev_body: dict[str, Any] | None = None

        # --- Main steps ---
        for step in scenario.steps:
            if scenario_failed:
                step_verdicts.append(
                    StepVerdict(
                        step_id=step.id,
                        transport=step.transport,
                        status="skip",
                    )
                )
                continue

            verdict = await self._execute_step(step, captured_vars, prev_transport, prev_body)
            step_verdicts.append(verdict)

            # Capture variables on success
            if verdict.status == "pass" and verdict.captured_vars:
                captured_vars.update(verdict.captured_vars)

            # Track previous transport/body for cross-interface detection
            if verdict.status == "pass":
                prev_transport = step.transport
                prev_body = verdict.actual.get("body")
            else:
                scenario_failed = True

        # --- Cleanup steps (always run) ---
        if scenario.cleanup:
            for step in scenario.cleanup:
                verdict = await self._execute_step(
                    step, captured_vars, prev_transport=None, prev_body=None
                )
                verdict.is_cleanup = True
                if verdict.status in ("fail", "error"):
                    cleanup_warnings.append(
                        f"Cleanup step '{step.id}' {verdict.status}: "
                        f"{verdict.error_message or verdict.diff}"
                    )
                step_verdicts.append(verdict)

        # --- Determine overall status ---
        main_verdicts = [v for v in step_verdicts if not v.is_cleanup]
        if not main_verdicts:
            overall_status = "pass"
        elif any(v.status == "error" for v in main_verdicts):
            overall_status = "error"
        elif any(v.status == "fail" for v in main_verdicts):
            overall_status = "fail"
        else:
            overall_status = "pass"

        failure_summary = None
        if overall_status in ("fail", "error"):
            failed = [v for v in main_verdicts if v.status in ("fail", "error")]
            if failed:
                first = failed[0]
                failure_summary = (
                    f"Step '{first.step_id}' {first.status}: {first.error_message or first.diff}"
                )

        elapsed = time.monotonic() - start

        # Compute endpoint-specific interface identifiers from steps,
        # matching the format returned by InterfaceDescriptor.all_interfaces():
        #   HTTP  → "METHOD /path"  (e.g. "POST /locks/acquire")
        #   MCP   → "mcp:tool_name" (e.g. "mcp:check_locks")
        #   CLI   → "cli:command"   (e.g. "cli:lock")
        interfaces_tested = self._extract_interfaces(scenario.steps)

        return ScenarioVerdict(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            status=overall_status,  # type: ignore[arg-type]
            steps=step_verdicts,
            duration_seconds=elapsed,
            interfaces_tested=interfaces_tested,
            failure_summary=failure_summary,
            cleanup_warnings=cleanup_warnings,
            category=scenario.category,
            backend_used=scenario.generated_by,
        )

    async def evaluate_batch(self, scenarios: list[Scenario]) -> list[ScenarioVerdict]:
        """Evaluate multiple scenarios sequentially.

        Parallelism is managed by the orchestrator layer, not here.
        """
        verdicts: list[ScenarioVerdict] = []
        for scenario in scenarios:
            verdict = await self.evaluate(scenario)
            verdicts.append(verdict)
        return verdicts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_step(
        self,
        step: ActionStep,
        captured_vars: dict[str, Any],
        prev_transport: str | None,
        prev_body: dict[str, Any] | None,
    ) -> StepVerdict:
        """Execute a single step and return its verdict."""
        step_start = time.monotonic()
        step_start_time = datetime.now(UTC).isoformat()
        timeout = step.timeout_seconds or self.default_timeout

        # Inject step_start_time into captured vars for side-effect interpolation
        step_vars = dict(captured_vars)
        step_vars["step_start_time"] = step_start_time

        # Interpolate variables into step fields
        interpolated = self._interpolate_step(step, step_vars)

        # Build context
        context = StepContext(
            variables=step_vars,
            timeout_seconds=timeout,
        )

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                self.clients.execute(interpolated.transport, interpolated, context),
                timeout=timeout,
            )
        except TimeoutError:
            elapsed_ms = (time.monotonic() - step_start) * 1000
            return StepVerdict(
                step_id=step.id,
                transport=step.transport,
                status="error",
                error_message=f"Step timed out after {timeout}s",
                duration_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = (time.monotonic() - step_start) * 1000
            return StepVerdict(
                step_id=step.id,
                transport=step.transport,
                status="error",
                error_message=f"Transport error: {exc}",
                duration_ms=elapsed_ms,
            )

        elapsed_ms = (time.monotonic() - step_start) * 1000

        # Transport-level error
        if result.error:
            return StepVerdict(
                step_id=step.id,
                transport=step.transport,
                status="error",
                actual={"error": result.error},
                error_message=result.error,
                duration_ms=elapsed_ms,
            )

        # Build actual dict
        actual: dict[str, Any] = {"body": result.body}
        if result.status_code is not None:
            actual["status"] = result.status_code
        if result.exit_code is not None:
            actual["exit_code"] = result.exit_code
        if result.headers:
            actual["headers"] = result.headers

        # Compare against expectations
        diff: dict[str, Any] | None = None
        expected_dict: dict[str, Any] | None = None
        status = "pass"

        if interpolated.expect:
            expected_dict, diff = self._compare(interpolated.expect, result)
            if diff:
                status = "fail"

        # Capture variables via JSONPath
        captured: dict[str, Any] | None = None
        if interpolated.capture and status == "pass":
            captured, capture_error = self._capture_vars(interpolated.capture, result.body)
            if capture_error:
                return StepVerdict(
                    step_id=step.id,
                    transport=step.transport,
                    status="error",
                    actual=actual,
                    error_message=capture_error,
                    duration_ms=elapsed_ms,
                )

        # Cross-interface mismatch detection
        cross_diff = self._detect_cross_interface_mismatch(
            step, result.body, prev_transport, prev_body
        )
        if cross_diff:
            status = "fail"
            if diff is None:
                diff = cross_diff
            else:
                diff["cross_interface"] = cross_diff

        # --- Side-effect verification (D2/D3) ---
        side_effect_verdicts: list[SideEffectVerdict] = []
        if status == "pass" and interpolated.side_effects:
            se_verdicts = await self._execute_side_effects(
                interpolated.side_effects.verify,
                interpolated.side_effects.prohibit,
                step_vars,
            )
            side_effect_verdicts = se_verdicts
            # If any side-effect verdict failed, step fails
            if any(v.status == "fail" for v in side_effect_verdicts):
                status = "fail"

        # --- Semantic evaluation (D4) ---
        semantic_verdict: SemanticVerdict | None = None
        if status == "pass" and interpolated.semantic and interpolated.semantic.judge:
            semantic_verdict = await self._evaluate_semantic(
                interpolated.semantic.criteria,
                interpolated.semantic.fields,
                interpolated.semantic.min_confidence,
                result.body,
            )
            if semantic_verdict.status == "fail":
                status = "fail"

        return StepVerdict(
            step_id=step.id,
            transport=step.transport,
            status=status,  # type: ignore[arg-type]
            actual=actual,
            expected=expected_dict,
            diff=diff,
            duration_ms=elapsed_ms,
            captured_vars=captured,
            side_effect_verdicts=side_effect_verdicts,
            semantic_verdict=semantic_verdict,
        )

    def _interpolate_step(self, step: ActionStep, variables: dict[str, Any]) -> ActionStep:
        """Return a copy of *step* with ``{{ var }}`` placeholders replaced."""
        if not variables:
            return step

        data = step.model_dump()
        interpolated = self._interpolate_value(data, variables)
        return ActionStep(**interpolated)

    def _interpolate_value(self, value: Any, variables: dict[str, Any]) -> Any:
        """Recursively interpolate variables in a value."""
        if isinstance(value, str):
            return _VAR_PATTERN.sub(
                lambda m: str(variables.get(m.group(1), m.group(0))),
                value,
            )
        if isinstance(value, dict):
            return {k: self._interpolate_value(v, variables) for k, v in value.items()}
        if isinstance(value, list):
            return [self._interpolate_value(item, variables) for item in value]
        return value

    def _compare(
        self, expect: ExpectBlock, result: StepResult
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Compare expectations against actual result.

        Returns (expected_dict, diff_or_none).
        """
        expected: dict[str, Any] = {}
        diff: dict[str, Any] = {}

        if expect.status is not None:
            expected["status"] = expect.status
            if result.status_code != expect.status:
                diff["status"] = {
                    "expected": expect.status,
                    "actual": result.status_code,
                }

        # Extended: status_one_of (mutually exclusive with status)
        if expect.status_one_of is not None:
            expected["status_one_of"] = expect.status_one_of
            if result.status_code not in expect.status_one_of:
                diff["status_one_of"] = {
                    "expected_one_of": expect.status_one_of,
                    "actual": result.status_code,
                }

        if expect.exit_code is not None:
            expected["exit_code"] = expect.exit_code
            if result.exit_code != expect.exit_code:
                diff["exit_code"] = {
                    "expected": expect.exit_code,
                    "actual": result.exit_code,
                }

        if expect.body is not None:
            expected["body"] = expect.body
            body_diff = self._compare_body(expect.body, result.body)
            if body_diff:
                diff["body"] = body_diff

        # Extended: body_contains — deep partial matching (D5)
        if expect.body_contains is not None:
            expected["body_contains"] = expect.body_contains
            if not self._deep_contains(result.body, expect.body_contains):
                diff["body_contains"] = {
                    "expected_subset": expect.body_contains,
                    "actual": result.body,
                }

        # Extended: body_excludes — negative assertion
        if expect.body_excludes is not None:
            expected["body_excludes"] = expect.body_excludes
            if self._deep_contains(result.body, expect.body_excludes):
                diff["body_excludes"] = {
                    "excluded_content_found": expect.body_excludes,
                    "actual": result.body,
                }

        if expect.error_contains is not None:
            expected["error_contains"] = expect.error_contains
            error_str = result.error or ""
            # Also check body for error messages
            body_str = str(result.body)
            if expect.error_contains not in error_str and expect.error_contains not in body_str:
                diff["error_contains"] = {
                    "expected_substring": expect.error_contains,
                    "actual_error": result.error,
                    "actual_body": result.body,
                }

        if expect.not_empty is True:
            expected["not_empty"] = True
            if not result.body:
                diff["not_empty"] = {"expected": "non-empty body", "actual": result.body}

        if expect.rows is not None:
            expected["rows"] = expect.rows
            actual_rows = result.body.get("rows") if isinstance(result.body, dict) else None
            if actual_rows != expect.rows:
                diff["rows"] = {"expected": expect.rows, "actual": actual_rows}

        # Extended: rows_gte
        if expect.rows_gte is not None:
            expected["rows_gte"] = expect.rows_gte
            actual_rows = result.body.get("rows") if isinstance(result.body, dict) else None
            if actual_rows is None or actual_rows < expect.rows_gte:
                diff["rows_gte"] = {
                    "expected_gte": expect.rows_gte,
                    "actual": actual_rows,
                }

        # Extended: rows_lte
        if expect.rows_lte is not None:
            expected["rows_lte"] = expect.rows_lte
            actual_rows = result.body.get("rows") if isinstance(result.body, dict) else None
            if actual_rows is None or actual_rows > expect.rows_lte:
                diff["rows_lte"] = {
                    "expected_lte": expect.rows_lte,
                    "actual": actual_rows,
                }

        if expect.row is not None:
            expected["row"] = expect.row
            actual_row = result.body.get("row") if isinstance(result.body, dict) else None
            row_diff = self._compare_body(expect.row, actual_row or {})
            if row_diff:
                diff["row"] = row_diff

        # Extended: array_contains
        if expect.array_contains is not None:
            expected["array_contains"] = expect.array_contains
            ac_diff = self._compare_array_contains(expect.array_contains, result.body)
            if ac_diff:
                diff["array_contains"] = ac_diff

        return expected, diff if diff else None

    def _compare_body(
        self, expected_body: dict[str, Any], actual_body: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Compare expected body fields against actual body using JSONPath.

        For simple keys, does direct lookup. For keys starting with ``$``,
        uses JSONPath matching.
        """
        diff: dict[str, Any] = {}
        for key, expected_val in expected_body.items():
            if key.startswith("$"):
                # JSONPath assertion
                try:
                    expr = jsonpath_parse(key)
                    matches = expr.find(actual_body)
                    if not matches:
                        diff[key] = {"expected": expected_val, "actual": None}
                    elif matches[0].value != expected_val:
                        diff[key] = {
                            "expected": expected_val,
                            "actual": matches[0].value,
                        }
                except JsonPathParserError:
                    diff[key] = {"error": f"Invalid JSONPath: {key}"}
            else:
                actual_val = actual_body.get(key) if isinstance(actual_body, dict) else None
                if actual_val != expected_val:
                    diff[key] = {"expected": expected_val, "actual": actual_val}

        return diff if diff else None

    def _capture_vars(
        self, capture: dict[str, str], body: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Extract variables from response body using JSONPath.

        Returns (captured_dict, error_message_or_none).
        """
        captured: dict[str, Any] = {}
        for var_name, jsonpath_expr in capture.items():
            try:
                expr = jsonpath_parse(jsonpath_expr)
            except JsonPathParserError:
                return None, f"Invalid JSONPath for capture '{var_name}': {jsonpath_expr}"

            matches = expr.find(body)
            if matches:
                captured[var_name] = matches[0].value
            else:
                # No match is not an error; variable just isn't captured
                captured[var_name] = None

        return captured, None

    @staticmethod
    def _extract_interfaces(steps: list[ActionStep]) -> list[str]:
        """Extract endpoint-specific interface identifiers from steps.

        Produces names matching ``InterfaceDescriptor.all_interfaces()``:
          - HTTP steps  → ``"METHOD /path"`` (path stripped of query string)
          - MCP steps   → ``"mcp:tool_name"``
          - CLI steps   → ``"cli:command subcommand"`` (words before first ``--`` flag)
          - DB/Wait     → omitted (not tracked as testable interfaces)
        """
        seen: set[str] = set()
        result: list[str] = []
        for step in steps:
            iface: str | None = None
            if step.transport == "http" and step.method and step.endpoint:
                # Strip query string for matching: /audit?limit=10 → /audit
                path = step.endpoint.split("?")[0]
                iface = f"{step.method.upper()} {path}"
            elif step.transport == "mcp" and step.tool:
                iface = f"mcp:{step.tool}"
            elif step.transport == "cli" and step.command:
                # Extract command + subcommand (words before the first --flag).
                # E.g., "lock status --file-path x" → "lock status"
                parts = step.command.strip().split()
                cmd_parts = []
                for part in parts:
                    if part.startswith("--") or part.startswith("-"):
                        break
                    cmd_parts.append(part)
                if cmd_parts:
                    iface = f"cli:{' '.join(cmd_parts)}"
            if iface and iface not in seen:
                seen.add(iface)
                result.append(iface)
        return result

    def _detect_cross_interface_mismatch(
        self,
        step: ActionStep,
        current_body: dict[str, Any],
        prev_transport: str | None,
        prev_body: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Detect state mismatches between consecutive cross-transport steps.

        When consecutive steps target different transports but access
        the same resource, compare overlapping response fields to detect
        inconsistencies.
        """
        if prev_transport is None or prev_body is None:
            return None
        if step.transport == prev_transport:
            return None
        if not isinstance(prev_body, dict) or not isinstance(current_body, dict):
            return None

        # Find overlapping keys
        overlapping = set(prev_body.keys()) & set(current_body.keys())
        mismatches: dict[str, Any] = {}
        for key in overlapping:
            if prev_body[key] != current_body[key]:
                mismatches[key] = {
                    f"via_{prev_transport}": prev_body[key],
                    f"via_{step.transport}": current_body[key],
                }

        if mismatches:
            return {
                "cross_interface_mismatch": True,
                "transports": [prev_transport, step.transport],
                "fields": mismatches,
            }
        return None

    # ------------------------------------------------------------------
    # Deep matching for body_contains / body_excludes (D5)
    # ------------------------------------------------------------------

    @staticmethod
    def _deep_contains(actual: Any, expected: Any) -> bool:
        """Recursive subset matching.

        - Dict: every key in expected exists in actual with a matching value.
        - List: every item in expected has a distinct matching item in actual
          (order-independent).
        - Scalar: direct equality.
        """
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                return False
            return all(
                k in actual and Evaluator._deep_contains(actual[k], v)
                for k, v in expected.items()
            )
        if isinstance(expected, list):
            if not isinstance(actual, list):
                return False
            # Each expected item must match a distinct actual item
            used: set[int] = set()
            for exp_item in expected:
                found = False
                for i, act_item in enumerate(actual):
                    if i not in used and Evaluator._deep_contains(act_item, exp_item):
                        used.add(i)
                        found = True
                        break
                if not found:
                    return False
            return True
        return actual == expected

    # ------------------------------------------------------------------
    # array_contains assertion
    # ------------------------------------------------------------------

    def _compare_array_contains(
        self, spec: dict[str, Any], body: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Assert a JSON array at a JSONPath contains a matching element.

        spec keys:
          - path: JSONPath to the array
          - match: dict of field criteria the element must satisfy
        """
        path = spec.get("path", "")
        match_criteria = spec.get("match", {})

        try:
            expr = jsonpath_parse(path)
            matches = expr.find(body)
        except JsonPathParserError:
            return {"error": f"Invalid JSONPath: {path}"}

        if not matches:
            return {"error": f"Path '{path}' not found in response"}

        array = matches[0].value
        if not isinstance(array, list):
            return {"error": f"Path '{path}' does not resolve to an array"}

        # Check if any element in the array matches the criteria
        for element in array:
            if self._deep_contains(element, match_criteria):
                return None  # Found a match — pass

        return {
            "expected_match": match_criteria,
            "in_array_at": path,
            "array_length": len(array),
        }

    # ------------------------------------------------------------------
    # Side-effect verification (D2/D3)
    # ------------------------------------------------------------------

    async def _execute_side_effects(
        self,
        verify_steps: list[SideEffectStep],
        prohibit_steps: list[SideEffectStep],
        captured_vars: dict[str, Any],
    ) -> list[SideEffectVerdict]:
        """Execute side-effect verification and prohibit steps."""
        verdicts: list[SideEffectVerdict] = []

        # Verify steps: expectations MUST match
        for se_step in verify_steps:
            verdict = await self._run_side_effect_step(se_step, captured_vars, mode="verify")
            verdicts.append(verdict)

        # Prohibit steps: expectations MUST NOT match (D3)
        for se_step in prohibit_steps:
            verdict = await self._run_side_effect_step(se_step, captured_vars, mode="prohibit")
            verdicts.append(verdict)

        return verdicts

    async def _run_side_effect_step(
        self,
        se_step: SideEffectStep,
        captured_vars: dict[str, Any],
        mode: str,
    ) -> SideEffectVerdict:
        """Execute a single side-effect step and produce its verdict."""
        # Convert SideEffectStep to ActionStep for transport execution
        action = ActionStep(
            id=se_step.id,
            transport=se_step.transport,
            method=se_step.method,
            endpoint=se_step.endpoint,
            body=se_step.body,
            headers=se_step.headers,
            tool=se_step.tool,
            params=se_step.params,
            command=se_step.command,
            args=se_step.args,
            sql=se_step.sql,
            seconds=se_step.seconds,
            expect=se_step.expect,
            capture=se_step.capture,
            timeout_seconds=se_step.timeout_seconds,
        )

        # Interpolate variables
        interpolated = self._interpolate_step(action, captured_vars)
        timeout = interpolated.timeout_seconds or self.default_timeout
        context = StepContext(variables=dict(captured_vars), timeout_seconds=timeout)

        try:
            result = await asyncio.wait_for(
                self.clients.execute(interpolated.transport, interpolated, context),
                timeout=timeout,
            )
        except Exception as exc:
            return SideEffectVerdict(
                step_id=se_step.id,
                mode=mode,  # type: ignore[arg-type]
                status="error",
                error_message=f"Side-effect transport error: {exc}",
            )

        if result.error:
            return SideEffectVerdict(
                step_id=se_step.id,
                mode=mode,  # type: ignore[arg-type]
                status="error",
                error_message=result.error,
            )

        # Compare expectations
        expected_dict: dict[str, Any] | None = None
        se_diff: dict[str, Any] | None = None
        if interpolated.expect:
            expected_dict, se_diff = self._compare(interpolated.expect, result)

        actual: dict[str, Any] = {"body": result.body}
        if result.status_code is not None:
            actual["status"] = result.status_code

        if mode == "verify":
            # Verify: expectations must match (no diff = pass)
            return SideEffectVerdict(
                step_id=se_step.id,
                mode="verify",
                status="fail" if se_diff else "pass",
                actual=actual,
                expected=expected_dict,
                diff=se_diff,
            )
        else:
            # Prohibit (D3): expectations MUST NOT match
            # If diff is None → expectations matched → prohibited state exists → FAIL
            if se_diff is None:
                return SideEffectVerdict(
                    step_id=se_step.id,
                    mode="prohibit",
                    status="fail",
                    actual=actual,
                    expected=expected_dict,
                    error_message="Prohibited state detected",
                )
            else:
                return SideEffectVerdict(
                    step_id=se_step.id,
                    mode="prohibit",
                    status="pass",
                    actual=actual,
                    expected=expected_dict,
                )

    # ------------------------------------------------------------------
    # Semantic evaluation (D4)
    # ------------------------------------------------------------------

    async def _evaluate_semantic(
        self,
        criteria: str,
        fields: list[str],
        min_confidence: float,
        body: dict[str, Any],
    ) -> SemanticVerdict:
        """Invoke LLM-as-judge semantic evaluation."""
        # Extract field values via JSONPath
        field_values: dict[str, Any] = {}
        for field_path in fields:
            try:
                expr = jsonpath_parse(field_path)
                matches = expr.find(body)
                field_values[field_path] = [m.value for m in matches] if matches else None
            except JsonPathParserError:
                field_values[field_path] = f"<invalid JSONPath: {field_path}>"

        if not field_values:
            # If no fields specified, use entire body
            field_values["$"] = body

        try:
            judgment = await semantic_judge_evaluate(
                criteria=criteria,
                field_values=field_values,
            )
        except Exception as exc:
            logger.warning("Semantic evaluation unavailable: %s", exc)
            return SemanticVerdict(
                status="skip",
                reasoning=f"LLM backend unavailable: {exc}",
            )

        confidence = judgment.get("confidence", 0.0)
        verdict_str = judgment.get("verdict", "fail")
        reasoning = judgment.get("reasoning", "")

        if verdict_str == "pass" and confidence >= min_confidence:
            return SemanticVerdict(
                status="pass",
                confidence=confidence,
                reasoning=reasoning,
            )
        else:
            return SemanticVerdict(
                status="fail",
                confidence=confidence,
                reasoning=reasoning,
            )
