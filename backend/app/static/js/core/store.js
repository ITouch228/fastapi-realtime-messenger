/**
 * Централизованный стор для управления чатами и сообщениями.
 * Нормализованная структура данных + реактивная система подписок.
 *
 * Структура:
 *   chats.byId   — Map<chatId, Chat>
 *   chats.order  — Array<chatId> — порядок чатов в списке
 *   messages.byId — Map<chatId, Map<msgId, Message>>
 *   messages.loading — Map<chatId, boolean>
 *   peerStatuses — Map<userId, { online, last_seen }>
 *   ui.activeChatId — текущий активный чат
 *   userId — ID текущего пользователя
 */

const store = {
  // ─── Пользователь ─────────────────────────────────────────────
  _userId: null,

  get userId() {
    return this._userId;
  },

  set userId(value) {
    this._userId = value;
    this.notify('userId');
  },

  // ─── UI-состояние ─────────────────────────────────────────────
  ui: {
    _activeChatId: null,

    get activeChatId() {
      return this._activeChatId;
    },

    set activeChatId(value) {
      this._activeChatId = value;
      store.notify('activeChat');
    },
  },

  setActiveChat(chatId) {
    this.ui.activeChatId = chatId;
  },

  /**
   * Проверка, является ли чат temp-чatom.
   */
  isTempChat(chatId) {
    return typeof chatId === 'string' && chatId.startsWith('temp-');
  },

  // ─── Чаты (нормализованные) ───────────────────────────────────
  chats: {
    byId: new Map(),
    order: [],

    /**
     * Устанавливает весь список чатов (первичная загрузка).
     */
    setAll(chats) {
      this.byId.clear();
      this.order = [];

      for (const chat of chats) {
        this.byId.set(chat.id, chat);
        this.order.push(chat.id);
      }

      store.notify('chatList');
    },

    /**
     * Добавляет новый чат (из WebSocket или создания нового).
     * Перемещает чат в начало списка.
     */
    add(chat) {
      const exists = this.byId.has(chat.id);
      if (!exists) {
        this.order.unshift(chat.id);
      }
      this.byId.set(chat.id, chat);
      store.notify('chatList');
    },

    /**
     * Обновляет last_message в чате (из WebSocket).
     */
    updateLastMessage(chatId, message) {
      const chat = this.byId.get(chatId);
      if (!chat) return;

      const lastMessageText = message.message_text || '';
      const lastMessageSentAt = message.sent_at || null;

      chat.last_message = lastMessageText;
      chat.last_message_sent_at = lastMessageSentAt;

      // Перемещаем чат в начало списка
      const idx = this.order.indexOf(chatId);
      if (idx > 0) {
        this.order.splice(idx, 1);
        this.order.unshift(chatId);
      }

      this.byId.set(chatId, chat);
      store.notify('chatList');
    },

    /**
     * Удаляет чат из стора.
     */
    remove(chatId) {
      this.byId.delete(chatId);
      this.order = this.order.filter((id) => id !== chatId);
      store.notify('chatList');
    },
  },

  /**
   * Получить все чаты в порядке отображения.
   */
  getChats() {
    return this.chats.order
      .map((id) => this.chats.byId.get(id))
      .filter(Boolean);
  },

  /**
   * Получить чат по ID.
   */
  getChat(chatId) {
    return this.chats.byId.get(chatId);
  },

  // ─── Сообщения (нормализованные по чатам) ─────────────────────
  messages: {
    byId: new Map(), // Map<chatId, Map<msgId, Message>>
    loading: new Map(), // Map<chatId, boolean>
    loaded: new Map(), // Map<chatId, boolean> — загружено ли с сервера

    /**
     * Приводит chatId к единому типу: number для реальных чатов,
     * строка `temp-*` для temp-чатов. Устраняет разнобой ключей Map.
     */
    _normalizeChatId(chatId) {
      if (typeof chatId === 'string' && chatId.startsWith('temp-')) {
        return chatId;
      }
      const num = Number(chatId);
      return Number.isFinite(num) ? num : chatId;
    },

    /**
     * Инициализирует Map для чата, если ещё не создан.
     */
    _ensureChatMap(chatId) {
      const key = this._normalizeChatId(chatId);
      if (!this.byId.has(key)) {
        this.byId.set(key, new Map());
      }
      return key;
    },

    /**
     * Устанавливает сообщения для чата (первичная загрузка).
     */
    setAll(chatId, messages) {
      const key = this._ensureChatMap(chatId);
      const chatMap = this.byId.get(key);
      chatMap.clear();

      for (const msg of messages) {
        chatMap.set(msg.id, msg);
      }

      // Отмечаем чат как загруженный — даже если сообщений нет,
      // повторно дёргать сервер не нужно
      this.loaded.set(key, true);
      store.notify('messages:replaced', key);
    },

    /**
     * Добавляет одно новое сообщение в чат.
     */
    add(chatId, message) {
      const key = this._ensureChatMap(chatId);
      const chatMap = this.byId.get(key);
      chatMap.set(message.id, message);

      store.notify('message:new', message);
    },

    /**
     * Проверяет, загружены ли сообщения чата с сервера.
     * Отличается от «есть сообщения»: пустой чат тоже считается загруженным.
     */
    isLoaded(chatId) {
      return this.loaded.get(this._normalizeChatId(chatId)) === true;
    },

    /**
     * Получает все сообщения для чата, отсортированные по ID.
     */
    getAll(chatId) {
      const chatMap = this.byId.get(this._normalizeChatId(chatId));
      if (!chatMap) return [];

      return Array.from(chatMap.values()).sort(
        (a, b) => (a.id || 0) - (b.id || 0),
      );
    },

    /**
     * Помечает чат как загружающийся.
     */
    setLoading(chatId, value) {
      this.loading.set(this._normalizeChatId(chatId), value);
    },

    /**
     * Проверяет, загружается ли чат.
     */
    isLoading(chatId) {
      return this.loading.get(this._normalizeChatId(chatId)) === true;
    },

    /**
     * Удаляет все сообщения чата и сбрасывает флаг загрузки.
     */
    clear(chatId) {
      const key = this._normalizeChatId(chatId);
      this.byId.delete(key);
      this.loading.delete(key);
      this.loaded.delete(key);
    },

    /**
     * Мягкое удаление сообщения (отметка is_deleted).
     */
    softDelete(chatId, messageId) {
      const chatMap = this.byId.get(this._normalizeChatId(chatId));
      if (!chatMap) return;

      const msg = chatMap.get(messageId);
      if (msg) {
        msg.is_deleted = true;
        chatMap.set(messageId, msg);
        store.notify('message:update', {
          oldId: messageId,
          message: msg,
        });
      }
    },
  },

  /**
   * Проверить, загружены ли сообщения чата с сервера.
   */
  isLoaded(chatId) {
    return this.messages.isLoaded(chatId);
  },

  /**
   * Инвалидировать кэш сообщений чата (например, пришло сообщение
   * в неактивный чат — при следующем открытии загрузим с сервера).
   */
  invalidateMessages(chatId) {
    this.messages.clear(chatId);
  },

  /**
   * Установить сообщения для чата.
   */
  setMessages(chatId, messages) {
    this.messages.setAll(chatId, messages);
  },

  /**
   * Получить сообщения для чата.
   */
  getMessages(chatId) {
    return this.messages.getAll(chatId);
  },

  /**
   * Установить статус загрузки для чата.
   */
  setLoading(chatId, value) {
    this.messages.setLoading(chatId, value);
  },

  // ─── Peer statuses (онлайн-статусы пользователей) ──────────────
  peerStatuses: {},

  /**
   * Установить статус конкретного пользователя.
   */
  setPeerStatus(userId, status) {
    this.peerStatuses[userId] = status;
    store.notify('peerStatuses');
  },

  /**
   * Получить статус пользователя.
   */
  getPeerStatus(userId) {
    return this.peerStatuses[userId] || { online: false, last_seen: null };
  },

  // ─── Подписки (реактивная система) ─────────────────────────────
  _subscribers: new Map(),

  /**
   * Подписаться на событие.
   * @param {string} key — ключ события ('chatList', 'activeChat', 'messages', 'messages:chatId', 'peerStatuses')
   * @param {Function} callback — функция обратного вызова
   * @returns {Function} функция для отписки
   */
  subscribe(key, callback) {
    if (typeof callback !== 'function') {
      console.error('Invalid callback function provided:', callback);
      return () => {};
    }

    if (!this._subscribers.has(key)) {
      this._subscribers.set(key, new Set());
    }

    this._subscribers.get(key).add(callback);

    // Возвращаем функцию для отписки
    return () => {
      const set = this._subscribers.get(key);
      if (set) {
        set.delete(callback);
        if (set.size === 0) {
          this._subscribers.delete(key);
        }
      }
    };
  },

  /**
   * Уведомить подписчиков о изменении.
   * @param {string} key — ключ события
   */
  notify(key, payload) {
    const subscribers = this._subscribers.get(key);
    if (!subscribers || subscribers.size === 0) return;

    for (const callback of subscribers) {
      try {
        callback(payload);
      } catch (error) {
        console.error(`Error in subscriber callback for "${key}":`, error);
      }
    }
  },

  // ─── Convenience-методы (используются в messageHandler.js) ─────

  /**
   * Установить список чатов (альяс для setChats).
   */
  setChats(chats) {
    this.chats.setAll(chats);
  },

  /**
   * Добавить чат (обёртка над chats.add).
   */
  addChat(chat) {
    this.chats.add(chat);
  },

  /**
   * Обновить last_message чата (обёртка над chats.updateLastMessage).
   */
  updateChatLastMessage(chatId, message) {
    this.chats.updateLastMessage(chatId, message);
  },

  /**
   * Оптимистично добавить сообщение (до подтверждения сервером).
   * clientId — стабильный идентификатор от клиента (uuid), по нему
   * сервер вернёт подтверждение, и мы надёжно заменим temp → real.
   * Возвращает temp ID для последующей замены.
   */
  addOptimisticMessage(chatId, messageData, clientId) {
    const optimisticMsg = {
      ...messageData,
      id: `temp-msg-${clientId}`,
      chat_id: chatId,
      sended: false,
      client_id: clientId,
    };
    this.messages.add(chatId, optimisticMsg);
    return optimisticMsg.id;
  },

  /**
   * Подтвердить доставку сообщения (WS или POST-ответ).
   * Матчинг по client_id (надёжно) → по реальному id (идемпотентно) → новое.
   */
  confirmMessage(message, clientId) {
    const chatId = message.chat_id;
    if (chatId === undefined) return;

    const key = this.messages._ensureChatMap(chatId);
    const chatMap = this.messages.byId.get(key);

    // Уже подтверждено этим id — повторный вызов игнорируем
    const existing = chatMap.get(message.id);
    if (existing && existing.sended === true) return;

    // 1. Находим оптимистичное сообщение по client_id
    if (clientId) {
      for (const [msgKey, msg] of chatMap) {
        if (msg.sended === false && msg.client_id === clientId) {
          chatMap.delete(msgKey);
          chatMap.set(message.id, {
            ...message,
            sended: true,
            client_id: clientId,
          });
          store.notify('message:update', { oldId: msgKey, message });
          return;
        }
      }
    }

    // 2. Сообщение уже есть по реальному id — обновляем
    if (existing) {
      chatMap.set(message.id, { ...existing, ...message, sended: true });
      store.notify('message:update', { oldId: message.id, message });
      return;
    }

    // 3. Новое сообщение (например, входящее от собеседника)
    chatMap.set(message.id, { ...message, sended: true });
    store.notify('message:new', { ...message, sended: true });
  },

  /**
   * Добавить сообщение (обёртка над messages.add).
   * Prevents duplicates.
   */
  addMessage(message) {
    const chatId = message.chat_id;
    if (chatId === undefined) return;

    const key = this.messages._normalizeChatId(chatId);
    const chatMap = this.messages.byId.get(key);
    if (chatMap && chatMap.has(message.id)) return;

    this.messages.add(chatId, message);
  },

  /**
   * Мягкое удаление сообщения (обёртка над messages.softDelete).
   */
  softDeleteMessage(messageId) {
    // Находим чат, в котором есть это сообщение
    for (const [chatId, chatMap] of this.messages.byId) {
      if (chatMap.has(messageId)) {
        this.messages.softDelete(chatId, messageId);
        return;
      }
    }
  },

  /**
   * Удалить чат (обёртка над chats.remove).
   */
  removeChat(chatId) {
    this.chats.remove(chatId);
    this.messages.clear(chatId);

    if (this.ui.activeChatId === chatId) {
      this.ui.activeChatId = null;
    }
  },

  /**
   * Заменить temp-чат на реальный ID (после создания чата на сервере).
   * Переносит чат, сообщения, флаги загрузки и активный ID на новый ключ.
   */
  replaceTempChat(tempId, realId) {
    const chat = this.chats.byId.get(tempId);
    if (!chat) return;

    // Удаляем temp, добавляем реальный с теми же данными
    const idx = this.chats.order.indexOf(tempId);
    this.chats.byId.delete(tempId);
    this.chats.order = this.chats.order.filter((id) => id !== tempId);

    const realChat = { ...chat, id: realId };
    this.chats.byId.set(realId, realChat);
    if (idx !== -1) {
      this.chats.order.splice(idx, 0, realId);
    } else {
      this.chats.order.unshift(realId);
    }

    // Переносим сообщения и флаги загрузки на реальный ключ
    const tempMsgs = this.messages.byId.get(tempId);
    if (tempMsgs) {
      this.messages.byId.set(realId, tempMsgs);
      this.messages.byId.delete(tempId);
    }
    if (this.messages.loaded.has(tempId)) {
      this.messages.loaded.set(realId, this.messages.loaded.get(tempId));
      this.messages.loaded.delete(tempId);
    }
    if (this.messages.loading.has(tempId)) {
      this.messages.loading.set(realId, this.messages.loading.get(tempId));
      this.messages.loading.delete(tempId);
    }

    // Обновляем активный ID
    if (this.ui.activeChatId === tempId) {
      this.ui.activeChatId = realId;
    }

    // Обновляем DOM-элемент чата
    const chatItem = document.getElementById(String(tempId));
    if (chatItem) {
      chatItem.id = String(realId);
      chatItem.dataset.chatId = String(realId);
    }

    this.notify('chatList');
  },
};

export default store;
