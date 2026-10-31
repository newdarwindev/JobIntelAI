const $ = id => document.getElementById(id);
let pending = null;
function node(tag, text, className) {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
}
function show(record) {
  $('output').hidden = false;
  $('meta').textContent = `Saved ${record.created_at} · job SHA-256 ${record.job_sha256} · candidate SHA-256 ${record.candidate_sha256} · model ${record.model}`;
  $('download').href = `/api/records/${record.id}/export`;
  $('items').replaceChildren();
  for (const item of record.result) {
    const box = node('article', '', 'item');
    box.append(node('h3', item.requirement), node('div', item.status, `tag ${item.status.toLowerCase()}`));
    box.append(node('p', item.reason), node('strong', 'Job source'), node('blockquote', item.job.quote));
    if (item.candidate) box.append(node('strong', 'Candidate source'), node('blockquote', item.candidate.quote));
    $('items').append(box);
  }
  window.location.hash = record.id;
}
async function history() {
  const response = await fetch('/api/records');
  const rows = await response.json();
  $('history').replaceChildren();
  if (!rows.length) $('history').append(node('p', 'No saved comparisons yet.'));
  for (const row of rows) {
    const button = node('button', `${new Date(row.created_at).toLocaleString()} · ${row.result.length} requirements`);
    button.onclick = () => show(row);
    $('history').append(button);
  }
}
$('form').addEventListener('submit', async event => {
  event.preventDefault();
  const body = {job: $('job').value, candidate: $('candidate').value, reference_url: $('url').value || null};
  const serialized = JSON.stringify(body);
  if (!pending || pending.body !== serialized) pending = {body: serialized, key: crypto.randomUUID()};
  $('submit').disabled = true;
  $('status').textContent = 'Comparing…';
  $('status').className = 'muted';
  try {
    const response = await fetch('/api/compare', {method:'POST', headers:{'Content-Type':'application/json', 'Idempotency-Key':pending.key}, body:serialized});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Comparison failed');
    pending = null;
    show(data);
    await history();
    $('status').textContent = 'Saved.';
  } catch (error) {
    $('status').textContent = `${error.message}. If the request may have reached the server, check Recent comparisons before retrying.`;
    $('status').className = 'error';
  } finally { $('submit').disabled = false; }
});
history().then(() => {
  if (location.hash.length > 1) fetch(`/api/records/${encodeURIComponent(location.hash.slice(1))}`)
    .then(r => r.ok ? r.json() : null).then(r => { if (r) show(r); });
}).catch(() => {$('history').textContent = 'Could not load saved comparisons.';});
