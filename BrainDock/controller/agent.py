"""Controller Agent — deterministic quality gates for the pipeline."""

from __future__ import annotations

from .models import GateThresholds, GateResult, ControllerState


class ControllerAgent:
    """Deterministic quality gate controller.

    Uses threshold checks (not LLM calls) to decide whether plans and
    execution results should proceed, trigger reflection, or trigger debate.

    Usage:
        controller = ControllerAgent()
        result = controller.check_plan_gate(plan_dict)
        if result.action == "debate":
            # trigger debate
    """

    def __init__(
        self,
        thresholds: GateThresholds | None = None,
        state: ControllerState | None = None,
    ):
        self.thresholds = thresholds or GateThresholds()
        self.state = state or ControllerState()

    def check_plan_gate(self, plan: dict) -> GateResult:
        """Check if a plan passes the quality gate.

        Args:
            plan: ActionPlan as a dict (from ActionPlan.to_dict()).

        Returns:
            GateResult with action: proceed, reflect, or debate.
        """
        metrics = plan.get("metrics", {})
        confidence = metrics.get("confidence", 0.0)
        entropy = metrics.get("entropy", 0.0)

        gate_metrics = {"confidence": confidence, "entropy": entropy}

        if entropy > self.thresholds.max_entropy:
            result = GateResult(
                gate_name="plan_quality",
                passed=False,
                action="debate",
                reason=f"Entropy {entropy:.2f} exceeds threshold {self.thresholds.max_entropy:.2f}",
                metrics=gate_metrics,
            )
        elif confidence < self.thresholds.min_confidence:
            result = GateResult(
                gate_name="plan_quality",
                passed=False,
                action="reflect",
                reason=f"Confidence {confidence:.2f} below threshold {self.thresholds.min_confidence:.2f}",
                metrics=gate_metrics,
            )
        else:
            result = GateResult(
                gate_name="plan_quality",
                passed=True,
                action="proceed",
                reason="Plan meets quality thresholds",
                metrics=gate_metrics,
            )

        self.state.record_gate(result)
        return result

    def check_execution_gate(self, execution: dict) -> GateResult:
        """Check if an execution result passes the quality gate.

        Args:
            execution: ExecutionResult as a dict.

        Returns:
            GateResult with action: proceed, reflect, or abort.
        """
        success = execution.get("success", False)
        gate_metrics = {"success": success, "failure_count": self.state.failure_count}

        if success:
            result = GateResult(
                gate_name="execution_quality",
                passed=True,
                action="proceed",
                reason="Execution succeeded",
                metrics=gate_metrics,
            )
        elif self.state.failure_count >= self.thresholds.max_failures:
            result = GateResult(
                gate_name="execution_quality",
                passed=False,
                action="abort",
                reason=f"Failure count {self.state.failure_count} reached maximum {self.thresholds.max_failures}",
                metrics=gate_metrics,
            )
        else:
            result = GateResult(
                gate_name="execution_quality",
                passed=False,
                action="reflect",
                reason=f"Execution failed (attempt {self.state.failure_count + 1}/{self.thresholds.max_failures})",
                metrics=gate_metrics,
            )

        self.state.record_gate(result)
        return result

    def check_reflection_gate(self) -> GateResult:
        """Check if another reflection iteration is allowed.

        Returns:
            GateResult with action: proceed (allow reflection) or abort.
        """
        if self.state.reflection_count < self.thresholds.max_reflection_iterations:
            return GateResult(
                gate_name="reflection_limit",
                passed=True,
                action="proceed",
                reason=f"Reflection {self.state.reflection_count + 1}/{self.thresholds.max_reflection_iterations} allowed",
            )
        return GateResult(
            gate_name="reflection_limit",
            passed=False,
            action="abort",
            reason=f"Maximum reflection iterations ({self.thresholds.max_reflection_iterations}) reached",
        )

    def check_debate_gate(self) -> GateResult:
        """Check if another debate round is allowed.

        Returns:
            GateResult with action: proceed (allow debate) or abort.
        """
        if self.state.debate_count < self.thresholds.max_debate_rounds:
            return GateResult(
                gate_name="debate_limit",
                passed=True,
                action="proceed",
                reason=f"Debate round {self.state.debate_count + 1}/{self.thresholds.max_debate_rounds} allowed",
            )
        return GateResult(
            gate_name="debate_limit",
            passed=False,
            action="abort",
            reason=f"Maximum debate rounds ({self.thresholds.max_debate_rounds}) reached",
        )
