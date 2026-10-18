import api from '/static/js/core/api.js';
import store from '/static/js/core/store.js';
import { formatTimeLocalFromUtcString, getFileIcon } from '/static/js/utils.js';
import { imageObserver } from '/static/js/ui/imageLoader.js';

const messagesContainer = document.getElementById('messages');

// TODO: [SMELL] IMAGE_PLACEHOLDER захардкожен — вынести в constants.
// docs/architecture.md §5: 🟢 IMAGE_PLACEHOLDER захардкожен
const IMAGE_PLACEHOLDER = `
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E
      %3Crect width='100' height='100' fill='%23f5f5f5'/%3E
      %3Ctext x='50' y='50' font-family='Arial' font-size='10' text-anchor='middle' fill='%23ccc'%3EImage%3C/text%3E
  %3C/svg%3E") no-repeat center/contain`;

// ─── Фабрика элемента сообщения ────────────────────────────────

function createImageFileEl(fileInfo) {
  const imgContainer = document.createElement('div');
  imgContainer.className = 'image-container lazy-load';

  const img = document.createElement('img');
  img.dataset.src = fileInfo.url;
  img.alt = 'Message image';
  img.className = 'lazy-image';
  img.loading = 'lazy';
  img.style.background = IMAGE_PLACEHOLDER;

  // Blob URL (оптимистичное сообщение) — ставим сразу, без observer
  if (fileInfo.url.startsWith('blob:')) {
    img.src = fileInfo.url;
    img.className = 'loaded-image loaded';
    imgContainer.appendChild(img);
    return imgContainer;
  }

  imgContainer.appendChild(img);
  imageObserver.observe(imgContainer);

  return imgContainer;
}

async function downloadFile(fileInfo) {
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
}

function createAttachFileEl(fileInfo) {
  const fileExt = fileInfo.filename.split('.').pop().toLowerCase();

  const fileLink = document.createElement('a');

  const fileInfoSpan = document.createElement('span');
  fileInfoSpan.className = 'file-info';

  const fileNameSpan = document.createElement('span');
  fileNameSpan.className = 'file-name';
  fileNameSpan.textContent = fileInfo.filename;

  const fileSizeSpan = document.createElement('span');
  fileSizeSpan.className = 'file-size';
  fileSizeSpan.textContent = fileInfo.size || '';

  fileInfoSpan.append(fileNameSpan, fileSizeSpan);

  const fileIconSpan = document.createElement('span');
  fileIconSpan.className = 'file-icon';
  fileIconSpan.textContent = getFileIcon(fileExt);

  fileLink.append(fileInfoSpan, fileIconSpan);
  fileLink.onclick = (e) => {
    e.preventDefault();
    downloadFile(fileInfo);
  };

  return fileLink;
}

function createFileEl(message) {
  const fileInfo = message.file;

  const fileDiv = document.createElement('div');
  fileDiv.className =
    message.sender_id === store.userId
      ? 'image message outgoing'
      : 'image message incoming';

  if (fileInfo.kind === 'image') {
    fileDiv.appendChild(createImageFileEl(fileInfo));
  } else {
    fileDiv.appendChild(createAttachFileEl(fileInfo));
  }

  return fileDiv;
}

/**
 * Создаёт DOM-элемент сообщения. Единственный источник разметки сообщения.
 */
function createMessageEl(message) {
  const isOutgoing = message.sender_id === store.userId;

  const el = document.createElement('div');
  el.className = `message ${isOutgoing ? 'outgoing' : 'incoming'}`;
  el.dataset.messageId = message.id;

  // Кнопка удаления
  if (!message.is_deleted && message.sender_id === store.userId) {
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'delete-btn';
    deleteBtn.innerHTML = '×';
    deleteBtn.onclick = () => deleteMessage(message.id, el);
    el.appendChild(deleteBtn);
  }

  const contentWrapper = document.createElement('div');
  contentWrapper.style.position = 'relative';

  // Файл
  if (message.message_file_id !== null && message.file) {
    contentWrapper.appendChild(createFileEl(message));
  }

  // Текст
  const contentDiv = document.createElement('div');
  contentDiv.className = 'message-content';

  if (message.is_deleted) {
    contentDiv.innerHTML = '<em>Удалено</em>';
  } else {
    contentDiv.textContent = message.message_text;
  }
  contentWrapper.appendChild(contentDiv);

  // Время + статус доставки
  const timeSpan = document.createElement('span');
  timeSpan.className = 'message-time';
  timeSpan.textContent = formatTimeLocalFromUtcString(message.sent_at);

  if (isOutgoing) {
    const statusSpan = document.createElement('span');
    statusSpan.className = `message-status${message.sended === false ? ' message-status-pending' : ''}`;
    statusSpan.dataset.messageId = message.id;
    statusSpan.textContent = message.sended === false ? '⏳' : '✓';
    timeSpan.appendChild(statusSpan);
  }
  contentWrapper.appendChild(timeSpan);

  el.appendChild(contentWrapper);
  return el;
}

// ─── Публичные функции отрисовки ───────────────────────────────

/** Полная перерисовка списка сообщений активного чата. */
export function renderMessages(messages) {
  try {
    messagesContainer.innerHTML = '';

    const fragment = document.createDocumentFragment();
    for (const message of messages) {
      fragment.appendChild(createMessageEl(message));
    }
    messagesContainer.appendChild(fragment);

    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  } catch (error) {
    console.error('Ошибка рендера сообщений:', error);
  }
}

/** Добавление одного сообщения в конец списка (отправка / входящее). */
export function appendMessage(message) {
  try {
    messagesContainer.appendChild(createMessageEl(message));
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  } catch (error) {
    console.error('Ошибка рендера нового сообщения:', error);
  }
}

/** Пометить сообщение в DOM как удалённое. */
function applyDeletedInDom(el) {
  const content = el.querySelector('.message-content');
  if (content) content.innerHTML = '<em>Удалено</em>';
  el.querySelector('.delete-btn')?.remove();
  el.querySelector('.image')?.remove();
}

/** Точечное обновление сообщения в DOM (без полной перерисовки). */
export function updateMessageInDom(oldId, message) {
  const el = messagesContainer.querySelector(`[data-message-id="${oldId}"]`);
  if (!el) return;

  // Обновляем реальный ID сообщения
  el.dataset.messageId = message.id;

  // Мягкое удаление
  if (message.is_deleted) {
    applyDeletedInDom(el);
    return;
  }

  // Файл мог прийти только что (optimistic без файла → подтверждённый с файлом) —
  // точечно до media-блок нельзя, пересоздаём элемент целиком
  if (message.file && !el.querySelector('.image-container, .file-info')) {
    el.replaceWith(createMessageEl(message));
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    return;
  }

  // Статус доставки для исходящих
  const isOutgoing = message.sender_id === store.userId;
  if (isOutgoing) {
    const statusSpan = el.querySelector('.message-status');
    if (statusSpan) {
      statusSpan.className = 'message-status';
      statusSpan.dataset.messageId = message.id;
      statusSpan.textContent = '✓';
    }
  }
}

/** Удаление сообщения (мягкое) с обновлением DOM. */
export async function deleteMessage(messageId, element) {
  if (!element || !messageId) return;

  if (!confirm('Удалить сообщение?')) return;

  try {
    await api.delete(`/messages/${messageId}`);
    store.softDeleteMessage(messageId);
    applyDeletedInDom(element);
  } catch (error) {
    console.error('Ошибка удаления сообщения:', error);
  }
}
