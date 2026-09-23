(() => {
  const filter = document.querySelector('[data-comparison-filter]');
  const sort = document.querySelector('[data-comparison-sort]');
  const list = document.querySelector('.comparison-list');
  if (!filter || !sort || !list) return;
  const cards = () => [...list.querySelectorAll('[data-comparison-card]')];
  const apply = () => {
    cards().forEach((card) => {
      const requested = filter.value;
      card.hidden = requested !== 'all' && card.dataset.status !== requested && card.dataset.kind !== requested;
    });
  };
  const order = () => {
    const key = sort.value;
    cards().sort((left, right) => {
      if (key === 'source') return (left.dataset.kind + left.dataset.metric).localeCompare(right.dataset.kind + right.dataset.metric);
      if (key === 'status') return left.dataset.status.localeCompare(right.dataset.status) || left.dataset.metric.localeCompare(right.dataset.metric);
      return left.dataset.metric.localeCompare(right.dataset.metric);
    }).forEach((card) => list.append(card));
  };
  filter.addEventListener('change', apply);
  sort.addEventListener('change', order);
})();
