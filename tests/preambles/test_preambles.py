"""Tests for the Preambles module."""

import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.preambles import (
    _read_preamble,
    get_preamble,
    load_preambles,
    build_system_prompt,
    DEV_OPS,
    EXEC_OPS,
    BUSINESS_OPS,
)


# ── Tests ──────────────────────────────────────────────────────────────

class TestConstants(unittest.TestCase):
    def test_preamble_names(self):
        self.assertEqual(DEV_OPS, "dev_ops")
        self.assertEqual(EXEC_OPS, "exec_ops")
        self.assertEqual(BUSINESS_OPS, "business_ops")


class TestReadPreamble(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_reads_existing_file(self):
        path = os.path.join(self._tmpdir, "test.md")
        with open(path, "w") as f:
            f.write("# Test Preamble\nSome content.")
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            content = _read_preamble("test")
        self.assertEqual(content, "# Test Preamble\nSome content.")

    def test_missing_file_returns_empty(self):
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            content = _read_preamble("nonexistent")
        self.assertEqual(content, "")

    def test_empty_file_returns_empty(self):
        path = os.path.join(self._tmpdir, "empty.md")
        with open(path, "w") as f:
            f.write("   \n  ")
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            content = _read_preamble("empty")
        self.assertEqual(content, "")

    def test_strips_whitespace(self):
        path = os.path.join(self._tmpdir, "padded.md")
        with open(path, "w") as f:
            f.write("\n\n  Content  \n\n")
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            content = _read_preamble("padded")
        self.assertEqual(content, "Content")


class TestGetPreamble(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        # Clear cache to avoid cross-test pollution
        from BrainDock.preambles import _cached_preamble
        _cached_preamble.cache_clear()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        from BrainDock.preambles import _cached_preamble
        _cached_preamble.cache_clear()

    def test_existing_preamble(self):
        path = os.path.join(self._tmpdir, "test.md")
        with open(path, "w") as f:
            f.write("Preamble content")
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            content = get_preamble("test")
        self.assertEqual(content, "Preamble content")

    def test_missing_preamble_returns_empty(self):
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            content = get_preamble("missing")
        self.assertEqual(content, "")


class TestLoadPreambles(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        from BrainDock.preambles import _cached_preamble
        _cached_preamble.cache_clear()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        from BrainDock.preambles import _cached_preamble
        _cached_preamble.cache_clear()

    def test_loads_multiple(self):
        for name, text in [("a", "Alpha"), ("b", "Beta")]:
            with open(os.path.join(self._tmpdir, f"{name}.md"), "w") as f:
                f.write(text)
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            result = load_preambles("a", "b")
        self.assertIn("Alpha", result)
        self.assertIn("Beta", result)

    def test_skips_missing(self):
        with open(os.path.join(self._tmpdir, "a.md"), "w") as f:
            f.write("Alpha")
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            result = load_preambles("a", "missing")
        self.assertIn("Alpha", result)
        self.assertNotIn("missing", result)

    def test_all_missing_returns_empty(self):
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            result = load_preambles("x", "y", "z")
        self.assertEqual(result, "")

    def test_no_args_returns_empty(self):
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            result = load_preambles()
        self.assertEqual(result, "")


class TestBuildSystemPrompt(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        from BrainDock.preambles import _cached_preamble
        _cached_preamble.cache_clear()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        from BrainDock.preambles import _cached_preamble
        _cached_preamble.cache_clear()

    def test_with_preamble(self):
        with open(os.path.join(self._tmpdir, "dev_ops.md"), "w") as f:
            f.write("Use Python 3.11+")
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            result = build_system_prompt("You are an agent.", "dev_ops")
        self.assertIn("Use Python 3.11+", result)
        self.assertIn("You are an agent.", result)
        self.assertIn("Context & Guidelines", result)
        self.assertIn("Agent Instructions", result)

    def test_without_preamble(self):
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            result = build_system_prompt("You are an agent.", "missing")
        self.assertEqual(result, "You are an agent.")

    def test_multiple_preambles(self):
        for name, text in [("a", "AAA"), ("b", "BBB")]:
            with open(os.path.join(self._tmpdir, f"{name}.md"), "w") as f:
                f.write(text)
        with patch("BrainDock.preambles._DIR", self._tmpdir):
            result = build_system_prompt("Base prompt.", "a", "b")
        self.assertIn("AAA", result)
        self.assertIn("BBB", result)
        self.assertIn("Base prompt.", result)


class TestRealPreambleFilesExist(unittest.TestCase):
    """Verify the actual preamble .md files exist in the source tree."""

    def test_dev_ops_exists(self):
        from BrainDock.preambles import _DIR
        path = os.path.join(_DIR, "dev_ops.md")
        self.assertTrue(os.path.isfile(path), f"Missing: {path}")

    def test_exec_ops_exists(self):
        from BrainDock.preambles import _DIR
        path = os.path.join(_DIR, "exec_ops.md")
        self.assertTrue(os.path.isfile(path), f"Missing: {path}")

    def test_business_ops_exists(self):
        from BrainDock.preambles import _DIR
        path = os.path.join(_DIR, "business_ops.md")
        self.assertTrue(os.path.isfile(path), f"Missing: {path}")


if __name__ == "__main__":
    unittest.main()
