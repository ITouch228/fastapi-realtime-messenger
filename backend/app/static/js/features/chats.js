import api from '/static/js/core/api.js';
import store from '/static/js/core/store.js';
import {
  formatTimeLocalFromUtcString,
  formatLastSeen,
} from '/static/js/utils.js';

const messagesContainer = document.getElementById('messages');

async function getUserInfo(userId) {
  try {
    const response = await api.get(`/users/${userId}`);
    return response.data;
  } catch (error) {
    console.error('Ошибка загрузки информации о пользователе:', error);
    return {
      username: `Пользователь ${userId}`,
    };
  }
}

export const loadChats = async () => {
  try {
    const response = await api.get('/chats');
    store.setChats(response.data);
  } catch (error) {
    console.error('Ошибка загрузки чатов:', error);
  }
};

// ─── Рендер чатов ──────────────────────────────────────────────

function resolvePeerStatus(chat, targetUserId) {
  const live = store.peerStatuses[targetUserId];
  if (live) {
    return { online: !!live.online, lastSeen: live.last_seen || null };
  }
  const online =
    typeof chat?.peer_online === 'boolean' ? chat.peer_online : false;
  const lastSeen = chat?.peer_last_seen || null;
  return { online, lastSeen };
}

function createPeerStatusEl(chat, targetUserId) {
  const { online, lastSeen } = resolvePeerStatus(chat, targetUserId);

  const statusDiv = document.createElement('div');
  statusDiv.className = 'chat-peer-status';

  const dot = document.createElement('span');
  dot.className = `peer-status-dot${online ? ' online' : ''}`;

  const text = document.createElement('span');
  text.className = 'peer-status-text';
  text.textContent = online ? 'в сети' : formatLastSeen(lastSeen);

  statusDiv.append(dot, text);
  return statusDiv;
}

async function createChatItem(chat) {
  const targetUserId = chat.users.find((id) => id !== store.userId);
  const userInfo = await getUserInfo(targetUserId);

  let lastMessageSentAt = '';
  if (chat.last_message_sent_at) {
    lastMessageSentAt = formatTimeLocalFromUtcString(chat.last_message_sent_at);
  }

  const chatItem = document.createElement('div');
  chatItem.className = 'chat-item';
  chatItem.id = String(chat.id);
  chatItem.dataset.chatId = String(chat.id);

  const avatarDiv = document.createElement('div');
  avatarDiv.className = 'chat-avatar';
  avatarDiv.textContent = userInfo.username.charAt(0) || '?';

  const chatNameDiv = document.createElement('div');
  chatNameDiv.className = 'chat-name';
  chatNameDiv.textContent = userInfo.username || 'Unknown User';

  const lastMessageDiv = document.createElement('div');
  lastMessageDiv.className = 'chat-last-message';
  lastMessageDiv.textContent = chat.last_message || 'Нет сообщений';

  if (lastMessageSentAt) {
    const timeSpan = document.createElement('span');
    timeSpan.style.float = 'right';
    timeSpan.textContent = lastMessageSentAt;
    lastMessageDiv.appendChild(timeSpan);
  }

  const chatInfoDiv = document.createElement('div');
  chatInfoDiv.className = 'chat-info';
  chatInfoDiv.append(
    chatNameDiv,
    createPeerStatusEl(chat, targetUserId),
    lastMessageDiv,
  );

  chatItem.append(avatarDiv, chatInfoDiv);

  if (typeof chat.id === 'number') {
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'delete-chat-btn';
    deleteBtn.setAttribute('aria-label', 'Удалить чат');

    const span = document.createElement('span');
    span.style.position = 'relative';
    span.style.top = '-2px';
    span.textContent = '×';

    deleteBtn.appendChild(span);
    chatItem.appendChild(deleteBtn);

    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteChat(chat.id);
    });
  }
  // temp-чат: без кнопки удаления, без парсинга ID при клике

  chatItem.addEventListener('click', () => {
    if (store.ui.activeChatId === chatItem.dataset.chatId) return;
    document
      .querySelectorAll('.chat-item')
      .forEach((i) => i.classList.remove('active'));
    chatItem.classList.add('active');
    store.setActiveChat(chat.id);
    messagesContainer.innerHTML = '';
  });

  return chatItem;
}

export const renderChats = async (chats) => {
  try {
    const chatList = document.querySelector('.chat-list');
    chatList.innerHTML = ''; // Очищаем перед рендером

    const chatItems = await Promise.all(chats.map(createChatItem));
    chatList.append(...chatItems);

    // Активируем первый чат или текущий активный
    if (chats.length > 0) {
      document
        .querySelectorAll('.chat-item')
        .forEach((i) => i.classList.remove('active'));
      document
        .querySelector(`.chat-item[id="${chats[0].id}"]`)
        ?.classList.add('active');
      if (!store.ui.activeChatId) {
        store.setActiveChat(chats[0].id);
      }
    }
  } catch (error) {
    console.error('Ошибка рендера чатов:', error);
  }
};

/** Обновить статусы собеседников в уже отрисованном списке чатов. */
export function updatePeerStatusesInDom() {
  document.querySelectorAll('.chat-item').forEach((chatItem) => {
    const statusEl = chatItem.querySelector('.chat-peer-status');
    if (!statusEl) return;

    const chatId = Number(chatItem.dataset.chatId);
    if (!Number.isFinite(chatId)) return;

    const chat = store.chats.byId.get(chatId);
    if (!chat) return;

    const targetUserId = chat.users.find((id) => id !== store.userId);
    if (!targetUserId) return;

    const { online, last_seen } = store.getPeerStatus(targetUserId);
    const dot = statusEl.querySelector('.peer-status-dot');
    const text = statusEl.querySelector('.peer-status-text');
    if (dot) dot.classList.toggle('online', online);
    if (text) text.textContent = online ? 'в сети' : formatLastSeen(last_seen);
  });
}

// ─── Создание / удаление чата ──────────────────────────────────

export const startNewChat = async (targetId) => {
  const response = await api.get(`/chats/direct/${targetId}`);
  const chatId = response.data;
  if (chatId) {
    // существующий чат — просто переключаемся
    const existingChat = document.getElementById(chatId);
    if (existingChat) {
      existingChat.click();
      return;
    }
  } else {
    // новый чат — создаём temp-чат с peer_id
    const tempChat = {
      id: `temp-${targetId}`,
      users: [store.userId, targetId],
      last_message: null,
      last_message_sent_at: null,
    };
    store.addChat(tempChat);

    // Если temp-чат стал активным — обновляем UI
    if (store.ui.activeChatId === tempChat.id) {
      store.setActiveChat(tempChat.id);
    }
  }
};

export const deleteChat = async (chatId) => {
  if (
    !confirm(
      'Вы уверены, что хотите удалить этот чат? Все сообщения будут удалены.',
    )
  ) {
    return;
  }

  try {
    const wasActive = store.ui.activeChatId === chatId;

    await api.delete(`/chats/${chatId}`);
    store.removeChat(chatId);

    if (wasActive) {
      messagesContainer.innerHTML = '';
    }
  } catch (error) {
    console.error('Ошибка удаления чата:', error);
  }
};
