"""Task Graph Agent — decomposes specs into task dependency graphs."""

from __future__ import annotations

import json

from BrainDock.base_agent import BaseAgent
from BrainDock.llm import LLMBackend
from BrainDock.preambles import build_system_prompt, DEV_OPS, BUSINESS_OPS
from .models import TaskGraph
from .prompts import SYSTEM_PROMPT, DECOMPOSE_PROMPT


class TaskGraphAgent(BaseAgent):
    """Agent that decomposes a project spec into a task graph.

    Usage:
        agent = TaskGraphAgent(llm=my_backend)
        graph = agent.decompose(spec_dict)
    """

    def __init__(self, llm: LLMBackend | None = None):
        super().__init__(llm=llm)
        self._sys_prompt = build_system_prompt(SYSTEM_PROMPT, DEV_OPS, BUSINESS_OPS)

    def decompose(self, spec: dict) -> TaskGraph:
        """Decompose a project specification into a task graph.

        Args:
            spec: Project specification as a dict (e.g. from ProjectSpec.to_dict()).

        Returns:
            A TaskGraph with ordered, dependency-linked tasks.
        """
        prompt = DECOMPOSE_PROMPT.format(spec_json=json.dumps(spec, indent=2))
        data = self._llm_query_json(self._sys_prompt, prompt)
        return TaskGraph.from_dict(data)
