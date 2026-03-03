"""Prompt templates for the Task Graph Agent."""

from BrainDock.prompts_common import JSON_FORMAT_INSTRUCTION

SYSTEM_PROMPT = f"""\
You are an expert project planner who decomposes software projects into \
well-structured task graphs. You identify dependencies, risks, and \
parallelization opportunities. Your task breakdowns are actionable, \
concrete, and follow the project's architecture.

{JSON_FORMAT_INSTRUCTION}"""


DECOMPOSE_PROMPT = """\
Given this project specification, decompose it into a task graph.

Project specification:
---
{spec_json}
---

Create a directed acyclic graph of implementation tasks. Each task should be:
- Atomic enough to be implemented in one session
- Concrete with clear deliverables
- Properly ordered by dependencies

Rules:
- First tasks should be project setup / scaffolding
- Group related work but keep tasks focused
- If multiple small tasks (<1 hour) are closely related with no inter-dependencies, \
merge them into a single medium task to reduce overhead
- Identify risks for complex or uncertain tasks
- Mark estimated effort: "small" (< 1 hour), "medium" (1-4 hours), "large" (4+ hours)
- Use task IDs like "t1", "t2", etc.
- depends_on references other task IDs
- Tag tasks that involve user-facing features, pricing, product positioning, or \
competitive differentiation with "needs_market_study" in the "tags" array. \
Other tasks should have an empty tags array.

Respond in this exact JSON format:
{{
  "project_title": "Project name",
  "tasks": [
    {{
      "id": "t1",
      "title": "Task title",
      "description": "What to implement, with specifics",
      "depends_on": [],
      "estimated_effort": "small",
      "tags": [],
      "risks": [
        {{
          "description": "What could go wrong",
          "severity": "low",
          "mitigation": "How to handle it"
        }}
      ]
    }}
  ]
}}"""
