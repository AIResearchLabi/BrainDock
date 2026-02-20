"""Controller — Quality gate controller (Mode 4).

Deterministic threshold-based quality gates that decide whether a plan
or execution result passes, needs reflection, or needs debate.

Usage:
    from BrainDock.controller import ControllerAgent, GateResult, GateThresholds

    controller = ControllerAgent()
    result = controller.check_plan_gate(plan_dict)
    result = controller.check_execution_gate(execution_dict)
"""

from .models import GateThresholds, GateResult, ControllerState
from .agent import ControllerAgent

__all__ = [
    "GateThresholds",
    "GateResult",
    "ControllerState",
    "ControllerAgent",
]
