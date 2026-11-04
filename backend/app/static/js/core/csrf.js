// Независимый от Axios модуль: используется также страницами входа и регистрации.
export function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
  return match ? match[1] : '';
}
