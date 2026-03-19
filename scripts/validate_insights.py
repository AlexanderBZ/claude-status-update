#!/usr/bin/env python3
"""Validate insights analyzer JSON output."""

import json
import sys

VALID_CATEGORIES = {
    "exploration_patterns",
    "correction_events",
    "repeated_prompts",
    "tool_errors",
    "bash_misuse",
}
VALID_SEVERITIES = {"info", "warning"}


def validate(data):
    """Validate that data matches the insights schema.

    Returns (True, "OK") on success, (False, error_message) on failure.
    """
    if not isinstance(data, dict):
        return False, "Expected a JSON object, got {}".format(type(data).__name__)

    for key in ("metadata", "categories", "session_profiles", "summary"):
        if key not in data:
            return False, "Missing top-level key: {!r}".format(key)

    # -- metadata --
    meta = data["metadata"]
    if not isinstance(meta, dict):
        return False, "metadata is not an object"

    for key, expected_type in [
        ("generated_at", str),
        ("project_slug", str),
        ("time_window_days", int),
        ("sessions_analyzed", int),
        ("total_tool_calls", int),
        ("total_user_messages", int),
    ]:
        val = meta.get(key)
        if not isinstance(val, expected_type):
            return False, "metadata.{} must be a {}".format(key, expected_type.__name__)

    # -- categories --
    categories = data["categories"]
    if not isinstance(categories, dict):
        return False, "categories is not an object"

    for name, cat in categories.items():
        if name not in VALID_CATEGORIES:
            return False, "Unknown category: {!r}".format(name)
        if not isinstance(cat, dict):
            return False, "categories.{} is not an object".format(name)
        if "triggered" not in cat:
            return False, "categories.{} missing 'triggered' field".format(name)
        if not isinstance(cat["triggered"], bool):
            return False, "categories.{}.triggered must be a bool".format(name)

        if cat["triggered"]:
            # Triggered categories must have severity, summary, statistics, evidence
            severity = cat.get("severity")
            if severity not in VALID_SEVERITIES:
                return False, "categories.{} has invalid severity: {!r}".format(name, severity)

            summary_val = cat.get("summary")
            if not isinstance(summary_val, str) or not summary_val.strip():
                return False, "categories.{} has missing or empty summary".format(name)

            if not isinstance(cat.get("statistics"), dict):
                return False, "categories.{}.statistics must be an object".format(name)

            if not isinstance(cat.get("evidence"), dict):
                return False, "categories.{}.evidence must be an object".format(name)

    # -- session_profiles --
    profiles = data["session_profiles"]
    if not isinstance(profiles, list):
        return False, "session_profiles is not an array"

    for i, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            return False, "session_profiles[{}] is not an object".format(i)
        for field in ("session_file", "tool_calls", "exploration_ratio", "errors", "corrections"):
            if field not in profile:
                return False, "session_profiles[{}] missing field: {!r}".format(i, field)

    # -- summary --
    summary = data["summary"]
    if not isinstance(summary, dict):
        return False, "summary is not an object"

    if not isinstance(summary.get("categories_triggered"), int):
        return False, "summary.categories_triggered must be an int"

    if not isinstance(summary.get("severity_counts"), dict):
        return False, "summary.severity_counts must be an object"

    return True, "OK"


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print("Invalid JSON: {}".format(e), file=sys.stderr)
        sys.exit(1)

    ok, msg = validate(data)
    if ok:
        print(msg)
        sys.exit(0)
    else:
        print(msg, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
