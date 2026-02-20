"""Planner Agent — creates detailed action plans for tasks."""

from __future__ import annotations

import json

from BrainDock.base_agent import BaseAgent
from BrainDock.llm import LLMBackend
from .models import ActionPlan
from .prompts import SYSTEM_PROMPT, PLAN_TASK_PROMPT

# Plans with entropy above this threshold should trigger debate
ENTROPY_THRESHOLD = 0.7


class PlannerAgent(BaseAgent):
    """Agent that creates detailed action plans for task graph nodes.

    Usage:
        agent = PlannerAgent(llm=my_backend)
        plan = agent.plan_task(task_dict, context)
        if agent.needs_debate(plan):
            # Trigger debate mode
    """

    def __init__(
        self,
        llm: LLMBackend | None = None,
        entropy_threshold: float = ENTROPY_THRESHOLD,
    ):
        super().__init__(llm=llm)
        self.entropy_threshold = entropy_threshold

    def plan_task(
        self,
        task: dict,
        context: str = "",
        available_skills: list[dict] | None = None,
    ) -> ActionPlan:
        """Create a detailed action plan for a task.

        Args:
            task: Task node as a dict (from TaskNode.to_dict()).
            context: Additional project context.
            available_skills: List of skill dicts from the skill bank.

        Returns:
            An ActionPlan with steps, metrics, and assumptions.
        """
        skills_section = ""
        if available_skills:
            skills_section = (
                "Available skills from the skill bank:\n---\n"
                + json.dumps(available_skills, indent=2)
                + "\n---\n\nLeverage relevant skills in your plan."
            )

        prompt = PLAN_TASK_PROMPT.format(
            task_json=json.dumps(task, indent=2),
            context=context or "(no additional context)",
            skills_section=skills_section or "No skills available from the skill bank.",
            task_id=task.get("id", ""),
            task_title=task.get("title", ""),
        )
        data = self._llm_query_json(SYSTEM_PROMPT, prompt)
        return ActionPlan.from_dict(data)

    def needs_debate(self, plan: ActionPlan) -> bool:
        """Check if a plan's entropy exceeds the threshold, suggesting debate."""
        return plan.metrics.entropy > self.entropy_threshold
