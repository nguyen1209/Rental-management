document.querySelectorAll('.flash-card').forEach((card) => {
  const closeButton = card.querySelector('.flash-card__close');
  let removed = false;

  const dismiss = () => {
    if (removed) return;
    removed = true;
    card.classList.add('is-leaving');
    card.addEventListener('animationend', () => card.remove(), { once: true });
  };

  closeButton?.addEventListener('click', dismiss);
  if (card.dataset.autoclose === 'true') {
    window.setTimeout(dismiss, 5500);
  }
});
