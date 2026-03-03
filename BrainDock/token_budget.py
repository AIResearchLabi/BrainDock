"""Token Budget Tracking — thread-safe global and per-task token budget tracker."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, asdict
from typing import Callable


@dataclass
class TokenBudgetConfig:
    """Configuration for token budgets."""
    global_token_budget: int = 500_000
    per_task_token_budget: int = 80_000
    pre_step_reserve: int = 15_000
    warn_pct: float = 0.8
    pause_pct: float = 0.95

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TokenBudgetConfig:
        return cls(
            global_token_budget=data.get("global_token_budget", 500_000),
            per_task_token_budget=data.get("per_task_token_budget", 80_000),
            pre_step_reserve=data.get("pre_step_reserve", 15_000),
            warn_pct=data.get("warn_pct", 0.8),
            pause_pct=data.get("pause_pct", 0.95),
        )


class TokenBudgetTracker:
    """Thread-safe token budget tracker for global and per-task usage.

    Tracks token usage across all agents and tasks, fires threshold
    callbacks when warn/pause percentages are crossed.

    Args:
        config: Budget configuration.
        on_threshold: Optional callback fired when a threshold is crossed.
            Called with (level, scope, used, budget) where level is "warn"
            or "pause", scope is "global" or "task".
    """

    def __init__(
        self,
        config: TokenBudgetConfig | None = None,
        on_threshold: Callable[[str, str, int, int], None] | None = None,
    ):
        self._config = config or TokenBudgetConfig()
        self._on_threshold = on_threshold
        self._lock = threading.Lock()

        # Global counters
        self._global_input: int = 0
        self._global_output: int = 0

        # Per-task counters
        self._current_task_id: str = ""
        self._task_input: int = 0
        self._task_output: int = 0

        # Per-agent totals: {agent_name: {"input": N, "output": N}}
        self._agent_totals: dict[str, dict[str, int]] = {}

        # Threshold flags to avoid re-firing
        self._global_warn_fired: bool = False
        self._global_pause_fired: bool = False
        self._task_warn_fired: bool = False
        self._task_pause_fired: bool = False

    def record(self, agent: str, input_tokens: int, output_tokens: int) -> None:
        """Record token usage from an LLM call.

        Args:
            agent: Agent name (e.g. "planner", "executor").
            input_tokens: Estimated input tokens.
            output_tokens: Estimated output tokens.
        """
        with self._lock:
            self._global_input += input_tokens
            self._global_output += output_tokens
            self._task_input += input_tokens
            self._task_output += output_tokens

            if agent not in self._agent_totals:
                self._agent_totals[agent] = {"input": 0, "output": 0}
            self._agent_totals[agent]["input"] += input_tokens
            self._agent_totals[agent]["output"] += output_tokens

            # Check global thresholds — collect callbacks to fire AFTER
            # releasing the lock to avoid blocking other threads.
            _pending_callbacks: list[tuple[str, str, int, int]] = []
            global_used = self._global_input + self._global_output
            global_budget = self._config.global_token_budget
            if global_budget > 0:
                pct = global_used / global_budget
                if pct >= self._config.pause_pct and not self._global_pause_fired:
                    self._global_pause_fired = True
                    _pending_callbacks.append(("pause", "global", global_used, global_budget))
                elif pct >= self._config.warn_pct and not self._global_warn_fired:
                    self._global_warn_fired = True
                    _pending_callbacks.append(("warn", "global", global_used, global_budget))

            # Check task thresholds
            task_used = self._task_input + self._task_output
            task_budget = self._config.per_task_token_budget
            if task_budget > 0:
                pct = task_used / task_budget
                if pct >= self._config.pause_pct and not self._task_pause_fired:
                    self._task_pause_fired = True
                    _pending_callbacks.append(("pause", "task", task_used, task_budget))
                elif pct >= self._config.warn_pct and not self._task_warn_fired:
                    self._task_warn_fired = True
                    _pending_callbacks.append(("warn", "task", task_used, task_budget))

        # Fire threshold callbacks outside the lock to prevent deadlock
        if self._on_threshold:
            for level, scope, used, budget in _pending_callbacks:
                self._on_threshold(level, scope, used, budget)

    def start_task(self, task_id: str) -> None:
        """Start tracking a new task, resetting per-task counters.

        Args:
            task_id: Identifier for the new task.
        """
        with self._lock:
            self._current_task_id = task_id
            self._task_input = 0
            self._task_output = 0
            self._task_warn_fired = False
            self._task_pause_fired = False

    def check_pre_step(self, est_tokens: int = 0) -> tuple[bool, str]:
        """Check if there's enough budget remaining to start an LLM call.

        Args:
            est_tokens: Estimated tokens for the upcoming call.

        Returns:
            Tuple of (allowed, reason). If allowed is False, reason
            explains why the step should not proceed.
        """
        with self._lock:
            reserve = self._config.pre_step_reserve + est_tokens

            # Check global budget
            global_used = self._global_input + self._global_output
            global_remaining = self._config.global_token_budget - global_used
            if global_remaining < reserve:
                return (False,
                        f"Global token budget nearly exhausted: "
                        f"{global_used:,}/{self._config.global_token_budget:,} used, "
                        f"{global_remaining:,} remaining (need {reserve:,})")

            # Check per-task budget
            task_used = self._task_input + self._task_output
            task_remaining = self._config.per_task_token_budget - task_used
            if task_remaining < reserve:
                return (False,
                        f"Task '{self._current_task_id}' token budget nearly exhausted: "
                        f"{task_used:,}/{self._config.per_task_token_budget:,} used, "
                        f"{task_remaining:,} remaining (need {reserve:,})")

            return (True, "")

    def get_snapshot(self) -> dict:
        """Get a snapshot of current budget usage for dashboard display.

        Returns:
            Dict with global, task, and per-agent usage data.
        """
        with self._lock:
            global_used = self._global_input + self._global_output
            global_budget = self._config.global_token_budget
            task_used = self._task_input + self._task_output
            task_budget = self._config.per_task_token_budget

            return {
                "global_used": global_used,
                "global_input": self._global_input,
                "global_output": self._global_output,
                "global_budget": global_budget,
                "global_pct": round(global_used / global_budget, 4) if global_budget > 0 else 0,
                "task_id": self._current_task_id,
                "task_used": task_used,
                "task_input": self._task_input,
                "task_output": self._task_output,
                "task_budget": task_budget,
                "task_pct": round(task_used / task_budget, 4) if task_budget > 0 else 0,
                "agent_totals": {
                    k: dict(v) for k, v in self._agent_totals.items()
                },
            }
