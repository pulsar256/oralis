// web/static/app.js

let _activeSSEs = {};
let _autoqueueRunId = null;

function initSSE(slug, runId, projectName) {
  if (_activeSSEs[runId]) { _activeSSEs[runId].close(); }
  
  const container = document.getElementById(`run-container-${runId}`);
  if (!container) return;
  
  const list = container.querySelector('.chunk-list');
  const es = new EventSource(`/projects/${slug}/runs/${runId}/stream`);
  _activeSSEs[runId] = es;
  
  let doneCount = list.querySelectorAll('.chunk-row').length;
  let totalCount = 0;

  es.addEventListener('plan', (e) => {
    totalCount = parseInt(e.data, 10);
    const bar = container.querySelector('.pb-inner');
    if (bar) bar.classList.remove('indeterminate');
    for (let i = 1; i <= totalCount; i++) {
      if (!container.querySelector(`#chunk-${runId}-${i}`)) {
        list.appendChild(_makePendingRow(runId, i));
      }
    }
    _updateBar(container, runId, doneCount, totalCount);
    _updateEta(container, runId, doneCount, totalCount);
  });

  es.addEventListener('progress', (e) => {
    const current = parseInt(e.data, 10);
    const row = container.querySelector(`#chunk-${runId}-${current}`);
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
    
    const existing = container.querySelector(`#${newRow.id}`);
    if (existing) {
      existing.replaceWith(newRow);
    } else {
      list.appendChild(newRow);
    }
    doneCount++;
    _updateBar(container, runId, doneCount, totalCount);
    _updateEta(container, runId, doneCount, totalCount);
    
    // Only scroll if the body is expanded
    if (container.querySelector('.run-body').style.display !== 'none') {
      newRow.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    
    const queueBtn = newRow.querySelector('.btn-queue');
    if (queueBtn && _autoqueueRunId === runId) {
      document.dispatchEvent(new CustomEvent('oralis:chunk-ready', {
        detail: { url: queueBtn.dataset.url, label: queueBtn.dataset.label }
      }));
    }
  });

  es.addEventListener('status', (e) => {
    const el = container.querySelector('.run-status');
    if (el) el.textContent = e.data;
  });

  es.addEventListener('done', (e) => {
    es.close();
    delete _activeSSEs[runId];
    const data = JSON.parse(e.data);
    
    const statusEl = container.querySelector('.run-status');
    if (statusEl) statusEl.textContent = '';
    
    const eta = container.querySelector('.run-eta');
    if (eta) eta.textContent = data.state === 'done' ? '✓ Complete' : '✕ Failed';
    
    const pill = container.querySelector('.run-status-pill');
    if (pill) {
      pill.textContent = data.state;
      pill.className = `run-status-pill ${data.state}`;
    }

    _updateBar(container, runId, totalCount, totalCount);
    
    if (data.state === 'done') {
        const trackLabel = (projectName || slug) + ' \u2014 Full output';

        // Update the header Play button to point to the final audio
        const playBtn = container.querySelector('.btn-play-run');
        if (playBtn) {
            playBtn.dataset.url = data.final_url;
            playBtn.dataset.label = trackLabel;
            playBtn.removeAttribute('title');
        }

        if (_autoqueueRunId === runId) {
          document.dispatchEvent(new CustomEvent('oralis:chunk-ready', {
            detail: { url: data.final_url, label: trackLabel }
          }));
        }
    }

    const cancelBtn = container.querySelector('.btn-cancel');
    if (cancelBtn) cancelBtn.closest('form').remove();

    const autoqueueLabel = container.querySelector('.run-autoqueue-label');
    if (autoqueueLabel) autoqueueLabel.remove();
    if (_autoqueueRunId === runId) _autoqueueRunId = null;

    const actions = container.querySelector('.run-header-actions');
    if (data.state === 'done') {
        const dlDrop = document.createElement('details');
        dlDrop.className = 'dl-drop';
        dlDrop.innerHTML =
            `<summary class="btn-dl-trigger" title="Download audio files">↓ Download</summary>` +
            `<div class="dl-menu">` +
            `<a href="/projects/${slug}/runs/${runId}/download">WAV</a>` +
            `<a href="/projects/${slug}/runs/${runId}/download-mp3">MP3</a>` +
            `<a href="/projects/${slug}/runs/${runId}/download-mp4">MP4</a>` +
            `</div>`;
        actions.appendChild(dlDrop);
    }
    const deleteForm = document.createElement('form');
    deleteForm.method = 'post';
    deleteForm.action = `/projects/${slug}/runs/${runId}/delete`;
    deleteForm.style.display = 'inline';
    deleteForm.setAttribute('hx-post', `/projects/${slug}/runs/${runId}/delete`);
    deleteForm.setAttribute('hx-target', '#main');
    deleteForm.setAttribute('hx-select', '#main');
    deleteForm.setAttribute('hx-swap', 'outerHTML');
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'submit';
    deleteBtn.className = 'btn-delete';
    deleteBtn.title = 'Delete this run and all its audio files';
    deleteBtn.addEventListener('click', (ev) => { if (!confirm('Delete this run and all its audio files?')) ev.preventDefault(); });
    deleteBtn.textContent = '✕';
    deleteForm.appendChild(deleteBtn);
    actions.appendChild(deleteForm);
    htmx.process(deleteForm);
  });

  es.onerror = () => { es.close(); delete _activeSSEs[runId]; };
}

function toggleRun(runId, event) {
  if (event && (event.target.closest('.run-header-actions') || event.target.closest('.dl-drop'))) return;
  
  const body = document.getElementById(`body-${runId}`);
  const arrow = document.getElementById(`arrow-${runId}`);
  if (!body || !arrow) return;
  
  if (body.style.display === 'none') {
    body.style.display = 'block';
    arrow.textContent = '▼';
  } else {
    body.style.display = 'none';
    arrow.textContent = '▶';
  }
}

function _makePendingRow(runId, index) {
  const div = document.createElement('div');
  div.className = 'chunk-row chunk-pending';
  div.id = `chunk-${runId}-${index}`;
  div.dataset.state = 'pending';
  div.innerHTML =
    `<span class="chunk-num">Chunk ${index}</span>` +
    `<span class="chunk-status chunk-snip">pending…</span>`;
  return div;
}

function _updateBar(container, runId, done, total) {
  const bar = container.querySelector('.pb-inner');
  const miniBar = container.querySelector('.run-mini-pb-inner');
  if (total > 0) {
    const pct = `${Math.round((done / total) * 100)}%`;
    if (bar && !bar.classList.contains('indeterminate')) bar.style.width = pct;
    if (miniBar) miniBar.style.width = pct;
  }
}

function _updateEta(container, runId, done, total) {
  const eta = container.querySelector('.run-eta');
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

// Playlist button delegation
document.addEventListener('click', (e) => {
  const queueBtn = e.target.closest('.btn-queue');
  const replaceBtn = e.target.closest('.btn-replace');
  const playRunBtn = e.target.closest('.btn-play-run');
  
  if (queueBtn) {
    document.dispatchEvent(new CustomEvent('oralis:playlist-add', {
      detail: { url: queueBtn.dataset.url, label: queueBtn.dataset.label }
    }));
  } else if (replaceBtn) {
    document.dispatchEvent(new CustomEvent('oralis:playlist-replace', {
      detail: { tracks: [{ url: replaceBtn.dataset.url, label: replaceBtn.dataset.label }] }
    }));
  } else if (playRunBtn) {
    const runId = playRunBtn.dataset.runId;
    const container = document.getElementById(`run-container-${runId}`);
    if (!container) return;
    
    // If we have a direct URL (finished run), use it to replace the whole queue
    if (playRunBtn.dataset.url) {
      document.dispatchEvent(new CustomEvent('oralis:playlist-replace', {
        detail: { tracks: [{ url: playRunBtn.dataset.url, label: playRunBtn.dataset.label }] }
      }));
      return;
    }

    // Otherwise (unfinished run), arm autoqueue for this run and load ready chunks
    const autoqueueCb = container.querySelector('.run-autoqueue-cb');
    if (autoqueueCb && !autoqueueCb.checked) {
      autoqueueCb.checked = true;
      autoqueueCb.dispatchEvent(new Event('change', { bubbles: true }));
    }

    const chunks = Array.from(container.querySelectorAll('.chunk-row:not(.chunk-pending):not(.chunk-synthesizing)'));
    const tracks = chunks.map(row => {
      const q = row.querySelector('.btn-queue');
      return { url: q.dataset.url, label: q.dataset.label };
    });

    if (tracks.length > 0) {
      document.dispatchEvent(new CustomEvent('oralis:playlist-replace', { detail: { tracks } }));
    }
  }
});

// Update sidebar active highlight after HTMX navigation
document.addEventListener('htmx:afterSettle', () => {
  const path = window.location.pathname;
  document.querySelectorAll('#sidebar .proj-link').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === path);
  });
});

// Per-run autoqueue mutual exclusion
document.addEventListener('change', (e) => {
  const cb = e.target.closest('.run-autoqueue-cb');
  if (!cb) return;
  const runId = cb.dataset.runId;
  if (cb.checked) {
    document.querySelectorAll('.run-autoqueue-cb').forEach(other => {
      if (other !== cb) other.checked = false;
    });
    _autoqueueRunId = runId;
  } else {
    if (_autoqueueRunId === runId) _autoqueueRunId = null;
  }
});

// Close live SSE stream before HTMX replaces the page content
document.addEventListener('htmx:beforeSwap', () => {
  Object.values(_activeSSEs).forEach(es => es.close());
  _activeSSEs = {};
  _autoqueueRunId = null;
});
