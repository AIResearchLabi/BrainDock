"""Tests for the Controller module."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.controller.models import GateThresholds, GateResult, ControllerState
from BrainDock.controller.agent import ControllerAgent


# ── Tests ──────────────────────────────────────────────────────────────

class TestGateThresholds(unittest.TestCase):
    def test_defaults(self):
        t = GateThresholds()
        self.assertAlmostEqual(t.min_confidence, 0.6)
        self.assertAlmostEqual(t.max_entropy, 0.7)
        self.assertEqual(t.max_failures, 3)

    def test_roundtrip(self):
        t = GateThresholds(min_confidence=0.8, max_entropy=0.5)
        d = t.to_dict()
        restored = GateThresholds.from_dict(d)
        self.assertAlmostEqual(restored.min_confidence, 0.8)
        self.assertAlmostEqual(restored.max_entropy, 0.5)


class TestGateResult(unittest.TestCase):
    def test_roundtrip(self):
        r = GateResult(gate_name="test", passed=True, action="proceed", reason="OK")
        d = r.to_dict()
        restored = GateResult.from_dict(d)
        self.assertEqual(restored.gate_name, "test")
        self.assertTrue(restored.passed)


class TestControllerState(unittest.TestCase):
    def test_record_gate(self):
        state = ControllerState()
        result = GateResult(gate_name="test", passed=False, action="reflect")
        state.record_gate(result)
        self.assertEqual(state.failure_count, 1)
        self.assertEqual(len(state.gate_history), 1)

    def test_record_gate_success(self):
        state = ControllerState()
        result = GateResult(gate_name="test", passed=True, action="proceed")
        state.record_gate(result)
        self.assertEqual(state.failure_count, 0)
        self.assertEqual(len(state.gate_history), 1)

    def test_roundtrip(self):
        state = ControllerState(failure_count=2, reflection_count=1, debate_count=1)
        d = state.to_dict()
        restored = ControllerState.from_dict(d)
        self.assertEqual(restored.failure_count, 2)
        self.assertEqual(restored.reflection_count, 1)


class TestControllerPlanGate(unittest.TestCase):
    def test_good_plan_passes(self):
        controller = ControllerAgent()
        plan = {"metrics": {"confidence": 0.85, "entropy": 0.15}}
        result = controller.check_plan_gate(plan)
        self.assertTrue(result.passed)
        self.assertEqual(result.action, "proceed")

    def test_low_confidence_triggers_reflect(self):
        controller = ControllerAgent()
        plan = {"metrics": {"confidence": 0.4, "entropy": 0.3}}
        result = controller.check_plan_gate(plan)
        self.assertFalse(result.passed)
        self.assertEqual(result.action, "reflect")

    def test_high_entropy_triggers_debate(self):
        controller = ControllerAgent()
        plan = {"metrics": {"confidence": 0.8, "entropy": 0.9}}
        result = controller.check_plan_gate(plan)
        self.assertFalse(result.passed)
        self.assertEqual(result.action, "debate")

    def test_high_entropy_takes_priority_over_low_confidence(self):
        """Entropy > threshold should trigger debate even if confidence is also low."""
        controller = ControllerAgent()
        plan = {"metrics": {"confidence": 0.3, "entropy": 0.9}}
        result = controller.check_plan_gate(plan)
        self.assertEqual(result.action, "debate")

    def test_custom_thresholds(self):
        thresholds = GateThresholds(min_confidence=0.9, max_entropy=0.1)
        controller = ControllerAgent(thresholds=thresholds)
        plan = {"metrics": {"confidence": 0.85, "entropy": 0.15}}
        result = controller.check_plan_gate(plan)
        self.assertFalse(result.passed)
        # entropy 0.15 > 0.1 → debate
        self.assertEqual(result.action, "debate")

    def test_gate_recorded_in_state(self):
        controller = ControllerAgent()
        plan = {"metrics": {"confidence": 0.85, "entropy": 0.15}}
        controller.check_plan_gate(plan)
        self.assertEqual(len(controller.state.gate_history), 1)


class TestControllerExecutionGate(unittest.TestCase):
    def test_success_passes(self):
        controller = ControllerAgent()
        result = controller.check_execution_gate({"success": True})
        self.assertTrue(result.passed)
        self.assertEqual(result.action, "proceed")

    def test_failure_triggers_reflect(self):
        controller = ControllerAgent()
        result = controller.check_execution_gate({"success": False})
        self.assertFalse(result.passed)
        self.assertEqual(result.action, "reflect")

    def test_max_failures_triggers_abort(self):
        controller = ControllerAgent()
        controller.state.failure_count = 3
        result = controller.check_execution_gate({"success": False})
        self.assertEqual(result.action, "abort")

    def test_failure_count_incremented(self):
        controller = ControllerAgent()
        controller.check_execution_gate({"success": False})
        # Gate itself records the failure
        self.assertEqual(controller.state.failure_count, 1)


class TestControllerReflectionGate(unittest.TestCase):
    def test_allowed(self):
        controller = ControllerAgent()
        result = controller.check_reflection_gate()
        self.assertTrue(result.passed)

    def test_exceeded(self):
        controller = ControllerAgent()
        controller.state.reflection_count = 2
        result = controller.check_reflection_gate()
        self.assertFalse(result.passed)
        self.assertEqual(result.action, "abort")


class TestControllerDebateGate(unittest.TestCase):
    def test_allowed(self):
        controller = ControllerAgent()
        result = controller.check_debate_gate()
        self.assertTrue(result.passed)

    def test_exceeded(self):
        controller = ControllerAgent()
        controller.state.debate_count = 3
        result = controller.check_debate_gate()
        self.assertFalse(result.passed)
        self.assertEqual(result.action, "abort")


if __name__ == "__main__":
    unittest.main()
