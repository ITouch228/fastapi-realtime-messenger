"""Проверки Origin для cookie-аутентифицированного WebSocket handshake."""

import unittest
from unittest.mock import patch

from app.config import settings
from app.routes.ws import is_allowed_ws_origin


class WebSocketOriginTests(unittest.TestCase):
    def test_allowed_origin(self):
        with patch.object(settings, 'ALLOWED_ORIGINS', ['https://chat.example.com']):
            self.assertTrue(is_allowed_ws_origin('https://chat.example.com'))

    def test_untrusted_origin(self):
        with patch.object(settings, 'ALLOWED_ORIGINS', ['https://chat.example.com']):
            self.assertFalse(is_allowed_ws_origin('https://evil.example.com'))

    def test_missing_origin(self):
        with patch.object(settings, 'ALLOWED_ORIGINS', ['https://chat.example.com']):
            self.assertFalse(is_allowed_ws_origin(None))

    def test_scheme_and_port_must_match(self):
        with patch.object(settings, 'ALLOWED_ORIGINS', ['https://chat.example.com']):
            self.assertFalse(is_allowed_ws_origin('http://chat.example.com'))
            self.assertFalse(is_allowed_ws_origin('https://chat.example.com:8443'))

    def test_prefix_and_suffix_are_rejected(self):
        with patch.object(settings, 'ALLOWED_ORIGINS', ['https://chat.example.com']):
            self.assertFalse(is_allowed_ws_origin('https://chat.example.com.evil.test'))
            self.assertFalse(is_allowed_ws_origin('https://chat.example.com/'))


if __name__ == '__main__':
    unittest.main()
