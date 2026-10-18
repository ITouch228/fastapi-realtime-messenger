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
