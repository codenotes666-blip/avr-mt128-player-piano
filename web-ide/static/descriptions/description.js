const search = document.getElementById('featureSearch');
const cards = [...document.querySelectorAll('.hardware-card')];
const count = document.getElementById('resultCount');

search.addEventListener('input', () => {
  const query = search.value.trim().toLowerCase();
  let visible = 0;
  cards.forEach((card) => {
    const matches = !query || card.dataset.search.toLowerCase().includes(query);
    card.classList.toggle('hidden', !matches);
    if (matches) visible += 1;
  });
  count.textContent = `${visible} subsystem${visible === 1 ? '' : 's'}`;
});