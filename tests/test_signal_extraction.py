"""Unit tests for signal extraction functions in status_update_parser."""

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
from status_update_parser import (
    derive_slug,
    parse_jsonl_entries,
    extract_user_messages,
    extract_ask_user_responses,
    build_session_block,
    write_signals_file,
)


def make_user_entry(content, timestamp="2026-03-15T14:00:00Z"):
    """User entry with string content (plain user message)."""
    return {"type": "user", "timestamp": timestamp, "message": {"content": content}}


def make_user_tool_result_entry(tool_use_id, result_content, timestamp="2026-03-15T14:00:00Z", is_error=False):
    """User entry with tool_result array content."""
    item = {"type": "tool_result", "tool_use_id": tool_use_id, "content": result_content}
    if is_error:
        item["is_error"] = True
    return {"type": "user", "timestamp": timestamp, "message": {"content": [item]}}


def make_assistant_entry(content_blocks, timestamp="2026-03-15T14:00:00Z"):
    """Assistant entry with array of content blocks."""
    return {"type": "assistant", "timestamp": timestamp, "message": {"content": content_blocks}}


def make_tool_use_block(tool_id, name):
    """A tool_use content block for assistant entries."""
    return {"type": "tool_use", "id": tool_id, "name": name, "input": {}}


def write_jsonl(tmpdir, filename, entries):
    """Write entries as JSONL file, return Path."""
    path = Path(tmpdir) / filename
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path


class TestParseJsonlEntries(unittest.TestCase):
    def test_valid_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = [{"a": 1}, {"b": 2}, {"c": 3}]
            path = write_jsonl(tmpdir, "valid.jsonl", entries)
            result = parse_jsonl_entries(path)
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0], {"a": 1})
            self.assertEqual(result[2], {"c": 3})

    def test_malformed_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mixed.jsonl"
            with open(path, "w") as f:
                f.write('{"valid": true}\n')
                f.write("not json at all\n")
                f.write('{"also_valid": 42}\n')
            result = parse_jsonl_entries(path)
            self.assertEqual(len(result), 2)
            self.assertTrue(result[0]["valid"])
            self.assertEqual(result[1]["also_valid"], 42)

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "empty.jsonl"
            path.write_text("")
            result = parse_jsonl_entries(path)
            self.assertEqual(result, [])


class TestExtractUserMessages(unittest.TestCase):
    def test_string_content(self):
        entries = [make_user_entry("Fix the login bug", "2026-03-15T14:00:00Z")]
        result = extract_user_messages(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ("2026-03-15T14:00:00Z", "Fix the login bug"))

    def test_skips_tool_results(self):
        entries = [make_user_tool_result_entry("tool1", "some result")]
        result = extract_user_messages(entries)
        self.assertEqual(result, [])

    def test_skips_non_user_types(self):
        entries = [make_assistant_entry([{"type": "text", "text": "Hello"}])]
        result = extract_user_messages(entries)
        self.assertEqual(result, [])

    def test_filters_continuation_noise(self):
        entries = [
            make_user_entry(
                "This session is being continued from a previous conversation. Here is the summary..."
            )
        ]
        result = extract_user_messages(entries)
        self.assertEqual(result, [])

    def test_filters_command_tags(self):
        for prefix in [
            "<command-name>",
            "<local-command-stdout>",
            "<local-command-stderr>",
            "<local-command-caveat>",
        ]:
            entries = [make_user_entry(prefix + " some content")]
            result = extract_user_messages(entries)
            self.assertEqual(result, [], f"Should have filtered message starting with {prefix}")

    def test_strips_at_mentions(self):
        entries = [make_user_entry("Fix @src/auth.py and @lib/utils.py")]
        result = extract_user_messages(entries)
        self.assertEqual(len(result), 1)
        _, content = result[0]
        self.assertNotIn("@src/auth.py", content)
        self.assertNotIn("@lib/utils.py", content)
        self.assertEqual(content, "Fix and")

    def test_discards_empty_after_strip(self):
        entries = [make_user_entry("@file.py")]
        result = extract_user_messages(entries)
        self.assertEqual(result, [])


