export function initLightbox() {
  document.addEventListener('click', (e) => {
    if (!e.target.classList.contains('loaded-image')) return;

    const modal = document.createElement('div');
    modal.style.position = 'fixed';
    modal.style.top = '0';
    modal.style.left = '0';
    modal.style.width = '100%';
    modal.style.height = '100%';
    modal.style.backgroundColor = 'rgba(0,0,0,0.9)';
    modal.style.display = 'flex';
    modal.style.alignItems = 'center';
    modal.style.justifyContent = 'center';
    modal.style.zIndex = '1000';

    const fullImage = document.createElement('img');
    fullImage.src = e.target.src;
    fullImage.style.maxWidth = '90%';
    fullImage.style.maxHeight = '90%';
    fullImage.style.objectFit = 'contain';

    modal.appendChild(fullImage);
    modal.onclick = () => document.body.removeChild(modal);

    document.body.appendChild(modal);
  });
}
