import api from '/static/js/core/api.js';
import store from '/static/js/core/store.js';

export const loadChatMessages = async (chatId) => {
  if (!chatId) return;
  if (store.isTempChat(chatId)) return;

  const id = Number(chatId);
  if (!Number.isFinite(id)) return;

  if (store.isLoaded(id)) {
    return;
  }

  store.setLoading(id, true);
  try {
    const response = await api.get(`/messages/${id}`);
    if (!response || !response.data) {
      console.error('Некорректный ответ от сервера', response);
      return;
    }
    store.setMessages(id, response.data);
  } catch (error) {
    console.error('Ошибка загрузки сообщений:', error);
  } finally {
    store.setLoading(id, false);
  }
};
