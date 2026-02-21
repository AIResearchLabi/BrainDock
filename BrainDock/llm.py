"""Shared LLM backend infrastructure for BrainDock.

Default backend: `claude -p` via subprocess (no API key needed).
Supports injecting a custom callable for testing or alternative providers.
"""

from __future__ import annotations

import subprocess
import json
import os
import time as _time
from typing import Any, Callable, Protocol


class LLMBackend(Protocol):
    """Protocol for LLM backends."""
    def query(self, system_prompt: str, user_prompt: str) -> str: ...


class ClaudeCLIBackend:
    """Uses `claude -p` subprocess as the LLM backend."""

    def __init__(self, model: str | None = None, timeout: int = 900):
        self.model = model
        self.timeout = timeout

    def query(self, system_prompt: str, user_prompt: str) -> str:
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        cmd = ["claude", "-p", "--dangerously-skip-permissions"]
        if self.model:
            cmd.extend(["--model", self.model])

        env = os.environ.copy()
        # Allow running from within Claude Code sessions
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            env=env,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"claude -p failed (exit {result.returncode}): {result.stderr}"
            )

        return result.stdout.strip()


class CallableBackend:
    """Wraps a simple callable as an LLM backend."""

    def __init__(self, fn: Callable[[str, str], str]):
        self._fn = fn

    def query(self, system_prompt: str, user_prompt: str) -> str:
        return self._fn(system_prompt, user_prompt)


class LoggingBackend:
    """Wraps any LLMBackend, capturing every call for logging/dashboard.

    Each call records: agent label, prompts, response, duration, and
    estimated token count. Calls an optional ``on_log`` callback with
    the log entry dict.
    """

    def __init__(self, inner: LLMBackend, on_log: Callable[[dict], Any] | None = None):
        self._inner = inner
        self._on_log = on_log
        self._agent_label: str = "unknown"

    def set_agent_label(self, label: str) -> None:
        """Set the agent label for the next call(s)."""
        self._agent_label = label

    def query(self, system_prompt: str, user_prompt: str) -> str:
        start = _time.time()
        response = self._inner.query(system_prompt, user_prompt)
        duration = _time.time() - start

        # Rough token estimate: ~4 chars per token for English text
        prompt_chars = len(system_prompt) + len(user_prompt)
        response_chars = len(response)
        est_input_tokens = prompt_chars // 4
        est_output_tokens = response_chars // 4

        entry: dict[str, Any] = {
            "ts": start,
            "agent": self._agent_label,
            "duration": round(duration, 2),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response": response,
            "est_input_tokens": est_input_tokens,
            "est_output_tokens": est_output_tokens,
        }

        if self._on_log:
            self._on_log(entry)

        return response


def extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling various wrapping formats.

    Handles: plain JSON, markdown code fences, JSON embedded in prose,
    and empty/malformed responses.
    """
    text = text.strip()

    if not text:
        raise ValueError("LLM returned empty response")

    # Try 1: direct parse (ideal case)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try 2: strip markdown code fences
    if "```" in text:
        # Find content between first ``` and last ```
        parts = text.split("```")
        for part in parts[1:]:  # skip text before first fence
            candidate = part.strip()
            # Remove language tag (e.g., "json\n")
            if candidate and candidate.split("\n", 1)[0].strip() in ("json", "JSON", ""):
                candidate = candidate.split("\n", 1)[-1].strip() if "\n" in candidate else ""
            if candidate:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue

    # Try 3: find first { and last } — JSON embedded in prose
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not extract valid JSON from LLM response. "
        f"Response starts with: {text[:200]!r}"
    )
