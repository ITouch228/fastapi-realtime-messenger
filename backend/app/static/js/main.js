import {
  formatLocalDateTime,
  formatTimeLocalFromUtcString,
} from '/static/js/utils.js';
import { getCurrentUser, logout } from '/static/js/auth.js';
import { handleWebSocketMessage } from '/static/js/messageHandler.js';
import { connectWebSocket } from '/static/js/websocket.js';
import {
  loadChats,
  renderChats,
  loadChatMessages,
  renderMessages,
  startNewChat,
} from '/static/js/messages.js';
import AppState from '/static/js/state.js';
import api from '/static/js/api.js';

document.addEventListener('DOMContentLoaded', async () => {
  const messageInput = document.getElementById('messageInput');
  const fileInput = document.getElementById('fileInput');
  const sendBtn = document.getElementById('sendBtn');
  const searchInput = document.getElementById('searchInput');
  const searchResults = document.getElementById('searchResults');

  let searchTimeout = null;
  let isSending = false;

  const setSendingState = state => {
    isSending = state;
    sendBtn.disabled = state;
    messageInput.disabled = state;
    fileInput.disabled = state;
    // необязательно, но приятно
    sendBtn.style.opacity = state ? '0.6' : '';
    sendBtn.style.pointerEvents = state ? 'none' : '';
  };

  // Загружаем пользователя
  const user = await getCurrentUser();
  const userId = user.id;
  const username = user.username;
  AppState.setUserId(user.id);

  // Отображаем информацию пользователя
  document.querySelector('.user-avatar').textContent =
    username[0].toUpperCase();
  document.querySelector('.user-name').textContent = username;
  document.querySelector('.logout-btn').addEventListener('click', logout);

  // Загружаем чаты
  loadChats(userId);

  // Подключаем вебсокет
  connectWebSocket(userId, handleWebSocketMessage);

  // Подписываемся на изменения AppState
  AppState.subscribe('chats', () => {
    document.querySelector('.chat-list').innerHTML = '';
    renderChats(AppState.persistentChats);
  });

  AppState.subscribe('chatActiveId', chatActiveId => {
    if (chatActiveId !== 0) {
      loadChatMessages(chatActiveId);
      document.getElementById('messages').innerHTML = '';
      setTimeout(() => {
        renderMessages(AppState.messages);
      }, 300);
    }

    if (
      typeof AppState.chatActiveId === 'string' &&
      AppState.chatActiveId.slice(0, 5) !== 'temp-' &&
      AppState.tempChat !== null
    ) {
      AppState.clearTempChat();
    }
  });

  AppState.subscribe('tempChat', () => {
    renderChats([AppState.tempChat]);
  });

  AppState.subscribe('newMessage', () => {
    const lastMessage = AppState.messages[AppState.messages.length - 1];
    renderMessages([lastMessage]);

    const chatLastMessageDiv = document
      .querySelector(`.chat-item[data-chat-id="${lastMessage.chat_id}"]`)
      .querySelector('.chat-info')
      .querySelector('.chat-last-message');
    if (lastMessage.message_text)
      chatLastMessageDiv.textContent = lastMessage.message_text;
    else chatLastMessageDiv.textContent = 'Файл';

    const timeSpan = document.createElement('span');
    timeSpan.style.float = 'right';
    timeSpan.textContent = formatTimeLocalFromUtcString(lastMessage.time);
    chatLastMessageDiv.appendChild(timeSpan);
  });

  // Поиск пользователей
  searchInput.addEventListener('input', function () {
    clearTimeout(searchTimeout);
    const query = this.value.trim();

    if (query.length < 2) {
      searchResults.style.display = 'none';
      return;
    }

    searchTimeout = setTimeout(async () => {
      await api
        .get('/users/search_users', {
          params: {
            query: query,
          },
        })
        .then(res => res.data)
        .then(data => {
          if (data.length > 0 && data.find(user => user.user_id !== userId)) {
            searchResults.innerHTML = 'Написать пользователю:';
            data.forEach(user => {
              if (user.user_id !== userId) {
                const item = document.createElement('div');
                item.className = 'search-result-item';
                item.innerHTML = `
                    <div style="display: flex; align-items: center;">
                        <div style="width: 30px; height: 30px; border-radius: 50%; background: #ddd; display: flex; align-items: center; justify-content: center; margin-right: 10px;">
                            ${user.username[0].toUpperCase()}
                        </div>
                        ${user.username}
                    </div>
                `;
                item.addEventListener('click', () => {
                  startNewChat(user.user_id);
                  searchInput.value = '';
                  searchResults.style.display = 'none';
                });
                searchResults.appendChild(item);
              }
            });
            searchResults.style.display = 'block';
          } else {
            searchResults.innerHTML =
              '<div class="search-result-item">Ничего не найдено</div>';
            searchResults.style.display = 'block';
          }
        })
        .catch(err => {
          console.error('Ошибка поиска:', err);
          searchResults.innerHTML =
            '<div class="search-result-item">Ошибка поиска</div>';
          searchResults.style.display = 'block';
        });
    }, 300);
  });

  // Закрытие результатов поиска при клике вне поля поиска
  document.addEventListener('click', function (e) {
    if (!searchInput.contains(e.target)) {
      searchResults.style.display = 'none';
    }
  });

  // Отправка сообщений
  sendBtn.addEventListener('click', sendMessage);
  messageInput.addEventListener('keypress', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  messageInput.addEventListener('paste', e => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const fileItem = Array.from(items).find(it => it.kind === 'file');
    if (!fileItem) return;

    const file = fileItem.getAsFile();
    if (!file) return;

    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;

    e.preventDefault();
  });

  async function sendMessage() {
    if (isSending) return;

    if (AppState.chatActiveId !== 0) {
      const text = messageInput.value.trim();
      const file = fileInput.files[0];

      if (!text && !file) return;

      setSendingState(true);

      const formData = new FormData();
      formData.append('chat_id', String(AppState.chatActiveId));
      formData.append('message_text', text);
      if (file) {
        formData.append('file', file);
        formData.append('file_name', file.name);
      }

      try {
        const response = await api.post('/messages/send_message', formData);

        if (response.data.status === 'success') {
          if (AppState.tempChat === null) {
            AppState.addMessage(response.data.message);
          } else {
            const response = await api.get('/chats/get_chat_by_user_ids', {
              params: {
                target_id: Number(
                  AppState.tempChat.id.slice(5, AppState.tempChat.id.length),
                ),
              },
            });

            const chatId = response.data;

            // TODO: Позже заменить newChat на ответ с бэкенда
            const newChat = {
              ...AppState.tempChat,
              lastMessage: messageInput.value,
              lastMessageTime: formatLocalDateTime(),
              id: chatId,
            };
            AppState.clearTempChat();
            AppState.setChatActiveId(newChat.id);
            AppState.addPersistentChat(newChat);
          }
        }
        messageInput.value = '';
        fileInput.value = null;
      } catch (error) {
        console.error('Ошибка отправки сообщения:', error);
      } finally {
        setSendingState(false);
      }
    }
  }

  // модальное окно при нажатии на изображение
  document.addEventListener('click', function (e) {
    if (e.target.classList.contains('loaded-image')) {
      const modal = document.createElement('div');
      modal.style.position = 'fixed';
      modal.style.top = '0';
      modal.style.left = '0';
      modal.style.width = '100%';
      modal.style.height = '100%';
      modal.style.backgroundColor = 'rgba(0,0,0,0.9)';
      modal.style.display = 'flex';
      modal.style.alignItems = 'center';
      modal.style.justifyContent = 'center';
      modal.style.zIndex = '1000';

      const fullImage = document.createElement('img');
      fullImage.src = e.target.src;
      fullImage.style.maxWidth = '90%';
      fullImage.style.maxHeight = '90%';
      fullImage.style.objectFit = 'contain';

      modal.appendChild(fullImage);
      modal.onclick = () => document.body.removeChild(modal);

      document.body.appendChild(modal);
    }
  });
});
