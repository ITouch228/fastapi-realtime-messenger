import AppState from '/static/js/state.js';

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
          user_from_id: message.message.user_from_id,
          message_text: message.message.message_text,
          message_file_id: message.message.message_file_id,
          time: message.message.time,
        });
      } else {
        setTimeout(() => {
          const chatLastMessageDiv = document
            .querySelector(
              `.chat-item[data-chat-id="${String(message.message.chat_id)}"]`,
            )
            .querySelector('.chat-info')
            .querySelector('.chat-last-message');
          if (message.message.message_text)
            chatLastMessageDiv.textContent = message.message.message_text;
          else chatLastMessageDiv.textContent = 'Файл';

          const timeParts = message.message.time.split(' ');
          const lastMessageTime = `${timeParts[3]}:${timeParts[4]}`;
          const timeSpan = document.createElement('span');
          timeSpan.style.float = 'right';
          timeSpan.textContent = lastMessageTime;
          chatLastMessageDiv.appendChild(timeSpan);
        }, 300);
      }
      break;

    default:
      console.warn('Неизвестный тип сообщения:', message);
  }
}
