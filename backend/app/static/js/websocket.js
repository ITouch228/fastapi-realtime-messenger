let socket = null;

function wsUrl(path) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/api/ws${path}`;
}

export function connectWebSocket(userId, messageHandler) {
  if (!userId || !messageHandler || typeof messageHandler !== 'function') {
    console.error('Invalid parameters for connectWebSocket:', {
      userId,
      messageHandler,
    });
    return;
  }

  const url = wsUrl(`/${userId}`);
  if (!isValidWsUrl(url)) {
    console.error('Invalid WebSocket URL:', url);
    return;
  }

  try {
    socket = new WebSocket(url);

    socket.onopen = () => {
      console.log('WebSocket соединение установлено');
    };

    socket.onmessage = event => {
      try {
        const message = JSON.parse(event.data);
        if (message && typeof message === 'object') {
          messageHandler(message);
        } else {
          console.warn('Invalid message received:', event.data);
        }
      } catch (e) {
        console.error('Error parsing WebSocket message:', e);
      }
    };

    socket.onclose = event => {
      console.log('WebSocket соединение закрыто', event.code, event.reason);
    };

    socket.onerror = error => {
      console.error('WebSocket ошибка:', error);
    };
  } catch (error) {
    console.error('Failed to create WebSocket connection:', error);
  }
}

function isValidWsUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'ws:' || parsed.protocol === 'wss:';
  } catch {
    return false;
  }
}

export function closeWebSocket() {
  if (socket) {
    socket.close(1000, 'Client disconnecting');
    socket = null;
  }
}
