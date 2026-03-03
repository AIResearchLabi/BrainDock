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
        use_llm: bool = False,
    ) -> list[dict]:
        """Find relevant skills for a task from the skill bank.

        Uses deterministic keyword matching by default (no LLM call).
        Set use_llm=True to use LLM-based matching for higher accuracy.

        Returns a list of dicts with skill_id, relevance, and application.
        """
        if not bank.skills:
            return []

        if use_llm:
            return self._match_skills_llm(task_description, bank)

        return self._match_skills_heuristic(task_description, bank)

    def _match_skills_heuristic(
        self,
        task_description: str,
        bank: SkillBank,
    ) -> list[dict]:
        """Keyword-based skill matching without LLM call.

        Scores skills by overlap between task keywords and skill
        name/tags/description/category. Returns top matches.
        """
        import re as _re

        # Extract keywords from task (3+ char words, lowered)
        task_words = set(
            w for w in _re.findall(r"[a-z][a-z0-9_]+", task_description.lower())
            if len(w) >= 3
        )

        scored: list[tuple[float, Skill]] = []
        for skill in bank.skills:
            # Build searchable text from skill metadata
            skill_text = " ".join([
                skill.name.lower(),
                skill.description.lower(),
                skill.category.lower(),
                " ".join(t.lower() for t in skill.tags),
            ])
            skill_words = set(
                w for w in _re.findall(r"[a-z][a-z0-9_]+", skill_text)
                if len(w) >= 3
            )

            # Score = overlap count, weighted by reliability
            overlap = len(task_words & skill_words)
            if overlap > 0:
                score = overlap * skill.reliability_score
                scored.append((score, skill))

        # Sort by score descending, take top 5
        scored.sort(key=lambda x: x[0], reverse=True)
        matches = []
        for score, skill in scored[:5]:
            if score >= 3:
                relevance = "high"
            elif score >= 1.5:
                relevance = "medium"
            else:
                relevance = "low"
            matches.append({
                "skill_id": skill.id,
                "relevance": relevance,
                "application": f"Apply {skill.name} pattern",
            })

        return matches

    def _match_skills_llm(
        self,
        task_description: str,
        bank: SkillBank,
    ) -> list[dict]:
        """LLM-based skill matching (original implementation)."""
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
