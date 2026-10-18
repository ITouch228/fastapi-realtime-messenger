// основной клиент для всего приложения
const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
});

// отдельный клиент для refresh/logout без refresh-интерсептора (чтобы не было циклов)
const authApi = axios.create({
  baseURL: '/api',
  withCredentials: true,
});

// authApi тоже шлёт CSRF-токен (для refresh/logout)
authApi.interceptors.request.use((config) => {
  const token = getCsrfToken();
  if (token) {
    config.headers['X-CSRF-Token'] = token;
  }
  return config;
});

let isRefreshing = false;
let refreshPromise = null;
let queue = [];

function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
  return match ? match[1] : '';
}

function flushQueue(err) {
  const pending = queue;
  queue = [];
  pending.forEach(({ resolve, reject }) => {
    if (err) reject(err);
    else resolve();
  });
}

async function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = authApi.post('/auth/refresh');
  }
  try {
    await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

async function hardLogout() {
  try {
    await authApi.post('/auth/logout');
  } catch {
    // даже если logout упал — всё равно считаем что сессии нет
  }
  window.location.href = '/auth/login';
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    // network error
    if (!err.response) return Promise.reject(err);

    const { status } = err.response;
    const original = err.config;

    // только 401
    if (status !== 401) return Promise.reject(err);

    // не пытаться рефрешить auth-роуты
    // TODO: [SMELL] isAuthRoute проверкой по строке URL — хрупко.
    // Лучше вынести список маршрутов в константу или проверять по original.url
    // через реестр routes.
    // docs/architecture.md §5: 🟢 auth route check по строке
    const url = original.url || '';
    const isAuthRoute =
      url.includes('/auth/refresh') ||
      url.includes('/auth/login') ||
      url.includes('/auth/logout');

    if (isAuthRoute) return Promise.reject(err);

    // защита от бесконечного повтора
    if (original._retry) return Promise.reject(err);
    original._retry = true;

    // если refresh уже идёт — ждём
    if (isRefreshing) {
      try {
        await new Promise((resolve, reject) => queue.push({ resolve, reject }));
        return api(original);
      } catch (e) {
        return Promise.reject(e);
      }
    }

    isRefreshing = true;
    try {
      await refreshSession();
      flushQueue(null);
      return api(original);
    } catch (refreshErr) {
      flushQueue(refreshErr);
      await hardLogout();
      return Promise.reject(refreshErr);
    } finally {
      isRefreshing = false;
    }
  },
);

// CSRF: шлём X-CSRF-Token из куки на каждый запрос
api.interceptors.request.use((config) => {
  const token = getCsrfToken();
  if (token) {
    config.headers['X-CSRF-Token'] = token;
  }
  return config;
});

export default api;
