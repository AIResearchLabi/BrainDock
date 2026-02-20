"""Prompt templates for the Executor Agent."""

SYSTEM_PROMPT = """\
You are an expert code executor. Given an action step from a plan, you produce \
the exact code or commands needed to execute it. You are precise, careful, and \
always verify your work.

IMPORTANT: Always respond in valid JSON format as specified in each prompt. \
Do not include any text outside the JSON object."""


EXECUTE_STEP_PROMPT = """\
Execute this action step from the plan.

Step:
---
{step_json}
---

Project directory: {project_dir}

Previous step outcomes:
---
{previous_outcomes}
---

Produce the exact implementation for this step. If the step involves writing \
code, include the complete file content. If it involves running a command, \
include the exact command.

Respond in this exact JSON format:
{{
  "step_id": "{step_id}",
  "action_type": "write_file|run_command|edit_file|create_dir|test",
  "file_path": "relative/path/to/file (if applicable)",
  "content": "File content or command to run",
  "verification": "How to verify this step succeeded"
}}"""


VERIFY_STEP_PROMPT = """\
Verify the outcome of this execution step.

Step:
---
{step_json}
---

Execution output:
---
{execution_output}
---

Did this step succeed? Evaluate the output against the expected result.

Respond in this exact JSON format:
{{
  "success": true,
  "explanation": "Why this succeeded or failed",
  "issues": ["Any issues found (empty list if none)"]
}}"""
