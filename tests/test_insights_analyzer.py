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
    build_session_profiles,
    detect_bash_misuse,
    detect_excessive_exploration,
    detect_repeated_prompts,
    detect_tool_errors,
    detect_user_corrections,
    extract_conversation_turns,
    extract_tool_results,
    extract_tool_uses,
    normalize_message,
    summarize_tool_input,
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


def make_user_tool_result(tool_use_id, is_error=False, error_content="", timestamp="2026-03-15T14:01:00Z"):
    """User entry with a single tool_result block."""
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": error_content or "output"}
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
            make_user_tool_result("t2", is_error=True, error_content="file not found"),
        ]
        result = extract_tool_results(entries)
        self.assertEqual(len(result), 2)
        self.assertFalse(result[0]["is_error"])
        self.assertEqual(result[0]["error_content"], "")
        self.assertTrue(result[1]["is_error"])
        self.assertEqual(result[1]["error_content"], "file not found")

    def test_skips_non_user_entries(self):
        entries = [make_assistant_tool_use("t1", "Read")]
        result = extract_tool_results(entries)
        self.assertEqual(result, [])

    def test_error_content_from_list(self):
        entry = {
            "type": "user",
            "timestamp": "2026-03-15T14:01:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "is_error": True,
                        "content": [{"text": "Error: "}],
                    }
                ]
            },
        }
        result = extract_tool_results([entry])
        self.assertEqual(result[0]["error_content"], "Error: ")


class TestExtractConversationTurns(unittest.TestCase):
    def test_groups_prompt_and_actions(self):
        entries = [
            make_user_message("Fix the auth bug", "2026-03-15T14:00:00Z"),
            make_assistant_tool_use("t1", "Read", {"file_path": "/auth.py"}, "2026-03-15T14:00:01Z"),
            make_assistant_tool_use("t2", "Edit", {"file_path": "/auth.py"}, "2026-03-15T14:00:02Z"),
        ]
        turns = extract_conversation_turns(entries)
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["prompt"], "Fix the auth bug")
        self.assertEqual(len(turns[0]["actions"]), 2)
        self.assertEqual(turns[0]["actions"][0]["tool"], "Read")
        self.assertEqual(turns[0]["actions"][1]["tool"], "Edit")

    def test_tool_results_do_not_start_new_turn(self):
        entries = [
            make_user_message("Fix it", "2026-03-15T14:00:00Z"),
            make_assistant_tool_use("t1", "Read", {}, "2026-03-15T14:00:01Z"),
            make_user_tool_result("t1", timestamp="2026-03-15T14:00:02Z"),
            make_assistant_tool_use("t2", "Edit", {}, "2026-03-15T14:00:03Z"),
        ]
        turns = extract_conversation_turns(entries)
        self.assertEqual(len(turns), 1)
        self.assertEqual(len(turns[0]["actions"]), 2)

    def test_new_user_message_starts_new_turn(self):
        entries = [
            make_user_message("First task", "2026-03-15T14:00:00Z"),
            make_assistant_tool_use("t1", "Read", {}, "2026-03-15T14:00:01Z"),
            make_user_message("Second task", "2026-03-15T14:01:00Z"),
            make_assistant_tool_use("t2", "Edit", {}, "2026-03-15T14:01:01Z"),
        ]
        turns = extract_conversation_turns(entries)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["prompt"], "First task")
        self.assertEqual(turns[1]["prompt"], "Second task")


class TestSummarizeToolInput(unittest.TestCase):
    def test_read(self):
        self.assertEqual(summarize_tool_input("Read", {"file_path": "/foo.py"}), "/foo.py")

    def test_grep(self):
        self.assertEqual(summarize_tool_input("Grep", {"pattern": "auth"}), "auth")

    def test_bash(self):
        self.assertEqual(summarize_tool_input("Bash", {"command": "npm test"}), "npm test")

    def test_bash_truncates(self):
        long_cmd = "x" * 200
        result = summarize_tool_input("Bash", {"command": long_cmd})
        self.assertEqual(len(result), 100)

    def test_unknown_tool(self):
        self.assertEqual(summarize_tool_input("AskUser", {}), "AskUser")


