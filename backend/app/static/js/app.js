import store from '/static/js/core/store.js';
import { connectWebSocket } from '/static/js/core/socket.js';
import { handleWebSocketMessage } from '/static/js/core/wsHandler.js';
import { getCurrentUser, logout } from '/static/js/features/auth.js';
import {
  loadChats,
  renderChats,
  updatePeerStatusesInDom,
} from '/static/js/features/chats.js';
import { loadChatMessages } from '/static/js/features/messages.js';
import { initSearch } from '/static/js/features/search.js';
import { initSender } from '/static/js/features/send.js';
import {
  renderMessages,
  appendMessage,
  updateMessageInDom,
} from '/static/js/ui/messageView.js';
import { updateWsStatus } from '/static/js/ui/wsStatus.js';
import { initLightbox } from '/static/js/ui/lightbox.js';

document.addEventListener('DOMContentLoaded', async () => {
  // ─── Пользователь ─────────────────────────────────────────────
  const user = await getCurrentUser();
  store.userId = user.id;

  document.querySelector('.user-avatar').textContent =
    user.username[0].toUpperCase();
  document.querySelector('.user-name').textContent = user.username;
  document.querySelector('.logout-btn').addEventListener('click', logout);

  // ─── Данные и сокет ───────────────────────────────────────────
  loadChats();
  connectWebSocket(user.id, handleWebSocketMessage, updateWsStatus);

  // ─── Подписки на store ────────────────────────────────────────

  // Перерисовываем список чатов при изменении
  store.subscribe('chatList', () => {
    renderChats(store.getChats());
  });

  // При переключении активного чата — lazy loading сообщений
  store.subscribe('activeChat', async () => {
    const activeChatId = store.ui.activeChatId;
    if (activeChatId === null) return;
    // Сразу рендерим из стора: если сообщения уже загружены — UI не мигает
    // и не зависит от сети. Догрузка с сервера обновит список через
    // событие 'messages:replaced' только при успехе.
    renderMessages(store.getMessages(activeChatId));
    await loadChatMessages(activeChatId);
  });

  // Перерисовка всего списка сообщений (первичная загрузка чата)
  store.subscribe('messages:replaced', (chatId) => {
    if (chatId !== store.ui.activeChatId) return;
    renderMessages(store.getMessages(chatId));
  });

  // Добавление одного сообщения (отправка / входящее от собеседника)
  store.subscribe('message:new', (message) => {
    if (message.chat_id !== store.ui.activeChatId) return;
    appendMessage(message);
  });

  // Точечное обновление сообщения (optimistic → подтверждено, удаление)
  store.subscribe('message:update', ({ oldId, message }) => {
    if (message.chat_id !== store.ui.activeChatId) return;
    updateMessageInDom(oldId, message);
  });

  // Обновление статусов собеседников
  store.subscribe('peerStatuses', updatePeerStatusesInDom);

  // ─── UI-модули ────────────────────────────────────────────────
  initSearch({
    searchInput: document.getElementById('searchInput'),
    searchResults: document.getElementById('searchResults'),
    userId: user.id,
  });

  initSender({
    messageInput: document.getElementById('messageInput'),
    fileInput: document.getElementById('fileInput'),
    sendBtn: document.getElementById('sendBtn'),
  });

  initLightbox();
});
