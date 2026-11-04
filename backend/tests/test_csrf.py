"""Baseline unit tests: CSRF tokens must be nonempty and unpredictable."""

import unittest

from app.utils.csrf import generate_csrf_token


class CsrfTokenTests(unittest.TestCase):
    def test_token_is_nonempty(self):
        self.assertGreaterEqual(len(generate_csrf_token()), 32)

    def test_successive_tokens_are_unique(self):
        self.assertNotEqual(generate_csrf_token(), generate_csrf_token())


if __name__ == '__main__':
    unittest.main()