class TestDetectExcessiveExploration(unittest.TestCase):
    def test_triggers_above_threshold(self):
        tool_uses = (
            [{"name": "Read", "id": str(i), "input": {}} for i in range(8)]
            + [{"name": "Edit", "id": str(i + 8), "input": {}} for i in range(2)]
        )
        result = detect_excessive_exploration(tool_uses, [])
        self.assertTrue(result["triggered"])
        self.assertAlmostEqual(result["statistics"]["exploration_ratio"], 0.8)
        self.assertIn("evidence", result)

    def test_warning_severity_above_0_8(self):
        tool_uses = (
            [{"name": "Read", "id": str(i), "input": {}} for i in range(9)]
            + [{"name": "Edit", "id": str(i + 9), "input": {}} for i in range(1)]
        )
        result = detect_excessive_exploration(tool_uses, [])
        self.assertTrue(result["triggered"])
        self.assertEqual(result["severity"], "warning")

    def test_info_severity_at_threshold(self):
        tool_uses = (
            [{"name": "Grep", "id": str(i), "input": {}} for i in range(8)]
            + [{"name": "Write", "id": str(i + 8), "input": {}} for i in range(2)]
        )
        result = detect_excessive_exploration(tool_uses, [])
        self.assertTrue(result["triggered"])
        self.assertEqual(result["severity"], "info")

    def test_not_triggered_below_threshold(self):
        tool_uses = (
            [{"name": "Read", "id": str(i), "input": {}} for i in range(5)]
            + [{"name": "Edit", "id": str(i + 5), "input": {}} for i in range(5)]
        )
        result = detect_excessive_exploration(tool_uses, [])
        self.assertFalse(result["triggered"])
        self.assertNotIn("severity", result)

    def test_not_triggered_below_min_calls(self):
        tool_uses = [{"name": "Read", "id": "1", "input": {}}, {"name": "Read", "id": "2", "input": {}}]
        result = detect_excessive_exploration(tool_uses, [])
        self.assertFalse(result["triggered"])

    def test_uncategorized_tools_not_counted(self):
        tool_uses = (
            [{"name": "Read", "id": str(i), "input": {}} for i in range(8)]
            + [{"name": "Edit", "id": str(i + 8), "input": {}} for i in range(2)]
            + [{"name": "AskUserQuestion", "id": str(i + 10), "input": {}} for i in range(20)]
        )
        result = detect_excessive_exploration(tool_uses, [])
        self.assertTrue(result["triggered"])
        self.assertEqual(result["statistics"]["total_tool_calls"], 30)
        self.assertAlmostEqual(result["statistics"]["exploration_ratio"], 0.8)

    def test_files_read_multiple_times(self):
        tool_uses = (
            [{"name": "Read", "id": str(i), "input": {"file_path": "/foo.py"}} for i in range(5)]
            + [{"name": "Read", "id": str(i + 5), "input": {"file_path": "/bar.py"}} for i in range(3)]
            + [{"name": "Read", "id": "r8", "input": {"file_path": "/baz.py"}}]
            + [{"name": "Edit", "id": "e1", "input": {}}]
        )
        result = detect_excessive_exploration(tool_uses, [])
        self.assertTrue(result["triggered"])
        files = result["evidence"]["files_read_multiple_times"]
        self.assertEqual(files[0]["path"], "/foo.py")
        self.assertEqual(files[0]["count"], 5)

    def test_exploration_bursts(self):
        entries = [
            make_user_message("Fix the auth bug", "2026-03-15T14:00:00Z"),
        ] + [
            make_assistant_tool_use("r{}".format(i), "Read", {"file_path": "/f{}.py".format(i)}, "2026-03-15T14:00:0{}Z".format(i + 1))
            for i in range(6)
        ]
        tool_uses = extract_tool_uses(entries)
        # Add an Edit so it triggers
        tool_uses.append({"name": "Edit", "id": "e1", "input": {}})
        # Need enough calls
        tool_uses.extend([{"name": "Read", "id": "extra{}".format(i), "input": {}} for i in range(5)])
        result = detect_excessive_exploration(tool_uses, entries)
        self.assertTrue(result["triggered"])
        bursts = result["evidence"]["exploration_bursts"]
        self.assertGreaterEqual(len(bursts), 1)
        self.assertGreaterEqual(bursts[0]["length"], 5)


