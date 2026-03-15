"""Unit tests for file discovery functions in status_update_parser."""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from status_update_parser import (
    derive_slug,
    find_project_dir,
    find_recent_sessions,
    get_file_mtime,
)


class TestDeriveSlug(unittest.TestCase):
    def test_derive_slug_basic(self):
        self.assertEqual(derive_slug("/Users/foo/bar"), "-Users-foo-bar")

    def test_derive_slug_with_dot(self):
        self.assertEqual(derive_slug("/Users/foo/.claude"), "-Users-foo--claude")

    def test_derive_slug_with_spaces(self):
        self.assertEqual(derive_slug("/Users/foo/My Project"), "-Users-foo-My-Project")

    def test_derive_slug_windows_path(self):
        self.assertEqual(derive_slug("D:\\Users\\foo\\bar"), "D:-Users-foo-bar")


class TestFindProjectDir(unittest.TestCase):
    def test_find_project_dir_exists(self):
        with tempfile.TemporaryDirectory() as base:
            slug = "-Users-foo-bar"
            project = Path(base) / slug
            project.mkdir()
            result = find_project_dir(slug, Path(base))
            self.assertEqual(result, project)

    def test_find_project_dir_missing(self):
        with tempfile.TemporaryDirectory() as base:
            result = find_project_dir("-nonexistent-slug", Path(base))
            self.assertIsNone(result)


class TestGetFileMtime(unittest.TestCase):
    def test_returns_utc_aware_datetime(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            f.write(b"data\n")
            path = Path(f.name)
        try:
            result = get_file_mtime(path)
            self.assertIsNotNone(result.tzinfo)
            self.assertEqual(result.tzinfo, timezone.utc)
        finally:
            path.unlink()

    def test_matches_set_mtime(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            f.write(b"data\n")
            path = Path(f.name)
        try:
            target = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
            os.utime(path, (target.timestamp(), target.timestamp()))
            result = get_file_mtime(path)
            self.assertEqual(result, target)
        finally:
            path.unlink()


class TestFindRecentSessions(unittest.TestCase):
    def test_filters_old_files(self):
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        with tempfile.TemporaryDirectory() as d:
            project = Path(d)

            recent = project / "recent.jsonl"
            recent.write_text("data\n")
            recent_ts = (now - timedelta(hours=2)).timestamp()
            os.utime(recent, (recent_ts, recent_ts))

            old = project / "old.jsonl"
            old.write_text("data\n")
            old_ts = (now - timedelta(hours=48)).timestamp()
            os.utime(old, (old_ts, old_ts))

            results = find_recent_sessions(project, cutoff)
            self.assertEqual(results, [recent])

    def test_skips_directories(self):
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        with tempfile.TemporaryDirectory() as d:
            project = Path(d)

            session_file = project / "session.jsonl"
            session_file.write_text("data\n")

            subdir = project / "subdir.jsonl"
            subdir.mkdir()

            results = find_recent_sessions(project, cutoff)
            self.assertEqual(results, [session_file])

    def test_skips_non_jsonl_files(self):
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        with tempfile.TemporaryDirectory() as d:
            project = Path(d)

            jsonl = project / "session.jsonl"
            jsonl.write_text("data\n")

            other = project / "sessions-index.json"
            other.write_text("{}\n")

            results = find_recent_sessions(project, cutoff)
            self.assertEqual(results, [jsonl])


if __name__ == "__main__":
    unittest.main()
