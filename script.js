// True if the visitor's OS/browser is set to reduce motion. When true, we skip
// animations (parallax, tilt, magnetic hover, etc.) so the page stays calm for people
// who get dizzy or distracted by movement.
const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ── i18n ──
   Simple hand-rolled translation system (no external library).
   TRANSLATIONS holds one object per language, and the HTML marks translatable
   spots with data-i18n / data-i18n-html / data-i18n-attr attributes that point
   at a dotted key path here (e.g. "hero.bio" -> TRANSLATIONS.en.hero.bio). */
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
      bio: `I build websites, apps, and tools by vibe-coding with AI, and mess around
        with media on the side — video, audio, 3D, whatever sticks. Away from the
        screen, I help people get unstuck on Windows and Linux, remotely or in person.`,
      storeAria: 'Visit the store',
      storeText: 'Visit<br>Store',
    },
    toolkit: {
      eyebrow: 'Toolkit',
      headline: 'What I work with',
      hint: "Hover or tap a tool to see what it's for.",
      infoDefault: "Hover or tap a tool above to find out what it's for.",
      tools: {
        vscode: "My daily driver — I pair it with AI so I can vibe-code fast without losing the plot.",
        docker: 'Docker keeps my environments clean and portable, n8n handles the automations I\'d rather not do by hand.',
        blender: 'For 3D modeling, animation, and the occasional render that eats my evening.',
        kdenlive: 'Where I cut and polish video footage.',
        obs: 'For screen recording and streaming.',
        audacity: 'For cleaning up and editing audio.',
        gimp: 'My go-to for image editing when I need a free Photoshop stand-in.',
      },
    },
    support: {
      eyebrow: 'Support',
      headline: 'Support, wherever you are',
      text: `Whether it's remote or face to face, I'll help you sort out setup issues,
        chase down the weird bugs, and everyday tech headaches — on Windows or Linux,
        in Arabic, English, or German.`,
      you: 'YOU',
      platforms: 'Platforms',
      languages: 'Languages',
    },
    build: {
      eyebrow: 'Build',
      headline: 'Websites, apps, tools & SaaS',
      text: `I design and build websites, apps, small tools, and SaaS products —
        leaning on AI-assisted vibe-coding to move fast without cutting corners.`,
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
      bio: `Ich baue Websites, Apps und Tools, indem ich mit KI vibe-code, und
        bastle nebenbei an Medien — Video, Audio, 3D, was eben hängen bleibt.
        Abseits des Bildschirms helfe ich Leuten bei Problemen mit Windows
        und Linux — remote oder vor Ort.`,
      storeAria: 'Zum Store gehen',
      storeText: 'Zum<br>Store',
    },
    toolkit: {
      eyebrow: 'Werkzeuge',
      headline: 'Womit ich arbeite',
      hint: 'Fahre über ein Tool oder tippe drauf, um zu sehen, wofür es ist.',
      infoDefault: 'Fahre über ein Tool oder tippe drauf, um zu erfahren, wofür es ist.',
      tools: {
        vscode: 'Mein täglicher Begleiter — kombiniert mit KI, damit ich schnell vibe-coden kann, ohne den Überblick zu verlieren.',
        docker: 'Docker hält meine Umgebungen sauber und portabel, n8n übernimmt die Automatisierungen, die ich nicht von Hand machen will.',
        blender: 'Für 3D-Modellierung, Animation und das gelegentliche Rendering, das meinen Abend frisst.',
        kdenlive: 'Hier schneide und poliere ich Videomaterial.',
        obs: 'Für Bildschirmaufnahmen und Streaming.',
        audacity: 'Zum Bereinigen und Bearbeiten von Audio.',
        gimp: 'Meine erste Wahl für Bildbearbeitung, wenn ein kostenloser Photoshop-Ersatz gebraucht wird.',
      },
    },
    support: {
      eyebrow: 'Support',
      headline: 'Support, wo auch immer du bist',
      text: `Ob remote oder persönlich — ich helfe dir bei Einrichtungsproblemen,
        spüre die kniffligen Bugs auf und kümmere mich um alltägliche
        Technikprobleme — auf Windows oder Linux, auf Arabisch, Englisch oder Deutsch.`,
      you: 'DU',
      platforms: 'Plattformen',
      languages: 'Sprachen',
    },
    build: {
      eyebrow: 'Erstellen',
      headline: 'Websites, Apps, Tools & SaaS',
      text: `Ich entwerfe und baue Websites, Apps, kleine Tools und SaaS-Produkte —
        mit KI-gestütztem Vibe-Coding, um schnell und trotzdem sauber zu arbeiten.`,
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

// Looks up a translated string by dotted path, e.g. getTranslation('en', 'hero.bio').
// Walks the TRANSLATIONS object one key segment at a time; returns undefined if any
// segment along the way doesn't exist, instead of throwing.
function getTranslation(lang, key) {
  return key.split('.').reduce((obj, part) => (obj ? obj[part] : undefined), TRANSLATIONS[lang]);
}

// Switches the whole page to the given language ('en' or 'de') by re-reading every
// translatable element and writing in the matching string. Called once on page load
// and again every time the user clicks the language toggle.
function applyLanguage(lang) {
  document.documentElement.lang = lang;

  // Plain text content, e.g. <span data-i18n="nav.toolkit">
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const value = getTranslation(lang, el.getAttribute('data-i18n'));
    if (value !== undefined) el.textContent = value;
  });

  // Text that is allowed to contain HTML (like the "Visit<br>Store" button label).
  document.querySelectorAll('[data-i18n-html]').forEach((el) => {
    const value = getTranslation(lang, el.getAttribute('data-i18n-html'));
    if (value !== undefined) el.innerHTML = value;
  });

  // Attribute values, e.g. data-i18n-attr="aria-label:hero.storeAria" or a
  // comma-separated list of "attr:key" pairs for elements needing more than one.
  document.querySelectorAll('[data-i18n-attr]').forEach((el) => {
    el.getAttribute('data-i18n-attr').split(',').forEach((pair) => {
      const [attr, key] = pair.split(':').map((s) => s.trim());
      const value = getTranslation(lang, key);
      if (value !== undefined) el.setAttribute(attr, value);
    });
  });

  // The little "🌐 DE/EN" button shows the language you'd switch TO, not the current one.
  const langToggle = document.getElementById('lang-toggle');
  if (langToggle) langToggle.textContent = getTranslation(lang, 'lang.toggle');

  // If a toolkit tag is currently selected, refresh its info text in the new language too.
  const activeTag = document.querySelector('.tag.is-active');
  const toolInfo = document.getElementById('tool-info');
  if (activeTag && toolInfo) toolInfo.textContent = activeTag.getAttribute('data-info');

  // The dark-mode button label ("Dark"/"Light") is also translated, so refresh it here.
  updateButtonText(html.classList.contains('dark-mode'));
}

