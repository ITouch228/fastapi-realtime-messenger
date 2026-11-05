"""Исполняемые HTTP-контракты на изолированной тестовой PostgreSQL/Redis.

Запускать только на временной CI/dev-инфраструктуре: создаются пользователи,
чаты и сообщения. Не входит в unit discovery — нужен работающий FastAPI.
"""

import http.cookiejar
import json
import os
import time
import unittest
import urllib.error
import urllib.request
from uuid import uuid4

BASE_URL = os.environ.get('TEST_BASE_URL', 'http://127.0.0.1:8000')


class ApiClient:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def csrf(self):
        return next(
            (cookie.value for cookie in self.cookies if cookie.name == 'csrftoken'),
            None,
        )

    def call(self, method, path, *, data=None, csrf=False, headers=None):
        request_headers = dict(headers or {})
        body = data
        if isinstance(data, dict):
            body = json.dumps(data).encode('utf-8')
            request_headers['Content-Type'] = 'application/json'
        if csrf:
            token = self.csrf()
            if token is None:
                raise AssertionError('CSRF cookie missing')
            request_headers['X-CSRF-Token'] = token
        request = urllib.request.Request(
            BASE_URL + path,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            response = self.opener.open(request, timeout=8)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            payload = response.read()
            content_type = response.headers.get('Content-Type', '')
            parsed = (
                json.loads(payload) if 'application/json' in content_type else payload
            )
            return response.status, parsed


def multipart_text(fields):
    boundary = 'contract-' + uuid4().hex
    body = b''.join(
        (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
            f'{value}\r\n'
        ).encode()
        for key, value in fields.items()
    ) + f'--{boundary}--\r\n'.encode('ascii')
    return body, {'Content-Type': f'multipart/form-data; boundary={boundary}'}


class HttpContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.anonymous = ApiClient()
        for _ in range(60):
            try:
                status, _ = cls.anonymous.call('GET', '/auth/login')
                if status == 200:
                    break
            except OSError:
                pass
            time.sleep(0.5)
        else:
            raise AssertionError('FastAPI did not become ready')

        stamp = uuid4().hex[:12]
        cls.clients = []
        cls.user_ids = []
        for index in range(3):
            client = ApiClient()
            username = f'contract_{index}_{stamp}'
            status, _ = client.call(
                'POST',
                '/api/auth/register',
                data={
                    'username': username,
                    'email': f'{username}@example.com',
                    'password': 'contract-test-password',
                },
            )
            if status != 201:
                raise AssertionError(f'Registration contract broken: {status}')
            status, _ = client.call('GET', '/auth/login')
            if status != 200:
                raise AssertionError('Login page must set CSRF cookie')
            status, _ = client.call(
                'POST',
                '/api/auth/login',
                csrf=True,
                data={'login': username, 'password': 'contract-test-password'},
            )
            if status != 200:
                raise AssertionError(f'Login contract broken: {status}')
            status, me = client.call('GET', '/api/users/me')
            if status != 200 or me['username'] != username:
                raise AssertionError('Session identity contract broken')
            cls.clients.append(client)
            cls.user_ids.append(me['id'])

    def test_anonymous_requests_rejected(self):
        for path in ('/api/users/me', '/api/chats', '/api/messages/999999'):
            with self.subTest(path=path):
                status, body = self.anonymous.call('GET', path)
                self.assertEqual(status, 401)
                self.assertIn('detail', body)

    def test_csrf_missing_and_incorrect_header_rejected(self):
        client = self.clients[0]
        for headers in ({}, {'X-CSRF-Token': 'incorrect'}):
            with self.subTest(headers=headers):
                status, body = client.call('POST', '/api/auth/logout', headers=headers)
                self.assertEqual(status, 403)
                self.assertIn('detail', body)
        status, me = client.call('GET', '/api/users/me')
        self.assertEqual(status, 200)
        self.assertEqual(me['id'], self.user_ids[0])

    def test_message_read_permissions_and_response_contract(self):
        author, peer, outsider = self.clients
        peer_id = self.user_ids[1]
        body, headers = multipart_text(
            {'message_text': 'contract test message', 'peer_id': peer_id}
        )
        status, message = author.call(
            'POST',
            f'/api/messages/temp-{peer_id}',
            data=body,
            headers=headers,
            csrf=True,
        )
        self.assertEqual(status, 201)
        self.assertEqual(message['message_text'], 'contract test message')
        self.assertEqual(message['sender_id'], self.user_ids[0])
        self.assertIsInstance(message['id'], int)
        self.assertIsInstance(message['chat_id'], int)
        chat_id = message['chat_id']

        status, history = peer.call('GET', f'/api/messages/{chat_id}')
        self.assertEqual(status, 200)
        self.assertTrue(any(item['id'] == message['id'] for item in history))

        status, denied = outsider.call('GET', f'/api/messages/{chat_id}')
        self.assertEqual(status, 403)
        self.assertIn('detail', denied)

        status, denied = outsider.call('DELETE', f'/api/chats/{chat_id}', csrf=True)
        self.assertEqual(status, 403)
        self.assertIn('detail', denied)

    def test_openapi_exposes_required_contracts(self):
        status, schema = self.anonymous.call('GET', '/openapi.json')
        self.assertEqual(status, 200)
        self.assertEqual(schema['openapi'].split('.')[0], '3')
        paths = schema['paths']
        self.assertIn('post', paths['/api/auth/login'])
        self.assertIn('post', paths['/api/messages/{chat_id}'])
        self.assertIn('get', paths['/api/messages/{chat_id}'])
        self.assertIn('delete', paths['/api/chats/{chat_id}'])
        self.assertIn('get', paths['/api/files/{file_id}'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
