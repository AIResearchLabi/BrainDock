"""Tests for the Task Graph module."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.task_graph.models import TaskNode, RiskNode, TaskGraph
from BrainDock.task_graph.agent import TaskGraphAgent
from BrainDock.task_graph.output import to_json, to_markdown, save_task_graph
from BrainDock.llm import CallableBackend


# ── Mock Responses ─────────────────────────────────────────────────────

DECOMPOSE_RESPONSE = json.dumps({
    "project_title": "TaskFlow",
    "tasks": [
        {
            "id": "t1",
            "title": "Project setup",
            "description": "Initialize project structure with package.json and directory layout",
            "depends_on": [],
            "estimated_effort": "small",
            "risks": [],
        },
        {
            "id": "t2",
            "title": "Database schema",
            "description": "Create PostgreSQL schema with Users and Tasks tables",
            "depends_on": ["t1"],
            "estimated_effort": "medium",
            "risks": [
                {"description": "Migration complexity", "severity": "low", "mitigation": "Use Alembic"}
            ],
        },
        {
            "id": "t3",
            "title": "Auth endpoints",
            "description": "Implement registration and login with JWT",
            "depends_on": ["t2"],
            "estimated_effort": "medium",
            "risks": [
                {"description": "Token security", "severity": "medium", "mitigation": "Use proven JWT library"}
            ],
        },
        {
            "id": "t4",
            "title": "Task CRUD API",
            "description": "REST endpoints for task management",
            "depends_on": ["t2"],
            "estimated_effort": "medium",
            "risks": [],
        },
        {
            "id": "t5",
            "title": "Frontend scaffold",
            "description": "React app with routing and auth context",
            "depends_on": ["t1"],
            "estimated_effort": "medium",
            "risks": [],
        },
    ],
})


def make_decompose_llm():
    return CallableBackend(lambda s, u: DECOMPOSE_RESPONSE)


# ── Tests ──────────────────────────────────────────────────────────────

class TestRiskNode(unittest.TestCase):
    def test_roundtrip(self):
        risk = RiskNode(description="Test risk", severity="high", mitigation="Handle it")
        d = risk.to_dict()
        restored = RiskNode.from_dict(d)
        self.assertEqual(restored.description, "Test risk")
        self.assertEqual(restored.severity, "high")

    def test_defaults(self):
        risk = RiskNode.from_dict({"description": "Minimal"})
        self.assertEqual(risk.severity, "medium")
        self.assertEqual(risk.mitigation, "")


class TestTaskNode(unittest.TestCase):
    def test_roundtrip(self):
        node = TaskNode(
            id="t1",
            title="Setup",
            description="Init project",
            depends_on=[],
            estimated_effort="small",
            risks=[RiskNode(description="None", severity="low")],
        )
        d = node.to_dict()
        restored = TaskNode.from_dict(d)
        self.assertEqual(restored.id, "t1")
        self.assertEqual(len(restored.risks), 1)

    def test_defaults(self):
        node = TaskNode.from_dict({"id": "t1", "title": "X", "description": "Y"})
        self.assertEqual(node.depends_on, [])
        self.assertEqual(node.estimated_effort, "medium")
        self.assertEqual(node.status, "pending")


class TestTaskGraph(unittest.TestCase):
    def setUp(self):
        self.graph = TaskGraph.from_dict(json.loads(DECOMPOSE_RESPONSE))

    def test_from_dict(self):
        self.assertEqual(self.graph.project_title, "TaskFlow")
        self.assertEqual(len(self.graph.tasks), 5)

    def test_get_task(self):
        task = self.graph.get_task("t3")
        self.assertIsNotNone(task)
        self.assertEqual(task.title, "Auth endpoints")

    def test_get_task_nonexistent(self):
        self.assertIsNone(self.graph.get_task("nope"))

    def test_get_ready_tasks(self):
        ready = self.graph.get_ready_tasks()
        ready_ids = [t.id for t in ready]
        self.assertIn("t1", ready_ids)
        # t2 depends on t1, should not be ready
        self.assertNotIn("t2", ready_ids)

    def test_get_ready_tasks_after_completion(self):
        self.graph.mark_completed("t1")
        ready = self.graph.get_ready_tasks()
        ready_ids = [t.id for t in ready]
        self.assertIn("t2", ready_ids)
        self.assertIn("t5", ready_ids)
        self.assertNotIn("t3", ready_ids)  # depends on t2

    def test_get_parallel_groups(self):
        groups = self.graph.get_parallel_groups()
        # Wave 1: t1 (no deps)
        self.assertEqual(len(groups[0]), 1)
        self.assertEqual(groups[0][0].id, "t1")
        # Wave 2: t2, t5 (depend on t1)
        wave2_ids = {t.id for t in groups[1]}
        self.assertEqual(wave2_ids, {"t2", "t5"})
        # Wave 3: t3, t4 (depend on t2)
        wave3_ids = {t.id for t in groups[2]}
        self.assertEqual(wave3_ids, {"t3", "t4"})

    def test_mark_completed(self):
        self.graph.mark_completed("t1", output="Done")
        task = self.graph.get_task("t1")
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.output, "Done")

    def test_mark_failed(self):
        self.graph.mark_failed("t1", output="Error occurred")
        task = self.graph.get_task("t1")
        self.assertEqual(task.status, "failed")

    def test_all_completed(self):
        self.assertFalse(self.graph.all_completed())
        for t in self.graph.tasks:
            self.graph.mark_completed(t.id)
        self.assertTrue(self.graph.all_completed())

    def test_roundtrip(self):
        d = self.graph.to_dict()
        restored = TaskGraph.from_dict(d)
        self.assertEqual(len(restored.tasks), 5)
        self.assertEqual(restored.project_title, "TaskFlow")


class TestTaskGraphAgent(unittest.TestCase):
    def test_decompose(self):
        agent = TaskGraphAgent(llm=make_decompose_llm())
        graph = agent.decompose({"title": "TaskFlow", "summary": "A todo app"})
        self.assertIsInstance(graph, TaskGraph)
        self.assertEqual(graph.project_title, "TaskFlow")
        self.assertEqual(len(graph.tasks), 5)
        self.assertEqual(graph.tasks[0].id, "t1")


class TestTaskGraphOutput(unittest.TestCase):
    def setUp(self):
        self.graph = TaskGraph.from_dict(json.loads(DECOMPOSE_RESPONSE))

    def test_to_json(self):
        j = to_json(self.graph)
        parsed = json.loads(j)
        self.assertEqual(parsed["project_title"], "TaskFlow")

    def test_to_markdown(self):
        md = to_markdown(self.graph)
        self.assertIn("# Task Graph: TaskFlow", md)
        self.assertIn("Wave 1", md)
        self.assertIn("t1: Project setup", md)

    def test_save_task_graph(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, md_path = save_task_graph(self.graph, output_dir=tmpdir)
            self.assertTrue(os.path.exists(json_path))
            self.assertTrue(os.path.exists(md_path))


if __name__ == "__main__":
    unittest.main()
