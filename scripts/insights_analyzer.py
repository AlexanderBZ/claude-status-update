#!/usr/bin/env python3
"""Analyze Claude Code session traces to detect behavioral patterns."""

import argparse
import json
import os
import re
import sys
from collections import Counter
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


def extract_tool_uses(entries):
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


def extract_tool_results(entries):
    """Extract tool_result blocks from user entries, including error content."""
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
                error_content = ""
                if block.get("is_error"):
                    raw = block.get("content", "")
                    if isinstance(raw, str):
                        error_content = raw[:500]
                    elif isinstance(raw, list):
                        error_content = "".join(
                            item.get("text", "") for item in raw if isinstance(item, dict)
                        )[:500]
                results.append({
                    "tool_use_id": block.get("tool_use_id", ""),
                    "is_error": bool(block.get("is_error", False)),
                    "error_content": error_content,
                    "timestamp": entry.get("timestamp", ""),
                })
    return results


def extract_conversation_turns(entries):
    """Group entries into turns: user prompt -> assistant actions.

    Returns: [{"prompt": str, "timestamp": str, "actions": [{"tool": str, "input_summary": str}]}]
    """
    turns = []
    current_turn = None

    for entry in entries:
        entry_type = entry.get("type", "")
        message = entry.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None

        if entry_type == "user" and isinstance(content, str):
            # New user text message starts a new turn
            current_turn = {
                "prompt": content,
                "timestamp": entry.get("timestamp", ""),
                "actions": [],
            }
            turns.append(current_turn)
        elif entry_type == "assistant" and isinstance(content, list):
            if current_turn is None:
                # Assistant message without a preceding user prompt
                current_turn = {
                    "prompt": "",
                    "timestamp": entry.get("timestamp", ""),
                    "actions": [],
                }
                turns.append(current_turn)
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    current_turn["actions"].append({
                        "tool": block.get("name", ""),
                        "input_summary": summarize_tool_input(
                            block.get("name", ""), block.get("input", {})
                        ),
                    })

    return turns


def summarize_tool_input(tool_name, tool_input):
    """Brief summary of tool call: file path for Read/Edit/Write, pattern for Grep/Glob, command for Bash."""
    if tool_name in ("Read", "Edit", "Write"):
        return tool_input.get("file_path", "unknown")
    elif tool_name == "Grep":
        return tool_input.get("pattern", "unknown")
    elif tool_name == "Glob":
        return tool_input.get("pattern", "unknown")
    elif tool_name == "Bash":
        return tool_input.get("command", "unknown")[:100]
    return tool_name


