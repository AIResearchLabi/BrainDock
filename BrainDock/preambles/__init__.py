"""User-editable preambles injected into agent system prompts.

Preambles provide domain context across three areas:
  - dev_ops.md    : Technical standards, architecture, code practices
  - exec_ops.md   : Execution philosophy, quality gates, debugging
  - business_ops.md : Product vision, audience, market, strategy

Edit the .md files in this directory to customize agent behaviour.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Sequence

_DIR = os.path.dirname(os.path.abspath(__file__))

# Canonical preamble names
DEV_OPS = "dev_ops"
EXEC_OPS = "exec_ops"
BUSINESS_OPS = "business_ops"


def _read_preamble(name: str) -> str:
    """Read a single preamble file. Returns empty string if missing/empty."""
    path = os.path.join(_DIR, f"{name}.md")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read().strip()
        return content
    except OSError:
        return ""


@lru_cache(maxsize=8)
def _cached_preamble(name: str, mtime: float) -> str:
    """Cache preamble content keyed by name + mtime for auto-reload on edit."""
    return _read_preamble(name)


def get_preamble(name: str) -> str:
    """Get a single preamble by name, auto-reloading if file was edited."""
    path = os.path.join(_DIR, f"{name}.md")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return ""
    return _cached_preamble(name, mtime)


def load_preambles(*names: str) -> str:
    """Load and concatenate multiple preambles into a single context block.

    Empty preambles are silently skipped.

    Example::

        context = load_preambles(DEV_OPS, EXEC_OPS)
    """
    parts: list[str] = []
    for name in names:
        text = get_preamble(name)
        if text:
            parts.append(text)
    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"


def build_system_prompt(base_prompt: str, *preamble_names: str) -> str:
    """Prepend preamble context to an agent's base system prompt.

    If no preambles have content, returns the base prompt unchanged.

    Example::

        prompt = build_system_prompt(SYSTEM_PROMPT, DEV_OPS, EXEC_OPS)
    """
    context = load_preambles(*preamble_names)
    if not context:
        return base_prompt
    return (
        "# Context & Guidelines (user-provided)\n\n"
        + context
        + "# Agent Instructions\n\n"
        + base_prompt
    )
