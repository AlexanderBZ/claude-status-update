#!/usr/bin/env python3
"""Analyze Claude Code session traces to detect behavioral patterns."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from status_update_parser import (
    derive_slug,
    extract_user_messages,
    find_project_dir,
    find_recent_sessions,
    parse_jsonl_entries,
)

EXPLORATION_TOOLS = {"Glob", "Grep", "Read", "ToolSearch"}
ACTION_TOOLS = {"Edit", "Write", "Bash"}

CORRECTION_PATTERNS = [
    r"(?i)\bno[,.]?\s+(do|don'?t|that|this|not|wrong|stop|I\s)",
    r"(?i)\bwrong\b",
    r"(?i)\bthat'?s not what i\b",
    r"(?i)\bundo\b",
    r"(?i)\brevert\b",
    r"(?i)\btry again\b",
    r"(?i)\bi said\b",
    r"(?i)\bnot what i asked\b",
    r"(?i)\bstart over\b",
    r"(?i)\bactually[,]\s",
]

BASH_MISUSE_PATTERNS = [
    (r"^\s*cat\s", "Read"),
    (r"^\s*head\s", "Read"),
    (r"^\s*tail\s", "Read"),
    (r"^\s*grep\s", "Grep"),
    (r"^\s*rg\s", "Grep"),
    (r"^\s*find\s", "Glob"),
    (r"^\s*ls\s", "Glob"),
]


def extract_tool_uses(entries: List[dict]) -> List[dict]:
    """Extract tool_use blocks from assistant entries."""
    results = []
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                results.append({
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "input": block.get("input", {}),
                    "timestamp": entry.get("timestamp", ""),
                })
    return results


def extract_tool_results(entries: List[dict]) -> List[dict]:
    """Extract tool_result blocks from user entries."""
    results = []
    for entry in entries:
        if entry.get("type") != "user":
            continue
        message = entry.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                results.append({
                    "tool_use_id": block.get("tool_use_id", ""),
                    "is_error": bool(block.get("is_error", False)),
                    "timestamp": entry.get("timestamp", ""),
                })
    return results


def detect_excessive_exploration(
    tool_uses: List[dict], threshold: float = 0.7, min_calls: int = 10
) -> Optional[dict]:
    """Detect when exploration tools dominate over action tools."""
    exploration_count = sum(1 for t in tool_uses if t["name"] in EXPLORATION_TOOLS)
    action_count = sum(1 for t in tool_uses if t["name"] in ACTION_TOOLS)
    total_categorized = exploration_count + action_count

    if total_categorized < min_calls:
        return None

    exploration_ratio = exploration_count / total_categorized
    if exploration_ratio <= threshold:
        return None

    return {
        "type": "excessive_exploration",
        "severity": "warning" if exploration_ratio > 0.8 else "info",
        "exploration_ratio": exploration_ratio,
        "exploration_count": exploration_count,
        "action_count": action_count,
        "total_tool_calls": len(tool_uses),
        "recommendation": (
            "{:.0%} of tool calls were spent searching or reading files. "
            "Consider adding more context to your CLAUDE.md or providing "
            "specific file paths in your prompts to reduce exploration overhead."
        ).format(exploration_ratio),
    }


def detect_user_corrections(
    user_messages: List[Tuple[str, str]], min_corrections: int = 2
) -> Optional[dict]:
    """Detect messages where the user corrected Claude."""
    compiled = [re.compile(p) for p in CORRECTION_PATTERNS]
    corrections = []

    for timestamp, content in user_messages:
        if any(pat.search(content) for pat in compiled):
            corrections.append({"timestamp": timestamp, "content": content})

    if len(corrections) < min_corrections:
        return None

    examples = [c["content"] for c in corrections[:3]]
    return {
        "type": "user_corrections",
        "severity": "warning",
        "correction_count": len(corrections),
        "examples": examples,
        "recommendation": (
            "Claude misunderstood your intent {} times across recent sessions. "
            "Consider adding a Gotchas section to CLAUDE.md with examples of "
            "common misunderstandings to prevent them."
        ).format(len(corrections)),
    }


def normalize_message(text: str) -> str:
    """Lowercase, strip, collapse whitespace, remove non-alphanumeric chars."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_repeated_prompts(
    user_messages: List[Tuple[str, str]], min_occurrences: int = 2
) -> Optional[dict]:
    """Detect messages the user sent multiple times."""
    groups: Dict[str, List[str]] = {}

    for _timestamp, content in user_messages:
        normalized = normalize_message(content)
        if len(normalized) < 10:
            continue
        groups.setdefault(normalized, []).append(content)

    repeated = [
        {"normalized": norm, "count": len(originals), "example": originals[0]}
        for norm, originals in groups.items()
        if len(originals) >= min_occurrences
    ]

    if not repeated:
        return None

    example_tasks = ", ".join(g["example"][:60] for g in repeated[:3])
    return {
        "type": "repeated_prompts",
        "severity": "info",
        "repeated_groups": repeated,
        "recommendation": (
            "You repeated similar prompts multiple times. Consider creating "
            "Claude Code slash commands for frequent tasks like: {}."
        ).format(example_tasks),
    }