class TestDetectUserCorrections(unittest.TestCase):
    def test_detects_corrections(self):
        messages = [
            ("2026-03-15T14:00:00Z", "No, that's not what I want"),
            ("2026-03-15T14:01:00Z", "Wrong approach"),
            ("2026-03-15T14:02:00Z", "Try again please"),
        ]
        result = detect_user_corrections(messages, [])
        self.assertTrue(result["triggered"])
        self.assertEqual(result["statistics"]["correction_count"], 3)
        self.assertEqual(len(result["evidence"]["events"]), 3)

    def test_not_triggered_below_min(self):
        messages = [("2026-03-15T14:00:00Z", "Wrong approach")]
        result = detect_user_corrections(messages, [])
        self.assertFalse(result["triggered"])

    def test_events_capped_at_5(self):
        messages = [
            ("2026-03-15T14:0{}:00Z".format(i), "No, don't do that number {}".format(i))
            for i in range(8)
        ]
        result = detect_user_corrections(messages, [])
        self.assertTrue(result["triggered"])
        self.assertEqual(result["statistics"]["correction_count"], 8)
        self.assertEqual(len(result["evidence"]["events"]), 5)

    def test_no_false_positives_on_normal_messages(self):
        messages = [
            ("t1", "Please add a new feature"),
            ("t2", "Can you fix the login page"),
            ("t3", "Thanks that looks great"),
        ]
        result = detect_user_corrections(messages, [])
        self.assertFalse(result["triggered"])

    def test_sessions_with_corrections(self):
        messages = [
            ("2026-03-15T14:00:00Z", "No, that's wrong"),
            ("2026-03-15T14:01:00Z", "Wrong approach"),
        ]
        session_map = {
            "s1.jsonl": [("2026-03-15T14:00:00Z", "No, that's wrong")],
            "s2.jsonl": [("2026-03-15T14:01:00Z", "Wrong approach")],
            "s3.jsonl": [("2026-03-15T14:02:00Z", "Looks good")],
        }
        result = detect_user_corrections(messages, [], session_map=session_map)
        self.assertTrue(result["triggered"])
        self.assertEqual(result["statistics"]["sessions_with_corrections"], 2)


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
        self.assertTrue(result["triggered"])
        self.assertEqual(result["statistics"]["group_count"], 1)
        self.assertEqual(result["evidence"]["groups"][0]["count"], 2)

    def test_skips_short_messages(self):
        messages = [
            ("t1", "yes"),
            ("t2", "yes"),
        ]
        result = detect_repeated_prompts(messages)
        self.assertFalse(result["triggered"])

    def test_normalizes_before_comparing(self):
        messages = [
            ("t1", "Run the tests!"),
            ("t2", "run the tests"),
        ]
        result = detect_repeated_prompts(messages)
        self.assertTrue(result["triggered"])

    def test_not_triggered_when_unique(self):
        messages = [
            ("t1", "Fix the login bug in auth module"),
            ("t2", "Add a new feature for user profiles"),
        ]
        result = detect_repeated_prompts(messages)
        self.assertFalse(result["triggered"])

    def test_sessions_seen_in(self):
        messages = [
            ("t1", "Run the test suite please"),
            ("t2", "Run the test suite please"),
        ]
        session_map = {
            "s1.jsonl": [("t1", "Run the test suite please")],
            "s2.jsonl": [("t2", "Run the test suite please")],
        }
        result = detect_repeated_prompts(messages, session_map=session_map)
        self.assertTrue(result["triggered"])
        self.assertEqual(result["evidence"]["groups"][0]["sessions_seen_in"], 2)