// Sets up the language feature on page load: restores the visitor's last-picked
// language from localStorage (falls back to English), applies it, and wires up
// the toggle button to flip between English and German.
function initLanguage() {
  let lang = 'en';
  try {
    lang = localStorage.getItem('lang') || 'en';
  } catch (e) {
    // localStorage can be unavailable (e.g. private browsing) — just keep the default.
  }
  applyLanguage(lang);

  const langToggle = document.getElementById('lang-toggle');
  if (langToggle) {
    langToggle.addEventListener('click', () => {
      const next = document.documentElement.lang === 'de' ? 'en' : 'de';
      try {
        localStorage.setItem('lang', next);
      } catch (e) {
        // If we can't save the preference, the page still works — it just won't be
        // remembered on the next visit.
      }
      applyLanguage(next);
    });
  }
}

/* ── Dark mode ──
   Note: the very first switch to dark mode (based on saved preference or the OS
   setting) happens in an inline <script> in the <head>, before the page paints,
   so there's no flash of the wrong theme. Everything below just keeps the toggle
   button and future clicks in sync with that. */
const darkModeToggle = document.querySelector('.dark-mode-toggle');
const html = document.documentElement;

// Makes sure the toggle button's label matches whatever mode the page already
// loaded in (set by the inline script in <head>).
function initDarkMode() {
  updateButtonText(html.classList.contains('dark-mode'));
}

// Flips the dark-mode class on <html>, remembers the choice for next time, and
// updates the button label to match.
function toggleDarkMode() {
  html.classList.toggle('dark-mode');
  const isDarkMode = html.classList.contains('dark-mode');
  localStorage.setItem('darkMode', isDarkMode);
  updateButtonText(isDarkMode);
}

// Sets the dark-mode button's text ("🌙 Dark" / "☀️ Light") and its aria-pressed
// state, in whichever language is currently active.
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

/* ── Scroll progress bar ──
   Fills the thin bar fixed to the top of the page as the visitor scrolls down,
   so they get a quick visual sense of how far through the page they are. */
function initScrollProgress() {
  const bar = document.querySelector('.scroll-progress-bar');
  if (!bar) return;
  const update = () => {
    const scrollTop = window.scrollY;
    // Total scrollable distance = full page height minus one viewport height.
    const height = document.documentElement.scrollHeight - window.innerHeight;
    const pct = height > 0 ? (scrollTop / height) * 100 : 0;
    bar.style.width = pct + '%';
  };
  window.addEventListener('scroll', update, { passive: true });
  update(); // run once immediately, in case the page loads already scrolled
}

/* ── Scroll-spy nav ──
   Watches which page section is currently in view and highlights the matching
   nav link, so the nav bar always shows the visitor "you are here". */
