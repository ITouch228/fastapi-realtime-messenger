// TODO: [SMELL] IMAGE_LOAD_TIMEOUT захардкожен — вынести в constants.
// docs/architecture.md §5: 🟢 IMAGE_LOAD_TIMEOUT захардкожен
const IMAGE_LOAD_TIMEOUT = 10000; // 10 секунд таймаут

const messagesContainer = document.getElementById('messages');

async function loadImageWithAuth(url, container) {
  if (!container) return;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), IMAGE_LOAD_TIMEOUT);

  const isMobile = window.innerWidth <= 768;
  const quality = isMobile ? 60 : 80;
  const width = isMobile ? Math.min(800, window.innerWidth * 0.9) : 1200;

  const optimizedUrl = `${url}?quality=${quality}&width=${width}`;

  try {
    const response = await fetch(optimizedUrl, {
      headers: {
        Accept: 'image/webp,image/*;q=0.8',
      },
      credentials: 'include',
      signal: controller.signal,
      priority: 'high',
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    // Используем createImageBitmap для более эффективного декодирования
    const blob = await response.blob();
    const imageBitmap = await createImageBitmap(blob);

    const img = new Image();
    img.src = URL.createObjectURL(blob);
    img.className = 'loaded-image';
    img.loading = 'lazy';
    img.decoding = 'async';

    // Очищаем контейнер и добавляем изображение
    container.innerHTML = '';
    container.appendChild(img);

    img.onload = () => {
      img.classList.add('loaded');
      imageBitmap.close();
    };

    img.onerror = () => {
      container.innerHTML = '<div class="image-error">Ошибка загрузки</div>';
      imageBitmap.close();
    };
  } catch (error) {
    console.error('Image load failed:', error);
    container.innerHTML = '<div class="image-error">Ошибка загрузки</div>';
  } finally {
    clearTimeout(timeoutId);
  }
}

export const imageObserver = new IntersectionObserver(
  (entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;

      const container = entry.target;
      if (container.dataset.loaded === '1') {
        imageObserver.unobserve(container);
        continue;
      }

      const img = container.querySelector('img[data-src]');
      if (img?.dataset?.src) {
        container.dataset.loaded = '1';
        loadImageWithAuth(img.dataset.src, container);
      }

      imageObserver.unobserve(container);
    }
  },
  {
    root: messagesContainer,
    rootMargin: '80px',
    threshold: 0.1,
  },
);
