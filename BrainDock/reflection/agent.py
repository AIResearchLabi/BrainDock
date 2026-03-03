"""Reflection Agent — analyzes failures and proposes plan modifications."""

from __future__ import annotations

import json

from BrainDock.base_agent import BaseAgent
from BrainDock.llm import LLMBackend
from BrainDock.preambles import build_system_prompt, EXEC_OPS
from .models import ReflectionResult
from .prompts import SYSTEM_PROMPT, REFLECT_PROMPT

MAX_ITERATIONS = 2
_MAX_ERROR_HISTORY = 50  # Cap error history to prevent unbounded growth
_MAX_REFLECTION_HISTORY = 50  # Cap reflection history to prevent unbounded growth

# Error signatures that indicate environment/shell issues unlikely to be
# fixed by retrying with a modified plan alone.
_RECURRING_ERROR_PATTERNS = (
    '/bin/sh: 1: Syntax error: "(" unexpected',
    "/bin/sh: 1: Syntax error",
    "Syntax error: \"(\" unexpected",
    "Command timed out after",
)


class ReflectionAgent(BaseAgent):
    """Agent that reflects on execution failures and proposes fixes.

    Limited to MAX_ITERATIONS to prevent infinite reflection loops.
    Tracks previous reflections to provide history and detect repeated errors.

    Usage:
        agent = ReflectionAgent(llm=my_backend)
        result = agent.reflect(execution_result, plan, context)
    """

    def __init__(
        self,
        llm: LLMBackend | None = None,
        max_iterations: int = MAX_ITERATIONS,
    ):
        super().__init__(llm=llm)
        self.max_iterations = max_iterations
        self._iteration = 0
        self._previous_reflections: list[dict] = []
        self._previous_errors: list[str] = []
        self._sys_prompt = build_system_prompt(SYSTEM_PROMPT, EXEC_OPS)

    def _extract_error_signatures(self, execution_result: dict) -> list[str]:
        """Extract error signatures from execution outcomes for dedup."""
        sigs = []
        for outcome in execution_result.get("outcomes", []):
            if outcome.get("success"):
                continue
            err = outcome.get("error", "")
            if err:
                # Normalize: take first line of stderr
                first_line = err.strip().split("\n")[0][:120]
                sigs.append(first_line)
        return sigs

    def _has_recurring_pattern(self, execution_result: dict) -> str | None:
        """Check if the current error matches a known recurring pattern.

        Returns the matched pattern string if found, None otherwise.
        """
        current_errors = self._extract_error_signatures(execution_result)
        for err in current_errors:
            for pattern in _RECURRING_ERROR_PATTERNS:
                if pattern in err:
                    # Check if we saw this same pattern before
                    for prev_err in self._previous_errors:
                        if pattern in prev_err:
                            return pattern
        return None

    def reflect(
        self,
        execution_result: dict,
        plan: dict,
        context: str = "",
    ) -> ReflectionResult:
        """Analyze a failed execution and propose modifications.

        Args:
            execution_result: ExecutionResult as a dict.
            plan: The ActionPlan that was executed, as a dict.
            context: Additional project context.

        Returns:
            ReflectionResult with root causes and proposed modifications.
        """
        self._iteration += 1

        if self._iteration > self.max_iterations:
            return ReflectionResult(
                summary=f"Max reflection iterations ({self.max_iterations}) reached. Cannot fix automatically.",
                should_retry=False,
            )

        # Early-exit: detect recurring error patterns that won't be fixed
        # by retrying (e.g., /bin/sh syntax errors appearing twice)
        recurring = self._has_recurring_pattern(execution_result)
        if recurring:
            new_sigs = self._extract_error_signatures(execution_result)
            self._previous_errors.extend(new_sigs)
            self._previous_errors = self._previous_errors[-_MAX_ERROR_HISTORY:]
            return ReflectionResult(
                summary=(
                    f"Recurring error detected: '{recurring}'. "
                    "This appears to be an environment/shell compatibility issue "
                    "that retrying with a modified plan cannot fix. "
                    "Escalating rather than wasting another attempt."
                ),
                should_retry=False,
                root_causes=[],
                needs_human=False,
            )

        # Build previous-reflection context so the LLM can avoid repeating fixes
        prev_context = ""
        if self._previous_reflections:
            prev_parts = []
            for i, prev in enumerate(self._previous_reflections, 1):
                cats = [rc.get("category", "") for rc in prev.get("root_causes", [])]
                prev_parts.append(
                    f"  Attempt {i}: categories={cats}, "
                    f"summary={prev.get('summary', '')[:200]}"
                )
            prev_context = (
                "\n\nPREVIOUS REFLECTION ATTEMPTS (do NOT repeat the same fixes):\n"
                + "\n".join(prev_parts)
            )

        prompt = REFLECT_PROMPT.format(
            execution_json=json.dumps(execution_result, indent=2),
            plan_json=json.dumps(plan, indent=2),
            context=(context or "(no additional context)") + prev_context,
            iteration=self._iteration,
            max_iterations=self.max_iterations,
        )
        data = self._llm_query_json(self._sys_prompt, prompt)
        result = ReflectionResult.from_dict(data)

        # Track for next iteration
        self._previous_reflections.append(result.to_dict())
        self._previous_reflections = self._previous_reflections[-_MAX_REFLECTION_HISTORY:]
        self._previous_errors.extend(
            self._extract_error_signatures(execution_result)
        )
        self._previous_errors = self._previous_errors[-_MAX_ERROR_HISTORY:]

        return result

    @property
    def iterations_remaining(self) -> int:
        """Number of reflection iterations remaining."""
        return max(0, self.max_iterations - self._iteration)

    def reset(self) -> None:
        """Reset iteration counter and history for a new task."""
        self._iteration = 0
        self._previous_reflections.clear()
        self._previous_errors.clear()
