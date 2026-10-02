export const formatTimeLocalFromUtcString = utcStr => {
  // ожидаем: "YYYY MM DD HH MM SS"
  const parts = String(utcStr).split(' ').map(Number);
  if (parts.length < 6 || parts.some(n => !Number.isFinite(n))) return '';

  const [y, mo, d, h, mi, s] = parts;
  // создаём дату в UTC
  const dt = new Date(Date.UTC(y, mo - 1, d, h, mi, s));

  // форматируем как локальное время пользователя
  return dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

export const formatLocalDateTime = (date = new Date()) => {
  if (!(date instanceof Date) || isNaN(date.getTime())) {
    console.error('Invalid date object provided:', date);
    return new Date().toISOString().replace('T', ' ').substring(0, 19);
  }
  const pad = n => n.toString().padStart(2, '0');
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join(' ');
};

export const getFileIcon = extension => {
  // Sanitize extension to prevent potential injection
  if (typeof extension !== 'string') {
    return '📁'; // default icon
  }

  // Convert to lowercase and only allow alphanumeric characters and common extensions
  const sanitizedExt = extension.toLowerCase().replace(/[^a-z0-9]/g, '');

  const icons = {
    pdf: '📄',
    doc: '📝',
    docx: '📝',
    xls: '📊',
    xlsx: '📊',
    ppt: '📑',
    pptx: '📑',
    zip: '🗂️',
    rar: '🗂️',
    '7z': '🗂️',
    mp3: '🎵',
    wav: '🎵',
    mp4: '🎬',
    mov: '🎬',
    avi: '🎬',
    txt: '📋',
    default: '📁',
  };

  // Only return icon if extension is in the allowed list
  return icons[sanitizedExt] || icons.default;
};
