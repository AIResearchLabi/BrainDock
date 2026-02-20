"""Tests for the Skill Bank module."""

import json
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.skill_bank.models import Skill, SkillBank
from BrainDock.skill_bank.agent import SkillLearningAgent
from BrainDock.skill_bank.storage import load_skill_bank, save_skill_bank
from BrainDock.llm import CallableBackend


# ── Mock Responses ─────────────────────────────────────────────────────

EXTRACT_SKILL_RESPONSE = json.dumps({
    "id": "skill_retry_with_backoff",
    "name": "Retry with Exponential Backoff",
    "description": "Retries a failing operation with exponentially increasing delays. Useful for transient failures in network calls or external services.",
    "tags": ["error-handling", "resilience", "networking"],
    "pattern": "for attempt in range(max_retries): try operation; except: sleep(2**attempt); raise after exhaustion",
    "example_code": "import time\ndef retry(fn, max_retries=3):\n    for i in range(max_retries):\n        try:\n            return fn()\n        except Exception:\n            if i == max_retries - 1:\n                raise\n            time.sleep(2 ** i)",
})

MATCH_SKILLS_RESPONSE = json.dumps({
    "matches": [
        {
            "skill_id": "skill_retry_with_backoff",
            "relevance": "high",
            "application": "Use retry with backoff for the API calls to handle transient failures.",
        }
    ]
})


def make_extract_llm():
    return CallableBackend(lambda s, u: EXTRACT_SKILL_RESPONSE)


def make_match_llm():
    return CallableBackend(lambda s, u: MATCH_SKILLS_RESPONSE)


# ── Tests ──────────────────────────────────────────────────────────────

class TestSkillModel(unittest.TestCase):
    def test_skill_roundtrip(self):
        skill = Skill(
            id="skill_test",
            name="Test Skill",
            description="A test skill",
            tags=["testing"],
            pattern="test pattern",
            example_code="print('hello')",
            source_task="test task",
            usage_count=0,
        )
        d = skill.to_dict()
        restored = Skill.from_dict(d)
        self.assertEqual(restored.id, "skill_test")
        self.assertEqual(restored.name, "Test Skill")
        self.assertEqual(restored.tags, ["testing"])
        self.assertEqual(restored.usage_count, 0)

    def test_skill_from_dict_defaults(self):
        data = {"id": "s1", "name": "Minimal", "description": "Minimal skill"}
        skill = Skill.from_dict(data)
        self.assertEqual(skill.tags, [])
        self.assertEqual(skill.pattern, "")
        self.assertEqual(skill.usage_count, 0)


class TestSkillBank(unittest.TestCase):
    def setUp(self):
        self.bank = SkillBank()
        self.skill1 = Skill(
            id="skill_retry",
            name="Retry Pattern",
            description="Retry with backoff",
            tags=["resilience", "networking"],
        )
        self.skill2 = Skill(
            id="skill_cache",
            name="Memoization Cache",
            description="Cache function results",
            tags=["performance", "caching"],
        )

    def test_add_and_get(self):
        self.bank.add(self.skill1)
        self.assertEqual(len(self.bank.skills), 1)
        found = self.bank.get("skill_retry")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Retry Pattern")

    def test_add_replaces_duplicate_id(self):
        self.bank.add(self.skill1)
        updated = Skill(
            id="skill_retry",
            name="Updated Retry",
            description="Updated",
            tags=["updated"],
        )
        self.bank.add(updated)
        self.assertEqual(len(self.bank.skills), 1)
        self.assertEqual(self.bank.get("skill_retry").name, "Updated Retry")

    def test_find_by_tags(self):
        self.bank.add(self.skill1)
        self.bank.add(self.skill2)
        results = self.bank.find_by_tags(["networking"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "skill_retry")

    def test_find_by_tags_multiple(self):
        self.bank.add(self.skill1)
        self.bank.add(self.skill2)
        results = self.bank.find_by_tags(["networking", "caching"])
        self.assertEqual(len(results), 2)

    def test_find_by_name(self):
        self.bank.add(self.skill1)
        self.bank.add(self.skill2)
        results = self.bank.find_by_name("retry")
        self.assertEqual(len(results), 1)

    def test_record_usage(self):
        self.bank.add(self.skill1)
        self.bank.record_usage("skill_retry")
        self.assertEqual(self.bank.get("skill_retry").usage_count, 1)

    def test_get_nonexistent(self):
        self.assertIsNone(self.bank.get("nope"))

    def test_roundtrip(self):
        self.bank.add(self.skill1)
        self.bank.add(self.skill2)
        d = self.bank.to_dict()
        restored = SkillBank.from_dict(d)
        self.assertEqual(len(restored.skills), 2)
        self.assertEqual(restored.get("skill_cache").name, "Memoization Cache")


class TestSkillStorage(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self._tmpdir, "skills.json")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_load_empty(self):
        bank = load_skill_bank(self.path)
        self.assertEqual(len(bank.skills), 0)

    def test_save_and_load(self):
        bank = SkillBank()
        bank.add(Skill(id="s1", name="Test", description="A test"))
        save_skill_bank(bank, self.path)
        self.assertTrue(os.path.exists(self.path))
        loaded = load_skill_bank(self.path)
        self.assertEqual(len(loaded.skills), 1)
        self.assertEqual(loaded.get("s1").name, "Test")


class TestSkillLearningAgent(unittest.TestCase):
    def test_extract_skill(self):
        agent = SkillLearningAgent(llm=make_extract_llm())
        skill = agent.extract_skill(
            task_description="Implement API retry logic",
            solution_code="def retry(): ...",
            outcome="All API calls now handle transient failures",
        )
        self.assertIsInstance(skill, Skill)
        self.assertEqual(skill.id, "skill_retry_with_backoff")
        self.assertEqual(skill.name, "Retry with Exponential Backoff")
        self.assertIn("error-handling", skill.tags)
        self.assertIn("Implement API retry", skill.source_task)

    def test_match_skills(self):
        agent = SkillLearningAgent(llm=make_match_llm())
        bank = SkillBank()
        bank.add(Skill(
            id="skill_retry_with_backoff",
            name="Retry with Backoff",
            description="Retry failing ops",
            tags=["resilience"],
        ))
        matches = agent.match_skills("Build an API client with error handling", bank)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["skill_id"], "skill_retry_with_backoff")
        self.assertEqual(matches[0]["relevance"], "high")

    def test_match_skills_empty_bank(self):
        agent = SkillLearningAgent(llm=make_match_llm())
        matches = agent.match_skills("Some task", SkillBank())
        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
