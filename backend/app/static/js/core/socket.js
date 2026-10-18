import {
  RECONNECT_BASE_DELAY,
  RECONNECT_MAX_DELAY,
  MAX_RECONNECT_ATTEMPTS,
  WS_STATUS,
} from '/static/js/core/constants.js';

let socket = null;
let reconnectAttempts = 0;
let reconnectTimer = null;
let intentionalClose = false;

function wsUrl(path) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/api/ws${path}`;
}

let statusCallback = null;

function updateStatus(status, detail) {
  if (statusCallback) {
    statusCallback(status, detail);
  }
}

function scheduleReconnect(userId, messageHandler) {
  if (intentionalClose) return;

  reconnectAttempts += 1;

  if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
    updateStatus(
      WS_STATUS.DISCONNECTED,
      'Соединение потеряно. Обновите страницу.',
    );
    return;
  }

  const delay = Math.min(
    RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttempts - 1),
    RECONNECT_MAX_DELAY,
  );

  updateStatus(
    WS_STATUS.RECONNECTING,
    `Переподключение (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`,
  );

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    openSocket(userId, messageHandler);
  }, delay);
}

function openSocket(userId, messageHandler) {
  const url = wsUrl(`/${userId}`);

  updateStatus(
    reconnectAttempts === 0 ? WS_STATUS.CONNECTING : WS_STATUS.RECONNECTING,
    reconnectAttempts === 0 ? 'Подключение...' : undefined,
  );

  try {
    socket = new WebSocket(url);

    socket.onopen = () => {
      reconnectAttempts = 0;
      updateStatus(WS_STATUS.CONNECTED);
    };

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message && typeof message === 'object') {
          if (message.type === 'ping') {
            if (socket && socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: 'pong' }));
            }
            return;
          }
          messageHandler(message);
        } else {
          console.warn('Invalid message received:', event.data);
        }
      } catch (e) {
        console.error('Error parsing WebSocket message:', e);
      }
    };

    socket.onclose = (event) => {
      // 4401/4404 — auth fail, переподключение бессмысленно
      if (event.code === 4401 || event.code === 4404) {
        updateStatus(
          WS_STATUS.DISCONNECTED,
          'Сессия недействительна. Обновите страницу.',
        );
        return;
      }

      if (intentionalClose) {
        updateStatus(WS_STATUS.DISCONNECTED, null);
        return;
      }

      scheduleReconnect(userId, messageHandler);
    };

    socket.onerror = () => {
      console.warn('WebSocket error');
    };
  } catch (error) {
    console.error('Failed to create WebSocket connection:', error);
    scheduleReconnect(userId, messageHandler);
  }
}

export function connectWebSocket(userId, messageHandler, onStatusChange) {
  if (!userId || !messageHandler || typeof messageHandler !== 'function') {
    console.error('Invalid parameters for connectWebSocket:', {
      userId,
      messageHandler,
    });
    return;
  }

  if (typeof onStatusChange === 'function') {
    statusCallback = onStatusChange;
  }

  intentionalClose = false;
  reconnectAttempts = 0;
  openSocket(userId, messageHandler);
}

export function closeWebSocket() {
  intentionalClose = true;

  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  if (socket) {
    if (
      socket.readyState === WebSocket.OPEN ||
      socket.readyState === WebSocket.CONNECTING
    ) {
      socket.close(1000, 'Client disconnecting');
    }
    socket = null;
  }

  updateStatus(WS_STATUS.DISCONNECTED, null);
}
