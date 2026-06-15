const lastSpoken = new Map();

export function speak(text, options = {}) {
  if (!text || !("speechSynthesis" in window)) return;
  if (options.interrupt !== false) {
    window.speechSynthesis.cancel();
  }
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = options.rate || 1.03;
  utterance.pitch = 1;
  window.speechSynthesis.speak(utterance);
}

export function speakGuidance(text, key = "guidance", minInterval = 1300) {
  if (!text) return;
  const now = Date.now();
  const previous = lastSpoken.get(key) || { text: "", time: 0 };
  if (previous.text === text && now - previous.time < minInterval) return;
  lastSpoken.set(key, { text, time: now });
  speak(text, { interrupt: true, rate: 1.08 });
}

export function speakStatus(text) {
  speakGuidance(text, "status", 900);
}
