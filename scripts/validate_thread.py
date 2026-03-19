#!/usr/bin/env python3
"""Validate X thread structure."""

import json
import sys

MIN_POSTS = 3
MAX_POSTS = 15
MAX_CHARS = 280


def validate(data):
    """Validate that data is a well-formed X thread.

    Returns (True, "OK") on success, (False, error_message) on failure.
    """
    if not isinstance(data, dict):
        return False, "Expected a JSON object, got {}".format(type(data).__name__)

    posts = data.get("posts")
    if not isinstance(posts, list):
        return False, "Missing or invalid 'posts' array"

    total = data.get("total_posts")
    if not isinstance(total, int):
        return False, "Missing or invalid 'total_posts' integer"

    if len(posts) < MIN_POSTS:
        return False, "Thread has {} posts, minimum is {}".format(len(posts), MIN_POSTS)

    if len(posts) > MAX_POSTS:
        return False, "Thread has {} posts, maximum is {}".format(len(posts), MAX_POSTS)

    if total != len(posts):
        return False, "total_posts ({}) does not match actual post count ({})".format(
            total, len(posts)
        )

    for i, post in enumerate(posts):
        if not isinstance(post, dict):
            return False, "Post {} is not an object".format(i)

        number = post.get("number")
        if not isinstance(number, int) or number != i + 1:
            return False, "Post {} has number {}, expected {}".format(i, number, i + 1)

        content = post.get("content")
        if not isinstance(content, str) or not content.strip():
            return False, "Post {} has missing or empty content".format(i)

        if len(content) > MAX_CHARS:
            return False, "Post {} is {} chars, maximum is {}".format(
                i, len(content), MAX_CHARS
            )

        has_image = post.get("has_image")
        if not isinstance(has_image, bool):
            return False, "Post {} has missing or non-boolean 'has_image'".format(i)

        if i == 0 and not has_image:
            return False, "Post 0 (the hook) must have has_image set to true"

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