function initScrollSpy() {
  const links = Array.from(document.querySelectorAll('.nav-link'));
  if (!links.length) return;
  // Each nav link's href (e.g. "#toolkit") points at the section it should highlight.
  const sections = links
    .map((link) => document.querySelector(link.getAttribute('href')))
    .filter(Boolean);
  if (!sections.length) return;

  // IntersectionObserver fires whenever a watched section crosses the given
  // rootMargin band — here, a horizontal strip roughly through the middle of the
  // viewport — which we treat as "this section is the one currently being read".
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

/* ── Reveal on scroll ──
   Fades/slides each ".reveal" element (section cards, footer) into view the first
   time it scrolls into the viewport, giving the page a bit of life without
   requiring the visitor to do anything. */
function initReveal() {
  const els = document.querySelectorAll('.reveal');
  if (!els.length) return;

  // Respect the visitor's reduced-motion preference: just show everything as-is.
  if (REDUCED_MOTION) {
    els.forEach((el) => el.classList.add('is-visible'));
    return;
  }

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target); // only reveal once, then stop watching it
        }
      });
    },
    { threshold: 0.15 } // trigger once 15% of the element is visible
  );
  els.forEach((el) => io.observe(el));
}

/* ── Magnetic hover ──
   Makes buttons marked ".magnetic" gently follow the cursor as it hovers nearby,
   like they're being pulled toward it — a small playful touch used on the
   round "Visit Store" button and the download/back buttons. */
function initMagnetic() {
  if (REDUCED_MOTION) return;
  document.querySelectorAll('.magnetic').forEach((el) => {
    el.addEventListener('mousemove', (e) => {
      const rect = el.getBoundingClientRect();
      // Offset of the cursor from the button's center point.
      const x = e.clientX - rect.left - rect.width / 2;
      const y = e.clientY - rect.top - rect.height / 2;
      // Move the button a fraction of that offset (0.28x) so it "chases" the cursor
      // without actually snapping to it.
      el.style.transform = `translate(${x * 0.28}px, ${y * 0.28}px)`;
    });
    el.addEventListener('mouseleave', () => {
      el.style.transform = ''; // snap back to its resting position
    });
  });
}

/* ── Tilt (hero photo) ──
   Gives the profile photo a subtle 3D tilt that follows the cursor, based on
   where the pointer is within its wrapping element. */
function initTilt() {
  if (REDUCED_MOTION) return;
  document.querySelectorAll('.tilt-el').forEach((el) => {
    const wrap = el.parentElement;
    wrap.addEventListener('mousemove', (e) => {
      const rect = wrap.getBoundingClientRect();
      // Cursor position within the wrapper, normalized to a -0.5..0.5 range
      // (0 = centered, negative = left/top, positive = right/bottom).
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;
      el.style.transform = `rotateY(${x * 16}deg) rotateX(${-y * 16}deg)`;
    });
    wrap.addEventListener('mouseleave', () => {
      el.style.transform = ''; // tilt back to flat
    });
  });
}

/* ── Toolkit tag info ──
   Powers the "hover or tap a tool to see what it's for" row: shows a short
   description under the tags on hover/focus, and lets one tag stay "selected"
   (its description stays visible) after a click/tap. */
function initToolTags() {
  const tags = document.querySelectorAll('.tag');
  const info = document.getElementById('tool-info');
  if (!tags.length || !info) return;

  // activeTag tracks the "pinned" tag from a click/tap — its info stays shown
  // even after the mouse moves away, until the same tag is clicked again.
  let activeTag = null;

  // Puts a tag's description into the info line below the tag cloud, falling
  // back to the default hint text if no tag is being shown.
  function showInfo(tag) {
    const text = tag ? tag.getAttribute('data-info') : null;
    const lang = document.documentElement.lang === 'de' ? 'de' : 'en';
    info.textContent = text || getTranslation(lang, 'toolkit.infoDefault');
  }

  // Goes back to showing whichever tag is currently pinned (or the default hint
  // if none is pinned) — used when the mouse/focus leaves a tag.
  function restoreInfo() {
    showInfo(activeTag);
  }

  tags.forEach((tag) => {
    // Hover/keyboard-focus previews the description without "pinning" it.
    tag.addEventListener('mouseenter', () => showInfo(tag));
    tag.addEventListener('mouseleave', restoreInfo);
    tag.addEventListener('focus', () => showInfo(tag));
    tag.addEventListener('blur', restoreInfo);
    // Click/tap toggles pinning: clicking the already-pinned tag unpins it,
    // clicking a different tag moves the pin there.
    tag.addEventListener('click', () => {
      if (activeTag === tag) {
        activeTag = null;
        tag.classList.remove('is-active');
      } else {
        if (activeTag) activeTag.classList.remove('is-active');
        activeTag = tag;
        tag.classList.add('is-active');
      }
      showInfo(activeTag);
    });
  });
}

