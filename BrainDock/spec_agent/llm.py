"""LLM backend for the Spec Agent.

Default backend: `claude -p` via subprocess (no API key needed).
Supports injecting a custom callable for testing or alternative providers.
"""

from __future__ import annotations

import subprocess
import json
import os
from typing import Callable, Protocol


class LLMBackend(Protocol):
    """Protocol for LLM backends."""
    def query(self, system_prompt: str, user_prompt: str) -> str: ...


class ClaudeCLIBackend:
    """Uses `claude -p` subprocess as the LLM backend."""

    def __init__(self, model: str | None = None):
        self.model = model

    def query(self, system_prompt: str, user_prompt: str) -> str:
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        cmd = ["claude", "-p"]
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
            timeout=120,
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
