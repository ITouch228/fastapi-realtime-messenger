import store from '/static/js/core/store.js';

export function handleWebSocketMessage(message) {
  if (!message || typeof message !== 'object') {
    console.error('Invalid message received:', message);
    return;
  }

  switch (message.type) {
    case 'new_chat':
      if (!message.message || typeof message.message !== 'object') {
        console.error('Invalid new_chat message structure:', message);
        return;
      }
      store.addChat(message.message);

      // Если активный чат — temp-чат с этими же пользователями,
      // заменяем на реальный ID (сохраняя сообщения и флаги загрузки)
      const newChat = message.message;
      const tempChatId = store.ui.activeChatId;
      if (tempChatId && store.isTempChat(tempChatId)) {
        const tempChat = store.chats.byId.get(tempChatId);
        if (tempChat) {
          const sameUsers =
            tempChat.users.length === newChat.users.length &&
            tempChat.users.every((id) => newChat.users.includes(id));
          if (sameUsers) {
            store.replaceTempChat(tempChatId, newChat.id);
          }
        }
      }
      break;

    case 'new_message':
      if (!message.message || typeof message.message !== 'object') {
        console.error('Invalid new_message message structure:', message);
        return;
      }

      const msg = message.message;
      const chatId = Number(msg.chat_id);
      const isActive = store.ui.activeChatId === chatId;

      // Звук уведомления
      const notifySound = document.getElementById('NotifySound');
      if (notifySound && !isActive) {
        notifySound.play().catch(() => {});
      }

      if (isActive) {
        // Подтверждаем по client_id (или добавляем, если не было оптимистичного)
        store.confirmMessage(msg, message.client_id);
      } else {
        // Неактивный чат — обновляем last_message и инвалидируем кэш
        // сообщений, чтобы при открытии чата они загрузились с сервера
        store.updateChatLastMessage(chatId, msg);
        store.invalidateMessages(chatId);
      }
      break;

    case 'presence_update':
      if (typeof message.online !== 'boolean') {
        console.error('Invalid presence_update:', message);
        return;
      }
      store.setPeerStatus(message.user_id, {
        online: message.online,
        last_seen: message.last_seen || null,
      });
      break;

    default:
      console.warn('Unknown WS message type:', message.type);
  }
}
