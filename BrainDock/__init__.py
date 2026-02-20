"""BrainDock — Autonomous Project Development Framework.

A modular system for autonomous project development with pluggable modules.

Modules:
    BrainDock.spec_agent   — Interactive project specification builder (Mode 1)
    BrainDock.task_graph    — Task decomposition and dependency graph (Mode 2)
    BrainDock.planner       — Action planning with entropy thresholds (Mode 3)
    BrainDock.controller    — Quality gate controller (Mode 4)
    BrainDock.executor      — Sandboxed task execution (Mode 5)
    BrainDock.skill_bank    — Reusable skill/pattern library (Mode 6)
    BrainDock.reflection    — Failure root-cause analysis (Mode 7)
    BrainDock.debate        — Multi-perspective design reasoning (Mode 8)
    BrainDock.orchestrator  — Pipeline orchestrator and CLI

Shared infrastructure:
    BrainDock.llm           — LLM backend protocol and implementations
    BrainDock.base_agent    — BaseAgent with _llm_query_json() helper
    BrainDock.session       — SessionMixin for JSON session persistence
"""

from .llm import LLMBackend, ClaudeCLIBackend, CallableBackend, extract_json
from .base_agent import BaseAgent
from .session import SessionMixin

__all__ = [
    "LLMBackend",
    "ClaudeCLIBackend",
    "CallableBackend",
    "extract_json",
    "BaseAgent",
    "SessionMixin",
]
