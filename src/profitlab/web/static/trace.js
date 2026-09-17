document.querySelectorAll('details').forEach(details => {
  details.addEventListener('toggle', async () => {
    if (!details.open) return;
    for (const payload of details.querySelectorAll('[data-payload-url]')) {
      try {
        const response = await fetch(payload.dataset.payloadUrl);
        if (!response.ok) throw new Error('Payload unavailable or damaged');
        payload.textContent = JSON.stringify(await response.json(), null, 2);
        delete payload.dataset.payloadUrl;
      } catch { payload.textContent = 'Payload unavailable; use the full payload link to retry.'; }
    }
  });
});
document.querySelectorAll('.copy-event').forEach(button => {
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(button.parentElement.querySelector('.event-json').textContent);
      button.textContent = 'Copied';
    } catch { button.textContent = 'Select the JSON below to copy'; }
  });
});
let cursor = Math.max(0, ...Array.from(document.querySelectorAll('.event-json'),
  element => JSON.parse(element.textContent).sequence));
setInterval(async () => {
  try {
    const url = new URL(location.href);
    url.pathname = location.pathname + '/events';
    url.search = location.search;
    url.searchParams.set('after_sequence', cursor);
    const response = await fetch(url);
    if (!response.ok) return;
    const data = await response.json();
    if (data.events.length) {
      cursor = Math.max(cursor, ...data.events.map(event => event.sequence));
      const notice = document.getElementById('updates');
      notice.textContent = 'New events available. ';
      const link = document.createElement('a');
      link.href = location.href;
      link.textContent = 'Refresh timeline';
      notice.appendChild(link);
    }
  } catch { /* A later poll retries local connectivity. */ }
}, 1000);
