"""Skill Learning Agent — extracts reusable skills from task completions."""

from __future__ import annotations

import json

from BrainDock.base_agent import BaseAgent
from BrainDock.llm import LLMBackend
from BrainDock.preambles import build_system_prompt, DEV_OPS
from .models import Skill, SkillBank
from .prompts import SYSTEM_PROMPT, EXTRACT_SKILL_PROMPT, MATCH_SKILLS_PROMPT


class SkillLearningAgent(BaseAgent):
    """Agent that learns reusable skills from successful task executions.

    Usage:
        agent = SkillLearningAgent(llm=my_backend)
        skill = agent.extract_skill(task_desc, solution, outcome)
        matches = agent.match_skills(task_desc, skill_bank)
    """

    def __init__(self, llm: LLMBackend | None = None):
        super().__init__(llm=llm)
        self._sys_prompt = build_system_prompt(SYSTEM_PROMPT, DEV_OPS)

    def extract_skill(
        self,
        task_description: str,
        solution_code: str,
        outcome: str,
    ) -> Skill:
        """Extract a reusable skill from a completed task."""
        prompt = EXTRACT_SKILL_PROMPT.format(
            task_description=task_description,
            solution_code=solution_code,
            outcome=outcome,
        )
        data = self._llm_query_json(self._sys_prompt, prompt)
        skill = Skill.from_dict(data)
        skill.source_task = task_description[:200]
        return skill

    def match_skills(
        self,
        task_description: str,
        bank: SkillBank,
    ) -> list[dict]:
        """Find relevant skills for a task from the skill bank.

        Returns a list of dicts with skill_id, relevance, and application.
        """
        if not bank.skills:
            return []

        skills_json = json.dumps(
            [{"id": s.id, "name": s.name, "description": s.description, "tags": s.tags}
             for s in bank.skills],
            indent=2,
        )

        prompt = MATCH_SKILLS_PROMPT.format(
            task_description=task_description,
            skills_json=skills_json,
        )
        data = self._llm_query_json(self._sys_prompt, prompt)
        return data.get("matches", [])
