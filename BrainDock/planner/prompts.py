"""Prompt templates for the Planner Agent."""

SYSTEM_PROMPT = """\
You are an expert implementation planner. Given a task from a project's task \
graph, you produce a detailed step-by-step action plan. Your plans are concrete, \
actionable, and include confidence metrics.

IMPORTANT: Always respond in valid JSON format as specified in each prompt. \
Do not include any text outside the JSON object.

IMPORTANT: In step descriptions and actions, use ONLY ASCII characters. \
Do NOT use Unicode arrows (→), bullets (•), em-dashes (—), or smart quotes. \
Use -> instead of →, - instead of •, -- instead of —."""


PLAN_TASK_PROMPT = """\
Create a detailed action plan for this task.

Task:
---
{task_json}
---

Project context:
---
{context}
---

{skills_section}

When files already exist in the project, prefer edit_file over write_file to \
preserve existing code. Reference specific existing files by their paths.

CRITICAL — Test step rules:
- For "test" steps, ONLY test the module(s) affected by the current task.
- NEVER plan a "run full test suite" or "run all tests" step.
- BAD: "Run python -m unittest discover -s tests -v to verify no regressions"
- GOOD: "Run python -m unittest tests.outreach.test_whatsapp -v to verify QR login tests"
- The full test suite may have hundreds of tests and will timeout or fail due to \
unrelated import errors. Always scope tests to the specific module being changed.

CRITICAL — Path rules:
- In step descriptions, use RELATIVE paths from the project root, not absolute paths.
- BAD: "Edit /home/user/project/output/idea-market-survey/project/src/agent.py"
- GOOD: "Edit BrainDock/outreach/agent.py"
- The executor runs commands from the project directory as working directory.

Create a step-by-step plan. Each step should be a concrete, executable action.
Rate your confidence and estimate the uncertainty (entropy).

Respond in this exact JSON format:
{{
  "task_id": "{task_id}",
  "task_title": "{task_title}",
  "steps": [
    {{
      "id": "s1",
      "action": "Short action name",
      "description": "Detailed description of what to do",
      "tool": "write_file|run_command|edit_file|create_dir|test|review",
      "expected_output": "What success looks like"
    }}
  ],
  "metrics": {{
    "confidence": 0.85,
    "entropy": 0.15,
    "estimated_steps": 5,
    "complexity": "medium"
  }},
  "relevant_skills": ["skill_id_1"],
  "assumptions": ["Assumption about the environment or codebase"]
}}

Confidence: 0.0 (no idea) to 1.0 (completely certain).
Entropy: 0.0 (no uncertainty) to 1.0 (maximum uncertainty).
A plan with entropy > 0.7 should trigger a debate round."""
