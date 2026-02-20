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

Analyze the root cause(s) and propose modifications to the plan.

Respond in this exact JSON format:
{{
  "root_causes": [
    {{
      "description": "What went wrong",
      "category": "missing_dependency|wrong_approach|env_issue|logic_error|config_error",
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
