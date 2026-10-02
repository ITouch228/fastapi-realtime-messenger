import api from '/static/js/api.js';
import { formatTimeLocalFromUtcString } from '/static/js/utils.js';
import AppState from '/static/js/state.js';

// const MOBILE_IMAGE_QUALITY = 60; // Качество для мобильных
// const DESKTOP_IMAGE_QUALITY = 80; // Качество для десктопов
// const IMAGE_WIDTH_MOBILE = 800; // Ширина для мобильных
// const IMAGE_WIDTH_DESKTOP = 1200; // Ширина для десктопов
const IMAGE_LOAD_TIMEOUT = 10000; // 10 секунд таймаут

const messagesContainer = document.getElementById('messages');

export const getUserInfo = async userId => {
  try {
    const response = await api.get('/users/get_user_info', {
      params: { user_id: userId },
    });
    const userInfo = response.data;
    return userInfo;
  } catch (error) {
    console.error('Ошибка загрузки информации о пользователе:', error);
    return {
      username: `Пользователь ${userId}`,
      avatar: '?',
    };
  }
};

export const loadChats = async () => {
  try {
    const response = await api.get('/chats/get_user_chats');
    const chats = response.data;
    AppState.setPersistentChats(chats);
  } catch (error) {
    console.error('Ошибка загрузки чатов:', error);
  }
};

export const renderChats = async chats => {
  try {
    const chatList = document.querySelector('.chat-list');

    const chatItems = await Promise.all(
      chats.map(async chat => {
        const targetUserId = chat.users.find(id => id !== AppState.userId);
        const userInfo = await getUserInfo(targetUserId);

        // Форматируем время последнего сообщения
        let lastMessageTime = '';
        if (chat.lastMessageTime) {
          lastMessageTime = formatTimeLocalFromUtcString(chat.lastMessageTime);
        }

        // Создаем элемент чата
        const chatItem = document.createElement('div');
        chatItem.className = 'chat-item';
        chatItem.id = String(chat.id);
        chatItem.dataset.chatId = String(chat.id);

        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'chat-avatar';
        avatarDiv.textContent = userInfo.avatar || '?';

        const chatNameDiv = document.createElement('div');
        chatNameDiv.className = 'chat-name';
        chatNameDiv.textContent = userInfo.username || 'Unknown User';

        const lastMessageDiv = document.createElement('div');
        lastMessageDiv.className = 'chat-last-message';

        const lastMessageText =
          chat.lastMessage || (chat.lastMessageTime ? 'Файл' : 'Нет сообщений');
        lastMessageDiv.textContent = lastMessageText;

        if (lastMessageTime) {
          const timeSpan = document.createElement('span');
          timeSpan.style.float = 'right';
          timeSpan.textContent = lastMessageTime;
          lastMessageDiv.appendChild(timeSpan);
        }

        const chatInfoDiv = document.createElement('div');
        chatInfoDiv.className = 'chat-info';
        chatInfoDiv.appendChild(chatNameDiv);
        chatInfoDiv.appendChild(lastMessageDiv);
        chatItem.appendChild(avatarDiv);
        chatItem.appendChild(chatInfoDiv);

        if (typeof chat.id === 'number') {
          chatItem.innerHTML += `<button class="delete-chat-btn" aria-label="Удалить чат">
                        <span style="position: relative; top: -2px">×</span>
                    </button>`;

          const deleteBtn = chatItem.querySelector('.delete-chat-btn');
          deleteBtn.addEventListener('click', e => {
            e.stopPropagation();
            deleteChat(chat.id, chatItem);
          });
        }

        chatItem.addEventListener('click', () => {
          if (Number(chatItem.id) !== AppState.chatActiveId) {
            document
              .querySelectorAll('.chat-item')
              .forEach(i => i.classList.remove('active'));
            chatItem.classList.add('active');
            AppState.setChatActiveId(Number(chatItem.id));
            messagesContainer.innerHTML = '';
          }
        });

        return chatItem;
      }),
    );

    // Добавляем все элементы чатов в DOM
    chatItems.forEach(chatItem => chatList.appendChild(chatItem));

    // Если есть чаты, загружаем первый
    if (
      chats.length > 0 &&
      (AppState.chatActiveId === 0 || AppState.chatActiveId === null)
    ) {
      const firstChat = chats[0];
      document
        .querySelectorAll('.chat-item')
        .forEach(i => i.classList.remove('active'));
      document
        .querySelector(`.chat-item[id="${firstChat.id}"]`)
        .classList.add('active');
      AppState.setChatActiveId(firstChat.id);
      messagesContainer.innerHTML = '';
    } else if (AppState.tempChat !== null) {
      document
        .querySelectorAll('.chat-item')
        .forEach(i => i.classList.remove('active'));
      document
        .querySelector(`.chat-item[id="${AppState.tempChat.id}"]`)
        .classList.add('active');
      AppState.setChatActiveId(AppState.tempChat.id);
      messagesContainer.innerHTML = '';
    } else {
      document
        .querySelectorAll('.chat-item')
        .forEach(i => i.classList.remove('active'));
      document
        .querySelector(`.chat-item[id="${AppState.chatActiveId}"]`)
        ?.classList.add('active');
      messagesContainer.innerHTML = '';
    }
  } catch (error) {
    console.error('Ошибка рендера чатов:', error);
  }
};

