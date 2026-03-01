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
from BrainDock.skill_bank.storage import load_skill_bank, load_with_seeds, save_skill_bank
from BrainDock.llm import CallableBackend


# ── Mock Responses ─────────────────────────────────────────────────────

EXTRACT_SKILL_RESPONSE = json.dumps({
    "id": "skill_retry_with_backoff",
    "name": "Retry with Exponential Backoff",
    "description": "Retries a failing operation with exponentially increasing delays. Useful for transient failures in network calls or external services.",
    "tags": ["error-handling", "resilience", "networking"],
    "category": "workflow/retry",
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


class TestSkillBankMerge(unittest.TestCase):
    def test_merge_empty(self):
        bank1 = SkillBank()
        bank2 = SkillBank()
        added = bank1.merge(bank2)
        self.assertEqual(added, 0)
        self.assertEqual(len(bank1.skills), 0)

    def test_merge_adds_new(self):
        bank1 = SkillBank()
        bank2 = SkillBank()
        bank2.add(Skill(id="s1", name="Skill 1", description="First"))
        bank2.add(Skill(id="s2", name="Skill 2", description="Second"))
        added = bank1.merge(bank2)
        self.assertEqual(added, 2)
        self.assertEqual(len(bank1.skills), 2)
        self.assertIsNotNone(bank1.get("s1"))
        self.assertIsNotNone(bank1.get("s2"))

    def test_merge_updates_existing(self):
        bank1 = SkillBank()
        bank1.add(Skill(id="s1", name="Original", description="Original desc"))
        bank2 = SkillBank()
        bank2.add(Skill(id="s1", name="Updated", description="Updated desc"))
        added = bank1.merge(bank2)
        self.assertEqual(added, 0)
        self.assertEqual(len(bank1.skills), 1)
        self.assertEqual(bank1.get("s1").name, "Updated")

    def test_merge_mixed(self):
        bank1 = SkillBank()
        bank1.add(Skill(id="s1", name="Existing", description="Stays"))
        bank2 = SkillBank()
        bank2.add(Skill(id="s1", name="Updated", description="Replaced"))
        bank2.add(Skill(id="s2", name="New", description="Added"))
        added = bank1.merge(bank2)
        self.assertEqual(added, 1)
        self.assertEqual(len(bank1.skills), 2)
        self.assertEqual(bank1.get("s1").name, "Updated")
        self.assertEqual(bank1.get("s2").name, "New")


class TestGlobalSkillStorage(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_first_run_creates_global(self):
        path = os.path.join(self._tmpdir, "skill_bank", "skills.json")
        bank = SkillBank()
        bank.add(Skill(id="s1", name="First", description="First run skill"))
        save_skill_bank(bank, path)
        self.assertTrue(os.path.exists(path))
        loaded = load_skill_bank(path)
        self.assertEqual(len(loaded.skills), 1)
        self.assertEqual(loaded.get("s1").name, "First")

    def test_second_run_merges(self):
        path = os.path.join(self._tmpdir, "skill_bank", "skills.json")
        # Run 1: save one skill
        bank1 = SkillBank()
        bank1.add(Skill(id="s1", name="Run1 Skill", description="From run 1"))
        save_skill_bank(bank1, path)

        # Run 2: load, add new skill, merge-save
        run2_bank = SkillBank()
        run2_bank.add(Skill(id="s2", name="Run2 Skill", description="From run 2"))
        global_bank = load_skill_bank(path)
        global_bank.merge(run2_bank)
        save_skill_bank(global_bank, path)

        # Verify both skills present
        final = load_skill_bank(path)
        self.assertEqual(len(final.skills), 2)
        self.assertIsNotNone(final.get("s1"))
        self.assertIsNotNone(final.get("s2"))


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
        self.assertEqual(skill.category, "workflow/retry")
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


class TestSkillCategory(unittest.TestCase):
    def test_category_roundtrip(self):
        skill = Skill(id="s1", name="Test", description="Test", category="code/scaffolding")
        d = skill.to_dict()
        restored = Skill.from_dict(d)
        self.assertEqual(restored.category, "code/scaffolding")

    def test_find_by_category_prefix(self):
        bank = SkillBank()
        bank.add(Skill(id="s1", name="A", description="A", category="code/scaffolding"))
        bank.add(Skill(id="s2", name="B", description="B", category="code/testing"))
        bank.add(Skill(id="s3", name="C", description="C", category="web/scraping"))
        results = bank.find_by_category("code")
        self.assertEqual(len(results), 2)
        ids = {s.id for s in results}
        self.assertEqual(ids, {"s1", "s2"})

    def test_find_by_category_exact(self):
        bank = SkillBank()
        bank.add(Skill(id="s1", name="A", description="A", category="code/scaffolding"))
        bank.add(Skill(id="s2", name="B", description="B", category="code"))
        results = bank.find_by_category("code")
        self.assertEqual(len(results), 2)

    def test_find_by_category_no_match(self):
        bank = SkillBank()
        bank.add(Skill(id="s1", name="A", description="A", category="web/scraping"))
        results = bank.find_by_category("code")
        self.assertEqual(len(results), 0)

    def test_find_by_category_case_insensitive(self):
        bank = SkillBank()
        bank.add(Skill(id="s1", name="A", description="A", category="Code/Scaffolding"))
        results = bank.find_by_category("code")
        self.assertEqual(len(results), 1)
        results2 = bank.find_by_category("CODE")
        self.assertEqual(len(results2), 1)

    def test_backward_compat_no_category(self):
        data = {"id": "s1", "name": "Old", "description": "Old skill"}
        skill = Skill.from_dict(data)
        self.assertEqual(skill.category, "")


class TestReliabilityScoring(unittest.TestCase):
    def test_reliability_no_data(self):
        skill = Skill(id="s1", name="A", description="A")
        self.assertEqual(skill.reliability_score, 1.0)

    def test_reliability_mixed(self):
        skill = Skill(id="s1", name="A", description="A", success_count=7, failure_count=3)
        self.assertAlmostEqual(skill.reliability_score, 0.7)

    def test_reliability_all_fail(self):
        skill = Skill(id="s1", name="A", description="A", success_count=0, failure_count=5)
        self.assertAlmostEqual(skill.reliability_score, 0.0)

    def test_reliability_all_success(self):
        skill = Skill(id="s1", name="A", description="A", success_count=5, failure_count=0)
        self.assertAlmostEqual(skill.reliability_score, 1.0)

    def test_record_success(self):
        bank = SkillBank()
        bank.add(Skill(id="s1", name="A", description="A"))
        bank.record_success("s1")
        s = bank.get("s1")
        self.assertEqual(s.success_count, 1)
        self.assertEqual(s.usage_count, 1)

    def test_record_failure(self):
        bank = SkillBank()
        bank.add(Skill(id="s1", name="A", description="A"))
        bank.record_failure("s1")
        s = bank.get("s1")
        self.assertEqual(s.failure_count, 1)
        self.assertEqual(s.usage_count, 1)

    def test_record_success_nonexistent(self):
        bank = SkillBank()
        bank.record_success("nonexistent")  # should not raise

    def test_record_failure_nonexistent(self):
        bank = SkillBank()
        bank.record_failure("nonexistent")  # should not raise

    def test_get_reliable_skills_boundary(self):
        bank = SkillBank()
        bank.add(Skill(id="s1", name="Boundary", description="A",
                        success_count=3, failure_count=7))  # 0.3 exactly
        reliable = bank.get_reliable_skills(0.3)
        self.assertEqual(len(reliable), 1)
        self.assertEqual(reliable[0].id, "s1")

    def test_get_reliable_skills(self):
        bank = SkillBank()
        bank.add(Skill(id="s1", name="Good", description="A", success_count=9, failure_count=1))
        bank.add(Skill(id="s2", name="Bad", description="B", success_count=1, failure_count=9))
        bank.add(Skill(id="s3", name="New", description="C"))  # no data = 1.0
        reliable = bank.get_reliable_skills(0.3)
        ids = {s.id for s in reliable}
        self.assertIn("s1", ids)
        self.assertNotIn("s2", ids)
        self.assertIn("s3", ids)

    def test_backward_compat_old_format(self):
        data = {"id": "s1", "name": "Old", "description": "Old skill"}
        skill = Skill.from_dict(data)
        self.assertEqual(skill.success_count, 0)
        self.assertEqual(skill.failure_count, 0)
        self.assertEqual(skill.reliability_score, 1.0)

    def test_full_roundtrip_with_new_fields(self):
        skill = Skill(
            id="s1", name="Full", description="Full test",
            tags=["a"], category="code/test",
            success_count=10, failure_count=2, usage_count=12,
        )
        d = skill.to_dict()
        restored = Skill.from_dict(d)
        self.assertEqual(restored.category, "code/test")
        self.assertEqual(restored.success_count, 10)
        self.assertEqual(restored.failure_count, 2)
        self.assertAlmostEqual(restored.reliability_score, 10 / 12)


class TestSeedBank(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_json(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def test_load_with_seeds_no_runtime(self):
        seed_path = os.path.join(self._tmpdir, "seeds.json")
        runtime_path = os.path.join(self._tmpdir, "runtime.json")
        self._write_json(seed_path, {
            "skills": [
                {"id": "seed1", "name": "Seed Skill", "description": "From seeds", "category": "code/test"}
            ]
        })
        bank = load_with_seeds(runtime_path, seed_path)
        self.assertEqual(len(bank.skills), 1)
        self.assertEqual(bank.get("seed1").name, "Seed Skill")

    def test_runtime_overrides_seed(self):
        seed_path = os.path.join(self._tmpdir, "seeds.json")
        runtime_path = os.path.join(self._tmpdir, "runtime.json")
        self._write_json(seed_path, {
            "skills": [
                {"id": "s1", "name": "Seed Version", "description": "Original"}
            ]
        })
        self._write_json(runtime_path, {
            "skills": [
                {"id": "s1", "name": "Runtime Version", "description": "Updated"},
                {"id": "s2", "name": "New Skill", "description": "Only in runtime"}
            ]
        })
        bank = load_with_seeds(runtime_path, seed_path)
        self.assertEqual(bank.get("s1").name, "Runtime Version")
        self.assertIsNotNone(bank.get("s2"))

    def test_missing_seed_file(self):
        runtime_path = os.path.join(self._tmpdir, "runtime.json")
        seed_path = os.path.join(self._tmpdir, "nonexistent_seeds.json")
        self._write_json(runtime_path, {
            "skills": [
                {"id": "s1", "name": "Runtime", "description": "Only runtime"}
            ]
        })
        bank = load_with_seeds(runtime_path, seed_path)
        self.assertEqual(len(bank.skills), 1)
        self.assertEqual(bank.get("s1").name, "Runtime")

    def test_both_files_missing(self):
        runtime_path = os.path.join(self._tmpdir, "nonexistent_runtime.json")
        seed_path = os.path.join(self._tmpdir, "nonexistent_seeds.json")
        bank = load_with_seeds(runtime_path, seed_path)
        self.assertEqual(len(bank.skills), 0)


if __name__ == "__main__":
    unittest.main()
