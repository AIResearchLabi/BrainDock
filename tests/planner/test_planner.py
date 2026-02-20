"""Tests for the Planner module."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.planner.models import ActionStep, PlanMetrics, ActionPlan
from BrainDock.planner.agent import PlannerAgent, ENTROPY_THRESHOLD
from BrainDock.planner.output import to_json, to_markdown, save_plan
from BrainDock.llm import CallableBackend


# ── Mock Responses ─────────────────────────────────────────────────────

PLAN_RESPONSE = json.dumps({
    "task_id": "t2",
    "task_title": "Database schema",
    "steps": [
        {
            "id": "s1",
            "action": "Create models file",
            "description": "Write SQLAlchemy models for User and Task tables",
            "tool": "write_file",
            "expected_output": "models.py with User and Task classes",
        },
        {
            "id": "s2",
            "action": "Create migration",
            "description": "Generate Alembic migration from models",
            "tool": "run_command",
            "expected_output": "Migration file in alembic/versions/",
        },
        {
            "id": "s3",
            "action": "Run migration",
            "description": "Apply migration to create tables",
            "tool": "run_command",
            "expected_output": "Tables created in database",
        },
    ],
    "metrics": {
        "confidence": 0.85,
        "entropy": 0.15,
        "estimated_steps": 3,
        "complexity": "medium",
    },
    "relevant_skills": [],
    "assumptions": ["PostgreSQL is installed and accessible"],
})

HIGH_ENTROPY_PLAN = json.dumps({
    "task_id": "t_uncertain",
    "task_title": "Uncertain task",
    "steps": [{"id": "s1", "action": "Try something", "description": "Not sure what to do", "tool": "", "expected_output": ""}],
    "metrics": {
        "confidence": 0.3,
        "entropy": 0.85,
        "estimated_steps": 1,
        "complexity": "high",
    },
    "relevant_skills": [],
    "assumptions": [],
})


def make_plan_llm():
    return CallableBackend(lambda s, u: PLAN_RESPONSE)


def make_high_entropy_llm():
    return CallableBackend(lambda s, u: HIGH_ENTROPY_PLAN)


# ── Tests ──────────────────────────────────────────────────────────────

class TestActionStep(unittest.TestCase):
    def test_roundtrip(self):
        step = ActionStep(id="s1", action="Write code", description="Write the code", tool="write_file")
        d = step.to_dict()
        restored = ActionStep.from_dict(d)
        self.assertEqual(restored.id, "s1")
        self.assertEqual(restored.tool, "write_file")

    def test_defaults(self):
        step = ActionStep.from_dict({"id": "s1", "action": "Do", "description": "Do it"})
        self.assertEqual(step.tool, "")
        self.assertEqual(step.expected_output, "")


class TestPlanMetrics(unittest.TestCase):
    def test_roundtrip(self):
        m = PlanMetrics(confidence=0.9, entropy=0.1, estimated_steps=5, complexity="low")
        d = m.to_dict()
        restored = PlanMetrics.from_dict(d)
        self.assertAlmostEqual(restored.confidence, 0.9)
        self.assertEqual(restored.complexity, "low")

    def test_defaults(self):
        m = PlanMetrics.from_dict({})
        self.assertEqual(m.confidence, 0.0)
        self.assertEqual(m.complexity, "medium")


class TestActionPlan(unittest.TestCase):
    def test_roundtrip(self):
        data = json.loads(PLAN_RESPONSE)
        plan = ActionPlan.from_dict(data)
        self.assertEqual(plan.task_id, "t2")
        self.assertEqual(len(plan.steps), 3)
        self.assertAlmostEqual(plan.metrics.confidence, 0.85)

        d = plan.to_dict()
        restored = ActionPlan.from_dict(d)
        self.assertEqual(restored.task_id, "t2")
        self.assertEqual(len(restored.steps), 3)


class TestPlannerAgent(unittest.TestCase):
    def test_plan_task(self):
        agent = PlannerAgent(llm=make_plan_llm())
        task = {"id": "t2", "title": "Database schema", "description": "Create DB tables"}
        plan = agent.plan_task(task, context="TaskFlow project")
        self.assertIsInstance(plan, ActionPlan)
        self.assertEqual(plan.task_id, "t2")
        self.assertEqual(len(plan.steps), 3)
        self.assertAlmostEqual(plan.metrics.confidence, 0.85)

    def test_plan_with_skills(self):
        agent = PlannerAgent(llm=make_plan_llm())
        task = {"id": "t2", "title": "Database schema", "description": "Create DB tables"}
        skills = [{"id": "skill_migration", "name": "DB Migration", "description": "Alembic migrations"}]
        plan = agent.plan_task(task, context="Test", available_skills=skills)
        self.assertIsInstance(plan, ActionPlan)

    def test_needs_debate_low_entropy(self):
        agent = PlannerAgent(llm=make_plan_llm())
        plan = ActionPlan.from_dict(json.loads(PLAN_RESPONSE))
        self.assertFalse(agent.needs_debate(plan))

    def test_needs_debate_high_entropy(self):
        agent = PlannerAgent(llm=make_high_entropy_llm())
        plan = ActionPlan.from_dict(json.loads(HIGH_ENTROPY_PLAN))
        self.assertTrue(agent.needs_debate(plan))

    def test_custom_entropy_threshold(self):
        agent = PlannerAgent(llm=make_plan_llm(), entropy_threshold=0.1)
        plan = ActionPlan.from_dict(json.loads(PLAN_RESPONSE))
        # entropy 0.15 > custom threshold 0.1
        self.assertTrue(agent.needs_debate(plan))


class TestPlannerOutput(unittest.TestCase):
    def setUp(self):
        self.plan = ActionPlan.from_dict(json.loads(PLAN_RESPONSE))

    def test_to_json(self):
        j = to_json(self.plan)
        parsed = json.loads(j)
        self.assertEqual(parsed["task_id"], "t2")

    def test_to_markdown(self):
        md = to_markdown(self.plan)
        self.assertIn("# Action Plan: Database schema", md)
        self.assertIn("Confidence", md)
        self.assertIn("s1. Create models file", md)

    def test_save_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, md_path = save_plan(self.plan, output_dir=tmpdir)
            self.assertTrue(os.path.exists(json_path))
            self.assertTrue(os.path.exists(md_path))


if __name__ == "__main__":
    unittest.main()
