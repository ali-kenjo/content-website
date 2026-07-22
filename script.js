const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ── i18n ── */
const TRANSLATIONS = {
  en: {
    nav: { logoAria: 'Back to top', toolkit: 'Toolkit', support: 'Support', build: 'Build' },
    lang: { toggle: '🌐 DE' },
    dark: { dark: '🌙 Dark', light: '☀️ Light' },
    hero: {
      eyebrow: "Hi, I'm",
      chip1: 'Builder',
      chip2: 'Media',
      chip3: 'Support',
      bio: `I build websites, apps, and tools with AI-assisted vibe-coding, and create
        media — video, audio, and 3D — on the side. Off-screen, I help people get
        unstuck on Windows and Linux, remotely or in person.`,
      storeAria: 'Visit the store',
      storeText: 'Visit<br>Store',
    },
    toolkit: {
      eyebrow: 'Toolkit',
      headline: 'What I work with',
      hint: 'Tap a tool to see it light up.',
    },
    support: {
      eyebrow: 'Support',
      headline: 'Support, wherever you are',
      text: `Remote or in person, I help with setup, troubleshooting, and everyday tech
        problems — across Windows and Linux, in Arabic, English, or German.`,
      you: 'YOU',
      platforms: 'Platforms',
      languages: 'Languages',
    },
    build: {
      eyebrow: 'Build',
      headline: 'Websites, apps, tools & SaaS',
      text: `I design and build websites, apps, small tools, and SaaS products —
        using AI-assisted "vibe-coding" workflows to move fast without cutting corners.`,
      step1: 'Design',
      step2: 'Build',
      step3: 'Ship',
    },
    footer: { status: 'IT · Web · Media — Germany' },
    meta: {
      description: 'Ali Kenjo — builder of websites, apps, and tools, and cross-platform tech support in Germany.',
    },
  },
  de: {
    nav: { logoAria: 'Nach oben', toolkit: 'Werkzeuge', support: 'Support', build: 'Erstellen' },
    lang: { toggle: '🌐 EN' },
    dark: { dark: '🌙 Nacht', light: '☀️ Hell' },
    hero: {
      eyebrow: 'Hallo, ich bin',
      chip1: 'Entwickler',
      chip2: 'Medien',
      chip3: 'Support',
      bio: `Ich baue Websites, Apps und Tools mit KI-gestütztem Vibe-Coding und erstelle
        nebenbei Medien — Video, Audio und 3D. Abseits des Bildschirms helfe ich
        Menschen bei Problemen mit Windows und Linux — remote oder vor Ort.`,
      storeAria: 'Zum Store gehen',
      storeText: 'Zum<br>Store',
    },
    toolkit: {
      eyebrow: 'Werkzeuge',
      headline: 'Womit ich arbeite',
      hint: 'Tippe auf ein Tool, damit es aufleuchtet.',
    },
    support: {
      eyebrow: 'Support',
      headline: 'Support, wo auch immer du bist',
      text: `Remote oder vor Ort helfe ich bei Einrichtung, Fehlerbehebung und
        alltäglichen Technikproblemen — auf Windows und Linux, auf Arabisch, Englisch oder Deutsch.`,
      you: 'DU',
      platforms: 'Plattformen',
      languages: 'Sprachen',
    },
    build: {
      eyebrow: 'Erstellen',
      headline: 'Websites, Apps, Tools & SaaS',
      text: `Ich entwerfe und baue Websites, Apps, kleine Tools und SaaS-Produkte —
        mit KI-gestützten „Vibe-Coding"-Workflows, um schnell und trotzdem sauber zu arbeiten.`,
      step1: 'Entwerfen',
      step2: 'Bauen',
      step3: 'Liefern',
    },
    footer: { status: 'IT · Web · Medien — Deutschland' },
    meta: {
      description: 'Ali Kenjo — baut Websites, Apps und Tools und bietet plattformübergreifenden Tech-Support in Deutschland.',
    },
  },
};

function getTranslation(lang, key) {
  return key.split('.').reduce((obj, part) => (obj ? obj[part] : undefined), TRANSLATIONS[lang]);
}

function applyLanguage(lang) {
  document.documentElement.lang = lang;

  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const value = getTranslation(lang, el.getAttribute('data-i18n'));
    if (value !== undefined) el.textContent = value;
  });

  document.querySelectorAll('[data-i18n-html]').forEach((el) => {
    const value = getTranslation(lang, el.getAttribute('data-i18n-html'));
    if (value !== undefined) el.innerHTML = value;
  });

  document.querySelectorAll('[data-i18n-attr]').forEach((el) => {
    el.getAttribute('data-i18n-attr').split(',').forEach((pair) => {
      const [attr, key] = pair.split(':').map((s) => s.trim());
      const value = getTranslation(lang, key);
      if (value !== undefined) el.setAttribute(attr, value);
    });
  });

  const langToggle = document.getElementById('lang-toggle');
  if (langToggle) langToggle.textContent = getTranslation(lang, 'lang.toggle');

  updateButtonText(html.classList.contains('dark-mode'));
}

function initLanguage() {
  let lang = 'en';
  try {
    lang = localStorage.getItem('lang') || 'en';
  } catch (e) {}
  applyLanguage(lang);

  const langToggle = document.getElementById('lang-toggle');
  if (langToggle) {
    langToggle.addEventListener('click', () => {
      const next = document.documentElement.lang === 'de' ? 'en' : 'de';
      try {
        localStorage.setItem('lang', next);
      } catch (e) {}
      applyLanguage(next);
    });
  }
}

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
    const lang = document.documentElement.lang === 'de' ? 'de' : 'en';
    darkModeToggle.textContent = getTranslation(lang, isDarkMode ? 'dark.light' : 'dark.dark');
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
      styles.getPropertyValue('--accent').trim(),
      styles.getPropertyValue('--accent-hover').trim(),
      styles.getPropertyValue('--accent-2').trim(),
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
  initLanguage();
  initDarkMode();
  initScrollProgress();
  initScrollSpy();
  initReveal();
  initMagnetic();
  initTilt();
  initToolTags();
  initBackgroundMotion();
});
