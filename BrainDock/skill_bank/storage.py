"""JSON persistence for the Skill Bank."""

from __future__ import annotations

import json
from pathlib import Path

from .models import SkillBank

DEFAULT_SKILL_FILE = "output/skill_bank/skills.json"


def load_skill_bank(path: str = DEFAULT_SKILL_FILE) -> SkillBank:
    """Load skill bank from JSON file. Returns empty bank if file doesn't exist."""
    p = Path(path)
    if not p.exists():
        return SkillBank()
    data = json.loads(p.read_text())
    return SkillBank.from_dict(data)


def save_skill_bank(bank: SkillBank, path: str = DEFAULT_SKILL_FILE) -> str:
    """Save skill bank to JSON file. Returns the path written to."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bank.to_dict(), indent=2))
    return str(p)
