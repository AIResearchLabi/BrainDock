"""Prompt templates for the Executor Agent."""

from BrainDock.prompts_common import (
    JSON_FORMAT_INSTRUCTION_STRICT,
    CONTENT_FIELD_RULE,
    IMPORT_ISOLATION_RULE,
    POSIX_SHELL_RULES,
    TEST_SCOPING_RULE,
    HUMAN_INTERACTION_RULE,
    SKIP_ACTION_HINT,
    PATH_RULES,
)

SYSTEM_PROMPT = f"""\
You are an expert code executor. Given an action step from a plan, you produce \
the exact code or commands needed to execute it.

{JSON_FORMAT_INSTRUCTION_STRICT}

{SKIP_ACTION_HINT}

{CONTENT_FIELD_RULE}

{IMPORT_ISOLATION_RULE}

{POSIX_SHELL_RULES}

{TEST_SCOPING_RULE}

{HUMAN_INTERACTION_RULE}"""


EXECUTE_STEP_PROMPT = """\
Execute this action step from the plan.

Step:
---
{step_json}
---

Project directory: {project_dir}

Current project files:
---
{project_file_context}
---

{edit_file_context}

Previous step outcomes:
---
{previous_outcomes}
---

Produce the exact implementation. For write_file/edit_file, content MUST be \
complete literal source code. For commands, include the exact shell command.

""" + PATH_RULES + """

Respond in this exact JSON format:
{{
  "step_id": "{step_id}",
  "action_type": "write_file|run_command|edit_file|create_dir|test",
  "file_path": "relative/path/to/file (if applicable)",
  "content": "File content or command to run",
  "verification": "How to verify this step succeeded"
}}"""


EXECUTE_BATCH_PROMPT = """\
Execute these action steps from the plan.

Steps:
---
{steps_json}
---

Project directory: {project_dir}

Current project files:
---
{project_file_context}
---

{edit_file_context}

For EACH step, produce the implementation. Content for write_file/edit_file \
MUST be complete literal source code. For test steps, only run module-scoped \
tests. For human interaction tasks, write detection/escalation CODE with mocks.

Respond with a JSON ARRAY of action objects, one per step, in order:
[
  {{"step_id": "...", "action_type": "write_file|run_command|edit_file|create_dir|test",
    "file_path": "...", "content": "...", "verification": "..."}}
]"""


EXECUTE_CONTINUATION_PROMPT = """\
Continue executing the plan. Here is what was done so far:

Session transcript:
---
{transcript}
---

Next steps to execute:
---
{steps_json}
---

Project directory: {project_dir}

{edit_file_context}

Content for write_file/edit_file MUST be complete literal source code. \
For test steps, only run module-scoped tests. For human interaction tasks, \
write detection/escalation CODE with mocks.

Respond with a JSON ARRAY of action objects, one per step, in order:
[
  {{"step_id": "...", "action_type": "write_file|run_command|edit_file|create_dir|test",
    "file_path": "...", "content": "...", "verification": "..."}}
]"""


RETRY_VALIDATION_PROMPT = """\
Your previous response for this step was REJECTED by the content validator.

The validation error was:
---
{validation_error}
---

Step to retry:
---
{step_json}
---

Project directory: {project_dir}

{existing_file_context}

WHAT WENT WRONG: You returned a description instead of actual source code.

RULES FOR THIS RETRY:
1. "content" MUST contain COMPLETE, LITERAL source code -- ready to execute.
2. Do NOT describe what the code does. Write the actual code.
3. If editing, provide the FULL updated file content (not a diff).
4. ASCII characters only in source code.

Respond in this exact JSON format:
{{
  "step_id": "{step_id}",
  "action_type": "{action_type}",
  "file_path": "{file_path}",
  "content": "THE ACTUAL COMPLETE SOURCE CODE HERE",
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
