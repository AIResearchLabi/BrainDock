"""Tests for the Reflection module."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.reflection.models import RootCause, PlanModification, ReflectionResult
from BrainDock.reflection.agent import ReflectionAgent
from BrainDock.llm import CallableBackend


# ── Mock Responses ─────────────────────────────────────────────────────

REFLECT_RESPONSE = json.dumps({
    "root_causes": [
        {
            "description": "Missing database driver package",
            "category": "missing_dependency",
            "confidence": 0.9,
        }
    ],
    "modifications": [
        {
            "action": "add_step",
            "target_step_id": "s1",
            "description": "Add pip install for psycopg2-binary before migration step",
            "new_step": {
                "id": "s1b",
                "action": "Install DB driver",
                "description": "pip install psycopg2-binary",
                "tool": "run_command",
                "expected_output": "Package installed",
            },
        }
    ],
    "summary": "The migration failed because psycopg2 was not installed. Adding an install step before migration.",
    "should_retry": True,
    "modified_plan": {
        "task_id": "t2",
        "task_title": "Database schema",
        "steps": [
            {"id": "s1", "action": "Create models", "description": "Write models", "tool": "write_file", "expected_output": "models.py"},
            {"id": "s1b", "action": "Install DB driver", "description": "pip install psycopg2-binary", "tool": "run_command", "expected_output": "Installed"},
            {"id": "s2", "action": "Run migration", "description": "alembic upgrade head", "tool": "run_command", "expected_output": "Tables created"},
        ],
        "metrics": {"confidence": 0.8, "entropy": 0.2, "estimated_steps": 3, "complexity": "medium"},
        "relevant_skills": [],
        "assumptions": ["psycopg2-binary available via pip"],
    },
})

UNRECOVERABLE_RESPONSE = json.dumps({
    "root_causes": [
        {
            "description": "Fundamental architecture mismatch",
            "category": "wrong_approach",
            "confidence": 0.95,
        }
    ],
    "modifications": [],
    "summary": "The chosen approach fundamentally conflicts with the requirements. Need to redesign.",
    "should_retry": False,
    "modified_plan": {},
})


def make_reflect_llm():
    return CallableBackend(lambda s, u: REFLECT_RESPONSE)


def make_unrecoverable_llm():
    return CallableBackend(lambda s, u: UNRECOVERABLE_RESPONSE)


# ── Tests ──────────────────────────────────────────────────────────────

class TestRootCause(unittest.TestCase):
    def test_roundtrip(self):
        rc = RootCause(description="Missing dep", category="missing_dependency", confidence=0.9)
        d = rc.to_dict()
        restored = RootCause.from_dict(d)
        self.assertEqual(restored.description, "Missing dep")
        self.assertEqual(restored.category, "missing_dependency")

    def test_defaults(self):
        rc = RootCause.from_dict({"description": "Issue"})
        self.assertEqual(rc.category, "")
        self.assertAlmostEqual(rc.confidence, 0.0)


class TestPlanModification(unittest.TestCase):
    def test_roundtrip(self):
        m = PlanModification(action="add_step", target_step_id="s1", description="Add install step")
        d = m.to_dict()
        restored = PlanModification.from_dict(d)
        self.assertEqual(restored.action, "add_step")
        self.assertEqual(restored.target_step_id, "s1")


class TestReflectionResult(unittest.TestCase):
    def test_roundtrip(self):
        data = json.loads(REFLECT_RESPONSE)
        result = ReflectionResult.from_dict(data)
        self.assertEqual(len(result.root_causes), 1)
        self.assertEqual(len(result.modifications), 1)
        self.assertTrue(result.should_retry)
        self.assertIn("psycopg2", result.summary)

        d = result.to_dict()
        restored = ReflectionResult.from_dict(d)
        self.assertEqual(len(restored.root_causes), 1)

    def test_empty(self):
        result = ReflectionResult.from_dict({})
        self.assertEqual(len(result.root_causes), 0)
        self.assertFalse(result.should_retry)


class TestReflectionAgent(unittest.TestCase):
    def test_reflect_success(self):
        agent = ReflectionAgent(llm=make_reflect_llm())
        execution = {"task_id": "t2", "success": False, "outcomes": [], "failure_count": 1}
        plan = {"task_id": "t2", "steps": []}
        result = agent.reflect(execution, plan, context="TaskFlow project")
        self.assertIsInstance(result, ReflectionResult)
        self.assertTrue(result.should_retry)
        self.assertEqual(len(result.root_causes), 1)
        self.assertEqual(result.root_causes[0].category, "missing_dependency")
        self.assertIn("t2", result.modified_plan.get("task_id", ""))

    def test_reflect_unrecoverable(self):
        agent = ReflectionAgent(llm=make_unrecoverable_llm())
        result = agent.reflect({"success": False}, {"steps": []})
        self.assertFalse(result.should_retry)

    def test_max_iterations_enforced(self):
        agent = ReflectionAgent(llm=make_reflect_llm(), max_iterations=2)
        execution = {"success": False}
        plan = {"steps": []}

        # First two reflections should work
        r1 = agent.reflect(execution, plan)
        self.assertTrue(r1.should_retry)
        r2 = agent.reflect(execution, plan)
        self.assertTrue(r2.should_retry)

        # Third should be blocked
        r3 = agent.reflect(execution, plan)
        self.assertFalse(r3.should_retry)
        self.assertIn("Max reflection", r3.summary)

    def test_iterations_remaining(self):
        agent = ReflectionAgent(llm=make_reflect_llm(), max_iterations=2)
        self.assertEqual(agent.iterations_remaining, 2)
        agent.reflect({"success": False}, {"steps": []})
        self.assertEqual(agent.iterations_remaining, 1)

    def test_reset(self):
        agent = ReflectionAgent(llm=make_reflect_llm(), max_iterations=2)
        agent.reflect({"success": False}, {"steps": []})
        agent.reflect({"success": False}, {"steps": []})
        self.assertEqual(agent.iterations_remaining, 0)
        agent.reset()
        self.assertEqual(agent.iterations_remaining, 2)


if __name__ == "__main__":
    unittest.main()
