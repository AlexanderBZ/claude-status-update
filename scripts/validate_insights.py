#!/usr/bin/env python3
"""Validate insights analyzer JSON output."""

import json
import sys

VALID_TYPES = {
    "excessive_exploration",
    "user_corrections",
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

    for key in ("metadata", "insights", "summary"):
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
    ]:
        val = meta.get(key)
        if not isinstance(val, expected_type):
            return False, "metadata.{} must be a {}".format(key, expected_type.__name__)

    # -- insights --
    insights = data["insights"]
    if not isinstance(insights, list):
        return False, "insights is not an array"

    for i, item in enumerate(insights):
        if not isinstance(item, dict):
            return False, "insights[{}] is not an object".format(i)

        itype = item.get("type")
        if itype not in VALID_TYPES:
            return False, "insights[{}] has invalid type: {!r} (expected one of {})".format(
                i, itype, ", ".join(sorted(VALID_TYPES))
            )

        severity = item.get("severity")
        if severity not in VALID_SEVERITIES:
            return False, "insights[{}] has invalid severity: {!r} (expected one of {})".format(
                i, severity, ", ".join(sorted(VALID_SEVERITIES))
            )

        rec = item.get("recommendation")
        if not isinstance(rec, str) or not rec.strip():
            return False, "insights[{}] has missing or empty recommendation".format(i)

    # -- summary --
    summary = data["summary"]
    if not isinstance(summary, dict):
        return False, "summary is not an object"

    if not isinstance(summary.get("total_insights"), int):
        return False, "summary.total_insights must be an int"

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
