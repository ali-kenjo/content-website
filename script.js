const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ── Dark mode ── */
const darkModeToggle = document.querySelector('.dark-mode-toggle');
const html = document.documentElement;

function initDarkMode() {
  updateButtonText(html.classList.contains('dark-mode'));
}

function toggleDarkMode() {
  html.classList.toggle('dark-mode');
  const isDarkMode = html.classList.contains('dark-mode');
  localStorage.setItem('darkMode', isDarkMode);
  updateButtonText(isDarkMode);
}

function updateButtonText(isDarkMode) {
  if (darkModeToggle) {
    darkModeToggle.textContent = isDarkMode ? '☀️ Light' : '🌙 Dark';
    darkModeToggle.setAttribute('aria-pressed', isDarkMode);
  }
}

if (darkModeToggle) {
  darkModeToggle.addEventListener('click', toggleDarkMode);
}

/* ── Scroll progress bar ── */
function initScrollProgress() {
  const bar = document.querySelector('.scroll-progress-bar');
  if (!bar) return;
  const update = () => {
    const scrollTop = window.scrollY;
    const height = document.documentElement.scrollHeight - window.innerHeight;
    const pct = height > 0 ? (scrollTop / height) * 100 : 0;
    bar.style.width = pct + '%';
  };
  window.addEventListener('scroll', update, { passive: true });
  update();
}

/* ── Scroll-spy nav ── */
function initScrollSpy() {
  const links = Array.from(document.querySelectorAll('.nav-link'));
  if (!links.length) return;
  const sections = links
    .map((link) => document.querySelector(link.getAttribute('href')))
    .filter(Boolean);
  if (!sections.length) return;

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        links.forEach((l) => l.classList.remove('is-active'));
        const active = document.querySelector(`.nav-link[href="#${entry.target.id}"]`);
        if (active) active.classList.add('is-active');
      });
    },
    { rootMargin: '-45% 0px -50% 0px', threshold: 0 }
  );
  sections.forEach((s) => io.observe(s));
}

/* ── Reveal on scroll ── */
function initReveal() {
  const els = document.querySelectorAll('.reveal');
  if (!els.length) return;

  if (REDUCED_MOTION) {
    els.forEach((el) => el.classList.add('is-visible'));
    return;
  }

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );
  els.forEach((el) => io.observe(el));
}

/* ── Magnetic hover ── */
function initMagnetic() {
  if (REDUCED_MOTION) return;
  document.querySelectorAll('.magnetic').forEach((el) => {
    el.addEventListener('mousemove', (e) => {
      const rect = el.getBoundingClientRect();
      const x = e.clientX - rect.left - rect.width / 2;
      const y = e.clientY - rect.top - rect.height / 2;
      el.style.transform = `translate(${x * 0.28}px, ${y * 0.28}px)`;
    });
    el.addEventListener('mouseleave', () => {
      el.style.transform = '';
    });
  });
}

/* ── Tilt (hero photo) ── */
function initTilt() {
  if (REDUCED_MOTION) return;
  document.querySelectorAll('.tilt-el').forEach((el) => {
    const wrap = el.parentElement;
    wrap.addEventListener('mousemove', (e) => {
      const rect = wrap.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;
      el.style.transform = `rotateY(${x * 16}deg) rotateX(${-y * 16}deg)`;
    });
    wrap.addEventListener('mouseleave', () => {
      el.style.transform = '';
    });
  });
}

/* ── Toolkit tag toggle ── */
function initToolTags() {
  document.querySelectorAll('.tag').forEach((tag) => {
    tag.addEventListener('click', () => tag.classList.toggle('is-active'));
  });
}

/* ── Interactive background: drifting node network ── */
function initBackgroundMotion() {
  const canvas = document.getElementById('bg-canvas');
  if (!canvas || !canvas.getContext) return;
  const ctx = canvas.getContext('2d');

  let dpr = 1;
  let points = [];
  const mouse = { x: null, y: null };

  function palette() {
    const styles = getComputedStyle(document.documentElement);
    return [
      styles.getPropertyValue('--c1').trim(),
      styles.getPropertyValue('--c2').trim(),
      styles.getPropertyValue('--c3').trim(),
    ];
  }

  function spawnPoints() {
    const area = window.innerWidth * window.innerHeight;
    const count = Math.min(90, Math.max(24, Math.round(area / 22000)));
    points = Array.from({ length: count }, () => ({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      vx: (Math.random() - 0.5) * 0.22,
      vy: (Math.random() - 0.5) * 0.22,
      r: Math.random() * 1.5 + 1,
      colorIndex: Math.floor(Math.random() * 3),
    }));
  }

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    canvas.style.width = window.innerWidth + 'px';
    canvas.style.height = window.innerHeight + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    spawnPoints();
  }

  function draw(animate) {
    const w = window.innerWidth;
    const h = window.innerHeight;
    const colors = palette();
    const linkDist = 130;

    ctx.clearRect(0, 0, w, h);

    if (animate) {
      for (const p of points) {
        p.x += p.vx;
        p.y += p.vy;

        if (mouse.x !== null) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const dist = Math.hypot(dx, dy) || 1;
          if (dist < 140) {
            const force = (140 - dist) / 140;
            p.x += (dx / dist) * force * 1.7;
            p.y += (dy / dist) * force * 1.7;
          }
        }

        if (p.x < -20) p.x = w + 20;
        if (p.x > w + 20) p.x = -20;
        if (p.y < -20) p.y = h + 20;
        if (p.y > h + 20) p.y = -20;
      }
    }

    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const a = points[i];
        const b = points[j];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (dist < linkDist) {
          ctx.strokeStyle = colors[a.colorIndex];
          ctx.globalAlpha = (1 - dist / linkDist) * 0.16;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }

    ctx.globalAlpha = 0.5;
    for (const p of points) {
      ctx.fillStyle = colors[p.colorIndex];
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  let raf = null;
  function loop() {
    draw(true);
    raf = requestAnimationFrame(loop);
  }

  resize();
  window.addEventListener('resize', resize);

  if (REDUCED_MOTION) {
    draw(false);
    return;
  }

  window.addEventListener('pointermove', (e) => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  });
  window.addEventListener('pointerleave', () => {
    mouse.x = null;
    mouse.y = null;
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      cancelAnimationFrame(raf);
    } else {
      raf = requestAnimationFrame(loop);
    }
  });

  loop();
}

document.addEventListener('DOMContentLoaded', () => {
  initDarkMode();
  initScrollProgress();
  initScrollSpy();
  initReveal();
  initMagnetic();
  initTilt();
  initToolTags();
  initBackgroundMotion();
});
