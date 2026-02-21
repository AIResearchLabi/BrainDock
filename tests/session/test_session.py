"""Tests for the Session module."""

import json
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.session import SessionMixin


# ── Test helper ────────────────────────────────────────────────────────

class ConcreteSession(SessionMixin):
    """Concrete class using SessionMixin for testing."""

    def __init__(self, session_file: str):
        self.session_file = session_file


# ── Tests ──────────────────────────────────────────────────────────────

class TestSessionMixin(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._session_path = os.path.join(self._tmpdir, "session.json")
        self.session = ConcreteSession(self._session_path)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_and_load(self):
        data = {"key": "value", "count": 42, "nested": {"a": 1}}
        self.session._save_session_data(data)

        loaded = self.session._load_session_data()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["key"], "value")
        self.assertEqual(loaded["count"], 42)
        self.assertEqual(loaded["nested"]["a"], 1)

    def test_load_nonexistent_returns_none(self):
        loaded = self.session._load_session_data()
        self.assertIsNone(loaded)

    def test_clear_removes_file(self):
        self.session._save_session_data({"test": True})
        self.assertTrue(os.path.exists(self._session_path))

        self.session._clear_session()
        self.assertFalse(os.path.exists(self._session_path))

    def test_clear_nonexistent_no_error(self):
        # Should not raise when file doesn't exist
        self.session._clear_session()

    def test_save_overwrites(self):
        self.session._save_session_data({"version": 1})
        self.session._save_session_data({"version": 2})

        loaded = self.session._load_session_data()
        self.assertEqual(loaded["version"], 2)

    def test_save_creates_valid_json(self):
        self.session._save_session_data({"key": "value"})
        with open(self._session_path) as f:
            data = json.load(f)
        self.assertEqual(data["key"], "value")

    def test_roundtrip_complex_data(self):
        data = {
            "questions": [
                {"id": "q1", "text": "What?", "options": ["a", "b"]},
            ],
            "decisions": [
                {"id": "d1", "topic": "Lang", "decision": "Python"},
            ],
            "understanding": "Building a CLI tool",
            "round": 3,
        }
        self.session._save_session_data(data)
        loaded = self.session._load_session_data()
        self.assertEqual(loaded["questions"][0]["id"], "q1")
        self.assertEqual(loaded["decisions"][0]["decision"], "Python")
        self.assertEqual(loaded["round"], 3)

    def test_save_after_clear_works(self):
        self.session._save_session_data({"v": 1})
        self.session._clear_session()
        self.session._save_session_data({"v": 2})
        loaded = self.session._load_session_data()
        self.assertEqual(loaded["v"], 2)


if __name__ == "__main__":
    unittest.main()
