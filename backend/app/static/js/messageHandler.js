import AppState from '/static/js/state.js';
import { formatTimeLocalFromUtcString } from '/static/js/utils.js';

export function handleWebSocketMessage(message) {
  if (!message || typeof message !== 'object') {
    console.error('Invalid message received:', message);
    return;
  }

  switch (message.type) {
    case 'new_chat':
      if (!message.message || typeof message.message !== 'object') {
        console.error('Invalid message structure:', message);
        return;
      }
      AppState.addPersistentChat(message.message);
      break;
    case 'new_message':
      if (!message.message || typeof message.message !== 'object') {
        console.error('Invalid message structure:', message);
        return;
      }

      if (document.getElementById('NotifySound')) {
        document
          .getElementById('NotifySound')
          .play()
          .catch(e => console.warn('Notification sound failed:', e));
      }

      if (message.message.chat_id === AppState.chatActiveId) {
        AppState.addMessage({
          id: message.message.id,
          chat_id: message.message.chat_id,
          sender_id: message.message.sender_id,
          message_text: message.message.message_text,
          message_file_id: message.message.message_file_id,
          sent_at: message.message.sent_at,
          file: message.message.file,
        });
      } else {
        setTimeout(() => {
          const chatItem = document.querySelector(
            `.chat-item[data-chat-id="${String(message.message.chat_id)}"]`,
          );
          const chatLastMessageDiv = chatItem
            ?.querySelector('.chat-info')
            ?.querySelector('.chat-last-message');
          if (!chatLastMessageDiv) return;

          chatLastMessageDiv.textContent = message.message.message_text || 'Файл';

          const timeSpan = document.createElement('span');
          timeSpan.style.float = 'right';
          timeSpan.textContent = formatTimeLocalFromUtcString(message.message.sent_at);
          chatLastMessageDiv.appendChild(timeSpan);
        }, 300);
      }
      break;

    default:
      console.warn('Неизвестный тип сообщения:', message);
  }
}
