"""Base agent class for all BrainDock agents.

Provides shared _llm_query_json() helper with retry logic and response caching.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time as _time

from .llm import LLMBackend, ClaudeCLIBackend, extract_json, extract_json_or_list

MAX_LLM_RETRIES = 3

# Module-level response cache: hash(system+user) -> raw LLM response string.
# Avoids duplicate LLM calls for identical prompts (e.g. retries, resume).
_RESPONSE_CACHE: dict[str, str] = {}
_RESPONSE_CACHE_MAX = 200


def _cache_key(system_prompt: str, user_prompt: str) -> str:
    """Compute a stable cache key from prompt pair."""
    h = hashlib.sha256()
    h.update(system_prompt.encode("utf-8", errors="replace"))
    h.update(b"\x00")
    h.update(user_prompt.encode("utf-8", errors="replace"))
    return h.hexdigest()


def clear_response_cache() -> None:
    """Clear the LLM response cache (useful in tests)."""
    _RESPONSE_CACHE.clear()


class BaseAgent:
    """Base class for BrainDock agents with shared LLM query helpers."""

    # Set to False to disable response caching per-instance
    enable_cache: bool = True

    def __init__(self, llm: LLMBackend | None = None):
        self.llm = llm or ClaudeCLIBackend()
        # Only enable cache for production backends (ClaudeCLIBackend or
        # LoggingBackend wrapping ClaudeCLIBackend). Disable for all test
        # backends to avoid cross-test leaks.
        from .llm import LoggingBackend
        backend = self.llm
        if isinstance(backend, LoggingBackend):
            backend = backend._inner
        if not isinstance(backend, ClaudeCLIBackend):
            self.enable_cache = False

    def _llm_query_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Query the LLM and parse JSON response, with retry on failure.

        Uses a hash-based response cache to avoid duplicate LLM calls for
        identical prompts. Retries on JSON parse errors and transient
        LLM/subprocess failures (RuntimeError, TimeoutExpired, OSError).
        On JSON parse failure, appends a stronger JSON enforcement reminder.
        """
        # Check cache first
        key = _cache_key(system_prompt, user_prompt)
        if self.enable_cache and key in _RESPONSE_CACHE:
            try:
                return extract_json(_RESPONSE_CACHE[key])
            except (ValueError, json.JSONDecodeError):
                del _RESPONSE_CACHE[key]  # stale/bad cache entry

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
                _time.sleep(min(2 ** attempt, 8))  # Exponential backoff (1s, 2s, 4s, max 8s)
                continue
            try:
                result = extract_json(response)
                # Cache successful response
                if self.enable_cache:
                    if len(_RESPONSE_CACHE) >= _RESPONSE_CACHE_MAX:
                        # Evict oldest entry (FIFO)
                        oldest = next(iter(_RESPONSE_CACHE))
                        del _RESPONSE_CACHE[oldest]
                    _RESPONSE_CACHE[key] = response
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
        a single dict, it is wrapped in a list for convenience. Uses response
        cache to avoid duplicate LLM calls.
        """
        # Check cache first
        key = _cache_key(system_prompt, user_prompt)
        if self.enable_cache and key in _RESPONSE_CACHE:
            try:
                result = extract_json_or_list(_RESPONSE_CACHE[key])
                if isinstance(result, dict):
                    return [result]
                return result
            except (ValueError, json.JSONDecodeError):
                del _RESPONSE_CACHE[key]

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
                _time.sleep(min(2 ** attempt, 8))  # Exponential backoff
                continue
            try:
                result = extract_json_or_list(response)
                # Cache successful response
                if self.enable_cache:
                    if len(_RESPONSE_CACHE) >= _RESPONSE_CACHE_MAX:
                        oldest = next(iter(_RESPONSE_CACHE))
                        del _RESPONSE_CACHE[oldest]
                    _RESPONSE_CACHE[key] = response
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
