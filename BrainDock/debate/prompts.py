"""Prompt templates for the Debate Agent."""

SYSTEM_PROMPT = """\
You are a panel of expert software architects debating the best approach \
to implement a task. You consider multiple perspectives, identify trade-offs, \
and converge on the strongest approach through structured critique.

IMPORTANT: Always respond in valid JSON format as specified in each prompt. \
Do not include any text outside the JSON object."""


PROPOSE_PROMPT = """\
A plan has high uncertainty. Generate alternative approaches from different \
engineering perspectives.

Original plan:
---
{plan_json}
---

Context:
---
{context}
---

Generate 2-3 distinct approaches from different perspectives (e.g., \
"pragmatist", "perfectionist", "minimalist").

Respond in this exact JSON format:
{{
  "proposals": [
    {{
      "perspective": "Pragmatist",
      "approach": "Detailed description of this approach",
      "strengths": ["Strength 1", "Strength 2"],
      "weaknesses": ["Weakness 1"],
      "confidence": 0.75
    }}
  ]
}}"""


CRITIQUE_PROMPT = """\
Critique these proposed approaches and identify the best path forward.

Proposals:
---
{proposals_json}
---

Original plan context:
---
{context}
---

Previous critiques (if any):
---
{previous_critiques}
---

Round {round} of {max_rounds}.

Critique each proposal and suggest improvements. If one approach is clearly \
superior, indicate convergence.

Respond in this exact JSON format:
{{
  "critiques": [
    {{
      "target_perspective": "Pragmatist",
      "issues": ["Issue 1"],
      "suggestions": ["Suggestion 1"]
    }}
  ],
  "converged": false,
  "winning_approach": "",
  "synthesis": "Summary of the current state of debate"
}}

Set converged to true when a clear winner emerges."""


SYNTHESIZE_PROMPT = """\
Synthesize the debate into a final improved plan.

Proposals:
---
{proposals_json}
---

Critiques:
---
{critiques_json}
---

Winning approach: {winning_approach}

Original plan:
---
{plan_json}
---

Create a final improved plan that incorporates the best insights from the debate.

Respond in this exact JSON format:
{{
  "improved_plan": {{
    "task_id": "...",
    "task_title": "...",
    "steps": [
      {{
        "id": "s1",
        "action": "Action name",
        "description": "Detailed description",
        "tool": "write_file|run_command|edit_file",
        "expected_output": "What to expect"
      }}
    ],
    "metrics": {{
      "confidence": 0.85,
      "entropy": 0.15,
      "estimated_steps": 5,
      "complexity": "medium"
    }},
    "relevant_skills": [],
    "assumptions": []
  }},
  "synthesis": "Final synthesis explaining the chosen approach"
}}"""
