"""Prompt templates for the Market Study Agent."""

from BrainDock.prompts_common import JSON_FORMAT_INSTRUCTION

SYSTEM_PROMPT = f"""\
You are a market research analyst specializing in software products and \
technology. You analyze competitive landscapes, identify target audiences, \
and provide strategic recommendations for product positioning. Your analysis \
is data-driven, actionable, and focused on practical implementation guidance.

{JSON_FORMAT_INSTRUCTION}"""


MARKET_STUDY_PROMPT = """\
Analyze the market context for the following task in a software project.

Task:
---
{task_json}
---

Project context:
---
{project_context}
---

Provide a market study covering:
1. Key competitors or existing solutions in this space
2. Target audience for this feature/product
3. Recommended positioning strategy
4. Actionable recommendations for differentiation
5. Market risks to be aware of

Respond in this exact JSON format:
{{
  "task_id": "{task_id}",
  "competitors": ["Competitor 1", "Competitor 2"],
  "target_audience": "Description of target users",
  "positioning": "Recommended positioning strategy",
  "recommendations": [
    "Specific actionable recommendation 1",
    "Specific actionable recommendation 2"
  ],
  "risks": [
    "Market risk 1",
    "Market risk 2"
  ]
}}"""
