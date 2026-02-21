"""Tests for the Market Study module."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.market_study.agent import MarketStudyAgent
from BrainDock.market_study.models import MarketStudyResult
from BrainDock.llm import CallableBackend


# ── Mock Responses ─────────────────────────────────────────────────────

MARKET_STUDY_RESPONSE = json.dumps({
    "task_id": "t1",
    "competitors": ["Notion", "Trello", "Asana"],
    "target_audience": "Small development teams",
    "positioning": "Lightweight alternative to heavy PM tools",
    "recommendations": [
        "Focus on developer workflow integration",
        "Offer a generous free tier",
    ],
    "risks": [
        "Saturated market with established players",
        "Difficulty achieving feature parity",
    ],
})

MINIMAL_RESPONSE = json.dumps({
    "task_id": "t2",
    "competitors": [],
    "target_audience": "",
    "positioning": "",
    "recommendations": [],
    "risks": [],
})


def make_market_llm():
    return CallableBackend(lambda s, u: MARKET_STUDY_RESPONSE)


def make_minimal_llm():
    return CallableBackend(lambda s, u: MINIMAL_RESPONSE)


# ── Tests ──────────────────────────────────────────────────────────────

class TestMarketStudyResult(unittest.TestCase):
    def test_roundtrip(self):
        result = MarketStudyResult(
            task_id="t1",
            competitors=["Acme", "Corp"],
            recommendations=["Focus on UX"],
            risks=["Market saturation"],
            target_audience="Developers",
            positioning="Best-in-class CLI tool",
        )
        d = result.to_dict()
        self.assertEqual(d["task_id"], "t1")
        self.assertEqual(d["competitors"], ["Acme", "Corp"])

        restored = MarketStudyResult.from_dict(d)
        self.assertEqual(restored.task_id, "t1")
        self.assertEqual(restored.positioning, "Best-in-class CLI tool")

    def test_defaults(self):
        result = MarketStudyResult()
        self.assertEqual(result.task_id, "")
        self.assertEqual(result.competitors, [])
        self.assertEqual(result.recommendations, [])
        self.assertEqual(result.risks, [])
        self.assertEqual(result.target_audience, "")
        self.assertEqual(result.positioning, "")

    def test_from_dict_missing_fields(self):
        result = MarketStudyResult.from_dict({"task_id": "t3"})
        self.assertEqual(result.task_id, "t3")
        self.assertEqual(result.competitors, [])
        self.assertEqual(result.target_audience, "")

    def test_from_dict_empty(self):
        result = MarketStudyResult.from_dict({})
        self.assertEqual(result.task_id, "")

    def test_to_context_string_full(self):
        result = MarketStudyResult(
            task_id="t1",
            competitors=["Acme", "Corp"],
            target_audience="Devs",
            positioning="Leader",
            recommendations=["Do X"],
            risks=["Risk Y"],
        )
        ctx = result.to_context_string()
        self.assertIn("t1", ctx)
        self.assertIn("Acme", ctx)
        self.assertIn("Corp", ctx)
        self.assertIn("Devs", ctx)
        self.assertIn("Leader", ctx)
        self.assertIn("Do X", ctx)
        self.assertIn("Risk Y", ctx)

    def test_to_context_string_minimal(self):
        result = MarketStudyResult(task_id="t2")
        ctx = result.to_context_string()
        self.assertIn("t2", ctx)
        # Should not crash even with empty fields


class TestMarketStudyAgent(unittest.TestCase):
    def test_analyze_full(self):
        agent = MarketStudyAgent(llm=make_market_llm())
        task = {
            "id": "t1",
            "title": "Build task board",
            "description": "Create a Kanban-style task board",
            "tags": ["needs_market_study"],
        }
        result = agent.analyze(task, context="Project context here")
        self.assertIsInstance(result, MarketStudyResult)
        self.assertEqual(result.task_id, "t1")
        self.assertEqual(len(result.competitors), 3)
        self.assertIn("Notion", result.competitors)
        self.assertEqual(result.target_audience, "Small development teams")
        self.assertEqual(len(result.recommendations), 2)
        self.assertEqual(len(result.risks), 2)

    def test_analyze_minimal_response(self):
        agent = MarketStudyAgent(llm=make_minimal_llm())
        task = {"id": "t2", "title": "Internal tool"}
        result = agent.analyze(task)
        self.assertEqual(result.task_id, "t2")
        self.assertEqual(result.competitors, [])
        self.assertEqual(result.target_audience, "")

    def test_analyze_no_context(self):
        agent = MarketStudyAgent(llm=make_market_llm())
        task = {"id": "t1", "title": "Test"}
        result = agent.analyze(task)
        self.assertEqual(result.task_id, "t1")

    def test_analyze_passes_task_id(self):
        """Verify the agent correctly extracts task_id from the task dict."""
        captured = {}

        def capture_fn(system_prompt, user_prompt):
            captured["user_prompt"] = user_prompt
            return MARKET_STUDY_RESPONSE

        agent = MarketStudyAgent(llm=CallableBackend(capture_fn))
        agent.analyze({"id": "task_42", "title": "Test"}, context="ctx")
        self.assertIn("task_42", captured["user_prompt"])


if __name__ == "__main__":
    unittest.main()
