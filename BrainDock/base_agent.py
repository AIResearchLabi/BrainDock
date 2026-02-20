"""Base agent class for all BrainDock agents.

Provides shared _llm_query_json() helper with retry logic.
"""

from __future__ import annotations

import json
import sys

from .llm import LLMBackend, ClaudeCLIBackend, extract_json

MAX_LLM_RETRIES = 2


class BaseAgent:
    """Base class for BrainDock agents with shared LLM query helpers."""

    def __init__(self, llm: LLMBackend | None = None):
        self.llm = llm or ClaudeCLIBackend()

    def _llm_query_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Query the LLM and parse JSON response, with retry on parse failure."""
        last_error = None
        for attempt in range(MAX_LLM_RETRIES):
            response = self.llm.query(system_prompt, user_prompt)
            try:
                return extract_json(response)
            except (ValueError, json.JSONDecodeError) as e:
                last_error = e
                print(
                    f"  [Retry {attempt + 1}/{MAX_LLM_RETRIES}] "
                    f"LLM response was not valid JSON, retrying...",
                    file=sys.stderr,
                )
        raise RuntimeError(
            f"LLM failed to return valid JSON after {MAX_LLM_RETRIES} attempts: {last_error}"
        )
