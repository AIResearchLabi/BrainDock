"""Tests for the Debate module."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.debate.models import DebatePlan, Critique, DebateOutcome
from BrainDock.debate.agent import DebateAgent
from BrainDock.llm import CallableBackend


# ── Mock Responses ─────────────────────────────────────────────────────

PROPOSE_RESPONSE = json.dumps({
    "proposals": [
        {
            "perspective": "Pragmatist",
            "approach": "Use SQLite for simplicity, upgrade later if needed",
            "strengths": ["Fast to implement", "No external deps"],
            "weaknesses": ["Not production-grade"],
            "confidence": 0.7,
        },
        {
            "perspective": "Perfectionist",
            "approach": "Use PostgreSQL from the start with proper migrations",
            "strengths": ["Production-ready", "Proper data integrity"],
            "weaknesses": ["More setup time"],
            "confidence": 0.8,
        },
    ]
})

CRITIQUE_CONVERGED_RESPONSE = json.dumps({
    "critiques": [
        {
            "target_perspective": "Pragmatist",
            "issues": ["SQLite won't handle concurrent writes"],
            "suggestions": ["Use SQLite for dev, PostgreSQL for prod"],
        },
        {
            "target_perspective": "Perfectionist",
            "issues": ["Setup time is worth it for production use"],
            "suggestions": ["Use Docker to simplify PostgreSQL setup"],
        },
    ],
    "converged": True,
    "winning_approach": "Perfectionist",
    "synthesis": "PostgreSQL with Docker is the best approach — production-ready with minimal setup.",
})

CRITIQUE_NOT_CONVERGED_RESPONSE = json.dumps({
    "critiques": [
        {
            "target_perspective": "Pragmatist",
            "issues": ["Scaling concerns"],
            "suggestions": ["Consider hybrid approach"],
        },
    ],
    "converged": False,
    "winning_approach": "",
    "synthesis": "Still debating...",
})

SYNTHESIZE_RESPONSE = json.dumps({
    "improved_plan": {
        "task_id": "t2",
        "task_title": "Database schema (improved)",
        "steps": [
            {"id": "s1", "action": "Docker setup", "description": "Create docker-compose for PostgreSQL", "tool": "write_file", "expected_output": "docker-compose.yml"},
            {"id": "s2", "action": "Create models", "description": "SQLAlchemy models", "tool": "write_file", "expected_output": "models.py"},
        ],
        "metrics": {"confidence": 0.9, "entropy": 0.1, "estimated_steps": 2, "complexity": "medium"},
        "relevant_skills": [],
        "assumptions": ["Docker available"],
    },
    "synthesis": "PostgreSQL with Docker — best of both worlds.",
})


def make_debate_llm():
    """LLM that converges in 1 round."""
    call_count = {"n": 0}
    responses = [PROPOSE_RESPONSE, CRITIQUE_CONVERGED_RESPONSE, SYNTHESIZE_RESPONSE]

    def mock_fn(system_prompt, user_prompt):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    return CallableBackend(mock_fn)


def make_slow_debate_llm():
    """LLM that doesn't converge until max rounds."""
    call_count = {"n": 0}
    responses = [
        PROPOSE_RESPONSE,
        CRITIQUE_NOT_CONVERGED_RESPONSE,
        CRITIQUE_NOT_CONVERGED_RESPONSE,
        CRITIQUE_CONVERGED_RESPONSE,
        SYNTHESIZE_RESPONSE,
    ]

    def mock_fn(system_prompt, user_prompt):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    return CallableBackend(mock_fn)


# ── Tests ──────────────────────────────────────────────────────────────

class TestDebatePlan(unittest.TestCase):
    def test_roundtrip(self):
        plan = DebatePlan(
            perspective="Pragmatist",
            approach="Simple approach",
            strengths=["Fast"],
            weaknesses=["Limited"],
            confidence=0.7,
        )
        d = plan.to_dict()
        restored = DebatePlan.from_dict(d)
        self.assertEqual(restored.perspective, "Pragmatist")
        self.assertEqual(len(restored.strengths), 1)

    def test_defaults(self):
        plan = DebatePlan.from_dict({"perspective": "X", "approach": "Y"})
        self.assertEqual(plan.strengths, [])
        self.assertAlmostEqual(plan.confidence, 0.0)


class TestCritique(unittest.TestCase):
    def test_roundtrip(self):
        c = Critique(target_perspective="Pragmatist", issues=["Issue 1"], suggestions=["Fix 1"])
        d = c.to_dict()
        restored = Critique.from_dict(d)
        self.assertEqual(restored.target_perspective, "Pragmatist")
        self.assertEqual(len(restored.issues), 1)


class TestDebateOutcome(unittest.TestCase):
    def test_roundtrip(self):
        outcome = DebateOutcome(
            proposals=[DebatePlan(perspective="P", approach="A")],
            critiques=[Critique(target_perspective="P", issues=["I"])],
            winning_approach="P",
            synthesis="Summary",
            improved_plan={"task_id": "t1"},
            rounds_used=1,
            converged=True,
        )
        d = outcome.to_dict()
        restored = DebateOutcome.from_dict(d)
        self.assertEqual(len(restored.proposals), 1)
        self.assertTrue(restored.converged)
        self.assertEqual(restored.rounds_used, 1)

    def test_empty(self):
        outcome = DebateOutcome.from_dict({})
        self.assertEqual(len(outcome.proposals), 0)
        self.assertFalse(outcome.converged)


class TestDebateAgentPropose(unittest.TestCase):
    def test_propose(self):
        agent = DebateAgent(llm=CallableBackend(lambda s, u: PROPOSE_RESPONSE))
        plan = {"task_id": "t2", "metrics": {"entropy": 0.9}}
        proposals = agent.propose(plan, context="TaskFlow")
        self.assertEqual(len(proposals), 2)
        self.assertEqual(proposals[0].perspective, "Pragmatist")
        self.assertEqual(proposals[1].perspective, "Perfectionist")


class TestDebateAgentFull(unittest.TestCase):
    def test_debate_converges_quickly(self):
        agent = DebateAgent(llm=make_debate_llm())
        plan = {"task_id": "t2", "metrics": {"entropy": 0.9}}
        outcome = agent.debate(plan, context="TaskFlow")
        self.assertIsInstance(outcome, DebateOutcome)
        self.assertTrue(outcome.converged)
        self.assertEqual(outcome.winning_approach, "Perfectionist")
        self.assertEqual(len(outcome.proposals), 2)
        self.assertGreater(len(outcome.critiques), 0)
        self.assertIn("t2", outcome.improved_plan.get("task_id", ""))

    def test_debate_max_rounds(self):
        agent = DebateAgent(llm=make_slow_debate_llm(), max_rounds=3)
        plan = {"task_id": "t2", "metrics": {"entropy": 0.9}}
        outcome = agent.debate(plan, context="Test")
        self.assertIsInstance(outcome, DebateOutcome)
        # Should have used multiple rounds
        self.assertGreater(len(outcome.critiques), 1)

    def test_debate_custom_max_rounds(self):
        agent = DebateAgent(llm=make_debate_llm(), max_rounds=1)
        self.assertEqual(agent.max_rounds, 1)


if __name__ == "__main__":
    unittest.main()
