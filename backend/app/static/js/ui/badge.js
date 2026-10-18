document.addEventListener('DOMContentLoaded', () => {
  const badge = document.querySelector('.pet-badge');
  if (!badge) return;

  try {
    if (localStorage.getItem('petBadgeDismissed') === '1') {
      badge.remove();
      return;
    }
  } catch {
    return;
  }

  const closeBtn = badge.querySelector('.pet-badge__close');
  if (!closeBtn) return;

  closeBtn.addEventListener('click', () => {
    badge.remove();
    try {
      localStorage.setItem('petBadgeDismissed', '1');
    } catch {
      return;
    }
  });
});
