const form = document.getElementById('loginForm');
const message = document.getElementById('message');

if (new URLSearchParams(location.search).get('registered')) {
  message.textContent = 'Регистрация успешна, войдите';
  message.className = 'message success';
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  message.textContent = '';
  message.className = '';

  const formData = new FormData(form);
  const payload = Object.fromEntries(formData);

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      location.href = '/messages';
      return;
    }

    const err = await res.json().catch(() => ({}));
    message.textContent = formatDetail(err.detail) || 'Ошибка входа';
    message.className = 'message error';
  } catch {
    message.textContent = 'Сервер недоступен';
    message.className = 'message error';
  }
});

function formatDetail(d) {
  if (Array.isArray(d)) return d.map((x) => x.msg).join(', ');
  return d;
}
