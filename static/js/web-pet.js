/**
 * Tamaweb-inspired lightweight mascot.
 *
 * Tamaweb has a rich pet roster and growth model, but its assets/code are
 * CC BY-NC-SA 4.0. This local implementation keeps the same spirit without
 * copying Tamaweb assets: random creature, idle growth, wandering, mouse
 * curiosity, hover avoidance, and occasional calls/greetings.
 */

'use strict';

(function () {
  const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const PET_SETTINGS_KEY = 'rf-web-pet-settings';

  const PETS = [
    { id: 'cat', name: 'Mochi Cat', call: ['meow', 'mrrp', 'hello'], body: '#d99a62', belly: '#f3c994', accent: '#8f5d38', ears: 'point', tail: 'curl', gait: 'walk' },
    { id: 'dog', name: 'Bento Dog', call: ['woof', 'arf', 'hi friend'], body: '#b77b44', belly: '#f1c18a', accent: '#5f3c26', ears: 'flop', tail: 'wag', gait: 'trot' },
    { id: 'lion', name: 'Tiny Lion', call: ['rawr', 'grr', 'brave day'], body: '#c99535', belly: '#f2c86d', accent: '#74451e', ears: 'round', tail: 'tuft', gait: 'prowl', mane: true },
    { id: 'snake', name: 'Noodle Snake', call: ['hiss', 'sssup', 'soft steps'], body: '#5da567', belly: '#a6db8f', accent: '#2e7144', ears: 'none', tail: 'none', gait: 'slither' },
    { id: 'kangaroo', name: 'Pocket Roo', call: ['boing', 'gday', 'hop hop'], body: '#b9824a', belly: '#e7b77c', accent: '#6d4327', ears: 'long', tail: 'balance', gait: 'hop', pouch: true },
    { id: 'rabbit', name: 'Moon Rabbit', call: ['squeak', 'hop?', 'good luck'], body: '#d8d8d2', belly: '#ffffff', accent: '#9a9a96', ears: 'long', tail: 'puff', gait: 'hop' },
    { id: 'fox', name: 'Spark Fox', call: ['yip', 'kon', 'quick quick'], body: '#d66f31', belly: '#ffe0b3', accent: '#70351e', ears: 'point', tail: 'fluffy', gait: 'dash' },
    { id: 'panda', name: 'Bao Panda', call: ['nom', 'hey', 'snack?'], body: '#f2f0e8', belly: '#ffffff', accent: '#2d3137', ears: 'round', tail: 'puff', gait: 'waddle', patches: true },
    { id: 'penguin', name: 'Pixel Penguin', call: ['peep', 'waddle', 'cool'], body: '#263746', belly: '#f7f4df', accent: '#f0a542', ears: 'none', tail: 'none', gait: 'waddle', beak: true },
    { id: 'turtle', name: 'Shell Turtle', call: ['hmm', 'slowly', 'steady'], body: '#5f9b65', belly: '#c9b36b', accent: '#3d6845', ears: 'none', tail: 'short', gait: 'crawl', shell: true },
    { id: 'dragon', name: 'Pocket Dragon', call: ['puff', 'spark', 'tiny roar'], body: '#7b6ee6', belly: '#c6baff', accent: '#4b3aa3', ears: 'horn', tail: 'spike', gait: 'fly', wings: true },
    { id: 'bird', name: 'Cloud Bird', call: ['chirp', 'tweet', 'hello'], body: '#70aee8', belly: '#d9f0ff', accent: '#315d92', ears: 'crest', tail: 'feather', gait: 'flutter', beak: true, wings: true },
    { id: 'fly', name: 'Tiny Fly', call: ['bzz', 'zip', 'hello?'], body: '#4f5d67', belly: '#9aa8ad', accent: '#c8f0ff', ears: 'antenna', tail: 'short', gait: 'fly', wings: true, insect: true },
    { id: 'mosquito', name: 'Mini Mosquito', call: ['zzzz', 'sip?', 'tiny hello'], body: '#59646d', belly: '#c9b3a0', accent: '#d8f5ff', ears: 'antenna', tail: 'needle', gait: 'fly', wings: true, insect: true, proboscis: true },
    { id: 'dragonfly', name: 'Glass Dragonfly', call: ['whirr', 'glide', 'sparkle'], body: '#3f9f95', belly: '#9ee6d8', accent: '#b7f3ff', ears: 'antenna', tail: 'long', gait: 'fly', wings: true, insect: true },
  ];

  const STAGES = [
    { id: 'hatchling', label: 'Hatchling', at: 0, scale: 0.62, roundness: 1.12 },
    { id: 'junior', label: 'Junior', at: 7 * 60 * 1000, scale: 0.86, roundness: 1.0 },
    { id: 'adult', label: 'Adult', at: 24 * 60 * 1000, scale: 1.08, roundness: 0.92 },
  ];

  let petDef = PETS[Math.floor(Math.random() * PETS.length)];
  let bornAt = Date.now();
  let el;
  let animal;
  let bubble;
  let pos = { x: window.innerWidth - 160, y: window.innerHeight - 112 };
  let vel = { x: 0, y: 0 };
  let target = { ...pos };
  let mouse = { x: window.innerWidth / 2, y: window.innerHeight / 2, active: false };
  let mode = 'settle';
  let mood = 'happy';
  let stageId = '';
  let morphBucket = -1;
  let frame = 0;
  let facing = 1;
  let last = performance.now();
  let rafId = 0;
  let active = false;
  let modeUntil = 0;
  let nextSpeakAt = performance.now() + random(3500, 9000);
  let nextMoodAt = performance.now() + random(7000, 16000);
  let audioReady = false;
  let audioContext = null;

  function random(min, max) {
    return min + Math.random() * (max - min);
  }

  function readSettings() {
    try {
      const saved = JSON.parse(localStorage.getItem(PET_SETTINGS_KEY) || '{}');
      return {
        enabled: saved.enabled !== false,
        species: saved.species || 'random',
      };
    } catch {
      return { enabled: true, species: 'random' };
    }
  }

  function choosePet(settings = readSettings()) {
    const selected = PETS.find((item) => item.id === settings.species);
    return selected || PETS[Math.floor(Math.random() * PETS.length)];
  }

  function resetState() {
    bornAt = Date.now();
    pos = { x: window.innerWidth - 180, y: window.innerHeight - 126 };
    vel = { x: 0, y: 0 };
    target = { ...pos };
    mode = 'settle';
    mood = 'happy';
    stageId = '';
    morphBucket = -1;
    frame = 0;
    facing = 1;
    last = performance.now();
    modeUntil = 0;
    nextSpeakAt = performance.now() + random(4500, 11000);
    nextMoodAt = performance.now() + random(8000, 18000);
  }

  function stage() {
    const age = Date.now() - bornAt;
    return STAGES.reduce((picked, item) => age >= item.at ? item : picked, STAGES[0]);
  }

  function growth() {
    const age = Date.now() - bornAt;
    const lastStage = STAGES[STAGES.length - 1];
    let from = STAGES[0];
    let to = lastStage;

    for (let i = 0; i < STAGES.length - 1; i += 1) {
      if (age >= STAGES[i].at && age < STAGES[i + 1].at) {
        from = STAGES[i];
        to = STAGES[i + 1];
        break;
      }
    }

    if (age >= lastStage.at) {
      return {
        stage: lastStage,
        scale: lastStage.scale,
        roundness: lastStage.roundness,
        progress: 1,
      };
    }

    const span = Math.max(1, to.at - from.at);
    const raw = Math.max(0, Math.min(1, (age - from.at) / span));
    const eased = raw * raw * (3 - 2 * raw);
    return {
      stage: from,
      scale: from.scale + (to.scale - from.scale) * eased,
      roundness: from.roundness + (to.roundness - from.roundness) * eased,
      progress: eased,
    };
  }

  function init() {
    active = true;
    el = document.createElement('div');
    el.id = 'rf-web-pet';
    el.dataset.pet = petDef.id;
    el.dataset.gait = petDef.gait;
    el.dataset.mode = mode;
    el.dataset.mood = mood;
    el.setAttribute('aria-label', petDef.name);
    el.title = `${petDef.name} - click to greet`;
    el.innerHTML = `
      <div class="rf-pet-speech" role="status"></div>
      <div class="rf-pet-shadow"></div>
      <div class="rf-pet-stage"></div>
    `;
    document.body.appendChild(el);
    animal = el.querySelector('.rf-pet-stage');
    bubble = el.querySelector('.rf-pet-speech');

    window.addEventListener('mousemove', onMouseMove, { passive: true });
    window.addEventListener('resize', clamp);
    window.addEventListener('pointerdown', unlockAudio, { once: true, passive: true });
    el.addEventListener('mouseenter', flee);
    el.addEventListener('click', greet);

    chooseTarget('wander');
    rafId = requestAnimationFrame(tick);
  }

  function destroy() {
    active = false;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = 0;
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('resize', clamp);
    window.removeEventListener('pointerdown', unlockAudio);
    if (el) {
      el.removeEventListener('mouseenter', flee);
      el.removeEventListener('click', greet);
      el.remove();
    }
    el = null;
    animal = null;
    bubble = null;
  }

  function restartFromSettings() {
    destroy();
    if (REDUCED_MOTION) return;
    const settings = readSettings();
    if (!settings.enabled) return;
    petDef = choosePet(settings);
    resetState();
    init();
  }

  function unlockAudio() {
    try {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      audioReady = true;
    } catch {
      audioReady = false;
    }
  }

  function chirp() {
    if (!audioReady || !audioContext) return;
    const now = audioContext.currentTime;
    const osc = audioContext.createOscillator();
    const gain = audioContext.createGain();
    const base = petDef.gait === 'slither' ? 240 : petDef.gait === 'fly' || petDef.gait === 'flutter' ? 720 : 420;
    osc.frequency.setValueAtTime(base + random(-80, 120), now);
    osc.frequency.exponentialRampToValueAtTime(base * random(1.08, 1.45), now + 0.11);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.035, now + 0.025);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);
    osc.type = petDef.id === 'snake' ? 'triangle' : 'sine';
    osc.connect(gain).connect(audioContext.destination);
    osc.start(now);
    osc.stop(now + 0.2);
  }

  function onMouseMove(event) {
    mouse = { x: event.clientX, y: event.clientY, active: true };
  }

  function say(text) {
    bubble.textContent = text;
    bubble.classList.add('visible');
    window.clearTimeout(say.timer);
    say.timer = window.setTimeout(() => bubble.classList.remove('visible'), 2200);
  }

  function greet() {
    setMood('excited', 2600);
    setMode('greet', 1900);
    say(`hi, I'm ${petDef.name}`);
    chirp();
  }

  function setMood(next, duration = 0) {
    mood = next;
    el.dataset.mood = mood;
    if (duration) {
      window.clearTimeout(setMood.timer);
      setMood.timer = window.setTimeout(() => {
        mood = 'happy';
        el.dataset.mood = mood;
      }, duration);
    }
  }

  function setMode(next, duration = 0) {
    mode = next;
    el.dataset.mode = mode;
    modeUntil = duration ? performance.now() + duration : 0;
  }

  function chooseTarget(nextMode = 'wander') {
    const flying = petDef.gait === 'fly' || petDef.gait === 'flutter';
    const bandBottom = flying ? Math.max(170, window.innerHeight - 118) : window.innerHeight - 68;
    const bandTop = flying ? 110 : Math.max(120, window.innerHeight - 190);
    target = {
      x: random(92, Math.max(116, window.innerWidth - 104)),
      y: random(bandTop, bandBottom),
    };
    setMode(nextMode, random(2600, 7200));
  }

  function flee() {
    const dx = pos.x - mouse.x || random(-1, 1);
    const dy = pos.y - mouse.y || random(-0.8, 0.3);
    const len = Math.hypot(dx, dy) || 1;
    target = {
      x: pos.x + (dx / len) * random(150, 260),
      y: pos.y + (dy / len) * random(60, 130),
    };
    clampTarget();
    setMode('flee', 1900);
    setMood('excited', 1800);
    say(petDef.id === 'snake' ? 'ss!' : 'eep!');
    chirp();
  }

  function clampTarget() {
    const flying = petDef.gait === 'fly' || petDef.gait === 'flutter';
    target.x = Math.max(78, Math.min(window.innerWidth - 86, target.x));
    target.y = Math.max(flying ? 96 : 120, Math.min(window.innerHeight - 66, target.y));
  }

  function clamp() {
    const flying = petDef.gait === 'fly' || petDef.gait === 'flutter';
    pos.x = Math.max(78, Math.min(window.innerWidth - 86, pos.x));
    pos.y = Math.max(flying ? 96 : 120, Math.min(window.innerHeight - 66, pos.y));
    clampTarget();
  }

  function behavior(now) {
    if (modeUntil && now < modeUntil) return;

    if (now > nextMoodAt) {
      const moods = ['happy', 'sleepy', 'sad', 'excited'];
      setMood(moods[Math.floor(Math.random() * moods.length)], random(2600, 5600));
      nextMoodAt = now + random(11000, 26000);
    }

    const distanceToMouse = Math.hypot(mouse.x - pos.x, mouse.y - pos.y);
    if (mouse.active && distanceToMouse < 460 && Math.random() < 0.012) {
      target = {
        x: mouse.x + random(-52, 64),
        y: mouse.y + random(petDef.gait === 'fly' ? -34 : 30, petDef.gait === 'fly' ? 48 : 78),
      };
      clampTarget();
      setMode('curious', random(1800, 3600));
      setMood('happy', 2400);
      return;
    }

    const distanceToTarget = Math.hypot(target.x - pos.x, target.y - pos.y);
    if (distanceToTarget < 18 || Math.random() < 0.01) {
      if (Math.random() < 0.33) setMode('idle', random(1600, 3600));
      else chooseTarget(Math.random() < 0.28 ? 'run' : 'wander');
    }

    if (now > nextSpeakAt) {
      const line = petDef.call[Math.floor(Math.random() * petDef.call.length)];
      if (Math.random() < 0.55) setMood('excited', 2200);
      say(line);
      chirp();
      nextSpeakAt = now + random(9000, 22000);
    }
  }

  function tick(now) {
    if (!active || !el) return;
    const dt = Math.min(42, now - last) / 16.67;
    last = now;

    const growthState = growth();
    const nextMorphBucket = Math.round(growthState.progress * 80);
    const stageChanged = growthState.stage.id !== stageId;
    if (growthState.stage.id !== stageId || nextMorphBucket !== morphBucket) {
      stageId = growthState.stage.id;
      morphBucket = nextMorphBucket;
      el.dataset.growth = stageId;
      render(growthState);
      if (stageChanged && stageId !== 'hatchling') say(`${growthState.stage.label}!`);
    }

    behavior(now);
    move(dt);
    paint(now, growthState);
    rafId = requestAnimationFrame(tick);
  }

  function move(dt) {
    const idle = mode === 'idle' || mode === 'greet';
    const speedMap = {
      settle: 0.18,
      idle: 0.02,
      greet: 0.025,
      wander: petDef.gait === 'fly' ? 0.34 : 0.26,
      curious: petDef.gait === 'fly' ? 0.42 : 0.34,
      run: petDef.gait === 'fly' ? 0.58 : 0.48,
      flee: petDef.gait === 'fly' ? 0.76 : 0.66,
    };
    const speed = speedMap[mode] || 0.5;
    const dx = target.x - pos.x;
    const dy = target.y - pos.y;
    const len = Math.hypot(dx, dy) || 1;

    if (!idle) {
      vel.x += (dx / len) * speed * dt;
      vel.y += (dy / len) * speed * dt;
    }
    vel.x *= idle ? 0.78 : 0.86;
    vel.y *= idle ? 0.78 : 0.86;

    pos.x += vel.x * dt;
    pos.y += vel.y * dt;
    clamp();
  }

  function paint(now, growthState) {
    const speed = Math.hypot(vel.x, vel.y);
    const moving = speed > 0.2;
    if (moving && Math.abs(vel.x) > 0.38) {
      facing = vel.x < 0 ? -1 : 1;
    }
    const cycle = now / gaitCycle();
    frame = moving ? Math.sin(cycle) : Math.sin(now / 600) * 0.12;
    const bob = moving ? gaitBob(frame) : Math.sin(now / 900) * 1.2;
    const tilt = Math.max(-4, Math.min(4, vel.x * 0.55));

    el.style.setProperty('--pet-scale', growthState.scale.toFixed(4));
    el.style.setProperty('--pet-growth', growthState.progress.toFixed(4));
    el.style.setProperty('--pet-frame', frame.toFixed(4));
    el.style.setProperty('--pet-speed', Math.min(1, speed / 7).toFixed(4));
    el.style.transform = `translate3d(${pos.x}px, ${pos.y - bob}px, 0) scaleX(${facing}) rotate(${tilt}deg)`;
    el.dataset.moving = moving ? 'true' : 'false';
  }

  function gaitCycle() {
    if (petDef.gait === 'fly') return 175;
    if (petDef.gait === 'flutter') return 155;
    if (petDef.gait === 'slither') return 115;
    if (petDef.gait === 'hop') return 92;
    if (petDef.gait === 'waddle') return 140;
    if (petDef.gait === 'dash') return 76;
    return 104;
  }

  function gaitBob(value) {
    if (petDef.gait === 'fly') return Math.sin(performance.now() / 180) * 5 + Math.abs(value) * 1.5;
    if (petDef.gait === 'flutter') return Math.sin(performance.now() / 210) * 4 + Math.abs(value) * 2;
    if (petDef.gait === 'slither') return Math.sin(performance.now() / 90) * 1.8;
    if (petDef.gait === 'hop') return Math.abs(value) * 9;
    if (petDef.gait === 'waddle') return Math.abs(value) * 4;
    return Math.abs(value) * 3.5;
  }

  function render(growthState) {
    animal.innerHTML = petDef.gait === 'slither'
      ? snakeSvg(growthState)
      : creatureSvg(growthState);
  }

  function creatureSvg(growthState) {
    const currentStage = growthState.stage;
    const adult = currentStage.id === 'adult';
    const baby = currentStage.id === 'hatchling';
    const bodyRx = 29 + 8 * growthState.progress;
    const bodyRy = 22 + 4 * growthState.progress;
    const headR = 20 + 3 * growthState.progress;
    const headX = petDef.id === 'penguin' ? 69 : 84;
    const legColor = petDef.id === 'penguin' ? petDef.accent : petDef.accent;
    return `
      <svg viewBox="0 0 140 112" width="140" height="112" aria-hidden="true">
        <ellipse cx="69" cy="99" rx="43" ry="7" fill="rgba(0,0,0,.18)"/>
        ${tailSvg()}
        ${petDef.wings ? wingsSvg() : ''}
        <g class="pet-leg pet-leg-back"><path d="${legPath('back')}" fill="${legColor}" stroke="${petDef.insect ? legColor : 'none'}" stroke-width="${petDef.insect ? 2.2 : 0}" stroke-linecap="round"/></g>
        <g class="pet-leg pet-leg-front"><path d="${legPath('front')}" fill="${legColor}" stroke="${petDef.insect ? legColor : 'none'}" stroke-width="${petDef.insect ? 2.2 : 0}" stroke-linecap="round"/></g>
        ${petDef.shell ? `<ellipse class="pet-body" cx="61" cy="64" rx="42" ry="28" fill="${petDef.accent}"/><path d="M28 63 C45 47 76 47 94 64 C78 83 47 84 28 63" fill="${petDef.body}"/>` : `<ellipse class="pet-body" cx="61" cy="64" rx="${petDef.insect ? bodyRx * 0.72 : bodyRx}" ry="${petDef.insect ? bodyRy * 1.12 : bodyRy}" fill="${petDef.body}"/>`}
        <ellipse cx="64" cy="69" rx="${bodyRx * 0.58}" ry="${bodyRy * 0.55}" fill="${petDef.belly}" opacity=".82"/>
        ${petDef.pouch && adult ? '<path d="M58 69 C64 79 77 79 83 69" fill="none" stroke="rgba(80,45,25,.65)" stroke-width="3" stroke-linecap="round"/>' : ''}
        ${petDef.mane && !baby ? `<circle cx="${headX}" cy="42" r="29" fill="${petDef.accent}"/>` : ''}
        <g class="pet-head">
          <circle cx="${headX}" cy="42" r="${headR}" fill="${petDef.id === 'penguin' ? petDef.body : petDef.belly}"/>
          ${earsSvg(headX)}
          ${petDef.patches ? `<ellipse cx="${headX - 9}" cy="39" rx="8" ry="9" fill="${petDef.accent}"/><ellipse cx="${headX + 9}" cy="39" rx="8" ry="9" fill="${petDef.accent}"/>` : ''}
          ${eyesSvg(headX)}
          ${faceSvg(headX)}
          ${petDef.proboscis ? `<path d="M${headX + 16} 50 C${headX + 27} 51 ${headX + 31} 57 ${headX + 35} 64" fill="none" stroke="${petDef.accent}" stroke-width="2" stroke-linecap="round"/>` : ''}
        </g>
      </svg>`;
  }

  function snakeSvg(growthState) {
    const adult = growthState.stage.id === 'adult';
    const headX = 106 + 7 * growthState.progress;
    return `
      <svg viewBox="0 0 140 112" width="140" height="112" aria-hidden="true">
        <ellipse cx="72" cy="99" rx="46" ry="6" fill="rgba(0,0,0,.16)"/>
        <path class="pet-snake-body" d="M16 76 C34 44 55 94 75 65 C91 42 110 53 121 75" fill="none" stroke="${petDef.body}" stroke-width="${adult ? 21 : 17}" stroke-linecap="round"/>
        <path class="pet-snake-belly" d="M28 75 C42 62 55 80 70 69 C85 57 99 61 111 74" fill="none" stroke="${petDef.belly}" stroke-width="${adult ? 9 : 7}" stroke-linecap="round" opacity=".9"/>
        <g class="pet-head">
          <ellipse cx="${headX}" cy="71" rx="${adult ? 18 : 15}" ry="${adult ? 13 : 11}" fill="${petDef.body}"/>
          ${eyesSvg(headX, 67, 11)}
          <path class="pet-mouth pet-mouth-happy" d="M${headX + 13} 73 L${headX + 24} 70 M${headX + 24} 70 L${headX + 29} 67 M${headX + 24} 70 L${headX + 29} 73" fill="none" stroke="#cc4058" stroke-width="2" stroke-linecap="round"/>
          <path class="pet-mouth pet-mouth-sleepy" d="M${headX + 11} 73 Q${headX + 17} 76 ${headX + 23} 73" fill="none" stroke="#cc4058" stroke-width="2" stroke-linecap="round"/>
        </g>
      </svg>`;
  }

  function legPath(side) {
    if (petDef.insect) {
      return side === 'back'
        ? 'M51 73 C42 81 38 90 42 96 M54 71 C48 82 49 91 55 97'
        : 'M70 72 C78 82 83 89 80 96 M75 70 C88 77 93 86 91 94';
    }
    if (petDef.gait === 'hop') {
      return side === 'back'
        ? 'M45 70 C36 82 33 94 42 98 C52 93 57 82 61 71'
        : 'M73 70 C79 84 91 92 102 92 C103 99 88 101 76 92 C69 85 67 77 66 71';
    }
    if (petDef.gait === 'waddle') {
      return side === 'back'
        ? 'M48 75 C43 84 43 92 51 95 C56 88 58 82 59 75'
        : 'M73 75 C80 84 83 91 77 96 C69 91 66 84 65 75';
    }
    if (petDef.gait === 'crawl') {
      return side === 'back'
        ? 'M40 72 C31 76 28 84 35 88 C43 84 48 78 53 72'
        : 'M75 72 C84 76 91 82 88 89 C78 87 71 80 66 72';
    }
    return side === 'back'
      ? 'M45 70 C39 80 39 91 47 94 C54 88 56 79 58 71'
      : 'M73 70 C80 80 82 90 75 94 C68 88 65 79 64 71';
  }

  function earsSvg(headX) {
    if (petDef.ears === 'none') return '';
    if (petDef.ears === 'flop') return `<ellipse class="pet-ear" cx="${headX - 15}" cy="33" rx="7" ry="15" fill="${petDef.accent}" transform="rotate(30 ${headX - 15} 33)"/><ellipse class="pet-ear" cx="${headX + 15}" cy="33" rx="7" ry="15" fill="${petDef.accent}" transform="rotate(-30 ${headX + 15} 33)"/>`;
    if (petDef.ears === 'round') return `<circle class="pet-ear" cx="${headX - 17}" cy="25" r="8" fill="${petDef.body}"/><circle class="pet-ear" cx="${headX + 17}" cy="25" r="8" fill="${petDef.body}"/>`;
    if (petDef.ears === 'long') return `<ellipse class="pet-ear" cx="${headX - 12}" cy="20" rx="6" ry="20" fill="${petDef.body}" transform="rotate(-12 ${headX - 12} 20)"/><ellipse class="pet-ear" cx="${headX + 12}" cy="20" rx="6" ry="20" fill="${petDef.body}" transform="rotate(12 ${headX + 12} 20)"/>`;
    if (petDef.ears === 'horn') return `<path class="pet-ear" d="M${headX - 15} 25 L${headX - 9} 8 L${headX - 4} 27 Z" fill="${petDef.accent}"/><path class="pet-ear" d="M${headX + 12} 27 L${headX + 18} 8 L${headX + 22} 29 Z" fill="${petDef.accent}"/>`;
    if (petDef.ears === 'crest') return `<path class="pet-ear" d="M${headX - 5} 22 C${headX - 6} 9 ${headX + 7} 7 ${headX + 5} 23" fill="${petDef.accent}"/>`;
    if (petDef.ears === 'antenna') return `<path class="pet-ear" d="M${headX - 8} 26 C${headX - 22} 13 ${headX - 21} 6 ${headX - 15} 8" fill="none" stroke="${petDef.accent}" stroke-width="2.4" stroke-linecap="round"/><path class="pet-ear" d="M${headX + 8} 26 C${headX + 22} 13 ${headX + 21} 6 ${headX + 15} 8" fill="none" stroke="${petDef.accent}" stroke-width="2.4" stroke-linecap="round"/>`;
    return `<path class="pet-ear" d="M${headX - 17} 29 L${headX - 10} 9 L${headX - 3} 30 Z" fill="${petDef.body}"/><path class="pet-ear" d="M${headX + 8} 30 L${headX + 17} 9 L${headX + 22} 32 Z" fill="${petDef.body}"/>`;
  }

  function eyesSvg(headX, y = 39, spread = 8) {
    return `
      <g class="pet-eyes">
        <ellipse class="pet-eye pet-eye-left" cx="${headX - spread}" cy="${y}" rx="3.1" ry="3.4" fill="#1c2430"/>
        <ellipse class="pet-eye pet-eye-right" cx="${headX + spread}" cy="${y}" rx="3.1" ry="3.4" fill="#1c2430"/>
        <path class="pet-eye-sleepy" d="M${headX - spread - 4} ${y} Q${headX - spread} ${y + 3} ${headX - spread + 4} ${y}" fill="none" stroke="#1c2430" stroke-width="2" stroke-linecap="round"/>
        <path class="pet-eye-sleepy" d="M${headX + spread - 4} ${y} Q${headX + spread} ${y + 3} ${headX + spread + 4} ${y}" fill="none" stroke="#1c2430" stroke-width="2" stroke-linecap="round"/>
        <path class="pet-eye-sad" d="M${headX - spread - 4} ${y - 4} L${headX - spread + 4} ${y - 1} M${headX + spread - 4} ${y - 1} L${headX + spread + 4} ${y - 4}" fill="none" stroke="#1c2430" stroke-width="2" stroke-linecap="round"/>
        <circle class="pet-eye-spark" cx="${headX - spread + 1}" cy="${y - 1}" r="1" fill="#fff"/>
        <circle class="pet-eye-spark" cx="${headX + spread + 1}" cy="${y - 1}" r="1" fill="#fff"/>
      </g>`;
  }

  function faceSvg(headX) {
    if (petDef.beak) {
      return `
        <path class="pet-beak" d="M${headX} 44 L${headX + 14} 49 L${headX} 54 Z" fill="${petDef.accent}"/>
        <path class="pet-mouth pet-mouth-sleepy" d="M${headX - 3} 55 Q${headX + 3} 58 ${headX + 10} 55" fill="none" stroke="#1c2430" stroke-width="2" stroke-linecap="round"/>`;
    }
    return `
      <ellipse cx="${headX}" cy="51" rx="10" ry="7" fill="rgba(255,238,218,.8)"/>
      <circle cx="${headX}" cy="48" r="3" fill="${petDef.accent}"/>
      <path class="pet-mouth pet-mouth-happy" d="M${headX - 7} 55 Q${headX} 60 ${headX + 8} 55" fill="none" stroke="#1c2430" stroke-width="2" stroke-linecap="round" opacity=".72"/>
      <path class="pet-mouth pet-mouth-sad" d="M${headX - 7} 59 Q${headX} 54 ${headX + 8} 59" fill="none" stroke="#1c2430" stroke-width="2" stroke-linecap="round" opacity=".72"/>
      <path class="pet-mouth pet-mouth-sleepy" d="M${headX - 5} 56 Q${headX} 58 ${headX + 5} 56" fill="none" stroke="#1c2430" stroke-width="2" stroke-linecap="round" opacity=".72"/>
      <ellipse class="pet-mouth pet-mouth-excited" cx="${headX}" cy="56" rx="4" ry="5" fill="#1c2430" opacity=".72"/>`;
  }

  function tailSvg() {
    if (petDef.tail === 'none') return '';
    if (petDef.tail === 'curl') return `<path class="pet-tail" d="M33 63 C8 49 21 25 39 34 C52 41 43 55 33 48" fill="none" stroke="${petDef.accent}" stroke-width="8" stroke-linecap="round"/>`;
    if (petDef.tail === 'fluffy') return `<path class="pet-tail" d="M32 61 C8 42 10 24 30 21 C50 22 46 48 32 61" fill="${petDef.accent}"/><path class="pet-tail" d="M22 29 C27 34 29 38 29 45" fill="none" stroke="${petDef.belly}" stroke-width="5" stroke-linecap="round" opacity=".75"/>`;
    if (petDef.tail === 'tuft') return `<path class="pet-tail" d="M35 63 C14 57 12 38 25 31" fill="none" stroke="${petDef.accent}" stroke-width="7" stroke-linecap="round"/><circle class="pet-tail" cx="24" cy="30" r="7" fill="${petDef.accent}"/>`;
    if (petDef.tail === 'balance') return `<path class="pet-tail" d="M36 69 C14 78 7 93 4 108" fill="none" stroke="${petDef.accent}" stroke-width="9" stroke-linecap="round"/>`;
    if (petDef.tail === 'spike') return `<path class="pet-tail" d="M35 65 C13 63 12 45 25 35" fill="none" stroke="${petDef.accent}" stroke-width="8" stroke-linecap="round"/><path d="M21 38 L13 34 L19 47 Z" fill="${petDef.accent}"/>`;
    if (petDef.tail === 'feather') return `<path class="pet-tail" d="M36 65 C20 66 13 56 14 45 C27 47 34 55 36 65" fill="${petDef.accent}"/>`;
    if (petDef.tail === 'needle') return `<path class="pet-tail" d="M35 66 C22 67 15 70 8 75" fill="none" stroke="${petDef.accent}" stroke-width="2.5" stroke-linecap="round"/>`;
    if (petDef.tail === 'long') return `<path class="pet-tail" d="M35 65 C19 64 10 66 2 72" fill="none" stroke="${petDef.body}" stroke-width="7" stroke-linecap="round"/><path d="M8 72 L3 68 L2 76 Z" fill="${petDef.accent}"/>`;
    if (petDef.tail === 'short') return `<path class="pet-tail" d="M31 67 C22 68 18 64 18 59" fill="none" stroke="${petDef.accent}" stroke-width="7" stroke-linecap="round"/>`;
    return `<circle class="pet-tail" cx="30" cy="66" r="8" fill="${petDef.accent}"/>`;
  }

  function wingsSvg() {
    return `<path class="pet-wing pet-wing-back" d="M49 54 C28 37 21 62 41 75" fill="${petDef.accent}" opacity=".75"/><path class="pet-wing pet-wing-front" d="M75 53 C99 35 103 62 84 76" fill="${petDef.accent}" opacity=".75"/>`;
  }

  window.addEventListener('rf:web-pet-settings', restartFromSettings);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', restartFromSettings);
  } else {
    restartFromSettings();
  }
})();
