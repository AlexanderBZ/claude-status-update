"""Unit tests for validate_thread.py."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from validate_thread import validate


def _make_post(number, content="Test post content", has_image=False):
    return {"number": number, "content": content, "has_image": has_image}


def _make_thread(count=5):
    posts = [_make_post(1, "Hook post with image", has_image=True)]
    for i in range(2, count + 1):
        posts.append(_make_post(i))
    return {"posts": posts, "total_posts": count}


class TestValidateThread(unittest.TestCase):
    def test_valid_thread(self):
        data = _make_thread(5)
        ok, msg = validate(data)
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")

    def test_valid_minimal_thread(self):
        data = _make_thread(3)
        ok, msg = validate(data)
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")

    def test_too_few_posts(self):
        data = _make_thread(2)
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("minimum", msg.lower())

    def test_too_many_posts(self):
        data = _make_thread(16)
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("maximum", msg.lower())

    def test_post_exceeds_char_limit(self):
        data = _make_thread(5)
        data["posts"][2]["content"] = "x" * 281
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("281", msg)

    def test_first_post_missing_image(self):
        data = _make_thread(5)
        data["posts"][0]["has_image"] = False
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("has_image", msg)

    def test_missing_content(self):
        data = _make_thread(5)
        data["posts"][1]["content"] = ""
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("content", msg.lower())

    def test_non_sequential_numbers(self):
        data = _make_thread(5)
        data["posts"][2]["number"] = 5
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("expected", msg.lower())

    def test_total_posts_mismatch(self):
        data = _make_thread(5)
        data["total_posts"] = 7
        ok, msg = validate(data)
        self.assertFalse(ok)
        self.assertIn("total_posts", msg)

    def test_not_a_dict(self):
        ok, msg = validate([{"number": 1, "content": "test", "has_image": True}])
        self.assertFalse(ok)
        self.assertIn("object", msg.lower())

    def test_invalid_json_via_main(self):
        """Test that main() rejects non-JSON input via subprocess."""
        import subprocess

        script = str(Path(__file__).resolve().parent.parent / "scripts" / "validate_thread.py")
        result = subprocess.run(
            [sys.executable, script],
            input="not json at all",
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
