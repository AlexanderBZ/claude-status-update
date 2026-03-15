#!/usr/bin/env python3
"""Discover recent JSONL session files for the current project."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple


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


def parse_jsonl_entries(filepath: Path) -> List[dict]:
    """Read a JSONL file and return a list of parsed entries."""
    entries = []
    with open(filepath, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                print(
                    "Warning: malformed JSON at {}:{}, skipping".format(filepath.name, lineno),
                    file=sys.stderr,
                )
    return entries


_NOISE_PREFIXES = (
    "This session is being continued from a previous conversation",
    "<command-name>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<local-command-caveat>",
)

_AT_MENTION_RE = re.compile(r"@[\w./-]+")


def extract_user_messages(entries: List[dict]) -> List[Tuple[str, str]]:
    """Extract cleaned user messages, filtering noise and at-mentions."""
    results = []
    for entry in entries:
        if entry.get("type") != "user":
            continue
        message = entry.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            continue

        if any(content.startswith(prefix) for prefix in _NOISE_PREFIXES):
            continue

        cleaned = _AT_MENTION_RE.sub("", content)
        cleaned = re.sub(r"  +", " ", cleaned).strip()
        if not cleaned:
            continue

        results.append((entry.get("timestamp", ""), cleaned))
    return results


def extract_ask_user_responses(entries: List[dict]) -> List[Tuple[str, str]]:
    """Extract user responses to AskUserQuestion tool calls."""
    ask_ids = set()
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "AskUserQuestion"
            ):
                ask_ids.add(block.get("id"))

    results = []
    for entry in entries:
        if entry.get("type") != "user":
            continue
        message = entry.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            if block.get("tool_use_id") not in ask_ids:
                continue
            if block.get("is_error"):
                continue

            raw = block.get("content", "")
            if isinstance(raw, str):
                text = raw
            elif isinstance(raw, list):
                text = "".join(
                    item.get("text", "") for item in raw if isinstance(item, dict)
                )
            else:
                continue

            if text:
                results.append((entry.get("timestamp", ""), text))
    return results


def build_session_block(session_path: Path, entries: List[dict]) -> Optional[dict]:
    """Build a session block with merged and sorted signals."""
    user_msgs = extract_user_messages(entries)
    ask_responses = extract_ask_user_responses(entries)

    signals = [
        {"type": "user", "timestamp": ts, "content": content}
        for ts, content in user_msgs
    ] + [
        {"type": "ask", "timestamp": ts, "content": content}
        for ts, content in ask_responses
    ]

    if not signals:
        return None

    signals.sort(key=lambda s: s["timestamp"])

    return {
        "session_file": session_path.name,
        "timestamp": signals[0]["timestamp"],
        "signals": signals,
    }


def write_signals_file(sessions: List[dict], output_path: Path) -> Path:
    """Write extracted signals to a JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"sessions": sessions}, f, indent=2)
        f.write("\n")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Extract user signals from Claude Code session traces."
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=os.getcwd(),
        help="Project directory. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.home() / ".claude" / "projects",
        help="Base directory containing project slug folders.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd() / ".status-update" / "signals.json",
        help="Path to write the extracted signals JSON file.",
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
    session_paths = find_recent_sessions(project_dir, cutoff)

    sessions = []
    for path in session_paths:
        entries = parse_jsonl_entries(path)
        block = build_session_block(path, entries)
        if block is not None:
            sessions.append(block)
    out = write_signals_file(sessions, args.output)
    print(out)


if __name__ == "__main__":
    main()
