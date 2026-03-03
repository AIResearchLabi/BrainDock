"""Prompt templates for the Reflection Agent."""

from BrainDock.prompts_common import JSON_FORMAT_INSTRUCTION

SYSTEM_PROMPT = f"""\
You are an expert debugger and root-cause analyst. When given a failed execution, \
you identify what went wrong, why, and how to fix the plan to succeed on retry.

{JSON_FORMAT_INSTRUCTION}"""


REFLECT_PROMPT = """\
An execution has failed. Analyze the failure and propose fixes.

Execution result:
---
{execution_json}
---

Original plan:
---
{plan_json}
---

Project context:
---
{context}
---

Iteration: {iteration} of {max_iterations}

Pay special attention to:
- Verification errors (runtime failures, import errors, missing deps)
- Existing files that may need editing rather than rewriting
- File path mismatches between plan and actual project

Root cause categories: missing_dependency, wrong_approach, env_issue, \
logic_error, config_error, auth_required, credentials_needed, \
external_setup, physical_action.

When root cause requires human action (auth_required, credentials_needed, \
external_setup, physical_action), set needs_human=true, should_retry=false, \
and provide escalation_reason.

Respond in this exact JSON format:
{{
  "root_causes": [
    {{
      "description": "What went wrong",
      "category": "missing_dependency|wrong_approach|env_issue|logic_error|config_error|auth_required|credentials_needed|external_setup|physical_action",
      "confidence": 0.85
    }}
  ],
  "modifications": [
    {{
      "action": "add_step|remove_step|modify_step|reorder",
      "target_step_id": "s2",
      "description": "What to change and why",
      "new_step": {{}}
    }}
  ],
  "summary": "Brief summary of what went wrong and what to change",
  "should_retry": true,
  "needs_human": false,
  "escalation_reason": "",
  "modified_plan": {{
    "task_id": "...",
    "task_title": "...",
    "steps": [],
    "metrics": {{}},
    "relevant_skills": [],
    "assumptions": []
  }}
}}

Set should_retry=false when: same error pattern recurred, env/shell issue \
code can't fix, human action required, or fundamental redesign needed.

If previous reflections are shown, do NOT repeat the same fix strategy."""
