"""Market Study Agent — competitive analysis for tagged tasks."""

from __future__ import annotations

import json

from BrainDock.base_agent import BaseAgent
from BrainDock.llm import LLMBackend
from BrainDock.preambles import build_system_prompt, BUSINESS_OPS
from .models import MarketStudyResult
from .prompts import SYSTEM_PROMPT, MARKET_STUDY_PROMPT


class MarketStudyAgent(BaseAgent):
    """Agent that performs market research for tasks needing competitive analysis.

    Usage:
        agent = MarketStudyAgent(llm=my_backend)
        result = agent.analyze(task_dict, context=project_context)
    """

    def __init__(self, llm: LLMBackend | None = None):
        super().__init__(llm=llm)
        self._sys_prompt = build_system_prompt(SYSTEM_PROMPT, BUSINESS_OPS)

    def analyze(self, task: dict, context: str = "") -> MarketStudyResult:
        """Run market study analysis for a task.

        Args:
            task: Task dictionary (from TaskNode.to_dict()).
            context: Project context string.

        Returns:
            MarketStudyResult with competitive analysis.
        """
        task_json = json.dumps(task, indent=2)
        task_id = task.get("id", "unknown")
        prompt = MARKET_STUDY_PROMPT.format(
            task_json=task_json,
            project_context=context,
            task_id=task_id,
        )
        result = self._llm_query_json(self._sys_prompt, prompt)
        return MarketStudyResult.from_dict(result)