class TestExtractAskUserResponses(unittest.TestCase):
    def test_matching_responses(self):
        entries = [
            make_assistant_entry(
                [make_tool_use_block("ask1", "AskUserQuestion")],
                "2026-03-15T14:00:00Z",
            ),
            make_user_tool_result_entry("ask1", "Yes, proceed", "2026-03-15T14:01:00Z"),
        ]
        result = extract_ask_user_responses(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ("2026-03-15T14:01:00Z", "Yes, proceed"))

    def test_ignores_non_ask_results(self):
        entries = [
            make_assistant_entry(
                [make_tool_use_block("tool1", "Read")],
                "2026-03-15T14:00:00Z",
            ),
            make_user_tool_result_entry("tool1", "file contents", "2026-03-15T14:01:00Z"),
        ]
        result = extract_ask_user_responses(entries)
        self.assertEqual(result, [])

    def test_handles_string_content(self):
        entries = [
            make_assistant_entry([make_tool_use_block("ask2", "AskUserQuestion")]),
            make_user_tool_result_entry("ask2", "plain string answer"),
        ]
        result = extract_ask_user_responses(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "plain string answer")

    def test_handles_array_content(self):
        entries = [
            make_assistant_entry([make_tool_use_block("ask3", "AskUserQuestion")]),
            make_user_tool_result_entry(
                "ask3", [{"type": "text", "text": "Yes"}]
            ),
        ]
        result = extract_ask_user_responses(entries)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "Yes")

    def test_skips_error_results(self):
        entries = [
            make_assistant_entry([make_tool_use_block("ask4", "AskUserQuestion")]),
            make_user_tool_result_entry("ask4", "error output", is_error=True),
        ]
        result = extract_ask_user_responses(entries)
        self.assertEqual(result, [])


class TestBuildSessionBlock(unittest.TestCase):
    def test_returns_dict_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = [make_user_entry("Implement the feature", "2026-03-15T14:00:00Z")]
            path = write_jsonl(tmpdir, "session.jsonl", entries)
            parsed = parse_jsonl_entries(path)
            block = build_session_block(path, parsed)
            self.assertIsNotNone(block)
            self.assertIn("session_file", block)
            self.assertIn("timestamp", block)
            self.assertIn("signals", block)
            self.assertEqual(block["session_file"], "session.jsonl")
            self.assertEqual(len(block["signals"]), 1)
            self.assertEqual(block["signals"][0]["content"], "Implement the feature")
            self.assertEqual(block["signals"][0]["type"], "user")

    def test_returns_none_for_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = [
                make_assistant_entry([{"type": "text", "text": "Here is the result"}])
            ]
            path = write_jsonl(tmpdir, "assistant_only.jsonl", entries)
            parsed = parse_jsonl_entries(path)
            block = build_session_block(path, parsed)
            self.assertIsNone(block)

    def test_sorts_by_timestamp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            entries = [
                make_user_entry("Second message", "2026-03-15T15:00:00Z"),
                make_user_entry("First message", "2026-03-15T13:00:00Z"),
                make_user_entry("Third message", "2026-03-15T16:00:00Z"),
            ]
            path = write_jsonl(tmpdir, "unordered.jsonl", entries)
            parsed = parse_jsonl_entries(path)
            block = build_session_block(path, parsed)
            self.assertIsNotNone(block)
            timestamps = [s["timestamp"] for s in block["signals"]]
            self.assertEqual(timestamps, sorted(timestamps))
            self.assertEqual(block["signals"][0]["content"], "First message")


class TestWriteSignalsFile(unittest.TestCase):
    def test_writes_valid_json(self):
        sessions = [{"session_file": "s.jsonl", "timestamp": "t", "signals": []}]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "signals.json"
            write_signals_file(sessions, path)
            with open(path) as f:
                data = json.load(f)
            self.assertIn("sessions", data)
            self.assertEqual(len(data["sessions"]), 1)

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "deep" / "signals.json"
            sessions = [{"session_file": "s.jsonl", "timestamp": "t", "signals": []}]
            write_signals_file(sessions, path)
            self.assertTrue(path.exists())

    def test_output_is_parseable(self):
        sessions = [
            {"session_file": "a.jsonl", "timestamp": "t1", "signals": [{"type": "user", "content": "hello"}]},
            {"session_file": "b.jsonl", "timestamp": "t2", "signals": []},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.json"
            write_signals_file(sessions, path)
            with open(path) as f:
                raw = f.read()
            data = json.loads(raw)
            self.assertEqual(data["sessions"], sessions)


class TestMainExtract(unittest.TestCase):
    def test_writes_signals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = os.path.join(tmpdir, "test-project")
            os.makedirs(project_path)

            slug = derive_slug(os.path.abspath(project_path))
            base_dir = os.path.join(tmpdir, "base")
            project_dir = Path(base_dir) / slug
            project_dir.mkdir(parents=True)

            entries = [make_user_entry("Fix the auth bug", "2026-03-15T14:00:00Z")]
            write_jsonl(project_dir, "session1.jsonl", entries)

            output_path = Path(tmpdir) / "output" / "signals.json"

            test_args = [
                "status_update_parser.py",
                project_path,
                "--base-dir", base_dir,
                "--output", str(output_path),
            ]

            with patch("sys.argv", test_args):
                captured = io.StringIO()
                with patch("sys.stdout", captured):
                    from status_update_parser import main
                    main()

            self.assertTrue(output_path.exists())
            with open(output_path) as f:
                data = json.load(f)
            self.assertIn("sessions", data)
            self.assertEqual(len(data["sessions"]), 1)
            self.assertEqual(data["sessions"][0]["signals"][0]["content"], "Fix the auth bug")


if __name__ == "__main__":
    unittest.main()
