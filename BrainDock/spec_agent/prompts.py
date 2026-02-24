"""Prompt templates for the Spec Agent."""

SYSTEM_PROMPT = """\
You are an expert software architect and product analyst. Given a problem \
statement, you analyze requirements, make routine technical decisions \
autonomously, and only ask the user about critical/ambiguous choices.

IMPORTANT: Always respond in valid JSON format as specified in each prompt. \
Do not include any text outside the JSON object."""


ANALYZE_PROMPT = """\
Analyze this problem statement and produce a structured understanding.

Problem:
---
{problem_statement}
---

For routine technical decisions (language idioms, standard patterns, obvious \
architecture choices), decide autonomously and list them under "self_decided".

Only ask the user about genuinely ambiguous or critical decisions — things \
where multiple valid approaches exist and the choice significantly impacts \
the project.

Respond in this exact JSON format:
{{
  "understanding": "Your comprehensive understanding of the problem",
  "self_decided": [
    {{
      "id": "d1",
      "topic": "What was decided",
      "decision": "The decision made and why"
    }}
  ],
  "user_questions": [
    {{
      "id": "q1",
      "question": "The question for the user",
      "why": "Why this question matters",
      "options": ["Option A", "Option B"]
    }}
  ]
}}

If no user questions are needed, return an empty "user_questions" array."""


REFINE_PROMPT = """\
Continue refining your understanding based on the conversation so far.

Problem:
---
{problem_statement}
---

Conversation:
---
{conversation_history}
---

Review the user's answers and either:
1. Ask follow-up questions if critical ambiguity remains
2. Signal readiness to generate the spec if you have enough information

Respond in this exact JSON format:
{{
  "understanding": "Updated comprehensive understanding",
  "ready": true,
  "self_decided": [
    {{
      "id": "d2",
      "topic": "New decision",
      "decision": "What was decided"
    }}
  ],
  "user_questions": [
    {{
      "id": "q2",
      "question": "Follow-up question",
      "why": "Why this matters",
      "options": ["Option A", "Option B"]
    }}
  ]
}}

Set "ready" to true when you have enough information to generate a complete \
spec. If ready is true, user_questions can be empty."""


GENERATE_SPEC_PROMPT = """\
Generate a complete project specification based on the analysis.

Problem:
---
{problem_statement}
---

Conversation:
---
{conversation_history}
---

Produce a comprehensive project specification in this exact JSON format:
{{
  "title": "Project title",
  "summary": "Brief project summary",
  "problem_statement": "Refined problem statement",
  "goals": ["Goal 1", "Goal 2"],
  "target_users": "Who will use this",
  "user_stories": [
    {{"role": "user", "action": "do something", "benefit": "get value"}}
  ],
  "functional_requirements": [
    {{
      "feature": "Feature name",
      "description": "What it does",
      "acceptance_criteria": ["Criterion 1"],
      "priority": "must-have"
    }}
  ],
  "non_functional_requirements": [
    {{
      "category": "performance",
      "requirement": "Response time < 200ms",
      "metric": "p95 latency"
    }}
  ],
  "tech_stack": {{
    "language": "Python",
    "framework": "None",
    "database": "None"
  }},
  "architecture_overview": "High-level architecture description",
  "data_models": [
    {{"name": "Model", "fields": {{"field": "type"}}, "relationships": []}}
  ],
  "api_endpoints": [
    {{"method": "GET", "path": "/api/resource", "description": "Get resource"}}
  ],
  "milestones": [
    {{"name": "v1", "description": "Initial release", "deliverables": ["Feature 1"]}}
  ],
  "constraints": ["Constraint 1"],
  "assumptions": ["Assumption 1"],
  "open_questions": ["Question that remains"]
}}

Be thorough but practical. Focus on actionable requirements."""
