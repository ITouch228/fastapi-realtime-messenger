import { WS_STATUS } from '/static/js/core/constants.js';

let wsStatusEl = null;

function createWsStatusIndicator() {
  const indicator = document.createElement('div');
  indicator.className = 'ws-status-indicator';
  indicator.innerHTML = `
    <div class="ws-status-dot"></div>
    <div class="ws-status-text">Подключение...</div>
  `;
  document.body.appendChild(indicator);

  wsStatusEl = indicator;
}

/** Обновить состояние индикатора. Колбэк для connectWebSocket. */
export function updateWsStatus(status, detail) {
  if (!wsStatusEl) createWsStatusIndicator();
  if (!wsStatusEl) return;

  const dot = wsStatusEl.querySelector('.ws-status-dot');
  const text = wsStatusEl.querySelector('.ws-status-text');

  wsStatusEl.className = 'ws-status-indicator';
  dot.className = 'ws-status-dot';

  switch (status) {
    case WS_STATUS.CONNECTING:
      wsStatusEl.classList.add('ws-status-connecting');
      text.textContent = 'Подключение...';
      break;
    case WS_STATUS.CONNECTED:
      wsStatusEl.classList.add('ws-status-connected');
      text.textContent = 'Онлайн';
      break;
    case WS_STATUS.RECONNECTING:
      wsStatusEl.classList.add('ws-status-reconnecting');
      text.textContent = detail || 'Переподключение...';
      break;
    case WS_STATUS.DISCONNECTED:
      wsStatusEl.classList.add('ws-status-disconnected');
      text.textContent = detail || 'Оффлайн';
      break;
  }
}
