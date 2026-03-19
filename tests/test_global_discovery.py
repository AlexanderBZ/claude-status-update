"""Unit tests for multi-project discovery functions in status_update_parser."""

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from status_update_parser import (
    derive_project_name,
    discover_active_projects,
    main,
    resolve_project_path,
    write_signals_file,
)


class TestResolveProjectPath(unittest.TestCase):
    def test_extracts_cwd_from_first_entry(self):
        with tempfile.TemporaryDirectory() as d:
            jsonl = Path(d) / "session.jsonl"
            jsonl.write_text(json.dumps({"cwd": "/Users/foo/bar", "type": "user"}) + "\n")
            result = resolve_project_path(Path(d))
            self.assertEqual(result, "/Users/foo/bar")

    def test_returns_none_for_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            result = resolve_project_path(Path(d))
            self.assertIsNone(result)

    def test_returns_none_for_malformed_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            jsonl = Path(d) / "session.jsonl"
            jsonl.write_text("not json at all\n")
            result = resolve_project_path(Path(d))
            self.assertIsNone(result)


class TestDeriveProjectName(unittest.TestCase):
    def test_basic_path(self):
        self.assertEqual(derive_project_name("/Users/foo/bar"), "bar")

    def test_trailing_slash(self):
        self.assertEqual(derive_project_name("/Users/foo/bar/"), "bar")


class TestDiscoverActiveProjects(unittest.TestCase):
    def test_finds_projects_with_recent_sessions(self):
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        with tempfile.TemporaryDirectory() as base:
            base_path = Path(base)

            # Active project with a recent session
            active = base_path / "project-active"
            active.mkdir()
            active_jsonl = active / "session1.jsonl"
            active_jsonl.write_text(
                json.dumps({"cwd": "/home/user/active-project", "type": "user"}) + "\n"
            )
            recent_ts = (now - timedelta(hours=2)).timestamp()
            os.utime(active_jsonl, (recent_ts, recent_ts))

            # Stale project with an old session
            stale = base_path / "project-stale"
            stale.mkdir()
            stale_jsonl = stale / "session2.jsonl"
            stale_jsonl.write_text(
                json.dumps({"cwd": "/home/user/stale-project", "type": "user"}) + "\n"
            )
            old_ts = (now - timedelta(hours=48)).timestamp()
            os.utime(stale_jsonl, (old_ts, old_ts))

            results = discover_active_projects(base_path, cutoff)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["project_name"], "active-project")
            self.assertEqual(results[0]["project_dir"], active)
            self.assertEqual(results[0]["recent_sessions"], [active_jsonl])

    def test_skips_empty_project_dirs(self):
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        with tempfile.TemporaryDirectory() as base:
            empty = Path(base) / "empty-project"
            empty.mkdir()

            results = discover_active_projects(Path(base), cutoff)
            self.assertEqual(results, [])

    def test_returns_empty_when_no_projects(self):
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        with tempfile.TemporaryDirectory() as base:
            results = discover_active_projects(Path(base), cutoff)
            self.assertEqual(results, [])


class TestGlobalMain(unittest.TestCase):
    def test_global_mode_collects_sessions_from_multiple_projects(self):
        now = datetime.now(timezone.utc)

        with tempfile.TemporaryDirectory() as base:
            base_path = Path(base)

            # Project A
            proj_a = base_path / "project-a"
            proj_a.mkdir()
            session_a = proj_a / "sess_a.jsonl"
            entry_a = {
                "type": "user",
                "cwd": "/home/user/alpha",
                "timestamp": "2026-03-15T10:00:00Z",
                "message": {"content": "Fix the login bug"},
            }
            session_a.write_text(json.dumps(entry_a) + "\n")
            recent_ts = (now - timedelta(hours=1)).timestamp()
            os.utime(session_a, (recent_ts, recent_ts))

            # Project B
            proj_b = base_path / "project-b"
            proj_b.mkdir()
            session_b = proj_b / "sess_b.jsonl"
            entry_b = {
                "type": "user",
                "cwd": "/home/user/beta",
                "timestamp": "2026-03-15T11:00:00Z",
                "message": {"content": "Add new dashboard"},
            }
            session_b.write_text(json.dumps(entry_b) + "\n")
            os.utime(session_b, (recent_ts, recent_ts))

            output_path = base_path / "output" / "signals.json"

            with unittest.mock.patch(
                "sys.argv",
                ["prog", "--global", "--base-dir", str(base_path), "--output", str(output_path)],
            ):
                main()

            self.assertTrue(output_path.exists())
            with open(output_path, "r") as f:
                data = json.load(f)

            self.assertIn("sessions", data)
            sessions = data["sessions"]
            self.assertEqual(len(sessions), 2)

            project_names = {s["project_name"] for s in sessions}
            self.assertEqual(project_names, {"alpha", "beta"})


if __name__ == "__main__":
    unittest.main()
