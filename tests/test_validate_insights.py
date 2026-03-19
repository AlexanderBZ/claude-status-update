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
        },
        "insights": [
            {
                "type": "excessive_exploration",
                "severity": "warning",
                "recommendation": "80% of tool calls were exploration.",
            }
        ],
        "summary": {
            "total_insights": 1,
            "severity_counts": {"warning": 1},
        },
    }


class TestValidate(unittest.TestCase):
    def test_valid_structure(self):
        ok, msg = validate(make_valid_insights())
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")

    def test_empty_insights_is_valid(self):
        data = make_valid_insights()
        data["insights"] = []
        data["summary"]["total_insights"] = 0
        data["summary"]["severity_counts"] = {}
        ok, _ = validate(data)
        self.assertTrue(ok)

    def test_all_insight_types_valid(self):
        for itype in [
            "excessive_exploration",
            "user_corrections",
            "repeated_prompts",
            "tool_errors",
            "bash_misuse",
        ]:
            data = make_valid_insights()
            data["insights"][0]["type"] = itype
            ok, msg = validate(data)
            self.assertTrue(ok, "type {!r} should be valid: {}".format(itype, msg))

    def test_both_severities_valid(self):
        for sev in ["info", "warning"]:
            data = make_valid_insights()
            data["insights"][0]["severity"] = sev
            ok, _ = validate(data)
            self.assertTrue(ok)

    def test_not_a_dict(self):
        ok, msg = validate([])
        self.assertFalse(ok)
        self.assertIn("object", msg)

    def test_missing_top_level_key(self):
        for key in ("metadata", "insights", "summary"):
            data = make_valid_insights()
            del data[key]
            ok, msg = validate(data)
            self.assertFalse(ok)
            self.assertIn(key, msg)

    def test_metadata_missing_field(self):
        for field in ("generated_at", "project_slug", "time_window_days", "sessions_analyzed"):
            data = make_valid_insights()
            del data["metadata"][field]
            ok, msg = validate(data)
            self.assertFalse(ok)
            self.assertIn(field, msg)

    def test_invalid_insight_type(self):
        data = make_valid_insights()
        data["insights"][0]["type"] = "invalid_type"
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("invalid_type", msg)

    def test_invalid_severity(self):
        data = make_valid_insights()
        data["insights"][0]["severity"] = "critical"
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("critical", msg)

    def test_empty_recommendation(self):
        data = make_valid_insights()
        data["insights"][0]["recommendation"] = ""
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("recommendation", msg)

    def test_missing_recommendation(self):
        data = make_valid_insights()
        del data["insights"][0]["recommendation"]
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("recommendation", msg)

    def test_missing_summary_total(self):
        data = make_valid_insights()
        del data["summary"]["total_insights"]
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("total_insights", msg)

    def test_missing_severity_counts(self):
        data = make_valid_insights()
        del data["summary"]["severity_counts"]
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("severity_counts", msg)


if __name__ == "__main__":
    unittest.main()
