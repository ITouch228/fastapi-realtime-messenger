import api from '/static/js/core/api.js';
import store from '/static/js/core/store.js';

export function initSender({ messageInput, fileInput, sendBtn }) {
  let isSending = false;

  const setSendingState = (state) => {
    isSending = state;
    sendBtn.disabled = state;
    messageInput.disabled = state;
    fileInput.disabled = state;
    sendBtn.style.opacity = state ? '0.6' : '';
    sendBtn.style.pointerEvents = state ? 'none' : '';
  };

  async function sendMessage() {
    if (isSending) return;

    const activeChatId = store.ui.activeChatId;
    if (activeChatId === null) return;

    const text = messageInput.value.trim();
    const file = fileInput.files[0];

    if (!text && !file) return;

    // client_id — стабильный идентификатор от клиента: сервер вернёт его
    // в ответе и в WS-событии, что позволяет надёжно подтвердить
    // оптимистичное сообщение (без матчинга по тексту)
    const clientId =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

    // Оптимистично добавляем сообщение в стор
    const optimisticMsg = {
      message_text: text,
      sender_id: store.userId,
      sent_at: new Date().toISOString(),
      is_deleted: false,
      message_file_id: file ? -1 : null,
      file: file
        ? {
            url: URL.createObjectURL(file),
            kind: file.type.startsWith('image/') ? 'image' : 'file',
            filename: file.name,
          }
        : null,
    };
    store.addOptimisticMessage(activeChatId, optimisticMsg, clientId);

    messageInput.value = '';
    fileInput.value = null;
    setSendingState(true);

    const formData = new FormData();
    formData.append('message_text', text);
    formData.append('client_id', clientId);
    if (file) {
      formData.append('file', file);
      formData.append('file_name', file.name);
    }

    // Передаём peer_id — сервер создаст реальный чат вместо парсинга temp-строки
    if (typeof activeChatId === 'string' && activeChatId.startsWith('temp-')) {
      formData.append('peer_id', activeChatId.replace('temp-', ''));
    }

    try {
      const response = await api.post(`/messages/${activeChatId}`, formData);

      if (store.isTempChat(activeChatId)) {
        // temp-чат → заменяем на реальный ID и подтверждаем сообщение
        const realChatId = response.data.chat_id;
        store.replaceTempChat(activeChatId, realChatId);
        store.confirmMessage(response.data, clientId);
      } else {
        // обычный чат: подтверждаем оптимистичное сообщение по client_id
        store.confirmMessage(response.data, clientId);
      }
    } catch (error) {
      console.error('Ошибка отправки сообщения:', error);
      const detail = error?.response?.data?.detail;
      alert(
        typeof detail === 'string' ? detail : 'Не удалось отправить сообщение',
      );
    } finally {
      setSendingState(false);
    }
  }

  sendBtn.addEventListener('click', sendMessage);

  messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  messageInput.addEventListener('paste', (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const fileItem = Array.from(items).find((it) => it.kind === 'file');
    if (!fileItem) return;

    const file = fileItem.getAsFile();
    if (!file) return;

    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;

    e.preventDefault();
  });
}