class TestDetectToolErrors(unittest.TestCase):
    def test_detects_errors(self):
        tool_uses = [
            {"id": "t1", "name": "Bash", "input": {"command": "npm test"}},
            {"id": "t2", "name": "Bash", "input": {"command": "npm build"}},
            {"id": "t3", "name": "Read", "input": {"file_path": "/foo.py"}},
            {"id": "t4", "name": "Read", "input": {"file_path": "/bar.py"}},
        ]
        tool_results = [
            {"tool_use_id": "t1", "is_error": True, "error_content": "exit code 1", "timestamp": "t"},
            {"tool_use_id": "t2", "is_error": True, "error_content": "exit code 1", "timestamp": "t"},
            {"tool_use_id": "t3", "is_error": True, "error_content": "not found", "timestamp": "t"},
            {"tool_use_id": "t4", "is_error": False, "error_content": "", "timestamp": "t"},
        ]
        result = detect_tool_errors(tool_uses, tool_results)
        self.assertTrue(result["triggered"])
        self.assertEqual(result["statistics"]["total_errors"], 3)
        self.assertEqual(result["statistics"]["errors_by_tool"]["Bash"], 2)
        self.assertEqual(result["statistics"]["errors_by_tool"]["Read"], 1)
        self.assertEqual(len(result["evidence"]["error_examples"]), 3)

    def test_not_triggered_below_min(self):
        tool_uses = [{"id": "t1", "name": "Bash", "input": {}}]
        tool_results = [{"tool_use_id": "t1", "is_error": True, "error_content": "", "timestamp": "t"}]
        result = detect_tool_errors(tool_uses, tool_results)
        self.assertFalse(result["triggered"])

    def test_warning_severity_above_20_percent(self):
        tool_uses = [{"id": "t{}".format(i), "name": "Bash", "input": {}} for i in range(5)]
        tool_results = [
            {"tool_use_id": "t{}".format(i), "is_error": i < 3, "error_content": "", "timestamp": "t"}
            for i in range(5)
        ]
        result = detect_tool_errors(tool_uses, tool_results)
        self.assertTrue(result["triggered"])
        self.assertEqual(result["severity"], "warning")

    def test_error_examples_include_input_summary(self):
        tool_uses = [
            {"id": "t{}".format(i), "name": "Bash", "input": {"command": "npm test"}}
            for i in range(4)
        ]
        tool_results = [
            {"tool_use_id": "t{}".format(i), "is_error": True, "error_content": "failed", "timestamp": "t"}
            for i in range(4)
        ]
        result = detect_tool_errors(tool_uses, tool_results)
        self.assertTrue(result["triggered"])
        ex = result["evidence"]["error_examples"][0]
        self.assertEqual(ex["tool"], "Bash")
        self.assertEqual(ex["input_summary"], "npm test")
        self.assertEqual(ex["error_content"], "failed")


class TestDetectBashMisuse(unittest.TestCase):
    def test_detects_misuse(self):
        tool_uses = [
            {"name": "Bash", "id": "1", "input": {"command": "cat /foo/bar.py"}, "timestamp": "t"},
            {"name": "Bash", "id": "2", "input": {"command": "grep -r 'test' ."}, "timestamp": "t"},
            {"name": "Bash", "id": "3", "input": {"command": "find . -name '*.py'"}, "timestamp": "t"},
            {"name": "Bash", "id": "4", "input": {"command": "npm install"}, "timestamp": "t"},
        ]
        result = detect_bash_misuse(tool_uses)
        self.assertTrue(result["triggered"])
        self.assertEqual(result["statistics"]["misuse_count"], 3)
        self.assertEqual(result["statistics"]["total_bash_calls"], 4)

    def test_not_triggered_below_min(self):
        tool_uses = [
            {"name": "Bash", "id": "1", "input": {"command": "cat foo.py"}, "timestamp": "t"},
        ]
        result = detect_bash_misuse(tool_uses)
        self.assertFalse(result["triggered"])

    def test_suggests_correct_tools(self):
        tool_uses = [
            {"name": "Bash", "id": "1", "input": {"command": "cat foo.py"}, "timestamp": "t"},
            {"name": "Bash", "id": "2", "input": {"command": "rg pattern ."}, "timestamp": "t"},
            {"name": "Bash", "id": "3", "input": {"command": "ls src/"}, "timestamp": "t"},
        ]
        result = detect_bash_misuse(tool_uses)
        self.assertTrue(result["triggered"])
        suggested = {e["suggested_tool"] for e in result["evidence"]["examples"]}
        self.assertEqual(suggested, {"Read", "Grep", "Glob"})

    def test_examples_capped_at_5(self):
        tool_uses = [
            {"name": "Bash", "id": str(i), "input": {"command": "cat file{}.py".format(i)}, "timestamp": "t"}
            for i in range(10)
        ]
        result = detect_bash_misuse(tool_uses)
        self.assertTrue(result["triggered"])
        self.assertEqual(len(result["evidence"]["examples"]), 5)
        self.assertEqual(result["statistics"]["misuse_count"], 10)