export const loadChatMessages = async chatId => {
  try {
    const response = await api.get('/chats/get_chat_messages', {
      params: {
        chat_id: chatId,
      },
    });

    if (!response || !response.data) {
      console.error('Некорректный ответ от сервера', response);
      return;
    }

    const messages = response.data;
    messages.sort((a, b) => {
      if (a.time > b.time) return 1;
      else if (a.time === b.time) return 0;
      else return -1;
    });
    AppState.setMessages(messages);
  } catch (error) {
    console.error('Полная ошибка:', {
      message: error.message,
      response: error.response?.data,
      stack: error.stack,
    });
  }
};

export const renderMessages = async messages => {
  try {
    const imgContainers = [];

    for (const message of messages) {
      const isOutgoing = message.user_from_id === AppState.userId;
      const new_message = document.createElement('div');
      new_message.className = `message ${isOutgoing ? 'outgoing' : 'incoming'}`;
      new_message.dataset.messageId = message.id;

      // Кнопка удаления
      if (message.message_text !== 'Удалено') {
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'delete-btn';
        deleteBtn.innerHTML = '×';
        deleteBtn.onclick = () => deleteMessage(message.id, new_message);
        new_message.appendChild(deleteBtn);
      }

      // Контент сообщения
      const contentWrapper = document.createElement('div');
      contentWrapper.style.position = 'relative';

      // Файл
      if (message.message_file_id !== null) {
        const fileDiv = document.createElement('div');
        fileDiv.className =
          message.user_from_id === AppState.userId
            ? 'image message outgoing'
            : 'image message incoming';

        const fileInfo = message.file;

        if (fileInfo.kind === 'image') {
          const imgContainer = document.createElement('div');
          imgContainer.className = 'image-container lazy-load';

          const img = document.createElement('img');
          img.dataset.src = fileInfo.url;
          img.alt = 'Message image';
          img.className = 'lazy-image';
          img.loading = 'lazy';

          img.style.background = `
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E
            %3Crect width='100' height='100' fill='%23f5f5f5'/%3E
            %3Ctext x='50' y='50' font-family='Arial' font-size='10' text-anchor='middle' fill='%23ccc'%3EImage%3C/text%3E
        %3C/svg%3E") no-repeat center/contain`;

          imgContainer.appendChild(img);
          imgContainers.push(imgContainer);
          fileDiv.appendChild(imgContainer);

          imageObserver.observe(imgContainer);
        } else {
          const fileExt = fileInfo.filename.split('.').pop().toLowerCase();

          const fileLink = document.createElement('a');
          fileLink.className = 'file-attachment file-link';
          fileLink.innerHTML = `
              <span class="file-info">
                  <span class="file-name">${fileInfo.filename}</span>
                  <span class="file-size">${fileInfo.size || ''}</span>
              </span>
              <span class="file-icon">${getFileIcon(fileExt)}</span>
          `;

          fileLink.onclick = async e => {
            e.preventDefault();

            try {
              const response = await fetch(fileInfo.url, {
                credentials: 'include',
              });

              if (!response.ok) throw new Error('File download failed');

              const blob = await response.blob();
              const downloadUrl = window.URL.createObjectURL(blob);

              const a = document.createElement('a');
              a.href = downloadUrl;
              a.download = fileInfo.filename;
              document.body.appendChild(a);
              a.click();
              window.URL.revokeObjectURL(downloadUrl);
              a.remove();
            } catch (error) {
              console.error('Download error:', error);
              alert('Failed to download file');
            }
          };
          fileDiv.append(fileLink);
        }
        contentWrapper.appendChild(fileDiv);
      }

      const contentDiv = document.createElement('div');
      contentDiv.className = 'message-content';

      if (message.message_text === 'Удалено') {
        contentDiv.innerHTML = '<em>Удалено</em>';
      } else {
        contentDiv.textContent = message.message_text;
      }
      contentWrapper.appendChild(contentDiv);

      // Время
      const timeSpan = document.createElement('span');
      timeSpan.className = 'message-time';
      timeSpan.textContent = formatTimeLocalFromUtcString(message.time);

      contentWrapper.appendChild(timeSpan);

      new_message.appendChild(contentWrapper);
      messagesContainer.appendChild(new_message);
    }
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  } catch (e) {
    console.log(e);
  }
};

