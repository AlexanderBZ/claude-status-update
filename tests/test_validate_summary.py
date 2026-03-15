"""Unit tests for validate_summary.py."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from validate_summary import validate


class TestValidateSummary(unittest.TestCase):
    def test_valid_single_item(self):
        data = [{"description": "Fix login timeout", "category": "bug"}]
        ok, msg = validate(data)
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")

    def test_valid_multiple_items_all_categories(self):
        data = [
            {"description": "Fix login timeout", "category": "bug"},
            {"description": "Add dark mode toggle", "category": "feature"},
            {"description": "Extract auth into module", "category": "refactor"},
            {"description": "Update CI config", "category": "other"},
        ]
        ok, msg = validate(data)
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")

    def test_invalid_json_via_main(self):
        """Test that main() rejects non-JSON input via subprocess."""
        import subprocess

        script = str(Path(__file__).resolve().parent.parent / "scripts" / "validate_summary.py")
        result = subprocess.run(
            [sys.executable, script],
            input="not json at all",
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid JSON", result.stderr)

    def test_not_an_array(self):
        ok, msg = validate({"description": "Fix bug", "category": "bug"})
        self.assertFalse(ok)
        self.assertIn("array", msg.lower())

    def test_empty_array(self):
        ok, msg = validate([])
        self.assertFalse(ok)
        self.assertIn("empty", msg.lower())

    def test_missing_description(self):
        ok, msg = validate([{"category": "bug"}])
        self.assertFalse(ok)
        self.assertIn("description", msg.lower())

    def test_empty_description(self):
        ok, msg = validate([{"description": "", "category": "bug"}])
        self.assertFalse(ok)
        self.assertIn("description", msg.lower())

    def test_invalid_category(self):
        ok, msg = validate([{"description": "Do something", "category": "chore"}])
        self.assertFalse(ok)
        self.assertIn("category", msg.lower())

    def test_missing_category(self):
        ok, msg = validate([{"description": "Do something"}])
        self.assertFalse(ok)
        self.assertIn("category", msg.lower())


if __name__ == "__main__":
    unittest.main()
