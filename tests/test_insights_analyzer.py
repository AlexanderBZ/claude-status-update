"""Unit tests for insights_analyzer behavioral pattern detection."""

import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from insights_analyzer import (
    analyze_sessions,
    detect_bash_misuse,
    detect_excessive_exploration,
    detect_repeated_prompts,
    detect_tool_errors,
    detect_user_corrections,
    extract_tool_results,
    extract_tool_uses,
    normalize_message,
)


def make_assistant_tool_use(tool_id, name, tool_input=None, timestamp="2026-03-15T14:00:00Z"):
    """Assistant entry with a single tool_use block."""
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": name,
                    "input": tool_input or {},
                }
            ]
        },
    }


def make_user_tool_result(tool_use_id, is_error=False, timestamp="2026-03-15T14:01:00Z"):
    """User entry with a single tool_result block."""
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": "output"}
    if is_error:
        block["is_error"] = True
    return {
        "type": "user",
        "timestamp": timestamp,
        "message": {"content": [block]},
    }


def make_user_message(content, timestamp="2026-03-15T14:00:00Z"):
    """User entry with plain string content."""
    return {"type": "user", "timestamp": timestamp, "message": {"content": content}}


def write_jsonl(tmpdir, filename, entries):
    """Write entries as JSONL file, return Path."""
    path = Path(tmpdir) / filename
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path


class TestExtractToolUses(unittest.TestCase):
    def test_extracts_tool_use_blocks(self):
        entries = [
            make_assistant_tool_use("t1", "Read", {"file_path": "/foo.py"}),
            make_assistant_tool_use("t2", "Edit", {"file_path": "/bar.py"}),
        ]
        result = extract_tool_uses(entries)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "t1")
        self.assertEqual(result[0]["name"], "Read")
        self.assertEqual(result[0]["input"]["file_path"], "/foo.py")
        self.assertEqual(result[1]["name"], "Edit")

    def test_skips_non_assistant_entries(self):
        entries = [make_user_message("hello")]
        result = extract_tool_uses(entries)
        self.assertEqual(result, [])

    def test_skips_text_blocks(self):
        entry = {
            "type": "assistant",
            "timestamp": "2026-03-15T14:00:00Z",
            "message": {
                "content": [
                    {"type": "text", "text": "Let me read that file."},
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
                ]
            },
        }
        result = extract_tool_uses([entry])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Read")


class TestExtractToolResults(unittest.TestCase):
    def test_extracts_tool_results(self):
        entries = [
            make_user_tool_result("t1", is_error=False),
            make_user_tool_result("t2", is_error=True),
        ]
        result = extract_tool_results(entries)
        self.assertEqual(len(result), 2)
        self.assertFalse(result[0]["is_error"])
        self.assertTrue(result[1]["is_error"])

    def test_skips_non_user_entries(self):
        entries = [make_assistant_tool_use("t1", "Read")]
        result = extract_tool_results(entries)
        self.assertEqual(result, [])


class TestDetectExcessiveExploration(unittest.TestCase):
    def test_triggers_above_threshold(self):
        tool_uses = (
            [{"name": "Read", "id": str(i)} for i in range(8)]
            + [{"name": "Edit", "id": str(i + 8)} for i in range(2)]
        )
        result = detect_excessive_exploration(tool_uses)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "excessive_exploration")
        self.assertAlmostEqual(result["exploration_ratio"], 0.8)

    def test_warning_severity_above_0_8(self):
        tool_uses = (
            [{"name": "Read", "id": str(i)} for i in range(9)]
            + [{"name": "Edit", "id": str(i + 9)} for i in range(1)]
        )
        result = detect_excessive_exploration(tool_uses)
        self.assertIsNotNone(result)
        self.assertEqual(result["severity"], "warning")

    def test_info_severity_at_threshold(self):
        # 8 exploration, 2 action = 0.8, which is NOT > 0.8, so info
        tool_uses = (
            [{"name": "Grep", "id": str(i)} for i in range(8)]
            + [{"name": "Write", "id": str(i + 8)} for i in range(2)]
        )
        result = detect_excessive_exploration(tool_uses)
        self.assertIsNotNone(result)
        self.assertEqual(result["severity"], "info")

    def test_returns_none_below_threshold(self):
        tool_uses = (
            [{"name": "Read", "id": str(i)} for i in range(5)]
            + [{"name": "Edit", "id": str(i + 5)} for i in range(5)]
        )
        result = detect_excessive_exploration(tool_uses)
        self.assertIsNone(result)

    def test_returns_none_below_min_calls(self):
        tool_uses = [{"name": "Read", "id": "1"}, {"name": "Read", "id": "2"}]
        result = detect_excessive_exploration(tool_uses)
        self.assertIsNone(result)

    def test_uncategorized_tools_not_counted(self):
        tool_uses = (
            [{"name": "Read", "id": str(i)} for i in range(8)]
            + [{"name": "Edit", "id": str(i + 8)} for i in range(2)]
            + [{"name": "AskUserQuestion", "id": str(i + 10)} for i in range(20)]
        )
        result = detect_excessive_exploration(tool_uses)
        self.assertIsNotNone(result)
        self.assertEqual(result["total_tool_calls"], 30)
        self.assertAlmostEqual(result["exploration_ratio"], 0.8)