def normalize_message(text):
    """Lowercase, strip, collapse whitespace, remove non-alphanumeric chars."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_excessive_exploration(tool_uses, entries, threshold=0.7, min_calls=10):
    """Detect when exploration tools dominate over action tools."""
    exploration_count = sum(1 for t in tool_uses if t["name"] in EXPLORATION_TOOLS)
    action_count = sum(1 for t in tool_uses if t["name"] in ACTION_TOOLS)
    total_categorized = exploration_count + action_count

    if total_categorized < min_calls:
        return {"triggered": False}

    exploration_ratio = exploration_count / total_categorized
    if exploration_ratio <= threshold:
        return {"triggered": False}

    # Files read multiple times
    read_paths = [
        t["input"].get("file_path", "")
        for t in tool_uses
        if t["name"] == "Read" and t["input"].get("file_path")
    ]
    path_counts = Counter(read_paths)
    files_read_multiple = [
        {"path": path, "count": count}
        for path, count in path_counts.most_common(10)
        if count > 1
    ]

    # Exploration bursts from conversation turns
    turns = extract_conversation_turns(entries)
    bursts = []
    for turn in turns:
        actions = turn["actions"]
        current_burst = []
        for action in actions:
            if action["tool"] in EXPLORATION_TOOLS:
                current_burst.append(action["tool"])
            elif action["tool"] in ACTION_TOOLS:
                if len(current_burst) >= 5:
                    bursts.append({
                        "length": len(current_burst),
                        "preceding_prompt": turn["prompt"][:150],
                        "tools": list(current_burst),
                    })
                current_burst = []
            # Tools not in either set do not break the burst
        # Check at end of turn
        if len(current_burst) >= 5:
            bursts.append({
                "length": len(current_burst),
                "preceding_prompt": turn["prompt"][:150],
                "tools": list(current_burst),
            })
    bursts.sort(key=lambda b: b["length"], reverse=True)

    # Frequent search terms from Grep
    grep_patterns = [
        t["input"].get("pattern", "")
        for t in tool_uses
        if t["name"] == "Grep" and t["input"].get("pattern")
    ]
    term_counts = Counter(grep_patterns)
    frequent_terms = [
        {"term": term, "count": count}
        for term, count in term_counts.most_common(10)
    ]

    return {
        "triggered": True,
        "severity": "warning" if exploration_ratio > 0.8 else "info",
        "summary": "{:.0%} of categorized tool calls were exploration ({} of {})".format(
            exploration_ratio, exploration_count, total_categorized
        ),
        "statistics": {
            "exploration_ratio": exploration_ratio,
            "exploration_count": exploration_count,
            "action_count": action_count,
            "total_tool_calls": len(tool_uses),
        },
        "evidence": {
            "files_read_multiple_times": files_read_multiple,
            "exploration_bursts": bursts[:5],
            "frequent_search_terms": frequent_terms,
        },
    }


def detect_user_corrections(user_messages, conversation_turns, session_map=None, min_corrections=2):
    """Detect messages where the user corrected Claude."""
    compiled = [re.compile(p) for p in CORRECTION_PATTERNS]
    corrections = []

    for timestamp, content in user_messages:
        if any(pat.search(content) for pat in compiled):
            corrections.append({"timestamp": timestamp, "content": content})

    if len(corrections) < min_corrections:
        return {"triggered": False}

    # Count sessions with corrections
    sessions_with_corrections = 0
    if session_map:
        for _session_file, messages in session_map.items():
            for _, content in messages:
                if any(pat.search(content) for pat in compiled):
                    sessions_with_corrections += 1
                    break

    # Build evidence events with context from conversation turns
    events = []
    for correction in corrections[:5]:
        preceding_actions = []
        original_prompt = ""

        # Find the turn just before this correction timestamp
        best_turn = None
        for turn in conversation_turns:
            if turn["timestamp"] and turn["timestamp"] < correction["timestamp"]:
                best_turn = turn
            elif turn["timestamp"] and turn["timestamp"] >= correction["timestamp"]:
                break

        if best_turn:
            preceding_actions = [
                a["input_summary"] for a in best_turn["actions"]
            ][-3:]
            original_prompt = best_turn["prompt"][:150]

        events.append({
            "correction": correction["content"][:200],
            "preceding_actions": preceding_actions,
            "original_prompt": original_prompt,
        })

    return {
        "triggered": True,
        "severity": "warning",
        "summary": "{} user corrections across {} sessions".format(
            len(corrections), sessions_with_corrections
        ),
        "statistics": {
            "correction_count": len(corrections),
            "sessions_with_corrections": sessions_with_corrections,
        },
        "evidence": {
            "events": events,
        },
    }


def detect_repeated_prompts(user_messages, session_map=None, min_occurrences=2):
    """Detect messages the user sent multiple times."""
    groups = {}

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
        return {"triggered": False}

    # Count sessions_seen_in for each repeated group
    for group in repeated:
        sessions_seen_in = 0
        if session_map:
            for _session_file, messages in session_map.items():
                for _, content in messages:
                    if normalize_message(content) == group["normalized"]:
                        sessions_seen_in += 1
                        break
        group["sessions_seen_in"] = sessions_seen_in

    # Sort by count descending, take top 5
    repeated.sort(key=lambda g: g["count"], reverse=True)
    top_groups = repeated[:5]

    evidence_groups = [
        {
            "example": g["example"][:100],
            "count": g["count"],
            "sessions_seen_in": g["sessions_seen_in"],
        }
        for g in top_groups
    ]

    return {
        "triggered": True,
        "severity": "info",
        "summary": "{} prompts repeated 2+ times across sessions".format(len(repeated)),
        "statistics": {"group_count": len(repeated)},
        "evidence": {
            "groups": evidence_groups,
        },
    }


def detect_tool_errors(tool_uses, tool_results, min_errors=3):
    """Detect high tool error rates, grouped by tool name."""
    id_to_tool = {t["id"]: t for t in tool_uses}
    errors_by_tool = {}
    total_errors = 0
    error_examples = []

    for result in tool_results:
        if result["is_error"]:
            tool_use_id = result["tool_use_id"]
            tool = id_to_tool.get(tool_use_id)
            tool_name = tool["name"] if tool else "unknown"
            errors_by_tool[tool_name] = errors_by_tool.get(tool_name, 0) + 1
            total_errors += 1

            if len(error_examples) < 5:
                input_summary = ""
                if tool:
                    input_summary = summarize_tool_input(tool["name"], tool["input"])
                error_examples.append({
                    "tool": tool_name,
                    "input_summary": input_summary,
                    "error_content": result.get("error_content", "")[:200],
                })

    if total_errors < min_errors:
        return {"triggered": False}

    total_tool_calls = len(tool_results)
    error_rate = total_errors / total_tool_calls if total_tool_calls > 0 else 0.0

    return {
        "triggered": True,
        "severity": "warning" if error_rate > 0.2 else "info",
        "summary": "{} tool calls failed ({:.0%} error rate)".format(total_errors, error_rate),
        "statistics": {
            "total_errors": total_errors,
            "total_tool_calls": total_tool_calls,
            "error_rate": error_rate,
            "errors_by_tool": errors_by_tool,
        },
        "evidence": {
            "error_examples": error_examples,
        },
    }


def detect_bash_misuse(tool_uses, min_occurrences=3):
    """Detect Bash calls that should have used dedicated tools."""
    bash_calls = [t for t in tool_uses if t["name"] == "Bash"]
    compiled = [(re.compile(p), suggested) for p, suggested in BASH_MISUSE_PATTERNS]
    misuses = []

    for call in bash_calls:
        command = call["input"].get("command", "")
        for pat, suggested in compiled:
            if pat.search(command):
                misuses.append({"command": command[:100], "suggested_tool": suggested})
                break

    if len(misuses) < min_occurrences:
        return {"triggered": False}

    return {
        "triggered": True,
        "severity": "info",
        "summary": "Claude used Bash for file operations {} times when dedicated tools exist".format(
            len(misuses)
        ),
        "statistics": {
            "misuse_count": len(misuses),
            "total_bash_calls": len(bash_calls),
        },
        "evidence": {
            "examples": misuses[:5],
        },
    }


def build_session_profiles(session_data_list):
    """Per-session summary statistics."""
    compiled = [re.compile(p) for p in CORRECTION_PATTERNS]
    profiles = []

    for data in session_data_list:
        tool_uses = data["tool_uses"]
        exploration = sum(1 for t in tool_uses if t["name"] in EXPLORATION_TOOLS)
        action = sum(1 for t in tool_uses if t["name"] in ACTION_TOOLS)
        total_cat = exploration + action

        errors = sum(1 for r in data["tool_results"] if r["is_error"])

        corrections = sum(
            1 for _, content in data["user_messages"]
            if any(pat.search(content) for pat in compiled)
        )

        profiles.append({
            "session_file": data["session_file"],
            "tool_calls": len(tool_uses),
            "exploration_ratio": round(exploration / total_cat, 2) if total_cat > 0 else 0.0,
            "errors": errors,
            "corrections": corrections,
        })

    profiles.sort(key=lambda p: p["tool_calls"], reverse=True)
    return profiles[:20]


def analyze_sessions(session_paths, days=7):
    """Run all detectors across aggregated session data."""
    all_tool_uses = []
    all_tool_results = []
    all_user_messages = []
    all_entries = []
    session_data_list = []
    session_message_map = {}

    for path in session_paths:
        entries = parse_jsonl_entries(path)
        tool_uses = extract_tool_uses(entries)
        tool_results = extract_tool_results(entries)
        user_messages = extract_user_messages(entries)
        turns = extract_conversation_turns(entries)

        all_tool_uses.extend(tool_uses)
        all_tool_results.extend(tool_results)
        all_user_messages.extend(user_messages)
        all_entries.extend(entries)

        session_data_list.append({
            "session_file": path.name,
            "tool_uses": tool_uses,
            "tool_results": tool_results,
            "user_messages": user_messages,
            "conversation_turns": turns,
        })
        session_message_map[path.name] = user_messages

    all_turns = extract_conversation_turns(all_entries)

    categories = {
        "exploration_patterns": detect_excessive_exploration(all_tool_uses, all_entries),
        "correction_events": detect_user_corrections(
            all_user_messages, all_turns, session_map=session_message_map
        ),
        "repeated_prompts": detect_repeated_prompts(
            all_user_messages, session_map=session_message_map
        ),
        "tool_errors": detect_tool_errors(all_tool_uses, all_tool_results),
        "bash_misuse": detect_bash_misuse(all_tool_uses),
    }

    session_profiles = build_session_profiles(session_data_list)

    severity_counts = {}
    categories_triggered = 0
    for cat in categories.values():
        if cat.get("triggered"):
            categories_triggered += 1
            sev = cat.get("severity", "")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

    slug = derive_slug(os.getcwd())

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_slug": slug,
            "time_window_days": days,
            "sessions_analyzed": len(session_paths),
            "total_tool_calls": len(all_tool_uses),
            "total_user_messages": len(all_user_messages),
        },
        "categories": categories,
        "session_profiles": session_profiles,
        "summary": {
            "categories_triggered": categories_triggered,
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
