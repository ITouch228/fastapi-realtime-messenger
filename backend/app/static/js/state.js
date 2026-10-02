const AppState = {
  userId: null,
  chatActiveId: null,
  messages: [],
  persistentChats: [],
  tempChat: null,

  setUserId(userId) {
    if (
      userId !== null &&
      userId !== undefined &&
      !Number.isInteger(userId) &&
      typeof userId !== 'string'
    ) {
      console.error('Invalid userId provided:', userId);
      return;
    }
    this.userId = userId;
    this.notify('userId');
  },

  setChatActiveId(chatActiveId) {
    if (
      chatActiveId !== null &&
      chatActiveId !== undefined &&
      !Number.isInteger(chatActiveId) &&
      !String(chatActiveId).startsWith('temp-')
    ) {
      console.error('Invalid chatActiveId provided:', chatActiveId);
      return;
    }
    this.chatActiveId = chatActiveId;
    this.notify('chatActiveId');
  },

  setMessages(messages) {
    if (!Array.isArray(messages)) {
      console.error('Invalid messages array provided:', messages);
      return;
    }
    this.messages = messages;
    this.notify('messages');
  },

  addMessage(message) {
    if (!message || typeof message !== 'object') {
      console.error('Invalid message object provided:', message);
      return;
    }
    this.messages.push(message);
    this.notify('newMessage');
  },

  setPersistentChats(chats) {
    if (!Array.isArray(chats)) {
      console.error('Invalid chats array provided:', chats);
      return;
    }
    this.persistentChats = chats;
    this.notify('chats');
  },

  addPersistentChat(chat) {
    if (!chat || typeof chat !== 'object') {
      console.error('Invalid chat object provided:', chat);
      return;
    }
    this.persistentChats.push(chat);
    this.notify('chats');
    return chat;
  },

  setTempChat(targetUser) {
    if (targetUser === null || targetUser === undefined) {
      console.error('Invalid targetUser provided:', targetUser);
      return;
    }

    const tempChat = {
      id: `temp-${targetUser}`,
      users: [this.userId, targetUser],
      lastMessage: null,
      lastMessageTime: null,
    };

    this.tempChat = tempChat;
    this.notify('tempChat');
    return tempChat;
  },

  clearTempChat() {
    if (this.tempChat && this.tempChat.id) {
      const element = document.querySelector(`#${this.tempChat.id}`);
      if (element) {
        element.remove();
      }
    }
    this.tempChat = null;
    this.notify('clearTempChat');
  },

  subscribers: {},

  subscribe(key, callback) {
    if (typeof callback !== 'function') {
      console.error('Invalid callback function provided:', callback);
      return;
    }
    this.subscribers[key] = callback;
  },

  notify(key) {
    if (this.subscribers[key]) {
      try {
        this.subscribers[key](this[key]);
        console.log(`Notify: ${key}`);
      } catch (error) {
        console.error('Error in subscriber callback:', error);
      }
    }
  },
};

export default AppState;
