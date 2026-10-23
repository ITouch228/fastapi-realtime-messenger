// TODO: [SMELL] константы WS (RECONNECT_BASE_DELAY и т.д.) живут отдельно от
// frontend constants. Вынести в один файл /constants или вынести в core.
// docs/architecture.md §5: 🟢 константы разбросаны

export const RECONNECT_BASE_DELAY = 1000;
export const RECONNECT_MAX_DELAY = 30000;
export const MAX_RECONNECT_ATTEMPTS = 10;
export const WS_STATUS = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  RECONNECTING: 'reconnecting',
  DISCONNECTED: 'disconnected',
};

export const IMAGE_LOAD_TIMEOUT = 10000; // 10 секунд таймаут
export const IMAGE_PLACEHOLDER = `
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E
      %3Crect width='100' height='100' fill='%23f5f5f5'/%3E
      %3Ctext x='50' y='50' font-family='Arial' font-size='10' text-anchor='middle' fill='%23ccc'%3EImage%3C/text%3E
  %3C/svg%3E") no-repeat center/contain`;
