// web/static/player.js
(function () {
  'use strict';

  const STORAGE_KEY = 'oralis_player_auto_queue';
  const MAX_VISIBLE_PILLS = 4;

  let queue = [];          // [{url, label}]
  let currentIndex = -1;
  let autoQueue = localStorage.getItem(STORAGE_KEY) !== 'false';
  const audio = new Audio();

  // DOM refs — populated on init
  let bar, playBtn, nextBtn, labelEl, timeEl, scrubber, scrubFill,
      autoToggle, pillRow, clearBtn;

  function init() {
    bar        = document.getElementById('player-bar');
    if (!bar) return;
    playBtn    = document.getElementById('player-play');
    nextBtn    = document.getElementById('player-next');
    labelEl    = document.getElementById('player-label');
    timeEl     = document.getElementById('player-time');
    scrubber   = document.getElementById('player-scrubber');
    scrubFill  = document.getElementById('player-scrub-fill');
    autoToggle = document.getElementById('player-auto-queue');
    pillRow    = document.getElementById('player-pills');
    clearBtn   = document.getElementById('player-clear');

    autoToggle.checked = autoQueue;

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('play',  () => { playBtn.textContent = '⏸'; });
    audio.addEventListener('pause', () => { playBtn.textContent = '▶'; });

    playBtn.addEventListener('click', togglePlay);
    nextBtn.addEventListener('click', () => { playTrack(currentIndex + 1); });
    clearBtn.addEventListener('click', clearQueue);
    scrubber.addEventListener('click', onScrubClick);
    autoToggle.addEventListener('change', () => {
      autoQueue = autoToggle.checked;
      localStorage.setItem(STORAGE_KEY, String(autoQueue));
    });

    document.addEventListener('oralis:chunk-ready', (e) => {
      if (autoQueue) addTrack(e.detail);
    });
    document.addEventListener('oralis:playlist-add', (e) => {
      addTrack(e.detail);
    });
    document.addEventListener('oralis:playlist-replace', (e) => {
      replaceQueue(e.detail.tracks);
    });

    // Re-show bar after HTMX navigation if queue is non-empty
    document.addEventListener('htmx:afterSettle', () => {
      if (queue.length > 0) showBar();
    });
  }

  function addTrack(track) {
    queue.push(track);
    if (currentIndex === -1) {
      playTrack(0);
    } else {
      renderPills();
    }
    showBar();
  }

  function replaceQueue(tracks) {
    audio.pause();
    queue = tracks.slice();
    currentIndex = -1;
    playTrack(0);
    showBar();
  }

  function playTrack(index) {
    if (index < 0 || index >= queue.length) return;
    currentIndex = index;
    audio.src = queue[index].url;
    audio.play().catch(() => {});
    labelEl.textContent = queue[index].label;
    renderPills();
  }

  function togglePlay() {
    if (audio.paused) audio.play().catch(() => {});
    else audio.pause();
  }

  function onEnded() {
    if (currentIndex + 1 < queue.length) {
      playTrack(currentIndex + 1);
    } else {
      playBtn.textContent = '▶';
    }
  }

  function onTimeUpdate() {
    if (!audio.duration) return;
    const pct = (audio.currentTime / audio.duration) * 100;
    scrubFill.style.width = pct + '%';
    timeEl.textContent = fmt(audio.currentTime) + ' / ' + fmt(audio.duration);
  }

  function onScrubClick(e) {
    if (!audio.duration) return;
    const rect = scrubber.getBoundingClientRect();
    audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
  }

  function clearQueue() {
    audio.pause();
    audio.src = '';
    queue = [];
    currentIndex = -1;
    labelEl.textContent = '';
    timeEl.textContent = '';
    scrubFill.style.width = '0%';
    playBtn.textContent = '▶';
    renderPills();
    hideBar();
  }

  function renderPills() {
    pillRow.innerHTML = '';
    if (queue.length === 0) return;

    // Show a window of MAX_VISIBLE_PILLS pills centred around currentIndex
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

  function showBar() { bar.style.display = ''; }
  function hideBar() { bar.style.display = 'none'; }

  function fmt(s) {
    const m   = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return m + ':' + String(sec).padStart(2, '0');
  }

  document.addEventListener('DOMContentLoaded', init);
})();
