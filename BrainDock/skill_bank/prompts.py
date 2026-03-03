"""Prompt templates for the Skill Learning Agent."""

from BrainDock.prompts_common import JSON_FORMAT_INSTRUCTION

SYSTEM_PROMPT = f"""\
You are a software engineering expert that extracts reusable patterns and skills \
from successful task completions. Your job is to identify the core transferable \
technique so it can be applied to future tasks.

{JSON_FORMAT_INSTRUCTION}"""


EXTRACT_SKILL_PROMPT = """\
A task was completed successfully. Extract the reusable skill/pattern from it.

Task description:
---
{task_description}
---

Solution code / approach:
---
{solution_code}
---

Outcome:
---
{outcome}
---

Extract the core reusable skill. Focus on the transferable technique, not the \
specific implementation details.

Respond in this exact JSON format:
{{
  "id": "skill_<short_snake_case_name>",
  "name": "Human-readable skill name",
  "description": "What this skill does and when to use it (2-3 sentences)",
  "tags": ["tag1", "tag2", "tag3"],
  "category": "domain/subdomain (e.g. code/scaffolding, web/scraping, data/parsing, integration/subprocess, workflow/retry, human/prompting)",
  "pattern": "The abstract pattern/algorithm (pseudo-code or description)",
  "example_code": "A minimal code example demonstrating the pattern"
}}"""


MATCH_SKILLS_PROMPT = """\
Given a task description and a list of available skills, identify which skills \
are relevant and how they should be applied.

Task description:
---
{task_description}
---

Available skills:
---
{skills_json}
---

Return the relevant skill IDs and how each should be applied.

Respond in this exact JSON format:
{{
  "matches": [
    {{
      "skill_id": "skill_xxx",
      "relevance": "high|medium|low",
      "application": "How to apply this skill to the current task"
    }}
  ]
}}"""
