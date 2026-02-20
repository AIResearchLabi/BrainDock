"""Reflection Agent — analyzes failures and proposes plan modifications."""

from __future__ import annotations

import json

from BrainDock.base_agent import BaseAgent
from BrainDock.llm import LLMBackend
from .models import ReflectionResult
from .prompts import SYSTEM_PROMPT, REFLECT_PROMPT

MAX_ITERATIONS = 2


class ReflectionAgent(BaseAgent):
    """Agent that reflects on execution failures and proposes fixes.

    Limited to MAX_ITERATIONS to prevent infinite reflection loops.

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

        Raises:
            RuntimeError: If max iterations exceeded.
        """
        self._iteration += 1

        if self._iteration > self.max_iterations:
            return ReflectionResult(
                summary=f"Max reflection iterations ({self.max_iterations}) reached. Cannot fix automatically.",
                should_retry=False,
            )

        prompt = REFLECT_PROMPT.format(
            execution_json=json.dumps(execution_result, indent=2),
            plan_json=json.dumps(plan, indent=2),
            context=context or "(no additional context)",
            iteration=self._iteration,
            max_iterations=self.max_iterations,
        )
        data = self._llm_query_json(SYSTEM_PROMPT, prompt)
        return ReflectionResult.from_dict(data)

    @property
    def iterations_remaining(self) -> int:
        """Number of reflection iterations remaining."""
        return max(0, self.max_iterations - self._iteration)

    def reset(self) -> None:
        """Reset iteration counter for a new task."""
        self._iteration = 0
