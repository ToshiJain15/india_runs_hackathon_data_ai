/* Redrob AI Ranker — app.js */

// ── Auto-animate stat values on load ───────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Animate number values
  document.querySelectorAll('.stat-value').forEach(el => {
    const raw = parseFloat(el.textContent.replace(/[^0-9.]/g, ''));
    if (!isNaN(raw) && raw > 0) {
      animateValue(el, 0, raw, 800);
    }
  });

  // Animate progress bars & mini bars after small delay
  setTimeout(() => {
    document.querySelectorAll('.comp-bar-fill, .score-bar-fill, .arch-bar').forEach(el => {
      el.style.transition = 'width 0.8s cubic-bezier(0.4,0,0.2,1), transform 0.8s cubic-bezier(0.4,0,0.2,1)';
    });
    document.querySelectorAll('.detail-comp-fill').forEach(el => {
      const w = el.style.width;
      el.style.width = '0%';
      requestAnimationFrame(() => { el.style.width = w; });
    });
  }, 100);

  // Fade in cards
  document.querySelectorAll('.glass').forEach((el, i) => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(12px)';
    el.style.transition = `opacity 0.4s ease ${i * 0.05}s, transform 0.4s ease ${i * 0.05}s`;
    setTimeout(() => {
      el.style.opacity = '1';
      el.style.transform = 'translateY(0)';
    }, 50);
  });
});

function animateValue(el, start, end, duration) {
  const isFloat = end % 1 !== 0;
  const step = (end - start) / (duration / 16);
  let cur = start;
  const suffix = el.textContent.replace(/[0-9.]/g, '').trim();
  const timer = setInterval(() => {
    cur += step;
    if ((step > 0 && cur >= end) || (step < 0 && cur <= end)) {
      clearInterval(timer);
      el.textContent = (isFloat ? end.toFixed(4) : Math.round(end)) + (suffix ? ' ' + suffix : '');
    } else {
      el.textContent = (isFloat ? cur.toFixed(2) : Math.round(cur)) + (suffix ? ' ' + suffix : '');
    }
  }, 16);
}

// ── Keyboard shortcuts ─────────────────────────────────────
document.addEventListener('keydown', (e) => {
  // ESC to close modal
  if (e.key === 'Escape') {
    const overlay = document.getElementById('modal-overlay');
    if (overlay) overlay.classList.remove('open');
  }
  // Ctrl+K to focus search
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const search = document.getElementById('search-input');
    if (search) { search.focus(); search.select(); }
  }
});

// ── Auto-update sidebar active state ──────────────────────
const path = window.location.pathname;
document.querySelectorAll('.nav-link').forEach(link => {
  link.parentElement.classList.remove('active');
  if (link.getAttribute('href') === '/' && path === '/') {
    link.parentElement.classList.add('active');
  } else if (link.getAttribute('href') !== '/' && path.startsWith(link.getAttribute('href'))) {
    link.parentElement.classList.add('active');
  }
});