class TestDetectUserCorrections(unittest.TestCase):
    def test_detects_corrections(self):
        messages = [
            ("t1", "No, that's not what I want"),
            ("t2", "Wrong approach"),
            ("t3", "Try again please"),
        ]
        result = detect_user_corrections(messages)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "user_corrections")
        self.assertEqual(result["correction_count"], 3)
        self.assertEqual(len(result["examples"]), 3)

    def test_returns_none_below_min(self):
        messages = [("t1", "Wrong approach")]
        result = detect_user_corrections(messages)
        self.assertIsNone(result)

    def test_examples_capped_at_3(self):
        messages = [
            ("t1", "No, don't do that"),
            ("t2", "Wrong"),
            ("t3", "Try again"),
            ("t4", "Undo that"),
            ("t5", "Revert it"),
        ]
        result = detect_user_corrections(messages)
        self.assertIsNotNone(result)
        self.assertEqual(result["correction_count"], 5)
        self.assertEqual(len(result["examples"]), 3)

    def test_no_false_positives_on_normal_messages(self):
        messages = [
            ("t1", "Please add a new feature"),
            ("t2", "Can you fix the login page"),
            ("t3", "Thanks that looks great"),
        ]
        result = detect_user_corrections(messages)
        self.assertIsNone(result)


class TestNormalizeMessage(unittest.TestCase):
    def test_lowercases(self):
        self.assertEqual(normalize_message("Hello World"), "hello world")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_message("  hello  "), "hello")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize_message("hello   world"), "hello world")

    def test_removes_punctuation(self):
        self.assertEqual(normalize_message("hello, world!"), "hello world")

    def test_keeps_alphanumeric(self):
        self.assertEqual(normalize_message("test123"), "test123")


class TestDetectRepeatedPrompts(unittest.TestCase):
    def test_detects_repeated_messages(self):
        messages = [
            ("t1", "Run the test suite please"),
            ("t2", "Run the test suite please"),
            ("t3", "Something different entirely here"),
        ]
        result = detect_repeated_prompts(messages)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "repeated_prompts")
        self.assertEqual(len(result["repeated_groups"]), 1)
        self.assertEqual(result["repeated_groups"][0]["count"], 2)

    def test_skips_short_messages(self):
        messages = [
            ("t1", "yes"),
            ("t2", "yes"),
        ]
        result = detect_repeated_prompts(messages)
        self.assertIsNone(result)

    def test_normalizes_before_comparing(self):
        messages = [
            ("t1", "Run the tests!"),
            ("t2", "run the tests"),
        ]
        result = detect_repeated_prompts(messages)
        self.assertIsNotNone(result)

    def test_returns_none_when_unique(self):
        messages = [
            ("t1", "Fix the login bug in auth module"),
            ("t2", "Add a new feature for user profiles"),
        ]
        result = detect_repeated_prompts(messages)
        self.assertIsNone(result)


class TestDetectToolErrors(unittest.TestCase):
    def test_detects_errors(self):
        tool_uses = [
            {"id": "t1", "name": "Bash"},
            {"id": "t2", "name": "Bash"},
            {"id": "t3", "name": "Read"},
            {"id": "t4", "name": "Read"},
        ]
        tool_results = [
            {"tool_use_id": "t1", "is_error": True, "timestamp": "t"},
            {"tool_use_id": "t2", "is_error": True, "timestamp": "t"},
            {"tool_use_id": "t3", "is_error": True, "timestamp": "t"},
            {"tool_use_id": "t4", "is_error": False, "timestamp": "t"},
        ]
        result = detect_tool_errors(tool_uses, tool_results)
        self.assertIsNotNone(result)
        self.assertEqual(result["total_errors"], 3)
        self.assertEqual(result["errors_by_tool"]["Bash"], 2)
        self.assertEqual(result["errors_by_tool"]["Read"], 1)

    def test_returns_none_below_min(self):
        tool_uses = [{"id": "t1", "name": "Bash"}]
        tool_results = [{"tool_use_id": "t1", "is_error": True, "timestamp": "t"}]
        result = detect_tool_errors(tool_uses, tool_results)
        self.assertIsNone(result)

    def test_warning_severity_above_20_percent(self):
        tool_uses = [{"id": "t{}".format(i), "name": "Bash"} for i in range(5)]
        tool_results = [
            {"tool_use_id": "t{}".format(i), "is_error": i < 3, "timestamp": "t"}
            for i in range(5)
        ]
        result = detect_tool_errors(tool_uses, tool_results)
        self.assertIsNotNone(result)
        self.assertEqual(result["severity"], "warning")