class TestBuildSessionProfiles(unittest.TestCase):
    def test_basic_profile(self):
        data = [{
            "session_file": "s1.jsonl",
            "tool_uses": [
                {"name": "Read", "id": "1", "input": {}},
                {"name": "Edit", "id": "2", "input": {}},
            ],
            "tool_results": [
                {"tool_use_id": "1", "is_error": False},
                {"tool_use_id": "2", "is_error": True},
            ],
            "user_messages": [("t1", "Wrong approach")],
            "conversation_turns": [],
        }]
        profiles = build_session_profiles(data)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["session_file"], "s1.jsonl")
        self.assertEqual(profiles[0]["tool_calls"], 2)
        self.assertEqual(profiles[0]["exploration_ratio"], 0.5)
        self.assertEqual(profiles[0]["errors"], 1)
        self.assertEqual(profiles[0]["corrections"], 1)

    def test_capped_at_20(self):
        data = [
            {
                "session_file": "s{}.jsonl".format(i),
                "tool_uses": [{"name": "Read", "id": str(i), "input": {}}] * (i + 1),
                "tool_results": [],
                "user_messages": [],
                "conversation_turns": [],
            }
            for i in range(25)
        ]
        profiles = build_session_profiles(data)
        self.assertEqual(len(profiles), 20)
        # Should be sorted by tool_calls descending
        self.assertGreaterEqual(profiles[0]["tool_calls"], profiles[1]["tool_calls"])


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
        self.assertIn("categories", result)
        self.assertIn("session_profiles", result)
        self.assertIn("summary", result)
        self.assertEqual(result["metadata"]["sessions_analyzed"], 1)
        self.assertEqual(result["metadata"]["time_window_days"], 7)
        self.assertIn("total_tool_calls", result["metadata"])
        self.assertIn("total_user_messages", result["metadata"])
        self.assertGreater(result["summary"]["categories_triggered"], 0)

    def test_empty_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_jsonl(tmpdir, "empty.jsonl", [])
            result = analyze_sessions([path], days=7)

        # All categories should be not triggered
        for cat in result["categories"].values():
            self.assertFalse(cat["triggered"])
        self.assertEqual(result["summary"]["categories_triggered"], 0)

    def test_metadata_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_jsonl(tmpdir, "s.jsonl", [])
            result = analyze_sessions([path], days=14)

        self.assertIn("generated_at", result["metadata"])
        self.assertIn("project_slug", result["metadata"])
        self.assertEqual(result["metadata"]["time_window_days"], 14)
        self.assertEqual(result["metadata"]["sessions_analyzed"], 1)
        self.assertEqual(result["metadata"]["total_tool_calls"], 0)
        self.assertEqual(result["metadata"]["total_user_messages"], 0)

    def test_not_triggered_categories_are_minimal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_jsonl(tmpdir, "s.jsonl", [])
            result = analyze_sessions([path], days=7)

        for cat in result["categories"].values():
            self.assertFalse(cat["triggered"])
            # Should only have "triggered" key
            self.assertEqual(set(cat.keys()), {"triggered"})


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
            self.assertIn("categories", data)
            self.assertIn("summary", data)
            self.assertIn("session_profiles", data)


if __name__ == "__main__":
    unittest.main()
