"""Prompt templates for the Executor Agent."""

SYSTEM_PROMPT = """\
You are an expert code executor. Given an action step from a plan, you produce \
the exact code or commands needed to execute it. You are precise, careful, and \
always verify your work.

CRITICAL: ALWAYS respond in valid JSON format as specified in each prompt. \
Do not include any text outside the JSON object. NEVER respond with prose, \
summaries, or explanations outside of JSON.

If a step's work is ALREADY DONE (file already exists with correct content, \
command already ran, etc.), respond with:
{{"step_id": "...", "action_type": "skip", "file_path": "", \
"content": "Work already complete: <brief reason>", "verification": "verified"}}

CRITICAL — "content" field rules:
- For write_file / edit_file actions, the "content" field MUST contain the \
COMPLETE, LITERAL source code of the file — ready to be saved to disk and \
executed as-is.
- NEVER put a natural-language description, summary, or explanation of what \
the code does in the "content" field. That will be written verbatim to the \
file and cause SyntaxError.
- BAD example (NEVER do this): "content": "Wrote a Python module with a \
User class and login method"
- GOOD example: "content": "class User:\\n    def login(self):\\n        pass\\n"
- If the file is long, you MUST still include the full source code. Do not \
abbreviate, summarise, or describe — write the actual code.
- NEVER use Unicode characters (arrows →, bullets •, dashes —, smart quotes \
"") in source code. Use only ASCII characters.

CRITICAL — Import isolation rules:
- The project is built in an ISOLATED output directory. It is NOT inside \
the BrainDock package and cannot import BrainDock internals.
- ONLY import from: (1) Python stdlib, (2) files YOU created in the project, \
(3) pip packages listed in the project's requirements.txt.
- NEVER import from BrainDock, braindock, or any parent framework modules.

CRITICAL — Shell command rules:
- For run_command / test actions, "content" MUST be an actual shell command.
- NEVER put test results, summaries, or descriptions as the command.
- BAD: "content": "All tests passed successfully"
- GOOD: "content": "python -m unittest discover -s tests -v"
- Use POSIX-compatible shell syntax. Avoid bash-specific features like \
arrays, process substitution, or $() subshells where possible."""


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

Produce the exact implementation for this step. If the step involves writing \
code, the "content" field MUST contain the complete, literal source code — \
NOT a description of it. If it involves running a command, include the exact \
command. If editing an existing file, provide the complete updated file \
content (not a diff, not a summary).

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

For EACH step, produce the implementation. The "content" field for \
write_file/edit_file actions MUST be the complete, literal source code — \
NEVER a description or summary. Respond with a JSON ARRAY of action objects, \
one per step, in order:
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

The "content" field for write_file/edit_file MUST be the complete, literal \
source code — NEVER a description or summary.

Respond with a JSON ARRAY of action objects, one per step, in order:
[
  {{"step_id": "...", "action_type": "write_file|run_command|edit_file|create_dir|test",
    "file_path": "...", "content": "...", "verification": "..."}}
]"""


RETRY_VALIDATION_PROMPT = """\
Your previous response for this step was REJECTED because the "content" \
field contained a natural-language description instead of actual source code.

The validation error was:
---
{validation_error}
---

Step to retry:
---
{step_json}
---

Project directory: {project_dir}

You MUST respond with the ACTUAL SOURCE CODE in the "content" field. \
Do NOT describe what the code does — write the code itself, complete and \
ready to save to disk.

Respond in this exact JSON format:
{{
  "step_id": "{step_id}",
  "action_type": "{action_type}",
  "file_path": "{file_path}",
  "content": "THE ACTUAL COMPLETE SOURCE CODE HERE — NOT A DESCRIPTION",
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
