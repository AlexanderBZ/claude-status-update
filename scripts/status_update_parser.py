#!/usr/bin/env python3
"""Discover recent JSONL session files for the current project."""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional


def derive_slug(cwd: str) -> str:
    """Transform a directory path into a project slug."""
    return cwd.replace("/", "-").replace(".", "-").replace(" ", "-")


def find_project_dir(slug: str, base_dir: Path) -> Optional[Path]:
    """Return base_dir/slug as a Path if it exists as a directory, else None."""
    candidate = base_dir / slug
    if candidate.is_dir():
        return candidate
    return None


def get_file_mtime(filepath: Path) -> datetime:
    """Return the file modification time as a timezone-aware UTC datetime."""
    mtime = filepath.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


def find_recent_sessions(project_dir: Path, cutoff: datetime) -> List[Path]:
    """Return sorted list of *.jsonl files modified or timestamped after cutoff."""
    results = []
    for entry in project_dir.iterdir():
        if not entry.is_file() or entry.suffix != ".jsonl":
            continue
        ts = get_file_mtime(entry)
        if ts >= cutoff:
            results.append(entry)
    results.sort()
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Discover recent JSONL session files for the current project."
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=os.getcwd(),
        help="Project directory to discover sessions for. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.home() / ".claude" / "projects",
        help="Base directory containing project slug folders.",
    )
    args = parser.parse_args()

    slug = derive_slug(os.path.abspath(args.project_path))
    project_dir = find_project_dir(slug, args.base_dir)

    if project_dir is None:
        expected = args.base_dir / slug
        print("No project directory found for slug: {}".format(slug), file=sys.stderr)
        print("The script expects a directory at: {}".format(expected), file=sys.stderr)
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for path in find_recent_sessions(project_dir, cutoff):
        print(path)


if __name__ == "__main__":
    main()
