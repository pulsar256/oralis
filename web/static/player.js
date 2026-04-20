// web/static/player.js
(function () {
  'use strict';

  const MAX_VISIBLE_PILLS = 4;
  const PERSIST_KEY = 'oralis_player_state';

  let queue = [];          // [{url, label}]
  let currentIndex = -1;
  const audio = new Audio();

  const waveformCache = {};   // url → {samples, duration}
  const waveformFetches = {}; // url → Promise

  // DOM refs — populated on init
  let bar, playBtn, prevBtn, nextBtn, labelEl, timeEl, scrubber, scrubFill,
      pillRow, clearBtn, waveformCanvas;

  function _saveState() {
    localStorage.setItem(PERSIST_KEY, JSON.stringify({
      queue,
      currentIndex,
      currentTime: audio.currentTime,
    }));
  }

  function _restoreState() {
    let saved;
    try { saved = JSON.parse(localStorage.getItem(PERSIST_KEY)); } catch (_) {}
    if (!saved || !Array.isArray(saved.queue) || saved.queue.length === 0) return;
    queue = saved.queue;
    currentIndex = saved.currentIndex ?? 0;
    const t = saved.currentTime || 0;
    if (currentIndex < 0 || currentIndex >= queue.length) currentIndex = 0;
    audio.src = queue[currentIndex].url;
    audio.addEventListener('canplay', () => { audio.currentTime = t; }, { once: true });
    audio.addEventListener('error', () => { _saveState(); }, { once: true });
    labelEl.textContent = queue[currentIndex].label;
    renderPills();
    const restoredUrl = queue[currentIndex].url;
    _fetchWaveform(restoredUrl).then(() => {
      if (queue[currentIndex]?.url === restoredUrl) _showWaveform(restoredUrl);
    });
  }

  function _updateControlState() {
    if (!playBtn) return;
    const hasItems = queue.length > 0;
    playBtn.disabled = !hasItems;
    
    if (!hasItems) {
      prevBtn.disabled = true;
      nextBtn.disabled = true;
    } else {
      // Disable Prev only if we are on the first track and at the very beginning (within 3s restart window)
      // because there's no previous track to skip to and restarting is basically what's already happening.
      prevBtn.disabled = (currentIndex === 0 && audio.currentTime <= 3);
      // Disable Next if we are on the last track
      nextBtn.disabled = (currentIndex === queue.length - 1);
    }
  }

  function init() {
    bar           = document.getElementById('player-bar');
    if (!bar) return;
    playBtn       = document.getElementById('player-play');
    prevBtn       = document.getElementById('player-prev');
    nextBtn       = document.getElementById('player-next');
    labelEl       = document.getElementById('player-label');
    timeEl        = document.getElementById('player-time');
    scrubber      = document.getElementById('player-scrubber');
    scrubFill     = document.getElementById('player-scrub-fill');
    pillRow       = document.getElementById('player-pills');
    clearBtn      = document.getElementById('player-clear');
    waveformCanvas = document.getElementById('player-waveform');

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('play',  () => { playBtn.setAttribute('data-icon', '⏸'); });
    audio.addEventListener('pause', () => { playBtn.setAttribute('data-icon', '▶'); _saveState(); });

    playBtn.addEventListener('click', togglePlay);
    prevBtn.addEventListener('click', skipPrev);
    nextBtn.addEventListener('click', () => { playTrack(currentIndex + 1); });
    clearBtn.addEventListener('click', clearQueue);
    scrubber.addEventListener('click', onScrubClick);
    waveformCanvas.addEventListener('click', onScrubClick);

    document.addEventListener('oralis:chunk-ready', (e) => { addTrack(e.detail); });
    document.addEventListener('oralis:playlist-add', (e) => { addTrack(e.detail); });
    document.addEventListener('oralis:playlist-replace', (e) => { replaceQueue(e.detail.tracks); });

    window.addEventListener('beforeunload', _saveState);

    _restoreState();
    _updateControlState();
  }

  function _fetchWaveform(url) {
    if (waveformFetches[url]) return waveformFetches[url];
    const p = fetch(url + '/waveform')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && Array.isArray(data.samples)) waveformCache[url] = data;
      })
      .catch(() => {});
    waveformFetches[url] = p;
    return p;
  }

  function _showWaveform(url) {
    const data = waveformCache[url];
    if (!data) return;
    waveformCanvas.style.display = 'block';
    scrubber.style.display = 'none';
    _drawWaveform(data, audio.currentTime, audio.duration);
  }

  function _showScrubber() {
    waveformCanvas.style.display = 'none';
    scrubber.style.display = '';
  }

  function _drawWaveform(data, currentTime, duration) {
    const ctx = waveformCanvas.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const w = waveformCanvas.offsetWidth;
    const h = 48;
    if (w === 0) return;
    waveformCanvas.width = w * dpr;
    waveformCanvas.height = h * dpr;
    ctx.scale(dpr, dpr);

    const samples = data.samples;
    const barW = 2;
    const gap = 2;
    const step = barW + gap;
    const n = Math.floor(w / step);

    ctx.fillStyle = '#161b22';
    ctx.fillRect(0, 0, w, h);

    ctx.fillStyle = '#2d4a7a';
    for (let i = 0; i < n; i++) {
      const si = Math.floor(i / n * samples.length);
      const amp = samples[si] || 0;
      const barH = Math.max(1, amp * h * 0.9);
      ctx.fillRect(i * step, (h - barH) / 2, barW, barH);
    }

    const pct = (duration && duration > 0) ? currentTime / duration : 0;
    const playheadX = pct * w;
    ctx.fillStyle = 'rgba(74, 158, 255, 0.25)';
    ctx.fillRect(0, 0, playheadX, h);
    ctx.fillStyle = '#4a9eff';
    ctx.fillRect(playheadX, 0, 2, h);
  }

  function addTrack(track) {
    if (queue.some(t => t.url === track.url)) return;
    queue.push(track);
    _fetchWaveform(track.url);
    if (currentIndex === -1) {
      playTrack(0);
    } else {
      renderPills();
      _saveState();
    }
    _updateControlState();
  }

  function replaceQueue(tracks) {
    audio.pause();
    queue = tracks.slice();
    currentIndex = -1;
    if (queue.length === 0) {
      clearQueue();
      return;
    }
    playTrack(0);
    _updateControlState();
  }

  function playTrack(index) {
    if (index < 0 || index >= queue.length) return;
    currentIndex = index;
    const url = queue[index].url;
    audio.src = url;
    audio.play().catch(() => {});
    labelEl.textContent = queue[index].label;
    renderPills();
    _saveState();

    if (waveformCache[url]) {
      _showWaveform(url);
    } else {
      _showScrubber();
      const p = waveformFetches[url] || _fetchWaveform(url);
      p.then(() => {
        if (queue[currentIndex]?.url === url) _showWaveform(url);
      });
    }
    _updateControlState();
  }

  function togglePlay() {
    if (audio.paused) audio.play().catch(() => {});
    else audio.pause();
  }

  function skipPrev() {
    if (audio.currentTime > 3) {
      audio.currentTime = 0;
    } else if (currentIndex > 0) {
      playTrack(currentIndex - 1);
    } else {
      audio.currentTime = 0;
    }
  }

  function onEnded() {
    if (currentIndex + 1 < queue.length) {
      playTrack(currentIndex + 1);
    } else {
      playBtn.textContent = '▶';
      _saveState();
    }
  }

  function onTimeUpdate() {
    if (!audio.duration) return;
    const pct = (audio.currentTime / audio.duration) * 100;
    timeEl.textContent = fmt(audio.currentTime) + ' / ' + fmt(audio.duration);
    const url = queue[currentIndex]?.url;
    if (url && waveformCache[url] && waveformCanvas.style.display !== 'none') {
      _drawWaveform(waveformCache[url], audio.currentTime, audio.duration);
    } else {
      scrubFill.style.width = pct + '%';
    }
    _updateControlState();
  }

  function onScrubClick(e) {
    if (!audio.duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
    _updateControlState();
  }

  function clearQueue() {
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    queue = [];
    currentIndex = -1;
    labelEl.textContent = '';
    timeEl.textContent = '';
    scrubFill.style.width = '0%';
    playBtn.setAttribute('data-icon', '▶');
    localStorage.removeItem(PERSIST_KEY);
    renderPills();
    _showScrubber();
    _updateControlState();
  }

  function renderPills() {
    pillRow.innerHTML = '';
    if (queue.length === 0) return;

    // Show up to MAX_VISIBLE_PILLS pills: 1 before currentIndex and up to 3 ahead
    const start = Math.max(0, currentIndex - 1);
    const end   = Math.min(queue.length, start + MAX_VISIBLE_PILLS);

    for (let i = start; i < end; i++) {
      const pill = document.createElement('div');
      const isActive = i === currentIndex;
      pill.className = 'player-pill' + (isActive ? ' player-pill-active' : '');
      pill.textContent = (isActive ? '▶ ' : '') + queue[i].label;
      if (!isActive) {
        const idx = i;
        pill.addEventListener('click', () => { playTrack(idx); });
      }
      pillRow.appendChild(pill);
    }

    const overflow = queue.length - end;
    if (overflow > 0) {
      const more = document.createElement('span');
      more.className = 'player-pill-more';
      more.textContent = '+' + overflow + ' more';
      pillRow.appendChild(more);
    }
  }

  function fmt(s) {
    const m   = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return m + ':' + String(sec).padStart(2, '0');
  }

  document.addEventListener('DOMContentLoaded', init);
})();
