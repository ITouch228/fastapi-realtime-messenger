"""HTTP smoke-test запуска приложения с настоящими PostgreSQL и Redis.

Запускать только в отдельной тестовой БД: создаёт двух пользователей и чат.
"""

import http.cookiejar
import json
import time
import urllib.error
import urllib.request
from uuid import uuid4

BASE_URL = 'http://127.0.0.1:8000'
cookies = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))


def call(path, *, method='GET', data=None, headers=None):
    body = None
    request_headers = dict(headers or {})
    if isinstance(data, dict):
        body = json.dumps(data).encode()
        request_headers['Content-Type'] = 'application/json'
    elif data is not None:
        body = data
    request = urllib.request.Request(
        BASE_URL + path, data=body, headers=request_headers, method=method
    )
    try:
        with client.open(request, timeout=5) as response:
            content = response.read()
            if 'application/json' in response.headers.get('Content-Type', ''):
                return response.status, json.loads(content)
            return response.status, content.decode() if content else None
    except urllib.error.HTTPError as exc:
        raise AssertionError(
            f'{method} {path} вернул {exc.code}: {exc.read().decode()}'
        ) from exc


def wait_until_ready():
    for _ in range(60):
        try:
            status, _ = call('/auth/login')
            if status == 200:
                return
        except (OSError, AssertionError):
            time.sleep(0.5)
    raise AssertionError('FastAPI не запустился за 30 секунд')


def csrf_token():
    return next(cookie.value for cookie in cookies if cookie.name == 'csrftoken')


def main():
    wait_until_ready()
    stamp = uuid4().hex[:12]
    usernames = [f'smoke_a_{stamp}', f'smoke_b_{stamp}']
    for name in usernames:
        status, _ = call(
            '/api/auth/register',
            method='POST',
            data={
                'username': name,
                'email': f'{name}@gmail.com',
                'password': 'secure-testing-password',
            },
        )
        assert status == 201

    status, _ = call(
        '/api/auth/login',
        method='POST',
        headers={'X-CSRF-Token': csrf_token()},
        data={'login': usernames[0], 'password': 'secure-testing-password'},
    )
    assert status == 200
    status, me = call('/api/users/me')
    assert status == 200 and me['username'] == usernames[0]

    status, users = call('/api/users/search?query=' + usernames[1])
    assert status == 200
    peer = next(user for user in users if user['username'] == usernames[1])
    boundary = 'itmessage-smoke-boundary'
    parts = {'message_text': 'smoke: hello', 'peer_id': str(peer['id'])}
    payload = (
        b''.join(
            (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f'{value}\r\n'
            ).encode()
            for name, value in parts.items()
        )
        + f'--{boundary}--\r\n'.encode()
    )
    status, message = call(
        f'/api/messages/temp-{peer["id"]}',
        method='POST',
        data=payload,
        headers={
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'X-CSRF-Token': csrf_token(),
        },
    )
    assert status == 201 and message['message_text'] == 'smoke: hello'
    status, history = call(f'/api/messages/{message["chat_id"]}')
    assert status == 200 and any(item['id'] == message['id'] for item in history)
    print('HTTP smoke OK: регистрация, вход, сессия, чат и сообщение')


if __name__ == '__main__':
    main()
