"""Prompt templates for the Task Graph Agent."""

SYSTEM_PROMPT = """\
You are an expert project planner who decomposes software projects into \
well-structured task graphs. You identify dependencies, risks, and \
parallelization opportunities. Your task breakdowns are actionable, \
concrete, and follow the project's architecture.

IMPORTANT: Always respond in valid JSON format as specified in each prompt. \
Do not include any text outside the JSON object."""


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
- Identify risks for complex or uncertain tasks
- Mark estimated effort: "small" (< 1 hour), "medium" (1-4 hours), "large" (4+ hours)
- Use task IDs like "t1", "t2", etc.
- depends_on references other task IDs

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
