"""Base agent class for all BrainDock agents.

Provides shared _llm_query_json() helper with retry logic.
"""

from __future__ import annotations

import json
import subprocess
import sys

from .llm import LLMBackend, ClaudeCLIBackend, extract_json, extract_json_or_list

MAX_LLM_RETRIES = 3


class BaseAgent:
    """Base class for BrainDock agents with shared LLM query helpers."""

    def __init__(self, llm: LLMBackend | None = None):
        self.llm = llm or ClaudeCLIBackend()

    def _llm_query_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Query the LLM and parse JSON response, with retry on failure.

        Retries on JSON parse errors and transient LLM/subprocess failures
        (RuntimeError, TimeoutExpired, OSError). On JSON parse failure,
        appends a stronger JSON enforcement reminder to the prompt.
        """
        last_error: Exception | None = None
        current_prompt = user_prompt
        for attempt in range(MAX_LLM_RETRIES):
            try:
                response = self.llm.query(system_prompt, current_prompt)
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as e:
                last_error = e
                print(
                    f"  [Retry {attempt + 1}/{MAX_LLM_RETRIES}] "
                    f"LLM query failed ({type(e).__name__}), retrying...",
                    file=sys.stderr,
                )
                continue
            try:
                return extract_json(response)
            except (ValueError, json.JSONDecodeError) as e:
                last_error = e
                print(
                    f"  [Retry {attempt + 1}/{MAX_LLM_RETRIES}] "
                    f"LLM response was not valid JSON, retrying...",
                    file=sys.stderr,
                )
                # Strengthen JSON enforcement on retry
                current_prompt = (
                    user_prompt
                    + "\n\nCRITICAL REMINDER: Your previous response was NOT valid JSON. "
                    "You MUST respond with ONLY a valid JSON object. "
                    "No prose, no markdown, no explanations — ONLY the JSON object. "
                    "If the work is already done, still respond with the JSON format "
                    "using action_type 'skip'."
                )
        raise RuntimeError(
            f"LLM failed after {MAX_LLM_RETRIES} attempts: {last_error}"
        )

    def _llm_query_json_list(self, system_prompt: str, user_prompt: str) -> list:
        """Query the LLM and parse JSON array response, with retry on failure.

        Like _llm_query_json but expects a JSON array. If the LLM returns
        a single dict, it is wrapped in a list for convenience.
        """
        last_error: Exception | None = None
        current_prompt = user_prompt
        for attempt in range(MAX_LLM_RETRIES):
            try:
                response = self.llm.query(system_prompt, current_prompt)
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as e:
                last_error = e
                print(
                    f"  [Retry {attempt + 1}/{MAX_LLM_RETRIES}] "
                    f"LLM query failed ({type(e).__name__}), retrying...",
                    file=sys.stderr,
                )
                continue
            try:
                result = extract_json_or_list(response)
                if isinstance(result, dict):
                    return [result]
                return result
            except (ValueError, json.JSONDecodeError) as e:
                last_error = e
                print(
                    f"  [Retry {attempt + 1}/{MAX_LLM_RETRIES}] "
                    f"LLM response was not valid JSON, retrying...",
                    file=sys.stderr,
                )
                # Strengthen JSON enforcement on retry
                current_prompt = (
                    user_prompt
                    + "\n\nCRITICAL REMINDER: Your previous response was NOT valid JSON. "
                    "You MUST respond with ONLY a valid JSON array. "
                    "No prose, no markdown, no explanations — ONLY the JSON array. "
                    "If the work is already done, respond with: "
                    '[{"action_type": "skip", "step_id": "", "content": "already done", '
                    '"file_path": "", "verification": "work already complete"}]'
                )
        raise RuntimeError(
            f"LLM failed after {MAX_LLM_RETRIES} attempts: {last_error}"
        )
