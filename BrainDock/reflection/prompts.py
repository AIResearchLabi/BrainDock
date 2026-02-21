"""Prompt templates for the Reflection Agent."""

SYSTEM_PROMPT = """\
You are an expert debugger and root-cause analyst. When given a failed execution, \
you identify what went wrong, why, and how to fix the plan to succeed on retry. \
You are systematic and thorough in your analysis.

IMPORTANT: Always respond in valid JSON format as specified in each prompt. \
Do not include any text outside the JSON object."""


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

Analyze the root cause(s) and propose modifications to the plan.

Root cause categories:
- missing_dependency — a package or library is not installed
- wrong_approach — fundamental design or logic problem
- env_issue — environment or configuration problem
- logic_error — bug in the generated code
- config_error — misconfiguration in files or settings
- auth_required — requires authentication tokens, API keys, or login
- credentials_needed — requires secrets, passwords, or access credentials
- external_setup — requires external service setup (database, cloud, DNS, etc.)
- physical_action — requires a physical or manual action by the user

When the root cause requires human action (auth_required, credentials_needed, \
external_setup, or physical_action), set "needs_human" to true, "should_retry" \
to false, and provide a clear "escalation_reason" explaining what the human \
needs to do.

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

If the failure is unrecoverable (e.g., fundamental approach is wrong), set \
should_retry to false and explain why in the summary."""