def detect_tool_errors(
    tool_uses: List[dict],
    tool_results: List[dict],
    min_errors: int = 3,
) -> Optional[dict]:
    """Detect high tool error rates, grouped by tool name."""
    id_to_name = {t["id"]: t["name"] for t in tool_uses}
    errors_by_tool: Dict[str, int] = {}
    total_errors = 0

    for result in tool_results:
        if result["is_error"]:
            tool_name = id_to_name.get(result["tool_use_id"], "unknown")
            errors_by_tool[tool_name] = errors_by_tool.get(tool_name, 0) + 1
            total_errors += 1

    if total_errors < min_errors:
        return None

    total_tool_calls = len(tool_results)
    error_rate = total_errors / total_tool_calls if total_tool_calls > 0 else 0.0

    top_tool = max(errors_by_tool, key=errors_by_tool.get)
    top_count = errors_by_tool[top_tool]

    return {
        "type": "tool_errors",
        "severity": "warning" if error_rate > 0.2 else "info",
        "total_errors": total_errors,
        "total_tool_calls": total_tool_calls,
        "error_rate": error_rate,
        "errors_by_tool": errors_by_tool,
        "recommendation": (
            "{} tool calls failed ({:.0%} error rate). "
            "{} had the most failures ({}). "
            "Review these patterns to improve prompt specificity."
        ).format(total_errors, error_rate, top_tool, top_count),
    }


def detect_bash_misuse(
    tool_uses: List[dict], min_occurrences: int = 3
) -> Optional[dict]:
    """Detect Bash calls that should have used dedicated tools."""
    bash_calls = [t for t in tool_uses if t["name"] == "Bash"]
    compiled = [(re.compile(p), suggested) for p, suggested in BASH_MISUSE_PATTERNS]
    misuses = []

    for call in bash_calls:
        command = call["input"].get("command", "")
        for pat, suggested in compiled:
            if pat.search(command):
                misuses.append({"command": command, "suggested_tool": suggested})
                break

    if len(misuses) < min_occurrences:
        return None

    return {
        "type": "bash_misuse",
        "severity": "info",
        "misuse_count": len(misuses),
        "total_bash_calls": len(bash_calls),
        "misuse_examples": misuses[:5],
        "recommendation": (
            "Claude used Bash for file operations {} times when dedicated "
            "tools (Read, Grep, Glob) would be faster and more reliable."
        ).format(len(misuses)),
    }


def analyze_sessions(session_paths: List[Path], days: int = 7) -> dict:
    """Run all detectors across aggregated session data."""
    all_tool_uses: List[dict] = []
    all_tool_results: List[dict] = []
    all_user_messages: List[Tuple[str, str]] = []

    for path in session_paths:
        entries = parse_jsonl_entries(path)
        all_tool_uses.extend(extract_tool_uses(entries))
        all_tool_results.extend(extract_tool_results(entries))
        all_user_messages.extend(extract_user_messages(entries))

    detectors = [
        detect_excessive_exploration(all_tool_uses),
        detect_user_corrections(all_user_messages),
        detect_repeated_prompts(all_user_messages),
        detect_tool_errors(all_tool_uses, all_tool_results),
        detect_bash_misuse(all_tool_uses),
    ]
    insights = [d for d in detectors if d is not None]

    severity_counts: Dict[str, int] = {}
    for insight in insights:
        sev = insight["severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    slug = derive_slug(os.getcwd())

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_slug": slug,
            "time_window_days": days,
            "sessions_analyzed": len(session_paths),
        },
        "insights": insights,
        "summary": {
            "total_insights": len(insights),
            "severity_counts": severity_counts,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Claude Code session traces for behavioral patterns."
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
        default=Path.cwd() / ".status-update" / "insights.json",
        help="Path to write the insights JSON file.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to look back for session data.",
    )
    args = parser.parse_args()

    slug = derive_slug(os.path.abspath(args.project_path))
    project_dir = find_project_dir(slug, args.base_dir)

    if project_dir is None:
        expected = args.base_dir / slug
        print("No project directory found for slug: {}".format(slug), file=sys.stderr)
        print("The script expects a directory at: {}".format(expected), file=sys.stderr)
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    session_paths = find_recent_sessions(project_dir, cutoff)

    result = analyze_sessions(session_paths, args.days)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(args.output)


if __name__ == "__main__":
    main()