class TestDetectBashMisuse(unittest.TestCase):
    def test_detects_misuse(self):
        tool_uses = [
            {"name": "Bash", "id": "1", "input": {"command": "cat /foo/bar.py"}, "timestamp": "t"},
            {"name": "Bash", "id": "2", "input": {"command": "grep -r 'test' ."}, "timestamp": "t"},
            {"name": "Bash", "id": "3", "input": {"command": "find . -name '*.py'"}, "timestamp": "t"},
            {"name": "Bash", "id": "4", "input": {"command": "npm install"}, "timestamp": "t"},
        ]
        result = detect_bash_misuse(tool_uses)
        self.assertIsNotNone(result)
        self.assertEqual(result["misuse_count"], 3)
        self.assertEqual(result["total_bash_calls"], 4)

    def test_returns_none_below_min(self):
        tool_uses = [
            {"name": "Bash", "id": "1", "input": {"command": "cat foo.py"}, "timestamp": "t"},
        ]
        result = detect_bash_misuse(tool_uses)
        self.assertIsNone(result)

    def test_suggests_correct_tools(self):
        tool_uses = [
            {"name": "Bash", "id": "1", "input": {"command": "cat foo.py"}, "timestamp": "t"},
            {"name": "Bash", "id": "2", "input": {"command": "rg pattern ."}, "timestamp": "t"},
            {"name": "Bash", "id": "3", "input": {"command": "ls src/"}, "timestamp": "t"},
        ]
        result = detect_bash_misuse(tool_uses)
        self.assertIsNotNone(result)
        suggested = {e["suggested_tool"] for e in result["misuse_examples"]}
        self.assertEqual(suggested, {"Read", "Grep", "Glob"})

    def test_examples_capped_at_5(self):
        tool_uses = [
            {"name": "Bash", "id": str(i), "input": {"command": "cat file{}.py".format(i)}, "timestamp": "t"}
            for i in range(10)
        ]
        result = detect_bash_misuse(tool_uses)
        self.assertIsNotNone(result)
        self.assertEqual(len(result["misuse_examples"]), 5)
        self.assertEqual(result["misuse_count"], 10)


class TestAnalyzeSessions(unittest.TestCase):
    def test_full_analysis(self):
        entries = (
            [make_assistant_tool_use("t{}".format(i), "Read") for i in range(9)]
            + [make_assistant_tool_use("t9", "Edit")]
            + [make_user_tool_result("t{}".format(i)) for i in range(10)]
            + [make_user_message("No, that's wrong")]
            + [make_user_message("Wrong approach entirely")]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_jsonl(tmpdir, "session.jsonl", entries)
            result = analyze_sessions([path], days=7)

        self.assertIn("metadata", result)
        self.assertIn("insights", result)
        self.assertIn("summary", result)
        self.assertEqual(result["metadata"]["sessions_analyzed"], 1)
        self.assertEqual(result["metadata"]["time_window_days"], 7)
        self.assertGreater(result["summary"]["total_insights"], 0)

    def test_empty_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_jsonl(tmpdir, "empty.jsonl", [])
            result = analyze_sessions([path], days=7)

        self.assertEqual(result["insights"], [])
        self.assertEqual(result["summary"]["total_insights"], 0)

    def test_metadata_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_jsonl(tmpdir, "s.jsonl", [])
            result = analyze_sessions([path], days=14)

        self.assertIn("generated_at", result["metadata"])
        self.assertIn("project_slug", result["metadata"])
        self.assertEqual(result["metadata"]["time_window_days"], 14)
        self.assertEqual(result["metadata"]["sessions_analyzed"], 1)


class TestMain(unittest.TestCase):
    def test_writes_insights_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "test-project")
            os.makedirs(project_path)

            from status_update_parser import derive_slug
            slug = derive_slug(os.path.abspath(project_path))
            base_dir = os.path.join(tmpdir, "base")
            project_dir = Path(base_dir) / slug
            project_dir.mkdir(parents=True)

            entries = [make_assistant_tool_use("t1", "Read")]
            write_jsonl(project_dir, "session1.jsonl", entries)

            output_path = Path(tmpdir) / "output" / "insights.json"

            test_args = [
                "insights_analyzer.py",
                project_path,
                "--base-dir", base_dir,
                "--output", str(output_path),
                "--days", "7",
            ]

            with patch("sys.argv", test_args):
                captured = io.StringIO()
                with patch("sys.stdout", captured):
                    from insights_analyzer import main
                    main()

            self.assertTrue(output_path.exists())
            with open(output_path) as f:
                data = json.load(f)
            self.assertIn("metadata", data)
            self.assertIn("insights", data)
            self.assertIn("summary", data)


if __name__ == "__main__":
    unittest.main()
