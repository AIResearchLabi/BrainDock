"""LLM backend for the Spec Agent.

Re-exports from BrainDock.llm for backward compatibility.
"""

from BrainDock.llm import (
    LLMBackend,
    ClaudeCLIBackend,
    CallableBackend,
    extract_json,
)

__all__ = ["LLMBackend", "ClaudeCLIBackend", "CallableBackend", "extract_json"]
