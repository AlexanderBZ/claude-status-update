#!/usr/bin/env python3
"""Validate Haiku subagent summary responses."""

import json
import sys

VALID_CATEGORIES = {"bug", "feature", "refactor", "research", "other"}


def validate(data):
    """Validate that data is a non-empty list of work items.

    Returns (True, "OK") on success, (False, error_message) on failure.
    """
    if not isinstance(data, list):
        return False, "Expected a JSON array, got {}".format(type(data).__name__)

    if len(data) == 0:
        return False, "Array is empty, expected at least one work item"

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return False, "Item {} is not an object".format(i)

        desc = item.get("description")
        if not isinstance(desc, str) or not desc.strip():
            return False, "Item {} has missing or empty description".format(i)

        cat = item.get("category")
        if cat not in VALID_CATEGORIES:
            return False, "Item {} has invalid category: {!r} (expected one of {})".format(
                i, cat, ", ".join(sorted(VALID_CATEGORIES))
            )

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