export const startNewChat = async targetId => {
  console.log(targetId);
  const response = await api.get('/chats/get_chat_by_user_ids', {
    params: { target_id: targetId },
  });
  const chatId = response.data;
  if (chatId) {
    const existingChat = document.getElementById(chatId);
    if (existingChat) {
      existingChat.click();
      return;
    }
  } else {
    AppState.setTempChat(targetId);
  }
};

export const deleteChat = async chatId => {
  if (
    !confirm(
      'Вы уверены, что хотите удалить этот чат? Все сообщения будут удалены.',
    )
  ) {
    return;
  }

  try {
    const response = await api.delete('/chats/delete_chat', {
      params: { chat_id: chatId },
    });

    if (!response || !response.data) {
      console.error('Некорректный ответ от сервера', response);
      return;
    }
    if (response.data) {
      // Удаляем чат из списка
      AppState.setPersistentChats(
        AppState.persistentChats.filter(chat => {
          return chat.id !== chatId;
        }),
      );

      // Если удаляемый чат был активным, очищаем область сообщений
      if (AppState.chatActiveId === chatId) {
        messagesContainer.innerHTML = '';
        AppState.setChatActiveId(0);
      }
    } else {
      throw new Error('Ошибка при удалении чата');
    }
  } catch (error) {
    console.error('Ошибка удаления чата:', error);
  }
};

export const getFileIcon = extension => {
  const icons = {
    pdf: '📄',
    doc: '📝',
    docx: '📝',
    xls: '📊',
    xlsx: '📊',
    ppt: '📑',
    pptx: '📑',
    zip: '🗂️',
    rar: '🗂️',
    '7z': '🗂️',
    mp3: '🎵',
    wav: '🎵',
    mp4: '🎬',
    mov: '🎬',
    avi: '🎬',
    txt: '📋',
    default: '📁',
  };
  return icons[extension] || icons.default;
};

// Удаление сообщений
export const deleteMessage = async (messageId, element) => {
  if (!element || !messageId) return;

  if (!confirm('Удалить сообщение?')) return;

  const response = await api.delete('/messages/delete_message', {
    params: { message_id: messageId },
  });

  if (!response || !response.data) {
    console.error('Некорректный ответ от сервера', response);
    return;
  }

  if (response.data.status === 'ok') {
    element.querySelector('.message-content').innerHTML = '<em>Удалено</em>';
    element.querySelector('.delete-btn').remove();
    element.querySelector('.image').remove();
  } else {
    console.error('Ошибка удаления сообщения');
  }
};

// Обновленная функция загрузки изображений
async function loadImageWithAuth(url, container, messagesContainer) {
  if (!container || !messagesContainer) return;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), IMAGE_LOAD_TIMEOUT);

  const isMobile = window.innerWidth <= 768;
  const quality = isMobile ? 60 : 80;
  const width = isMobile ? Math.min(800, window.innerWidth * 0.9) : 1200;

  const optimizedUrl = `${url}?quality=${quality}&width=${width}`;

  try {
    const response = await fetch(optimizedUrl, {
      headers: {
        Accept: 'image/webp,image/*;q=0.8',
      },
      credentials: 'include',
      signal: controller.signal,
      priority: 'high',
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    // Используем createImageBitmap для более эффективного декодирования
    const blob = await response.blob();
    const imageBitmap = await createImageBitmap(blob);

    const img = new Image();
    img.src = URL.createObjectURL(blob);
    img.className = 'loaded-image';
    img.loading = 'lazy';
    img.decoding = 'async';

    // Очищаем контейнер и добавляем изображение
    container.innerHTML = '';
    container.appendChild(img);

    img.onload = () => {
      // URL.revokeObjectURL(img.src);
      img.classList.add('loaded');
      imageBitmap.close();
    };

    img.onerror = () => {
      container.innerHTML = '<div class="image-error">Ошибка загрузки</div>';
      imageBitmap.close();
    };
  } catch (error) {
    console.error('Image load failed:', error);
    container.innerHTML = '<div class="image-error">Ошибка загрузки</div>';
  } finally {
    clearTimeout(timeoutId);
  }
}

const imageObserver = new IntersectionObserver(
  entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;

      const container = entry.target;
      if (container.dataset.loaded === '1') {
        imageObserver.unobserve(container);
        continue;
      }

      const img = container.querySelector('img[data-src]');
      if (img?.dataset?.src) {
        container.dataset.loaded = '1';
        loadImageWithAuth(img.dataset.src, container, messagesContainer);
      }

      imageObserver.unobserve(container);
    }
  },
  {
    root: messagesContainer,
    rootMargin: '80px',
    threshold: 0.1,
  },
);
