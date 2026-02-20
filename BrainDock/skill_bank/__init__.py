"""Skill Bank — Reusable skill/pattern library (Mode 6).

Learns reusable skills from successful task executions and stores them
for future retrieval. Skills persist across runs via JSON storage.

Usage:
    from BrainDock.skill_bank import SkillLearningAgent, Skill, SkillBank

    agent = SkillLearningAgent(llm=my_backend)
    skill = agent.extract_skill(task_description, solution_code, outcome)
    bank = SkillBank.load()
    bank.add(skill)
    bank.save()
"""

from .models import Skill, SkillBank
from .agent import SkillLearningAgent
from .storage import load_skill_bank, save_skill_bank

__all__ = [
    "Skill",
    "SkillBank",
    "SkillLearningAgent",
    "load_skill_bank",
    "save_skill_bank",
]
