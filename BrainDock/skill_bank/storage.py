"""JSON persistence for the Skill Bank."""

from __future__ import annotations

import json
from pathlib import Path

from .models import SkillBank

DEFAULT_SKILL_FILE = "output/skill_bank/skills.json"
SEED_SKILL_FILE = str(Path(__file__).resolve().parent.parent.parent / "data" / "seed_skills.json")


def load_skill_bank(path: str = DEFAULT_SKILL_FILE) -> SkillBank:
    """Load skill bank from JSON file. Returns empty bank if file doesn't exist."""
    p = Path(path)
    if not p.exists():
        return SkillBank()
    data = json.loads(p.read_text())
    return SkillBank.from_dict(data)


def load_with_seeds(path: str = DEFAULT_SKILL_FILE, seed_path: str = SEED_SKILL_FILE) -> SkillBank:
    """Load seed bank as baseline, then merge runtime-learned skills on top.

    Runtime skills override seeds with the same ID.
    """
    # Start with seeds
    seed_p = Path(seed_path)
    if seed_p.exists():
        seed_data = json.loads(seed_p.read_text())
        bank = SkillBank.from_dict(seed_data)
    else:
        bank = SkillBank()

    # Merge runtime skills on top (they override seeds)
    runtime_p = Path(path)
    if runtime_p.exists():
        runtime_data = json.loads(runtime_p.read_text())
        runtime_bank = SkillBank.from_dict(runtime_data)
        for skill in runtime_bank.skills:
            bank.add(skill)

    return bank


def save_skill_bank(bank: SkillBank, path: str = DEFAULT_SKILL_FILE) -> str:
    """Save skill bank to JSON file. Returns the path written to."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bank.to_dict(), indent=2))
    return str(p)
