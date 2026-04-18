// web/static/app.js

function initSSE(slug, runId) {
  const list = document.getElementById('chunk-list');
  if (!list) return;
  const es = new EventSource(`/projects/${slug}/runs/${runId}/stream`);
  let doneCount = list.querySelectorAll('.chunk-row').length;
  let totalCount = 0;

  es.addEventListener('plan', (e) => {
    totalCount = parseInt(e.data, 10);
    const bar = document.getElementById('run-progress');
    if (bar) bar.classList.remove('indeterminate');
    for (let i = 1; i <= totalCount; i++) {
      if (!document.getElementById(`chunk-${i}`)) {
        list.appendChild(_makePendingRow(i));
      }
    }
    _updateBar(doneCount, totalCount);
    _updateEta(doneCount, totalCount);
  });

  es.addEventListener('progress', (e) => {
    const current = parseInt(e.data, 10);
    const row = document.getElementById(`chunk-${current}`);
    if (row && row.dataset.state === 'pending') {
      row.dataset.state = 'synthesizing';
      row.classList.remove('chunk-pending');
      row.classList.add('chunk-synthesizing');
      row.querySelector('.chunk-status').textContent = '⟳ synthesizing…';
    }
  });

  es.addEventListener('chunk', (e) => {
    const tmp = document.createElement('div');
    tmp.innerHTML = e.data;
    const newRow = tmp.firstElementChild;
    if (!newRow) return;
    const existing = document.getElementById(newRow.id);
    if (existing) {
      existing.replaceWith(newRow);
    } else {
      list.appendChild(newRow);
    }
    doneCount++;
    _updateBar(doneCount, totalCount);
    _updateEta(doneCount, totalCount);
    newRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });

  es.addEventListener('status', (e) => {
    const el = document.getElementById('run-status');
    if (el) el.textContent = e.data;
  });

  es.addEventListener('done', (e) => {
    es.close();
    const data = JSON.parse(e.data);
    const statusEl = document.getElementById('run-status');
    if (statusEl) statusEl.textContent = '';
    const eta = document.getElementById('run-eta');
    if (eta) eta.textContent = data.state === 'done' ? '✓ Complete' : '✕ Failed';
    const bar = document.getElementById('run-progress');
    if (bar) { bar.classList.remove('indeterminate'); bar.style.width = '100%'; }
    const cancelForm = document.getElementById('cancel-form');
    if (cancelForm) cancelForm.style.display = 'none';
    if (data.final_url && data.state === 'done') {
      const container = document.getElementById('final-audio-container');
      if (container) {
        const wrapper = document.createElement('div');
        wrapper.className = 'final-audio';
        const label = document.createElement('span');
        label.textContent = 'Full output';
        const audio = document.createElement('audio');
        audio.controls = true;
        audio.preload = 'none';
        audio.src = data.final_url;
        wrapper.append(label, audio, _makeDownloadDropdown(data.final_url));
        container.replaceChildren(wrapper);
      }
    }
  });

  es.onerror = () => es.close();
}

function _makeDownloadDropdown(baseUrl) {
  const details = document.createElement('details');
  details.className = 'dl-drop';
  const summary = document.createElement('summary');
  summary.textContent = '↓ download';
  const menu = document.createElement('div');
  menu.className = 'dl-menu';
  for (const [label, suffix, hint] of [
    ['WAV', '', ''],
    ['MP3', '-mp3', 'Transcodes on first download'],
    ['MP4', '-mp4', 'Transcodes on first download'],
  ]) {
    const a = document.createElement('a');
    a.href = baseUrl + suffix;
    if (hint) a.title = hint;
    a.textContent = label;
    menu.appendChild(a);
  }
  details.append(summary, menu);
  return details;
}

function _makePendingRow(index) {
  const div = document.createElement('div');
  div.className = 'chunk-row chunk-pending';
  div.id = `chunk-${index}`;
  div.dataset.state = 'pending';
  div.innerHTML =
    `<span class="chunk-num">Chunk ${index}</span>` +
    `<span class="chunk-status chunk-snip">pending…</span>`;
  return div;
}

function _updateBar(done, total) {
  const bar = document.getElementById('run-progress');
  if (bar && total > 0 && !bar.classList.contains('indeterminate')) {
    bar.style.width = `${Math.round((done / total) * 100)}%`;
  }
}

function _updateEta(done, total) {
  const eta = document.getElementById('run-eta');
  if (!eta) return;
  if (total > 0) {
    eta.textContent = `${done} / ${total} chunks`;
  }
}

function confirmDeleteProject(btn) {
  return confirm('Delete "' + btn.dataset.name + '" and all its audio files?');
}

function startRename(slug) {
  const item = document.querySelector(`.proj-item[data-slug="${slug}"]`);
  item.querySelector('.proj-link').style.display = 'none';
  item.querySelector('.btn-proj-rename').style.display = 'none';
  item.querySelector('.proj-delete-form').style.display = 'none';
  const form = item.querySelector('.rename-form');
  form.style.display = 'flex';
  const input = form.querySelector('input');
  input.focus();
  input.select();
}

function cancelRename(btn) {
  const item = btn.closest('.proj-item');
  item.querySelector('.proj-link').style.display = '';
  item.querySelector('.btn-proj-rename').style.display = '';
  item.querySelector('.proj-delete-form').style.display = '';
  item.querySelector('.rename-form').style.display = 'none';
}

function openFullText() {
  document.getElementById('full-text-panel').classList.add('open');
}

function closeFullText() {
  document.getElementById('full-text-panel').classList.remove('open');
}

function toggleDiff() {
  const on = document.getElementById('diff-toggle').checked;
  document.querySelectorAll('#full-text-body del, #full-text-body ins')
    .forEach(el => el.style.display = on ? '' : 'none');
}

// Cancel rename on Escape
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  const form = document.querySelector('.rename-form[style*="flex"]');
  if (form) cancelRename(form.querySelector('button[type=button]'));
});

// Keep hidden step mirrors in sync with checkboxes; auto-refresh full-text panel if open
document.addEventListener('change', (e) => {
  if (e.target.type !== 'checkbox' || !e.target.name.startsWith('step_')) return;
  const mirror = document.querySelector(`#step-mirrors input[name="${e.target.name}"]`);
  if (mirror) mirror.value = e.target.checked ? '1' : '0';
  const panel = document.getElementById('full-text-panel');
  if (panel && panel.classList.contains('open')) {
    const form = document.getElementById('settings-form');
    fetch('/preprocess/full', { method: 'POST', body: new FormData(form) })
      .then(r => r.text())
      .then(html => {
        const body = document.getElementById('full-text-body');
        if (body) body.innerHTML = html;
      });
  }
});