/* ── Interactive background: drifting node network ──
   Draws the animated "constellation" backdrop on the full-page <canvas>: a bunch
   of small dots slowly drift around, get pulled toward the mouse when it's
   nearby, and lines are drawn between dots that are close enough to each other —
   giving a network/particle-field look. Pauses when the tab isn't visible to
   save battery/CPU, and skips the animation loop entirely if the visitor prefers
   reduced motion (drawing one static frame instead). */
function initBackgroundMotion() {
  const canvas = document.getElementById('bg-canvas');
  if (!canvas || !canvas.getContext) return;
  const ctx = canvas.getContext('2d');

  let dpr = 1; // device pixel ratio, for crisp rendering on high-DPI screens
  let points = []; // the drifting dots
  const mouse = { x: null, y: null }; // null when the pointer is off-screen

  // Reads the current theme's accent colors straight from CSS custom properties,
  // so the dots automatically match light/dark mode without duplicating colors here.
  function palette() {
    const styles = getComputedStyle(document.documentElement);
    return [
      styles.getPropertyValue('--accent').trim(),
      styles.getPropertyValue('--accent-hover').trim(),
      styles.getPropertyValue('--accent-2').trim(),
    ];
  }

  // Creates a fresh set of randomly placed, randomly drifting dots. The count
  // scales with screen area (more space = more dots), clamped between 24 and 90
  // so it stays light on both small and huge screens.
  function spawnPoints() {
    const area = window.innerWidth * window.innerHeight;
    const count = Math.min(90, Math.max(24, Math.round(area / 22000)));
    points = Array.from({ length: count }, () => ({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      vx: (Math.random() - 0.5) * 0.22, // slow, slight horizontal drift
      vy: (Math.random() - 0.5) * 0.22, // slow, slight vertical drift
      r: Math.random() * 1.5 + 1, // dot radius
      colorIndex: Math.floor(Math.random() * 3), // which accent color this dot uses
    }));
  }

  // Resizes the canvas to match the window and current pixel density, then
  // reseeds the dots (their old positions wouldn't make sense at a new size).
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2); // cap at 2x to limit cost on very dense screens
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    canvas.style.width = window.innerWidth + 'px';
    canvas.style.height = window.innerHeight + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); // draw in CSS pixels, browser scales up for us
    spawnPoints();
  }

  // Draws one frame. When `animate` is true, dots are first moved (including
  // being nudged away from the mouse and wrapped around screen edges) before
  // being drawn; when false, it just renders the dots at their current spot
  // (used for the single static frame under reduced motion).
  function draw(animate) {
    const w = window.innerWidth;
    const h = window.innerHeight;
    const colors = palette();
    const linkDist = 130; // max distance (px) at which two dots get a connecting line

    ctx.clearRect(0, 0, w, h);

    if (animate) {
      for (const p of points) {
        p.x += p.vx;
        p.y += p.vy;

        // Push dots away from the cursor when it's close, creating a ripple
        // effect as the visitor moves their mouse through the field.
        if (mouse.x !== null) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const dist = Math.hypot(dx, dy) || 1; // avoid divide-by-zero if dist is 0
          if (dist < 140) {
            const force = (140 - dist) / 140; // closer to mouse = stronger push
            p.x += (dx / dist) * force * 1.7;
            p.y += (dy / dist) * force * 1.7;
          }
        }

        // Wrap dots around the edges instead of letting them fly off-screen,
        // so the field always looks evenly populated.
        if (p.x < -20) p.x = w + 20;
        if (p.x > w + 20) p.x = -20;
        if (p.y < -20) p.y = h + 20;
        if (p.y > h + 20) p.y = -20;
      }
    }

    // Draw a faint line between every pair of dots that are close enough,
    // fading out as they get farther apart (up to linkDist).
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

    // Draw the dots themselves on top of the lines.
    ctx.globalAlpha = 0.5;
    for (const p of points) {
      ctx.fillStyle = colors[p.colorIndex];
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  let raf = null; // handle for the current requestAnimationFrame call, so it can be cancelled
  function loop() {
    draw(true);
    raf = requestAnimationFrame(loop);
  }

  resize();
  window.addEventListener('resize', resize);

  // Reduced-motion visitors get one still frame and no animation loop at all.
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

  // Stop animating when the tab is in the background (saves CPU/battery), and
  // pick the loop back up when the visitor returns to the tab.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      cancelAnimationFrame(raf);
    } else {
      raf = requestAnimationFrame(loop);
    }
  });

  loop();
}

// Kick everything off once the HTML is fully parsed. Each init function is
// independent and safe to call even if its target elements aren't on the
// current page (e.g. store.html doesn't have a toolkit tag cloud).
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
