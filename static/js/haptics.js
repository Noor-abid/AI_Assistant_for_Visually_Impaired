let audioContext = null;
let lastPulse = 0;

function ctx() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
  }
  return audioContext;
}

export function modePulse() {
  vibrate([35, 40, 35]);
  tone(520, 0.08);
}

export function successPulse() {
  vibrate([80, 35, 120]);
  tone(660, 0.08);
  setTimeout(() => tone(880, 0.1), 100);
}

export function errorPulse() {
  vibrate([120]);
  tone(180, 0.12);
}

export function guidePulse(strength, centered = false) {
  const now = Date.now();
  const clamped = Math.max(0, Math.min(1, Number(strength) || 0));
  const wait = centered ? 260 : Math.max(90, 420 - clamped * 300);
  if (now - lastPulse < wait) return;
  lastPulse = now;
  if (centered) {
    successPulse();
    return;
  }
  const duration = Math.round(18 + clamped * 42);
  vibrate([duration]);
  tone(420 + clamped * 520, 0.045);
}

function vibrate(pattern) {
  if ("vibrate" in navigator) {
    navigator.vibrate(pattern);
  }
}

function tone(freq, duration) {
  try {
    const context = ctx();
    context.resume();
    const osc = context.createOscillator();
    const gain = context.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.12, context.currentTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + duration);
    osc.connect(gain);
    gain.connect(context.destination);
    osc.start();
    osc.stop(context.currentTime + duration + 0.02);
  } catch {
    // Audio feedback is best-effort.
  }
}

