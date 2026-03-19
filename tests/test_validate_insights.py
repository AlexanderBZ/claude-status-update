"""Unit tests for validate_insights schema validation."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from validate_insights import validate


def make_valid_insights():
    """Return a minimal valid insights structure."""
    return {
        "metadata": {
            "generated_at": "2026-03-19T10:00:00Z",
            "project_slug": "-Users-test-project",
            "time_window_days": 7,
            "sessions_analyzed": 3,
            "total_tool_calls": 100,
            "total_user_messages": 20,
        },
        "categories": {
            "exploration_patterns": {
                "triggered": True,
                "severity": "warning",
                "summary": "82% of categorized tool calls were exploration (82 of 100)",
                "statistics": {"exploration_ratio": 0.82},
                "evidence": {"files_read_multiple_times": []},
            },
        },
        "session_profiles": [
            {
                "session_file": "s1.jsonl",
                "tool_calls": 50,
                "exploration_ratio": 0.8,
                "errors": 2,
                "corrections": 1,
            }
        ],
        "summary": {
            "categories_triggered": 1,
            "severity_counts": {"warning": 1},
        },
    }


class TestValidate(unittest.TestCase):
    def test_valid_structure(self):
        ok, msg = validate(make_valid_insights())
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")

    def test_empty_categories_is_valid(self):
        data = make_valid_insights()
        data["categories"] = {}
        data["session_profiles"] = []
        data["summary"]["categories_triggered"] = 0
        data["summary"]["severity_counts"] = {}
        ok, _ = validate(data)
        self.assertTrue(ok)

    def test_not_triggered_category_is_valid(self):
        data = make_valid_insights()
        data["categories"] = {
            "exploration_patterns": {"triggered": False},
        }
        ok, msg = validate(data)
        self.assertTrue(ok, msg)

    def test_all_category_names_valid(self):
        for name in [
            "exploration_patterns",
            "correction_events",
            "repeated_prompts",
            "tool_errors",
            "bash_misuse",
        ]:
            data = make_valid_insights()
            data["categories"] = {
                name: {"triggered": False},
            }
            ok, msg = validate(data)
            self.assertTrue(ok, "category {!r} should be valid: {}".format(name, msg))

    def test_both_severities_valid(self):
        for sev in ["info", "warning"]:
            data = make_valid_insights()
            data["categories"]["exploration_patterns"]["severity"] = sev
            ok, _ = validate(data)
            self.assertTrue(ok)

    def test_not_a_dict(self):
        ok, msg = validate([])
        self.assertFalse(ok)
        self.assertIn("object", msg)

    def test_missing_top_level_key(self):
        for key in ("metadata", "categories", "summary"):
            data = make_valid_insights()
            del data[key]
            ok, msg = validate(data)
            self.assertFalse(ok)
            self.assertIn(key, msg)

    def test_metadata_missing_field(self):
        for field in ("generated_at", "project_slug", "time_window_days",
                       "sessions_analyzed", "total_tool_calls", "total_user_messages"):
            data = make_valid_insights()
            del data["metadata"][field]
            ok, msg = validate(data)
            self.assertFalse(ok)
            self.assertIn(field, msg)

    def test_invalid_category_name(self):
        data = make_valid_insights()
        data["categories"]["invalid_type"] = {"triggered": False}
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("invalid_type", msg)

    def test_invalid_severity(self):
        data = make_valid_insights()
        data["categories"]["exploration_patterns"]["severity"] = "critical"
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("critical", msg)

    def test_empty_summary_field(self):
        data = make_valid_insights()
        data["categories"]["exploration_patterns"]["summary"] = ""
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("summary", msg)

    def test_missing_summary_field(self):
        data = make_valid_insights()
        del data["categories"]["exploration_patterns"]["summary"]
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("summary", msg)

    def test_missing_categories_triggered(self):
        data = make_valid_insights()
        del data["summary"]["categories_triggered"]
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("categories_triggered", msg)

    def test_missing_severity_counts(self):
        data = make_valid_insights()
        del data["summary"]["severity_counts"]
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("severity_counts", msg)

    def test_triggered_category_missing_statistics(self):
        data = make_valid_insights()
        del data["categories"]["exploration_patterns"]["statistics"]
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("statistics", msg)

    def test_triggered_category_missing_evidence(self):
        data = make_valid_insights()
        del data["categories"]["exploration_patterns"]["evidence"]
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("evidence", msg)


if __name__ == "__main__":
    unittest.main()
