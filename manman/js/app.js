// 慢慢來 - short-burst Taiwanese Mandarin practice.
(function () {
  'use strict';

  const Z = window.Zhuyin;
  const { DECKS, ITEMS: RAW_ITEMS, SCENES } = window.MANMAN_DATA;
  const DAY = 864e5;
  const STORE_KEY = 'manman.v1';
  const $app = document.getElementById('app');

  // ---------------------------------------------------------------------------
  // Content
  // ---------------------------------------------------------------------------

  const ITEMS = [];
  for (const deck of DECKS) {
    for (const [hz, py, en, note] of RAW_ITEMS[deck.id]) {
      ITEMS.push({ id: hz, deck: deck.id, hz, py, en, note, chars: Z.annotate(hz, py) });
    }
  }
  const ITEM_BY_ID = new Map(ITEMS.map((i) => [i.id, i]));
  for (const scene of SCENES) {
    scene.lines = scene.lines.map(([who, hz, py, en]) => ({ who, hz, py, en, chars: Z.annotate(hz, py) }));
  }
  const syllables = (x) => x.chars.filter((c) => c.syl).map((c) => c.syl);

  // ---------------------------------------------------------------------------
  // Storage (everything stays in this browser)
  // ---------------------------------------------------------------------------

  const DEFAULT_SETTINGS = {
    zhuyin: 'auto', // 'always' | 'auto' | 'tap'
    pinyin: false,
    sceneEnglish: true,
    rate: 0.85,
    voiceURI: '',
    sfx: true,
    theme: 'system',
    decks: Object.fromEntries(DECKS.map((d) => [d.id, true])),
  };
  let storageOk = true;
  let state = load();

  function load() {
    let saved = null;
    try {
      saved = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
    } catch (e) {
      storageOk = false;
    }
    return normalize(saved);
  }
  function normalize(saved) {
    const s = saved && typeof saved === 'object' ? saved : {};
    return {
      settings: { ...DEFAULT_SETTINGS, ...(s.settings || {}), decks: { ...DEFAULT_SETTINGS.decks, ...((s.settings || {}).decks || {}) } },
      items: s.items || {},
      days: s.days || {},
      scenes: s.scenes || {},
    };
  }
  function save() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(state));
    } catch (e) {
      storageOk = false;
    }
  }
  const S = () => state.settings;

  function dayKey(d = new Date()) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }
  function logActivity(n = 1) {
    const k = dayKey();
    state.days[k] = (state.days[k] || 0) + n;
    save();
  }
  function lastPracticeDaysAgo() {
    const keys = Object.keys(state.days).sort();
    if (!keys.length) return null;
    const [y, m, d] = keys[keys.length - 1].split('-').map(Number);
    const last = new Date(y, m - 1, d);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    return Math.round((today - last) / DAY);
  }

  // ---------------------------------------------------------------------------
  // Spaced repetition. Stability `s` is in days: the gap after which you'd
  // still remember about 90% of the time. It grows with each success.
  // ---------------------------------------------------------------------------

  const stOf = (item) => state.items[item.id];
  const strength = (item) => (stOf(item) ? stOf(item).s : -1);

  function isFading(item, now = Date.now()) {
    const st = stOf(item);
    return !!st && st.s > 0 && now >= st.due;
  }
  function retrievability(item, now = Date.now()) {
    const st = stOf(item);
    if (!st) return 1;
    if (st.s <= 0) return 0.3;
    return Math.pow(0.9, (now - st.last) / DAY / st.s);
  }
  function meet(item) {
    if (!stOf(item)) {
      const now = Date.now();
      state.items[item.id] = { s: 0, due: now, last: now, seen: 0, lapses: 0 };
      save();
    }
  }
  function grade(item, result) {
    const now = Date.now();
    const st = state.items[item.id] || { s: 0, due: now, last: now, seen: 0, lapses: 0 };
    const elapsed = (now - st.last) / DAY;
    if (result === 'miss') {
      st.lapses++;
      st.s = st.s > 0 ? Math.max(0.3, st.s * 0.35) : 0;
      st.due = now + 10 * 60e3;
    } else {
      const mult = { hard: 1.4, good: 2.5, easy: 3.5 }[result];
      if (st.s <= 0) {
        st.s = { hard: 0.5, good: 1, easy: 3 }[result];
      } else {
        // Reviewing early gives a smaller boost than reviewing on time.
        const ratio = Math.max(0.15, Math.min(1, elapsed / st.s));
        st.s = Math.min(365, st.s * (1 + (mult - 1) * ratio));
      }
      st.due = now + st.s * DAY;
    }
    st.last = now;
    st.seen++;
    state.items[item.id] = st;
    save();
  }

  function enabledItems() {
    return ITEMS.filter((i) => S().decks[i.deck]);
  }
  function zhuyinVisibility(item) {
    const mode = S().zhuyin;
    if (mode === 'always') return 'show';
    if (mode === 'tap') return 'tap';
    return strength(item) >= 7 ? 'tap' : 'show';
  }

  // ---------------------------------------------------------------------------
  // Speech synthesis
  // ---------------------------------------------------------------------------

  const Speech = {
    supported: 'speechSynthesis' in window,
    voices: [],
    ready: false,
    init() {
      if (!this.supported) return;
      const load = () => {
        this.voices = speechSynthesis.getVoices();
        if (this.voices.length) this.ready = true;
        if (current && current.name === 'home') render();
      };
      load();
      speechSynthesis.addEventListener('voiceschanged', load);
      // Some setups never announce voices; stop waiting after a moment.
      setTimeout(() => { if (!this.ready) { this.ready = true; load(); } }, 1500);
    },
    zhVoices() {
      return this.voices.filter((v) => /^(zh|cmn)/i.test(v.lang) && !/HK|yue/i.test(v.lang));
    },
    isTaiwan(v) {
      return /TW|Hant|Taiwan/i.test(v.lang) || /Taiwan|台灣|臺灣|Hanhan|Yating|Zhiwei|Mei-?Jia|HsiaoChen|HsiaoYu|YunJhe/i.test(v.name);
    },
    voice() {
      const zh = this.zhVoices();
      const chosen = zh.find((v) => v.voiceURI === S().voiceURI);
      if (chosen) return chosen;
      return zh.find((v) => this.isTaiwan(v)) || zh[0] || null;
    },
    status() {
      if (!this.supported) return 'none';
      const v = this.voice();
      if (!v) return this.ready ? 'none' : 'loading';
      return this.isTaiwan(v) ? 'tw' : 'other';
    },
    speak(text, rate) {
      return new Promise((resolve) => {
        if (!this.supported) return resolve();
        speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text.replace(/[…—]+/g, '，'));
        const v = this.voice();
        if (v) u.voice = v;
        u.lang = v ? v.lang : 'zh-TW';
        u.rate = rate || S().rate;
        let done = false;
        const finish = () => { if (!done) { done = true; resolve(); } };
        u.onend = finish;
        u.onerror = finish;
        // Safety net: some engines never fire onend.
        setTimeout(finish, 1500 + text.length * 600 / u.rate);
        speechSynthesis.speak(u);
      });
    },
    stop() { if (this.supported) speechSynthesis.cancel(); },
  };

  // ---------------------------------------------------------------------------
  // Little sound effects
  // ---------------------------------------------------------------------------

  let audioCtx = null;
  function blip(kind) {
    if (!S().sfx) return;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const notes = kind === 'good' ? [660, 880] : kind === 'done' ? [523, 659, 784, 1047] : [220, 196];
      notes.forEach((f, i) => {
        const o = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        const t = audioCtx.currentTime + i * 0.09;
        o.type = kind === 'bad' ? 'triangle' : 'sine';
        o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.12, t + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
        o.connect(g).connect(audioCtx.destination);
        o.start(t);
        o.stop(t + 0.2);
      });
    } catch (e) { /* sound is optional */ }
  }

  // ---------------------------------------------------------------------------
  // Recording + pitch analysis
  // ---------------------------------------------------------------------------

  const Rec = {
    supported: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder),
    recorder: null,
    stream: null,
    async start() {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const chunks = [];
      this.recorder = new MediaRecorder(this.stream);
      this.recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      this.done = new Promise((resolve) => {
        this.recorder.onstop = () => {
          // Release the mic straight away so the browser's mic indicator goes off.
          this.stream.getTracks().forEach((t) => t.stop());
          resolve(new Blob(chunks, { type: this.recorder.mimeType || 'audio/webm' }));
        };
      });
      this.recorder.start();
    },
    stop() {
      if (this.recorder && this.recorder.state !== 'inactive') this.recorder.stop();
      return this.done;
    },
    get active() { return !!this.recorder && this.recorder.state === 'recording'; },
  };

  // Autocorrelation pitch tracker. Returns semitones relative to the
  // speaker's median pitch for each 10ms frame (null = unvoiced/silent).
  async function analyzePitch(blob) {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    let audio;
    try {
      audio = await ctx.decodeAudioData(await blob.arrayBuffer());
    } finally {
      ctx.close();
    }
    const raw = audio.getChannelData(0);
    const factor = Math.max(1, Math.floor(audio.sampleRate / 16000));
    const sr = audio.sampleRate / factor;
    const x = new Float32Array(Math.floor(raw.length / factor));
    for (let i = 0; i < x.length; i++) {
      let sum = 0;
      for (let j = 0; j < factor; j++) sum += raw[i * factor + j];
      x[i] = sum / factor;
    }
    const frame = Math.round(sr * 0.04);
    const hop = Math.round(sr * 0.01);
    const minLag = Math.floor(sr / 450);
    const maxLag = Math.floor(sr / 70);
    const rms = [];
    for (let start = 0; start + frame + maxLag < x.length; start += hop) {
      let e = 0;
      for (let i = 0; i < frame; i++) e += x[start + i] * x[start + i];
      rms.push(Math.sqrt(e / frame));
    }
    const peak = Math.max(...rms, 1e-9);
    const freqs = [];
    rms.forEach((r, n) => {
      const start = n * hop;
      if (r < peak * 0.12) { freqs.push(null); return; }
      const corr = new Float32Array(maxLag + 1);
      let best = 0;
      for (let lag = minLag; lag <= maxLag; lag++) {
        let c = 0, e1 = 0, e2 = 0;
        for (let i = 0; i < frame; i++) {
          const a = x[start + i], b = x[start + i + lag];
          c += a * b; e1 += a * a; e2 += b * b;
        }
        corr[lag] = c / Math.sqrt(e1 * e2 + 1e-12);
        if (corr[lag] > best) best = corr[lag];
      }
      if (best < 0.6) { freqs.push(null); return; }
      // First peak close to the best one, to avoid octave errors.
      for (let lag = minLag + 1; lag < maxLag; lag++) {
        if (corr[lag] >= best * 0.9 && corr[lag] >= corr[lag - 1] && corr[lag] >= corr[lag + 1]) {
          freqs.push(sr / lag);
          return;
        }
      }
      freqs.push(null);
    });
    const voiced = freqs.filter(Boolean).sort((a, b) => a - b);
    if (voiced.length < 5) return null;
    const median = voiced[Math.floor(voiced.length / 2)];
    const semis = freqs.map((f) => (f && f / median < 1.9 && f / median > 0.53 ? 12 * Math.log2(f / median) : null));
    // Light median smoothing.
    return semis.map((v, i) => {
      if (v === null) return null;
      const win = semis.slice(Math.max(0, i - 2), i + 3).filter((y) => y !== null).sort((a, b) => a - b);
      return win[Math.floor(win.length / 2)];
    });
  }

  // Target pitch shapes on the 1-5 scale. Taiwan Mandarin 3rd tone is
  // usually a low dip without the big rise.
  function targetContours(sylls) {
    const tones = sylls.map(Z.toneOf);
    for (let i = 0; i < tones.length - 1; i++) {
      if (tones[i] === 3 && tones[i + 1] === 3) tones[i] = 2; // 3-3 sandhi
    }
    return tones.map((t, i) => {
      const prev = tones[i - 1];
      switch (t) {
        case 1: return { pts: [5, 5], w: 1 };
        case 2: return { pts: [3, 3.3, 5], w: 1 };
        case 3: return { pts: [2.2, 1.2, 1], w: 1 };
        case 4: return { pts: [5, 1], w: 0.9 };
        default: return { pts: prev === 3 ? [3.5, 3.3] : prev === 4 ? [1.6, 1.3] : [2.6, 2.3], w: 0.55 };
      }
    });
  }

  function drawPitch(canvas, sylls, semis) {
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.clientWidth, H = canvas.clientHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    const g = canvas.getContext('2d');
    g.scale(dpr, dpr);
    const css = getComputedStyle(document.documentElement);
    const accent = css.getPropertyValue('--accent').trim();
    const you = css.getPropertyValue('--you').trim();
    const muted = css.getPropertyValue('--muted').trim();
    const border = css.getPropertyValue('--border').trim();
    const padX = 14, top = 14, bottom = 26;
    const y = (v) => top + (5 - v) / 4 * (H - top - bottom);

    const shapes = targetContours(sylls);
    const totalW = shapes.reduce((n, s) => n + s.w, 0);
    let x0 = padX;
    g.lineCap = 'round'; g.lineJoin = 'round';
    shapes.forEach((sh, i) => {
      const w = sh.w / totalW * (W - padX * 2);
      if (i > 0) {
        g.strokeStyle = border; g.lineWidth = 1; g.setLineDash([3, 4]);
        g.beginPath(); g.moveTo(x0, top); g.lineTo(x0, H - bottom); g.stroke(); g.setLineDash([]);
      }
      g.strokeStyle = accent; g.globalAlpha = 0.35; g.lineWidth = 12;
      g.beginPath();
      sh.pts.forEach((p, k) => {
        const px = x0 + w * (0.12 + 0.76 * k / (sh.pts.length - 1));
        k ? g.lineTo(px, y(p)) : g.moveTo(px, y(p));
      });
      g.stroke(); g.globalAlpha = 1;
      g.fillStyle = muted; g.font = '14px ' + css.getPropertyValue('--font-zh');
      g.textAlign = 'center';
      const label = Z.toZhuyin(sylls[i]);
      if (g.measureText(label).width < w - 4) g.fillText(label, x0 + w / 2, H - 8);
      x0 += w;
    });

    if (!semis) return;
    const first = semis.findIndex((v) => v !== null);
    let last = semis.length - 1;
    while (last > 0 && semis[last] === null) last--;
    if (first < 0 || last <= first) return;
    const vals = semis.slice(first, last + 1).filter((v) => v !== null).sort((a, b) => a - b);
    const lo = vals[Math.floor(vals.length * 0.08)], hi = vals[Math.floor(vals.length * 0.92)];
    const span = Math.max(hi - lo, 7); // don't exaggerate a flat voice
    const mid = (hi + lo) / 2;
    const toScale = (v) => Math.max(0.6, Math.min(5.4, 3 + (v - mid) / span * 4));
    g.strokeStyle = you; g.lineWidth = 3;
    g.beginPath();
    let pen = false;
    for (let i = first; i <= last; i++) {
      const v = semis[i];
      if (v === null) { pen = false; continue; }
      const px = padX + (i - first) / (last - first) * (W - padX * 2);
      pen ? g.lineTo(px, y(toScale(v))) : g.moveTo(px, y(toScale(v)));
      pen = true;
    }
    g.stroke();
  }

  // ---------------------------------------------------------------------------
  // HTML helpers
  // ---------------------------------------------------------------------------

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const shuffle = (a) => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  const pick = (a) => a[Math.floor(Math.random() * a.length)];

  // vis: 'show' | 'tap' | 'none'
  function hzHtml(x, { size = 'hz-xl', vis = 'show', pinyin = S().pinyin } = {}) {
    const inner = x.chars.map(({ ch, syl }) => (syl
      ? (vis === 'none' ? esc(ch) : `<ruby>${esc(ch)}<rt>${esc(Z.toZhuyin(syl))}</rt></ruby>`)
      : `<span>${esc(ch)}</span>`)).join('');
    const cls = `hz ${size}${vis === 'tap' ? ' zy-hidden' : ''}`;
    const tip = vis === 'tap' ? ' title="Tap to show Zhuyin"' : '';
    const py = pinyin ? `<div class="pinyin">${syllables(x).map(Z.toPinyin).join(' ')}</div>` : '';
    return `<div class="${cls}"${tip} lang="zh-TW">${inner}</div>${py}`;
  }
  const zhuyinLine = (sylls) => sylls.map(Z.toZhuyin).join(' ');

  function contourSvg(tones) {
    const shapes = { 1: [5, 5], 2: [3, 5], 3: [2, 1, 2], 4: [5, 1], 5: [3, 3] };
    const w = 26;
    const paths = tones.map((t, i) => {
      const pts = shapes[t];
      return pts.map((p, k) => `${k ? 'L' : 'M'}${(i * w + 5 + (w - 10) * k / (pts.length - 1)).toFixed(1)} ${(3 + (5 - p) * 3.5).toFixed(1)}`).join(' ');
    }).join(' ');
    return `<svg width="${tones.length * w}" height="20" viewBox="0 0 ${tones.length * w} 20" aria-hidden="true"><path d="${paths}" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  }

  function nav(name, params) {
    Speech.stop();
    if (Rec.active) Rec.stop();
    current = { name, ...(params || {}) };
    document.body.classList.toggle('focus', name === 'session');
    document.querySelectorAll('.topnav button').forEach((b) => b.classList.toggle('active', b.dataset.nav === name));
    render();
    window.scrollTo(0, 0);
  }

  let current = { name: 'home' };
  let keyHandler = null;

  function render() {
    keyHandler = null;
    const screens = { home: renderHome, session: renderSession, scenes: renderScenes, scene: renderScene, browse: renderBrowse, settings: renderSettings, help: renderHelp };
    (screens[current.name] || renderHome)();
  }

  // Wires a recorder widget inside `root` for the given text.
  function wireRecorder(root, x) {
    const box = root.querySelector('.recorder');
    if (!box) return;
    const btn = box.querySelector('[data-rec]');
    const after = box.querySelector('.rec-after');
    const canvas = box.querySelector('canvas');
    const msg = box.querySelector('.rec-msg');
    let url = null;
    const sylls = syllables(x);
    const draw = (semis) => drawPitch(canvas, sylls, semis);
    requestAnimationFrame(() => draw(null));

    async function toggle() {
      if (Rec.active) { btn.disabled = true; return; }
      try {
        Speech.stop();
        await Rec.start();
      } catch (e) {
        msg.textContent = 'Could not use the microphone. Check that the browser has permission.';
        return;
      }
      btn.classList.add('recording');
      btn.innerHTML = '■ Stop';
      const autoStop = setTimeout(() => Rec.active && Rec.stop(), 2500 + sylls.length * 700);
      btn.onclick = () => { clearTimeout(autoStop); Rec.stop(); };
      const blob = await Rec.done;
      clearTimeout(autoStop);
      btn.disabled = false;
      btn.classList.remove('recording');
      btn.innerHTML = '🎙 Record again <span class="k">R</span>';
      btn.onclick = toggle;
      if (url) URL.revokeObjectURL(url);
      url = URL.createObjectURL(blob);
      after.hidden = false;
      msg.textContent = 'Analyzing…';
      try {
        const semis = await analyzePitch(blob);
        draw(semis);
        msg.textContent = semis ? 'Blue is you, orange is the target shape. Match the shapes, not the exact height.' : "Couldn't hear much - try a bit louder or closer to the mic.";
      } catch (e) {
        msg.textContent = 'Recorded, but this browser could not analyze the audio.';
      }
    }
    btn.onclick = toggle;
    box.querySelector('[data-mine]').onclick = () => { Speech.stop(); new Audio(url).play(); };
    box.querySelector('[data-both]').onclick = async () => { await Speech.speak(x.hz); new Audio(url).play(); };
    box.toggleRecord = () => btn.click();
  }

  function recorderHtml() {
    if (!Rec.supported) return '<p class="small muted">Recording is not available in this browser.</p>';
    return `<div class="recorder">
      <div class="row" style="justify-content:center">
        <button class="btn rec" data-rec>🎙 Record yourself <span class="k">R</span></button>
        <span class="rec-after row" hidden>
          <button class="btn" data-mine>▶ Mine</button>
          <button class="btn" data-both>🔁 Model, then mine</button>
        </span>
      </div>
      <canvas aria-label="Pitch graph"></canvas>
      <div class="legend"><span><i style="background:var(--accent);opacity:.5"></i>target tones</span><span><i style="background:var(--you)"></i>your voice</span></div>
      <p class="small muted rec-msg" style="text-align:center;margin-top:6px">Optional. Nothing leaves your computer.</p>
    </div>`;
  }

  // Tap-to-reveal Zhuyin, anywhere.
  $app.addEventListener('click', (e) => {
    const hz = e.target.closest('.hz.zy-hidden');
    if (hz) hz.classList.toggle('zy-show');
  });

  // ---------------------------------------------------------------------------
  // Home
  // ---------------------------------------------------------------------------

  function renderHome() {
    const now = Date.now();
    const pool = enabledItems();
    const fading = pool.filter((i) => isFading(i, now)).length;
    const known = ITEMS.filter((i) => strength(i) >= 1).length;
    const unseen = pool.filter((i) => !stOf(i)).length;
    const gap = lastPracticeDaysAgo();

    const dots = [];
    let active7 = 0;
    for (let k = 13; k >= 0; k--) {
      const d = new Date(); d.setDate(d.getDate() - k);
      const on = !!state.days[dayKey(d)];
      if (on && k < 7) active7++;
      dots.push(`<span class="dot${on ? ' on' : ''}${k === 0 ? ' today' : ''}" title="${dayKey(d)}"></span>`);
    }

    let greeting, sub;
    if (gap === null) {
      greeting = '歡迎！Welcome!';
      sub = 'Short bursts, no pressure. Start with a couple of minutes.';
    } else if (gap === 0) {
      greeting = '又來了！Back again!';
      sub = "Every extra burst today makes the words stick harder.";
    } else if (gap >= 3) {
      greeting = '好久不見！Long time no see!';
      sub = "No problem. You remember more than you think - this burst starts with a quick refresh.";
    } else {
      greeting = '你好！Hi again.';
      sub = fading ? `${fading} word${fading === 1 ? '' : 's'} could use a quick refresh.` : 'Ready for something new?';
    }

    const status = Speech.status();
    let voiceNote = '';
    if (status === 'none') voiceNote = `<div class="notice">🔇 No Chinese voice found, so you won't hear audio. <a href="#" data-go="help">How to add a Taiwan voice</a>.</div>`;
    else if (status === 'other') voiceNote = `<div class="notice">🔈 Using a non-Taiwan Chinese voice (${esc(Speech.voice().name)}). It'll work, but the accent is mainland. <a href="#" data-go="help">Add a Taiwan voice</a>.</div>`;
    const storageNote = storageOk ? '' : '<div class="notice">⚠️ This browser is blocking storage, so progress won\'t be saved after you close the tab.</div>';
    const nothingEnabled = !pool.length;

    $app.innerHTML = `<div class="stack">
      ${voiceNote}${storageNote}
      <section class="card hero">
        <h1>${greeting}</h1>
        <p class="sub muted">${sub}</p>
        <div class="start-row">
          <button class="btn primary big" data-start="10" ${nothingEnabled ? 'disabled' : ''}>▶ Start a burst <span class="k">~3 min · Enter</span></button>
        </div>
        <div class="start-row" style="margin-top:10px">
          <button class="btn" data-start="5" ${nothingEnabled ? 'disabled' : ''}>⚡ Just 1 minute</button>
          <button class="btn" data-start="20" ${nothingEnabled ? 'disabled' : ''}>🔥 Longer (~6 min)</button>
        </div>
      </section>
      <section class="stats">
        <div class="stat"><b>${known}</b><span>words you know</span></div>
        <div class="stat"><b>${fading}</b><span>need a refresh</span></div>
        <div class="stat"><b>${unseen}</b><span>still to meet</span></div>
      </section>
      <section class="card">
        <h3>Momentum: ${active7} of the last 7 days</h3>
        <p class="small muted">No streaks to break. Any day you show up counts.</p>
        <div class="dots" aria-label="Last 14 days">${dots.join('')}</div>
      </section>
      <section class="card stack">
        <div><h3>What are you in the mood for?</h3><p class="small muted">Bursts mix words from whatever is switched on.</p></div>
        <div class="chips">${DECKS.map((d) => `<button class="chip" data-deck="${d.id}" aria-pressed="${!!S().decks[d.id]}">${d.icon} ${esc(d.name)} <span class="zh">${d.zh}</span></button>`).join('')}</div>
        ${nothingEnabled ? '<p class="small" style="color:var(--bad)">Switch on at least one topic to start.</p>' : ''}
      </section>
      <section class="card row" style="justify-content:space-between">
        <div><h3>🎭 Feeling brave?</h3><p class="small muted">Practice real conversations, privately. The app plays the other person.</p></div>
        <button class="btn" data-go="scenes">Try a scene</button>
      </section>
    </div>`;

    $app.querySelectorAll('[data-start]').forEach((b) => (b.onclick = () => startSession(Number(b.dataset.start))));
    $app.querySelectorAll('[data-deck]').forEach((b) => (b.onclick = () => {
      S().decks[b.dataset.deck] = !S().decks[b.dataset.deck];
      save(); render();
    }));
    $app.querySelectorAll('[data-go]').forEach((b) => (b.onclick = (e) => { e.preventDefault(); nav(b.dataset.go); }));
    keyHandler = (e) => { if (e.key === 'Enter' && !nothingEnabled) startSession(10); };
  }

  // ---------------------------------------------------------------------------
  // Session ("burst")
  // ---------------------------------------------------------------------------

  let session = null;

  function canTone(item) {
    const s = syllables(item);
    if (!s.length || s.length > 4) return false;
    for (let i = 0; i < s.length - 1; i++) if (Z.toneOf(s[i]) === 3 && Z.toneOf(s[i + 1]) === 3) return false;
    return true;
  }

  function chooseActivity(item, prev) {
    const s = strength(item);
    let opts;
    if (s < 1) opts = ['listen', 'read', 'pick', 'listen'];
    else if (s < 7) opts = ['listen', 'listen', 'read', 'pick', 'say', 'tone', 'tone', 'shadow'];
    else opts = ['read', 'read', 'say', 'listen', 'shadow', 'tone', 'pick'];
    if (!canTone(item)) opts = opts.filter((o) => o !== 'tone');
    if (!Speech.voice()) opts = opts.filter((o) => o !== 'listen' && o !== 'tone' && o !== 'shadow');
    const fresh = opts.filter((o) => o !== prev);
    return pick(fresh.length ? fresh : opts);
  }

  function buildQueue(size) {
    const now = Date.now();
    const pool = enabledItems();
    const due = pool.filter((i) => stOf(i) && stOf(i).due <= now).sort((a, b) => retrievability(a, now) - retrievability(b, now));
    // Round-robin across topics so new words come with variety.
    const byDeck = DECKS.map((d) => pool.filter((i) => i.deck === d.id && !stOf(i)));
    const unseen = [];
    for (let k = 0; byDeck.some((l) => l[k]); k++) byDeck.forEach((l) => l[k] && unseen.push(l[k]));

    let newCount = due.length > 25 ? 0 : Math.min(unseen.length, size <= 5 ? 1 : size <= 10 ? 3 : 5);
    const reviews = due.slice(0, Math.max(0, size - newCount * 2));
    while (reviews.length + newCount * 2 < size && newCount < unseen.length) newCount++;
    if (reviews.length + newCount * 2 < size) {
      const extra = pool.filter((i) => stOf(i) && !reviews.includes(i)).sort((a, b) => retrievability(a, now) - retrievability(b, now));
      reviews.push(...extra.slice(0, size - reviews.length - newCount * 2));
    }

    const cards = [];
    let prev = null;
    for (const item of shuffle(reviews)) {
      const type = chooseActivity(item, prev);
      cards.push({ type, item });
      prev = type;
    }
    unseen.slice(0, newCount).forEach((item, n) => {
      const pos = Math.round((n * cards.length) / newCount);
      cards.splice(pos, 0, { type: 'meet', item });
      cards.splice(Math.min(cards.length, pos + 3), 0, { type: pick(Speech.voice() ? ['listen', 'pick'] : ['read', 'pick']), item, followUp: true });
    });
    return cards.slice(0, Math.max(size, newCount * 2));
  }

  function startSession(size) {
    const queue = buildQueue(size);
    if (!queue.length) { nav('home'); return; }
    session = { queue, idx: 0, correct: 0, answered: 0, combo: 0, best: 0, met: 0, retried: new Set() };
    nav('session');
  }

  // Only moves on if `card` is still showing, so stray timers or double
  // key presses can't skip the next card.
  function advance(card) {
    if (!session || session.queue[session.idx] !== card) return;
    session.idx++;
    render();
  }

  function requeue(item) {
    // Cap retries so a rough round doesn't keep getting longer.
    if (session.retried.has(item.id) || session.retried.size >= 3) return;
    session.retried.add(item.id);
    const type = pick(Speech.voice() ? ['listen', 'read', 'pick'] : ['read', 'pick']);
    session.queue.splice(Math.min(session.queue.length, session.idx + 3), 0, { type, item, retry: true });
  }

  function scoreAnswer(card, result) {
    const ok = result !== 'miss';
    session.answered++;
    logActivity();
    if (ok) {
      session.correct++;
      session.combo++;
      session.best = Math.max(session.best, session.combo);
      blip('good');
    } else {
      session.combo = 0;
      blip('bad');
      requeue(card.item);
    }
    grade(card.item, result);
    const c = $app.querySelector('.combo');
    if (c) { c.textContent = session.combo >= 2 ? `🔥 ${session.combo}` : ''; c.classList.remove('bump'); void c.offsetWidth; c.classList.add('bump'); }
  }

  function renderSession() {
    if (!session) return nav('home');
    if (session.idx >= session.queue.length) return renderDone();
    const card = session.queue[session.idx];
    const pct = (session.idx / session.queue.length) * 100;
    const head = `<div class="session-top">
      <button class="btn ghost" data-quit title="Stop (Esc)">✕</button>
      <div class="progress"><i style="width:${pct}%"></i></div>
      <div class="combo">${session.combo >= 2 ? `🔥 ${session.combo}` : ''}</div>
    </div>`;
    const body = { meet: cardMeet, listen: cardChoice, read: cardChoice, pick: cardChoice, tone: cardTone, say: cardSay, shadow: cardShadow }[card.type](card);
    $app.innerHTML = head + `<section class="card prompt">${body.html}</section>`;
    $app.querySelector('[data-quit]').onclick = () => (session.answered ? renderDone() : nav('home'));
    body.wire && body.wire();
    const baseKeys = keyHandler;
    keyHandler = (e) => {
      if (e.key === 'Escape') { session.answered ? renderDone() : nav('home'); return; }
      if (e.key === 'r' || e.key === 'R') { const rec = $app.querySelector('.recorder'); if (rec && rec.toggleRecord) rec.toggleRecord(); return; }
      baseKeys && baseKeys(e);
    };
  }

  const playBtn = (label = '🔊') => `<button class="play-big" data-play aria-label="Play audio (Space)">${label}</button>`;
  const deckLabel = (item) => { const d = DECKS.find((x) => x.id === item.deck); return `${d.icon} ${esc(d.name)}`; };

  function cardMeet(card) {
    const { item } = card;
    return {
      html: `<div class="stack">
        <div class="task-label">New word · ${deckLabel(item)}</div>
        ${hzHtml(item, { vis: 'show' })}
        <div class="en">${esc(item.en)}</div>
        ${item.note ? `<div class="note">💡 ${esc(item.note)}</div>` : ''}
        <p class="small muted">Say it out loud with the audio. Whispering counts.</p>
        <div class="actions">
          <button class="btn" data-play>🔊 Play <span class="k">Space</span></button>
          <button class="btn" data-slow>🐢 Slow</button>
        </div>
        ${recorderHtml()}
        <div class="actions"><button class="btn primary" data-next>Got it → <span class="k">Enter</span></button></div>
      </div>`,
      wire() {
        meet(item);
        session.met++;
        const play = () => Speech.speak(item.hz);
        $app.querySelector('[data-play]').onclick = play;
        $app.querySelector('[data-slow]').onclick = () => Speech.speak(item.hz, 0.55);
        $app.querySelector('[data-next]').onclick = () => advance(card);
        wireRecorder($app, item);
        play();
        keyHandler = (e) => {
          if (e.key === ' ') { e.preventDefault(); play(); }
          if (e.key === 'Enter') advance(card);
        };
      },
    };
  }

  function distractors(item, n, key) {
    const same = shuffle(ITEMS.filter((i) => i.deck === item.deck && i !== item));
    const other = shuffle(ITEMS.filter((i) => i.deck !== item.deck));
    const out = [];
    const seenVals = new Set([key(item)]);
    for (const c of same.concat(other)) {
      if (out.length >= n) break;
      if (!seenVals.has(key(c))) { seenVals.add(key(c)); out.push(c); }
    }
    return out;
  }

  // listen / read / pick: four-option multiple choice.
  function cardChoice(card) {
    const { item, type } = card;
    const options = shuffle([item, ...distractors(item, 3, (i) => (type === 'pick' ? i.hz : i.en))]);
    let prompt, label;
    if (type === 'listen') {
      label = 'Listen · what does it mean?';
      prompt = `${playBtn()}<p class="small muted">Space to replay</p>`;
    } else if (type === 'read') {
      label = 'Read · what does it mean?';
      prompt = `${hzHtml(item, { vis: zhuyinVisibility(item) })}${zhuyinVisibility(item) === 'tap' ? '<p class="tap-hint">Tap the characters if you need Zhuyin</p>' : ''}`;
    } else {
      label = 'Which one means…';
      prompt = `<div class="en" style="font-size:24px;font-weight:600">“${esc(item.en)}”</div>`;
    }
    const optHtml = options.map((o, n) => `<button class="option" data-opt="${n}"><span class="num">${n + 1}</span>${
      type === 'pick' ? hzHtml(o, { size: '', vis: zhuyinVisibility(o) === 'show' ? 'show' : 'none', pinyin: false }) : esc(o.en)
    }</button>`).join('');
    return {
      html: `<div class="stack">
        <div class="task-label">${label}</div>
        ${prompt}
      </div>
      <div class="options">${optHtml}</div>
      <div class="reveal" hidden></div>`,
      wire() {
        let answered = false;
        let autoTimer = null;
        const play = () => Speech.speak(item.hz);
        const playBtnEl = $app.querySelector('[data-play]');
        if (playBtnEl) playBtnEl.onclick = play;
        if (type === 'listen') play();
        const buttons = [...$app.querySelectorAll('[data-opt]')];
        const next = () => { clearTimeout(autoTimer); advance(card); };
        const choose = async (n) => {
          if (answered) return;
          answered = true;
          const right = options[n] === item;
          buttons.forEach((b, k) => {
            b.disabled = true;
            if (options[k] === item) b.classList.add('correct');
            else if (k === n) b.classList.add('wrong');
          });
          scoreAnswer(card, right ? 'good' : 'miss');
          const rev = $app.querySelector('.reveal');
          rev.hidden = false;
          rev.innerHTML = `<div class="stack">
            <div class="feedback ${right ? 'good' : 'bad'}">${right ? pick(['對！', '很好！', '厲害！', '沒錯！']) : "Not quite - it'll come back soon."}</div>
            ${type !== 'read' || !right ? hzHtml(item, { size: 'hz-lg', vis: 'show' }) : ''}
            <div class="en">${esc(item.en)}</div>
            <div class="actions"><button class="btn" data-play2>🔊</button><button class="btn primary" data-next>Next → <span class="k">Enter</span></button></div>
          </div>`;
          rev.querySelector('[data-play2]').onclick = play;
          rev.querySelector('[data-next]').onclick = next;
          rev.querySelector('[data-next]').focus({ preventScroll: true });
          await play();
          // Keep momentum on correct answers; pause on mistakes so they can look.
          if (right) autoTimer = setTimeout(next, 700);
        };
        buttons.forEach((b, n) => (b.onclick = () => choose(n)));
        keyHandler = (e) => {
          if (e.key === ' ') { e.preventDefault(); play(); }
          if (/^[1-4]$/.test(e.key) && !answered) choose(Number(e.key) - 1);
          if (e.key === 'Enter' && answered) next();
        };
      },
    };
  }

  function cardTone(card) {
    const { item } = card;
    const sylls = syllables(item);
    const tones = sylls.map(Z.toneOf);
    const key = (t) => t.join('');
    const pool = new Map([[key(tones), tones]]);
    let guard = 0;
    while (pool.size < 4 && guard++ < 200) {
      const t = tones.slice();
      const changes = sylls.length === 1 ? 1 : 1 + Math.floor(Math.random() * 2);
      for (let c = 0; c < changes; c++) {
        const i = Math.floor(Math.random() * t.length);
        if (t[i] !== 5) t[i] = 1 + Math.floor(Math.random() * 4);
      }
      pool.set(key(t), t);
    }
    const options = shuffle([...pool.values()]);
    const withTones = (t) => sylls.map((s, i) => Z.toZhuyin(s.replace(/\d$/, t[i]))).join(' ');
    return {
      html: `<div class="stack">
        <div class="task-label">Tone hunt · which tones do you hear?</div>
        ${playBtn()}
        ${hzHtml(item, { size: 'hz-lg', vis: 'none', pinyin: false })}
        <div class="muted">${esc(item.en)}</div>
      </div>
      <div class="options">${options.map((t, n) => `<button class="option" data-opt="${n}"><span class="num">${n + 1}</span><span class="zy">${esc(withTones(t))}</span>${contourSvg(t)}</button>`).join('')}</div>
      <div class="reveal" hidden></div>`,
      wire() {
        let answered = false;
        let autoTimer = null;
        const play = () => Speech.speak(item.hz);
        $app.querySelector('[data-play]').onclick = play;
        play();
        const buttons = [...$app.querySelectorAll('[data-opt]')];
        const next = () => { clearTimeout(autoTimer); advance(card); };
        const choose = (n) => {
          if (answered) return;
          answered = true;
          const right = key(options[n]) === key(tones);
          buttons.forEach((b, k) => {
            b.disabled = true;
            if (key(options[k]) === key(tones)) b.classList.add('correct');
            else if (k === n) b.classList.add('wrong');
          });
          // Tone mistakes shouldn't wipe out a word you otherwise know.
          scoreAnswer(card, right ? 'good' : (strength(item) >= 1 ? 'hard' : 'miss'));
          const rev = $app.querySelector('.reveal');
          rev.hidden = false;
          rev.innerHTML = `<div class="stack">
            <div class="feedback ${right ? 'good' : 'bad'}">${right ? '耳朵很好！Good ear!' : 'Tones are tricky. Listen once more:'}</div>
            ${hzHtml(item, { size: 'hz-lg', vis: 'show' })}
            <div class="actions"><button class="btn" data-play2>🔊</button><button class="btn primary" data-next>Next → <span class="k">Enter</span></button></div>
          </div>`;
          rev.querySelector('[data-play2]').onclick = play;
          rev.querySelector('[data-next]').onclick = next;
          if (right) autoTimer = setTimeout(next, 1400);
          else play();
        };
        buttons.forEach((b, n) => (b.onclick = () => choose(n)));
        keyHandler = (e) => {
          if (e.key === ' ') { e.preventDefault(); play(); }
          if (/^[1-4]$/.test(e.key) && !answered) choose(Number(e.key) - 1);
          if (e.key === 'Enter' && answered) next();
        };
      },
    };
  }

  function rateRow() {
    return `<div class="rate-row">
      <button class="btn" data-rate="miss">😵 Not yet<span class="k">1</span></button>
      <button class="btn" data-rate="hard">🤏 Close<span class="k">2</span></button>
      <button class="btn primary" data-rate="good">🎯 Nailed it<span class="k">3</span></button>
    </div>`;
  }
  function wireRate(card) {
    let done = false;
    const rate = (r) => {
      if (done) return;
      done = true;
      scoreAnswer(card, r);
      setTimeout(() => advance(card), 250);
    };
    $app.querySelectorAll('[data-rate]').forEach((b) => (b.onclick = () => rate(b.dataset.rate)));
    return rate;
  }

  function cardSay(card) {
    const { item } = card;
    return {
      html: `<div class="stack">
        <div class="task-label">Say it · out loud (or whisper)</div>
        <div class="en" style="font-size:26px;font-weight:600">“${esc(item.en)}”</div>
        <p class="small muted">Say it in Chinese first, then check.</p>
        <div class="say-reveal" hidden></div>
        <div class="actions" data-reveal-row><button class="btn primary" data-reveal>Check → <span class="k">Enter</span></button></div>
      </div>`,
      wire() {
        let revealed = false;
        let rate = null;
        const play = () => Speech.speak(item.hz);
        const reveal = () => {
          if (revealed) return;
          revealed = true;
          $app.querySelector('[data-reveal-row]').remove();
          const box = $app.querySelector('.say-reveal');
          box.hidden = false;
          box.innerHTML = `${hzHtml(item, { size: 'hz-lg', vis: zhuyinVisibility(item) })}
            <div class="actions"><button class="btn" data-play>🔊 Again <span class="k">Space</span></button></div>
            ${recorderHtml()}
            <p class="small muted" style="margin-top:12px">How did you do?</p>${rateRow()}`;
          box.querySelector('[data-play]').onclick = play;
          wireRecorder(box, item);
          rate = wireRate(card);
          play();
        };
        $app.querySelector('[data-reveal]').onclick = reveal;
        keyHandler = (e) => {
          if (!revealed && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); reveal(); return; }
          if (e.key === ' ') { e.preventDefault(); play(); }
          if (revealed && rate && /^[1-3]$/.test(e.key)) rate(['miss', 'hard', 'good'][Number(e.key) - 1]);
        };
      },
    };
  }

  function cardShadow(card) {
    const { item } = card;
    return {
      html: `<div class="stack">
        <div class="task-label">Shadow · copy the sound</div>
        ${hzHtml(item, { size: 'hz-lg', vis: zhuyinVisibility(item) })}
        <div class="muted">${esc(item.en)}</div>
        <div class="actions">
          <button class="btn" data-play>🔊 Play <span class="k">Space</span></button>
          <button class="btn" data-slow>🐢 Slow</button>
        </div>
        <p class="small muted">Listen, then say it at the same time as the audio or straight after. Record yourself to see your tones.</p>
        ${recorderHtml()}
        ${rateRow()}
      </div>`,
      wire() {
        const play = () => Speech.speak(item.hz);
        $app.querySelector('[data-play]').onclick = play;
        $app.querySelector('[data-slow]').onclick = () => Speech.speak(item.hz, 0.55);
        wireRecorder($app, item);
        const rate = wireRate(card);
        play();
        keyHandler = (e) => {
          if (e.key === ' ') { e.preventDefault(); play(); }
          if (/^[1-3]$/.test(e.key)) rate(['miss', 'hard', 'good'][Number(e.key) - 1]);
        };
      },
    };
  }

  function renderDone() {
    Speech.stop();
    blip('done');
    const s = session;
    const pct = s.answered ? Math.round((s.correct / s.answered) * 100) : 0;
    const emoji = pct >= 90 ? '🏆' : pct >= 70 ? '🎉' : '🌱';
    const line = pct >= 90 ? '太厲害了！' : pct >= 70 ? '很好！' : '每一次都有進步！';
    const lineEn = pct >= 90 ? 'Amazing!' : pct >= 70 ? 'Nice work!' : 'Every round counts.';
    const fact = pick([
      '💡 Most of remembering happens when you come back later. A tiny burst tomorrow is worth more than a long one today.',
      '💡 In Taiwan, 吃飽了沒？ ("have you eaten?") is often just a friendly hello.',
      '💡 Taiwan uses Zhuyin (ㄅㄆㄇㄈ) to teach kids to read. You\'re learning the same way they did.',
      '💡 Shy about speaking? Shadowing along with audio builds the muscle memory first, so real conversations feel less scary.',
      '💡 Ghost Month (鬼月) tip: don\'t whistle at night, and don\'t say 鬼 too loudly. Call them 好兄弟 instead.',
      '💡 Taiwan Mandarin usually skips the big rise at the end of the 3rd tone. Think "low and creaky".',
    ]);
    $app.innerHTML = `<section class="card done stack">
      <div class="big-emoji">${emoji}</div>
      <h1 lang="zh-TW">${line}</h1>
      <p class="muted">${lineEn}</p>
      <div class="stats">
        <div class="stat"><b>${s.correct}/${s.answered}</b><span>correct</span></div>
        <div class="stat"><b>${s.best}</b><span>best combo</span></div>
        <div class="stat"><b>${s.met}</b><span>new words</span></div>
      </div>
      <p class="note" style="text-align:left">${fact}</p>
      <div class="actions">
        <button class="btn primary big" data-again>One more burst <span class="k">Enter</span></button>
        <button class="btn" data-home>Done for now <span class="k">Esc</span></button>
      </div>
    </section>`;
    session = null;
    document.body.classList.remove('focus');
    $app.querySelector('[data-again]').onclick = () => startSession(10);
    $app.querySelector('[data-home]').onclick = () => nav('home');
    keyHandler = (e) => {
      if (e.key === 'Enter') startSession(10);
      if (e.key === 'Escape') nav('home');
    };
  }

  // ---------------------------------------------------------------------------
  // Scenes
  // ---------------------------------------------------------------------------

  function renderScenes() {
    $app.innerHTML = `<div class="stack">
      <div><h1>🎭 Scenes</h1><p class="muted">Rehearse real conversations where nobody's watching. The app plays the other person. Your lines show in English - say them in Chinese, then check.</p></div>
      <div class="scene-list">${SCENES.map((sc) => `<button class="scene-tile" data-scene="${sc.id}">
        <div class="icon">${sc.icon}</div>
        <h3>${esc(sc.title)}</h3>
        <div class="zh">${sc.zh}</div>
        <p class="small muted">${state.scenes[sc.id] ? `Played ${state.scenes[sc.id]}×` : 'Not tried yet'}</p>
      </button>`).join('')}</div>
    </div>`;
    $app.querySelectorAll('[data-scene]').forEach((b) => (b.onclick = () => nav('scene', { id: b.dataset.scene, step: 0, swap: false, revealed: false })));
  }

  function renderScene() {
    const sc = SCENES.find((s) => s.id === current.id);
    if (!sc) return nav('scenes');
    const youRole = current.swap ? 'npc' : 'you';
    const lines = sc.lines;
    const step = current.step;
    const finished = step >= lines.length;

    const bubble = (ln) => {
      const mine = ln.who === youRole;
      return `<div class="bubble ${mine ? 'you' : 'npc'}">
        <div class="who">${mine ? 'You' : 'Them'}</div>
        ${hzHtml(ln, { size: '', vis: S().zhuyin === 'tap' ? 'tap' : 'show' })}
        ${S().sceneEnglish || mine ? `<div class="en">${esc(ln.en)}</div>` : ''}
      </div>`;
    };

    let past = lines.slice(0, step).map(bubble).join('');
    let currentHtml = '';
    let isMine = false;
    if (!finished) {
      const ln = lines[step];
      isMine = ln.who === youRole;
      if (!isMine) {
        past += bubble(ln);
        currentHtml = `<div class="actions"><button class="btn" data-replay>🔊 Replay <span class="k">Space</span></button><button class="btn primary" data-next>Next → <span class="k">Enter</span></button></div>`;
      } else if (!current.revealed) {
        currentHtml = `<div class="your-turn stack">
          <div class="task-label">Your turn · say it in Chinese</div>
          <div class="say">“${esc(ln.en)}”</div>
          <div class="hint" hidden><p class="small muted">Hint:</p><div class="zy" style="font-family:var(--font-zh);font-size:20px">${esc(zhuyinLine(syllables(ln)))}</div></div>
          <div class="actions">
            <button class="btn" data-hint>💡 Zhuyin hint <span class="k">H</span></button>
            <button class="btn primary" data-reveal>Check → <span class="k">Enter</span></button>
          </div>
        </div>`;
      } else {
        past += bubble(ln);
        currentHtml = `<div class="your-turn">
          <div class="actions" style="margin-top:0"><button class="btn" data-replay>🔊 Hear it <span class="k">Space</span></button><button class="btn primary" data-next>Next → <span class="k">Enter</span></button></div>
          ${recorderHtml()}
        </div>`;
      }
    } else {
      currentHtml = `<div class="card done stack">
        <div class="big-emoji">🎬</div>
        <h2>Scene complete! 完成了！</h2>
        <p class="muted">${current.swap ? 'You played both sides now.' : 'Try swapping roles to practice the other side.'}</p>
        <div class="actions">
          <button class="btn primary" data-again>${current.swap ? 'Play again' : '🔄 Swap roles'} <span class="k">Enter</span></button>
          <button class="btn" data-back>All scenes</button>
        </div>
      </div>`;
    }

    $app.innerHTML = `<div class="stack">
      <div class="row" style="justify-content:space-between">
        <button class="btn ghost" data-back>← Scenes</button>
        <span class="muted small">${Math.min(step + 1, lines.length)} / ${lines.length}${current.swap ? ' · roles swapped' : ''}</span>
      </div>
      <div><h2>${sc.icon} ${esc(sc.title)} <span class="muted" style="font-family:var(--font-zh);font-weight:400">${sc.zh}</span></h2>
      <p class="small muted">${esc(current.swap ? 'Roles swapped: now you play the other person.' : sc.intro)}</p></div>
      <div class="chat">${past}</div>
      ${currentHtml}
    </div>`;

    const go = (patch) => { Object.assign(current, patch); render(); scrollEnd(); };
    const scrollEnd = () => requestAnimationFrame(() => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }));
    $app.querySelectorAll('[data-back]').forEach((b) => (b.onclick = () => nav('scenes')));
    const ln = lines[step];
    const play = () => ln && Speech.speak(ln.hz);
    const next = () => go({ step: step + 1, revealed: false });
    const reveal = () => { logActivity(); go({ revealed: true }); };
    const again = () => go({ step: 0, revealed: false, swap: !current.swap });

    if (finished) {
      if (!current.counted) { state.scenes[sc.id] = (state.scenes[sc.id] || 0) + 1; save(); current.counted = true; blip('done'); }
      $app.querySelector('[data-again]').onclick = () => { current.counted = false; again(); };
      keyHandler = (e) => { if (e.key === 'Enter') { current.counted = false; again(); } };
      return;
    }
    const q = (s) => $app.querySelector(s);
    if (q('[data-replay]')) q('[data-replay]').onclick = play;
    if (q('[data-next]')) q('[data-next]').onclick = next;
    if (q('[data-reveal]')) q('[data-reveal]').onclick = reveal;
    const hint = () => { const h = q('.hint'); if (h) h.hidden = false; };
    if (q('[data-hint]')) q('[data-hint]').onclick = hint;
    if (q('.recorder')) wireRecorder($app, ln);
    if (!isMine || current.revealed) play();
    keyHandler = (e) => {
      if (e.key === ' ') { e.preventDefault(); if (!isMine || current.revealed) play(); }
      if (e.key === 'Enter') (isMine && !current.revealed ? reveal : next)();
      if (e.key === 'h' || e.key === 'H') hint();
      if (e.key === 'r' || e.key === 'R') { const rec = q('.recorder'); if (rec && rec.toggleRecord) rec.toggleRecord(); }
      if (e.key === 'Escape') nav('scenes');
    };
  }

  // ---------------------------------------------------------------------------
  // Browse
  // ---------------------------------------------------------------------------

  function renderBrowse() {
    const deck = current.deck || 'all';
    const q = (current.q || '').trim().toLowerCase();
    const list = ITEMS.filter((i) => (deck === 'all' || i.deck === deck) && (!q || i.hz.includes(q) || i.en.toLowerCase().includes(q) || syllables(i).map(Z.toPinyin).join(' ').includes(q) || i.py.includes(q)));
    $app.innerHTML = `<div class="stack">
      <h1>📖 Words</h1>
      <div class="chips">
        <button class="chip" data-d="all" aria-pressed="${deck === 'all'}">All</button>
        ${DECKS.map((d) => `<button class="chip" data-d="${d.id}" aria-pressed="${deck === d.id}">${d.icon} ${esc(d.name)}</button>`).join('')}
      </div>
      <input class="search" type="search" placeholder="Search English, characters or pinyin…" value="${esc(current.q || '')}">
      <ul class="word-list">${list.map((i) => {
        const s = strength(i);
        const w = s < 0 ? 0 : Math.min(100, Math.round((Math.log2(1 + Math.max(0, s)) / Math.log2(31)) * 100));
        return `<li>
          <button class="icon-btn" data-say="${esc(i.id)}" aria-label="Play">🔊</button>
          <div class="meta">${hzHtml(i, { size: '', vis: 'show' })}<div class="small">${esc(i.en)}</div>${i.note ? `<div class="small muted">${esc(i.note)}</div>` : ''}</div>
          <div class="meter" title="${s < 0 ? 'Not met yet' : isFading(i) ? 'Due for a refresh' : 'Strength'}"><i style="width:${w}%"></i></div>
        </li>`;
      }).join('') || '<li class="muted">Nothing matches.</li>'}</ul>
    </div>`;
    $app.querySelectorAll('[data-d]').forEach((b) => (b.onclick = () => { current.deck = b.dataset.d; render(); }));
    $app.querySelectorAll('[data-say]').forEach((b) => (b.onclick = () => Speech.speak(ITEM_BY_ID.get(b.dataset.say).hz)));
    const input = $app.querySelector('.search');
    input.oninput = () => {
      current.q = input.value;
      const pos = input.selectionStart;
      render();
      const again = $app.querySelector('.search');
      again.focus();
      again.setSelectionRange(pos, pos);
    };
  }

  // ---------------------------------------------------------------------------
  // Settings
  // ---------------------------------------------------------------------------

  function renderSettings() {
    const zh = Speech.zhVoices();
    const v = Speech.voice();
    $app.innerHTML = `<div class="stack">
      <h1>⚙️ Settings</h1>
      <section class="card">
        <div class="setting"><div><label for="zy">Zhuyin</label><div class="desc">"Fade out" hides it on words you know well. Tap characters to peek.</div></div>
          <select id="zy"><option value="auto">Fade out as I learn</option><option value="always">Always show</option><option value="tap">Hidden (tap to show)</option></select></div>
        <div class="setting"><div><label for="py">Show pinyin too</label><div class="desc">Off by default, to keep your eyes on Zhuyin.</div></div><input type="checkbox" id="py"></div>
        <div class="setting"><div><label for="se">English under the other person's lines in scenes</label></div><input type="checkbox" id="se"></div>
        <div class="setting"><div><label for="sfx">Sound effects</label></div><input type="checkbox" id="sfx"></div>
        <div class="setting"><div><label for="theme">Theme</label></div>
          <select id="theme"><option value="system">Match system</option><option value="light">Light</option><option value="dark">Dark</option></select></div>
      </section>
      <section class="card">
        <h2>Voice</h2>
        <div class="setting"><div><label for="voice">Chinese voice</label><div class="desc">${v ? (Speech.isTaiwan(v) ? '✅ Taiwan voice in use.' : '⚠️ Not a Taiwan voice - see Help to add one.') : 'No Chinese voice found - see Help.'}</div></div>
          <select id="voice">${zh.length ? zh.map((x) => `<option value="${esc(x.voiceURI)}"${v && x.voiceURI === v.voiceURI ? ' selected' : ''}>${esc(x.name)} (${esc(x.lang)})</option>`).join('') : '<option>None available</option>'}</select></div>
        <div class="setting"><div><label for="rate">Speed</label><div class="desc" id="rateval"></div></div><input type="range" id="rate" min="0.5" max="1.2" step="0.05"></div>
        <div class="actions"><button class="btn" data-test>🔊 Test: 我要一杯珍珠奶茶</button></div>
      </section>
      <section class="card stack">
        <h2>Your progress</h2>
        <p class="small muted">Progress is saved in this browser only. Export a backup now and then, especially before clearing browser data.</p>
        <div class="row">
          <button class="btn" data-export>⬇ Export backup</button>
          <label class="btn">⬆ Import backup<input type="file" accept="application/json,.json" hidden data-import></label>
          <button class="btn ghost" data-reset style="color:var(--bad)">Reset everything</button>
        </div>
        <p class="small rs-msg"></p>
      </section>
    </div>`;
    const el = (id) => document.getElementById(id);
    el('zy').value = S().zhuyin;
    el('py').checked = S().pinyin;
    el('se').checked = S().sceneEnglish;
    el('sfx').checked = S().sfx;
    el('theme').value = S().theme;
    el('rate').value = S().rate;
    const rateText = () => (el('rateval').textContent = `${Math.round(S().rate * 100)}%`);
    rateText();
    const set = (k, val) => { S()[k] = val; save(); };
    el('zy').onchange = (e) => set('zhuyin', e.target.value);
    el('py').onchange = (e) => set('pinyin', e.target.checked);
    el('se').onchange = (e) => set('sceneEnglish', e.target.checked);
    el('sfx').onchange = (e) => set('sfx', e.target.checked);
    el('theme').onchange = (e) => { set('theme', e.target.value); applyTheme(); };
    el('voice').onchange = (e) => { set('voiceURI', e.target.value); render(); };
    el('rate').oninput = (e) => { set('rate', Number(e.target.value)); rateText(); };
    $app.querySelector('[data-test]').onclick = () => Speech.speak('我要一杯珍珠奶茶');
    const msg = $app.querySelector('.rs-msg');
    $app.querySelector('[data-export]').onclick = () => {
      const blob = new Blob([JSON.stringify(state, null, 1)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `manman-backup-${dayKey()}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    };
    $app.querySelector('[data-import]').onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        const data = JSON.parse(await file.text());
        if (!data || typeof data !== 'object' || !data.items) throw new Error('not a backup');
        state = normalize(data);
        save();
        applyTheme();
        render();
        $app.querySelector('.rs-msg').textContent = '✅ Backup restored.';
      } catch (err) {
        msg.textContent = "That file doesn't look like a 慢慢來 backup.";
      }
    };
    $app.querySelector('[data-reset]').onclick = () => {
      if (confirm('Erase all progress and settings? This cannot be undone. (Export a backup first if unsure.)')) {
        state = normalize(null);
        save();
        applyTheme();
        render();
      }
    };
  }

  function applyTheme() {
    const t = S().theme;
    if (t === 'system') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', t);
  }

  // ---------------------------------------------------------------------------
  // Help
  // ---------------------------------------------------------------------------

  function renderHelp() {
    const v = Speech.voice();
    $app.innerHTML = `<div class="card help">
      <h1>❔ Help</h1>
      <p class="muted" style="margin-top:8px">Current voice: ${v ? `<b>${esc(v.name)}</b> (${esc(v.lang)})${Speech.isTaiwan(v) ? ' ✅' : ' - not a Taiwan voice'}` : '<b>none found</b>'}</p>

      <h2>How it works</h2>
      <ul>
        <li><b>Bursts</b> are 5-20 quick cards. Words you're about to forget come first, then a few new ones. The app schedules everything, so you just press Start.</li>
        <li>Activities rotate (listen, read, pick, tone hunt, say it, shadow) so it doesn't get repetitive.</li>
        <li><b>Zhuyin fades out</b> on words you know well. Tap the characters to peek any time.</li>
        <li><b>Scenes</b> let you rehearse conversations privately: the app plays the other person.</li>
        <li><b>Missed a few days?</b> Nothing resets. The next burst focuses on refreshing what's fading.</li>
      </ul>

      <h2>Keyboard</h2>
      <ul>
        <li><kbd>Enter</kbd> start / check / next</li>
        <li><kbd>Space</kbd> replay audio</li>
        <li><kbd>1</kbd>-<kbd>4</kbd> choose an answer (or rate yourself 1-3)</li>
        <li><kbd>R</kbd> start/stop recording · <kbd>H</kbd> hint in scenes · <kbd>Esc</kbd> stop</li>
      </ul>

      <h2>Getting a Taiwan voice</h2>
      <p>Audio uses voices built into your computer, so quality depends on what's installed.</p>
      <ul>
        <li><b>Windows 10/11:</b> Settings → Time &amp; language → Language &amp; region → Add a language → <i>Chinese (Traditional, Taiwan)</i>. Make sure <i>Text-to-speech</i> is ticked. Restart the browser. Firefox will then list "Microsoft Hanhan" (and sometimes Yating/Zhiwei).</li>
        <li><b>macOS:</b> System Settings → Accessibility → Spoken Content → System voice → Manage Voices → Chinese (Taiwan) → download <i>Mei-Jia</i>. Restart the browser.</li>
        <li><b>Linux:</b> Firefox uses speech-dispatcher, usually with eSpeak, which sounds robotic and is not Taiwan-accented. It works for rough practice, but a Windows or Mac voice is much better.</li>
      </ul>
      <p>Then pick the voice in Settings if it isn't chosen automatically.</p>

      <h2>About the tone graph</h2>
      <p>When you record yourself, the app draws your pitch (blue) over the target tone shapes (orange). It's a rough guide. Voices differ in height, so aim to match the <i>shapes</i>: flat, rising, low dip, falling. Taiwan Mandarin usually says the 3rd tone low without the big rise at the end.</p>

      <h2>Privacy</h2>
      <p>Everything runs in your browser. Progress is saved in this browser only, and recordings are never saved or uploaded. The mic is only on while the record button is red.</p>

      <h2>Notes on the content</h2>
      <ul>
        <li>Readings follow Taiwan standard (e.g. 血 xiě, 垃圾 lè sè).</li>
        <li>不 and 一 show their spoken tone changes (不要 ㄅㄨˊ ㄧㄠˋ).</li>
        <li>Computer voices sometimes use mainland readings. When the Zhuyin and the audio disagree, trust the Zhuyin.</li>
      </ul>
    </div>`;
  }

  // ---------------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------------

  document.querySelectorAll('[data-nav]').forEach((b) => (b.onclick = () => {
    if (current.name === 'session' && session && session.answered && !confirm('Leave this burst? Progress so far is saved.')) return;
    nav(b.dataset.nav);
  }));
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA')) return;
    // Let Enter/Space activate a focused button normally, except during bursts
    // where the shortcuts drive everything.
    if (t && t.tagName === 'BUTTON' && (e.key === 'Enter' || e.key === ' ') && current.name !== 'session' && current.name !== 'scene') return;
    if (keyHandler) {
      if ((e.key === 'Enter' || e.key === ' ') && t && t.tagName === 'BUTTON') e.preventDefault();
      keyHandler(e);
    }
  });

  applyTheme();
  Speech.init();
  nav('home');
})();
