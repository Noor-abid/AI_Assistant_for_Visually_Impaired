const state = {
  stream: null,
  lastFrame: null,
  liveTimer: null,
  liveBusy: false,
  lastSpoken: new Map(),
  trackedObjects: new Map(),
  audio: {
    context: null,
    gain: null,
    lastCue: 0,
  },
  taskSteps: [],
  stepIndex: 0,
  activeTask: "tea",
  taskTitle: "Make tea",
  lastNavigation: null,
  installPrompt: null,
  demoScenarioIndex: -1,
};

const TASK_STORAGE_KEY = "visio-netra-task-state";

const demoScenarios = [
  {
    name: "Stairwell",
    target: "stairs",
    hint: "Demo: stairwell and handrail.",
  },
  {
    name: "Social",
    target: "person",
    hint: "Demo: possible person waving.",
  },
  {
    name: "Kitchen",
    target: "cup",
    hint: "Demo: kitchen task setup.",
  },
];

const fallbackTasks = {
  tea: ["Find the cup", "Locate the kettle", "Confirm water is poured", "Check the cup is safely placed"],
  coffee: ["Find the mug", "Locate the coffee container", "Confirm water or milk is nearby", "Check the mug is stable"],
  door: ["Face the nearest door", "Center the door handle", "Confirm the path is clear", "Approach slowly"],
  label: ["Hold the product steady", "Center the label", "Read the text", "Confirm the item name"],
  seat: ["Scan for a chair or bench", "Check if the seat appears occupied", "Locate the front edge", "Sit only after touch confirmation"],
  elevator: ["Find the elevator panel", "Center the button area", "Use precision mode for the target button", "Confirm the door area is clear"],
};

const els = {
  serviceStatus: document.querySelector("#serviceStatus"),
  modeStatus: document.querySelector("#modeStatus"),
  modelStatus: document.querySelector("#modelStatus"),
  riskStatus: document.querySelector("#riskStatus"),
  latencyBadge: document.querySelector("#latencyBadge"),
  camera: document.querySelector("#camera"),
  overlay: document.querySelector("#overlay"),
  cameraFallback: document.querySelector("#cameraFallback"),
  latestGuidance: document.querySelector("#latestGuidance"),
  distanceValue: document.querySelector("#distanceValue"),
  directionValue: document.querySelector("#directionValue"),
  latencyValue: document.querySelector("#latencyValue"),
  confidenceValue: document.querySelector("#confidenceValue"),
  targetObject: document.querySelector("#targetObject"),
  sceneSummary: document.querySelector("#sceneSummary"),
  hazardList: document.querySelector("#hazardList"),
  riskLabel: document.querySelector("#riskLabel"),
  riskMeter: document.querySelector("#riskMeter"),
  nextAction: document.querySelector("#nextAction"),
  actionList: document.querySelector("#actionList"),
  objectList: document.querySelector("#objectList"),
  objectCount: document.querySelector("#objectCount"),
  socialCue: document.querySelector("#socialCue"),
  environmentCue: document.querySelector("#environmentCue"),
  microVector: document.querySelector("#microVector"),
  objectResult: document.querySelector("#objectResult"),
  answerResult: document.querySelector("#answerResult"),
  modelDetails: document.querySelector("#modelDetails"),
  ocrResult: document.querySelector("#ocrResult"),
  commandInput: document.querySelector("#commandInput"),
  manualText: document.querySelector("#manualText"),
  taskSelect: document.querySelector("#taskSelect"),
  customTask: document.querySelector("#customTask"),
  taskSteps: document.querySelector("#taskSteps"),
  taskProgress: document.querySelector("#taskProgress"),
  taskResult: document.querySelector("#taskResult"),
  landmarkName: document.querySelector("#landmarkName"),
  landmarkNote: document.querySelector("#landmarkNote"),
  landmarkList: document.querySelector("#landmarkList"),
  locationMatch: document.querySelector("#locationMatch"),
  pathClearance: document.querySelector("#pathClearance"),
  installApp: document.querySelector("#installApp"),
  installHint: document.querySelector("#installHint"),
};

function normalizeSpeech(text) {
  return text.toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").trim();
}

function speak(text, priority = "medium") {
  if (!("speechSynthesis" in window) || !text) return;
  const key = normalizeSpeech(text);
  const now = Date.now();
  const cooldown = priority === "high" ? 1200 : priority === "medium" ? 3500 : 7000;
  const last = state.lastSpoken.get(key) || 0;
  if (priority !== "high" && now - last < cooldown) return;
  state.lastSpoken.set(key, now);
  if (priority === "high") window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 0.95;
  window.speechSynthesis.speak(utterance);
}

function vibrate(pattern) {
  if ("vibrate" in navigator && Array.isArray(pattern)) {
    navigator.vibrate(pattern);
  }
}

function initAudio() {
  if (state.audio.context) return state.audio.context;
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return null;
  const context = new AudioContext();
  const gain = context.createGain();
  gain.gain.value = 0.18;
  gain.connect(context.destination);
  state.audio.context = context;
  state.audio.gain = gain;
  return context;
}

function directionPan(direction = "") {
  if (direction.includes("9") || direction.includes("left")) return -0.75;
  if (direction.includes("3") || direction.includes("right")) return 0.75;
  return 0;
}

function playTone(frequency, duration = 0.12, pan = 0, type = "sine") {
  const context = initAudio();
  if (!context || !state.audio.gain) return;
  context.resume?.();
  const osc = context.createOscillator();
  const gain = context.createGain();
  const panner = context.createStereoPanner ? context.createStereoPanner() : null;
  osc.type = type;
  osc.frequency.value = frequency;
  gain.gain.setValueAtTime(0.001, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.35, context.currentTime + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + duration);
  if (panner) {
    panner.pan.value = pan;
    osc.connect(gain);
    gain.connect(panner);
    panner.connect(state.audio.gain);
  } else {
    osc.connect(gain);
    gain.connect(state.audio.gain);
  }
  osc.start();
  osc.stop(context.currentTime + duration + 0.02);
}

function playNavigationCue(result) {
  const now = Date.now();
  if (now - state.audio.lastCue < 900) return;
  state.audio.lastCue = now;
  const primary = result.target || result.objects?.[0];
  const pan = directionPan(primary?.direction || "");
  if (result.priority === "high") {
    playTone(880, 0.1, pan, "square");
    setTimeout(() => playTone(660, 0.12, pan, "square"), 120);
  } else if (result.target_detected) {
    playTone(1040, 0.09, pan, "triangle");
  } else {
    playTone(result.priority === "medium" ? 620 : 420, 0.08, pan, "sine");
  }
}

function playMicroCue(result) {
  const pan = Math.max(-1, Math.min(1, (result.x || 0) / 100));
  const frequency = result.tone_hz || 520;
  playTone(frequency, result.action === "hold" ? 0.18 : 0.08, pan, result.action === "hold" ? "triangle" : "sine");
  if (result.action === "hold") {
    setTimeout(() => playTone(frequency * 1.25, 0.14, pan, "triangle"), 170);
  }
}

function setMode(mode) {
  els.modeStatus.textContent = mode;
}

function setLatency(ms) {
  els.latencyBadge.textContent = `${ms} ms`;
  if (els.latencyValue) els.latencyValue.textContent = `${ms} ms`;
}

function announce(text, priority = "medium") {
  els.latestGuidance.textContent = text;
  speak(text, priority);
}

function setResult(target, value) {
  const pre = document.createElement("pre");
  pre.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  target.replaceChildren(pre);
}

async function postJson(route, payload = {}) {
  const start = performance.now();
  const response = await fetch(route, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  result._latency = Math.round(performance.now() - start);
  if (!response.ok) throw new Error(result.error || "Analysis failed.");
  setLatency(result._latency);
  return result;
}

async function postFrame(route, extra = {}) {
  const image = state.lastFrame || captureFrame();
  if (!image) throw new Error("Start the camera or capture a demo frame first.");
  return postJson(route, { image, ...extra });
}

function drawDemoFrame(ctx, width, height, scenario) {
  ctx.fillStyle = "#101417";
  ctx.fillRect(0, 0, width, height);

  if (scenario.name === "Stairwell") {
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, "#283033");
    gradient.addColorStop(0.54, "#5d6869");
    gradient.addColorStop(1, "#1e2326");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = "#d8e2e5";
    ctx.fillRect(width * 0.62, height * 0.08, width * 0.18, height * 0.24);
    ctx.fillStyle = "#252b2f";
    ctx.fillRect(width * 0.1, height * 0.24, width * 0.055, height * 0.58);
    ctx.fillStyle = "#0f1418";
    ctx.fillRect(width * 0.18, height * 0.38, width * 0.035, height * 0.46);
    ctx.strokeStyle = "#151a1f";
    ctx.lineWidth = width * 0.022;
    ctx.beginPath();
    ctx.moveTo(width * 0.08, height * 0.5);
    ctx.lineTo(width * 0.62, height * 0.28);
    ctx.stroke();
    for (let index = 0; index < 6; index += 1) {
      const y = height * (0.48 + index * 0.075);
      ctx.fillStyle = index % 2 ? "#3c4448" : "#272e33";
      ctx.fillRect(width * 0.28, y, width * 0.58, height * 0.032);
      ctx.fillStyle = "#687175";
      ctx.fillRect(width * 0.24, y + height * 0.035, width * 0.66, height * 0.012);
    }
    return;
  }

  if (scenario.name === "Social") {
    ctx.fillStyle = "#272027";
    ctx.fillRect(0, 0, width, height);
    for (let x = 0; x < width; x += width * 0.08) {
      ctx.fillStyle = x % 2 ? "#40323f" : "#241d25";
      ctx.fillRect(x, 0, width * 0.055, height);
    }
    ctx.fillStyle = "#c89070";
    ctx.beginPath();
    ctx.ellipse(width * 0.5, height * 0.34, width * 0.07, height * 0.09, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#efded2";
    ctx.fillRect(width * 0.39, height * 0.45, width * 0.22, height * 0.22);
    ctx.fillStyle = "#d8856d";
    ctx.fillRect(width * 0.36, height * 0.43, width * 0.05, height * 0.26);
    ctx.fillRect(width * 0.59, height * 0.43, width * 0.05, height * 0.26);
    ctx.fillStyle = "#c89070";
    ctx.beginPath();
    ctx.ellipse(width * 0.67, height * 0.36, width * 0.035, height * 0.055, -0.45, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#c89070";
    ctx.lineWidth = width * 0.035;
    ctx.beginPath();
    ctx.moveTo(width * 0.62, height * 0.47);
    ctx.lineTo(width * 0.68, height * 0.36);
    ctx.stroke();
    return;
  }

  const counter = ctx.createLinearGradient(0, 0, width, height);
  counter.addColorStop(0, "#252a27");
  counter.addColorStop(1, "#0d1111");
  ctx.fillStyle = counter;
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#cfd2ca";
  ctx.beginPath();
  ctx.ellipse(width * 0.32, height * 0.2, width * 0.13, height * 0.07, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#0c0e10";
  ctx.fillRect(width * 0.58, height * 0.06, width * 0.28, height * 0.16);
  ctx.fillStyle = "#b45309";
  ctx.fillRect(width * 0.46, height * 0.6, width * 0.13, height * 0.15);
  ctx.fillStyle = "#111827";
  ctx.fillRect(width * 0.5, height * 0.38, width * 0.32, height * 0.035);
  ctx.fillRect(width * 0.5, height * 0.44, width * 0.25, height * 0.035);
  ctx.strokeStyle = "#99e447";
  ctx.lineWidth = width * 0.018;
  ctx.beginPath();
  ctx.arc(width * 0.18, height * 0.5, width * 0.045, 0, Math.PI * 2);
  ctx.arc(width * 0.27, height * 0.47, width * 0.045, 0, Math.PI * 2);
  ctx.moveTo(width * 0.22, height * 0.49);
  ctx.lineTo(width * 0.38, height * 0.39);
  ctx.stroke();
}

function captureFrame(options = {}) {
  const video = els.camera;
  const canvas = document.createElement("canvas");
  const width = video.videoWidth || 960;
  const height = video.videoHeight || 600;
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");

  if (video.readyState >= 2) {
    ctx.drawImage(video, 0, 0, width, height);
  } else {
    if (options.advanceDemo || state.demoScenarioIndex < 0) {
      state.demoScenarioIndex = (state.demoScenarioIndex + 1) % demoScenarios.length;
      els.targetObject.value = demoScenarios[state.demoScenarioIndex].target;
    }
    drawDemoFrame(ctx, width, height, demoScenarios[state.demoScenarioIndex]);
  }

  state.lastFrame = canvas.toDataURL("image/jpeg", 0.82);
  if (video.readyState < 2) {
    const scenario = demoScenarios[state.demoScenarioIndex] || demoScenarios[0];
    els.cameraFallback.classList.add("demo-active");
    els.cameraFallback.classList.remove("hidden");
    els.cameraFallback.style.backgroundImage = `linear-gradient(180deg, rgba(0, 0, 0, 0.12), rgba(0, 0, 0, 0.66)), url("${state.lastFrame}")`;
    els.cameraFallback.textContent = scenario.hint;
  }
  return state.lastFrame;
}

function clearOverlay() {
  const canvas = els.overlay;
  const rect = els.camera.getBoundingClientRect();
  canvas.width = Math.max(1, rect.width);
  canvas.height = Math.max(1, rect.height);
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
}

function drawBoxes(items = [], primaryBox = null) {
  const canvas = els.overlay;
  const rect = els.camera.getBoundingClientRect();
  canvas.width = Math.max(1, rect.width);
  canvas.height = Math.max(1, rect.height);
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const drawOne = (box, color, label) => {
    if (!box) return;
    const x = box.x * canvas.width;
    const y = box.y * canvas.height;
    const w = box.w * canvas.width;
    const h = box.h * canvas.height;
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = color;
    ctx.fillRect(x, Math.max(0, y - 28), Math.min(220, Math.max(72, w)), 26);
    ctx.fillStyle = "#fff";
    ctx.font = "14px Arial";
    ctx.fillText(label, x + 8, Math.max(18, y - 10));
  };

  items.forEach((item) => drawOne(item.box, "#3454d1", item.name));
  if (primaryBox) drawOne(primaryBox, "#0f766e", "target");
}

function classForPriority(priority) {
  return priority === "high" ? "priority-high" : priority === "medium" ? "priority-medium" : "priority-low";
}

function renderHazards(hazards) {
  if (!hazards || hazards.length === 0) {
    els.hazardList.className = "stack empty";
    els.hazardList.textContent = "No hazards reported.";
    return;
  }
  els.hazardList.className = "stack";
  els.hazardList.replaceChildren(
    ...hazards.map((hazard) => {
      const item = document.createElement("div");
      item.className = `hazard-item ${classForPriority(hazard.priority)}`;
      item.textContent = hazard.message;
      return item;
    }),
  );
}

function updateTrackedObjects(objects = []) {
  const now = Date.now();
  const seen = new Set();

  objects.forEach((object) => {
    const key = `${object.category || "object"}:${object.name}`.toLowerCase();
    const previous = state.trackedObjects.get(key);
    const distance = Number(object.distance || 0);
    const confidence = Number(object.confidence || 0);
    if (previous) {
      previous.seen += 1;
      previous.lastSeen = now;
      previous.distance = Number(((previous.distance * 0.65) + (distance * 0.35)).toFixed(2));
      previous.confidence = Number(Math.max(previous.confidence * 0.75, confidence).toFixed(3));
      previous.direction = object.direction || previous.direction;
      previous.region = object.region || previous.region;
      previous.box = object.box || previous.box;
      previous.detector = object.detector || previous.detector;
      previous.confidence_band = previous.confidence >= 0.78 ? "high" : previous.confidence >= 0.52 ? "medium" : "low";
      previous.stable = previous.seen >= 2;
      state.trackedObjects.set(key, previous);
    } else {
      state.trackedObjects.set(key, {
        ...object,
        distance,
        confidence,
        seen: 1,
        lastSeen: now,
        stable: false,
      });
    }
    seen.add(key);
  });

  for (const [key, item] of state.trackedObjects.entries()) {
    if (now - item.lastSeen > 6500) {
      state.trackedObjects.delete(key);
    } else if (!seen.has(key)) {
      item.stable = false;
      state.trackedObjects.set(key, item);
    }
  }

  return [...state.trackedObjects.values()]
    .sort((a, b) => Number(b.stable) - Number(a.stable) || a.distance - b.distance || b.confidence - a.confidence);
}

function stableObjects() {
  return [...state.trackedObjects.values()]
    .filter((object) => object.stable)
    .sort((a, b) => a.distance - b.distance || b.confidence - a.confidence);
}

function renderObjects(objects) {
  const stableCount = objects.filter((object) => object.stable).length;
  els.objectCount.textContent = `${stableCount}/${objects.length}`;
  els.objectCount.title = "Stable objects / recently seen objects";
  if (!objects || objects.length === 0) {
    els.objectList.className = "object-list empty";
    els.objectList.textContent = "No objects tracked yet.";
    return;
  }
  els.objectList.className = "object-list";
  els.objectList.replaceChildren(
    ...objects.map((object) => {
      const item = document.createElement("div");
      item.className = `object-item ${object.stable ? "stable" : "warming"}`;
      const name = document.createElement("strong");
      name.textContent = object.name;
      const distance = document.createElement("span");
      distance.textContent = `${object.distance} m`;
      const meta = document.createElement("span");
      meta.className = "object-meta";
      meta.textContent = `${object.direction}, ${object.confidence_band} confidence, seen ${object.seen || 1}x${object.stable ? ", stable" : ", warming up"}`;
      item.append(name, distance, meta);
      return item;
    }),
  );
}

function renderMarkers(target, markers, emptyText) {
  if (!markers || markers.length === 0) {
    target.className = "stack empty";
    target.textContent = emptyText;
    return;
  }
  target.className = "stack";
  const nodes = markers.map((marker) => {
    const div = document.createElement("div");
    div.textContent = marker;
    return div;
  });
  target.replaceChildren(...nodes);
}

function prettyStatus(value = "") {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderActionSteps(actions) {
  const steps = actions?.steps || [];
  if (!steps.length) {
    els.actionList.className = "action-list empty";
    els.actionList.textContent = "No action steps yet.";
    return;
  }
  els.actionList.className = "action-list";
  els.actionList.replaceChildren(
    ...steps.map((step) => {
      const item = document.createElement("div");
      item.textContent = step;
      return item;
    }),
  );
}

function renderRisk(result) {
  const risk = result.risk;
  const actions = result.next_actions;
  const level = risk?.level || "low";
  const score = Math.max(0, Math.min(100, Number(risk?.score || 0)));
  const label = risk ? `${risk.label} ${score}/100` : "Awaiting scan";
  els.riskLabel.textContent = label;
  els.riskMeter.style.width = `${score}%`;
  els.riskMeter.dataset.level = level;
  els.riskStatus.textContent = risk ? risk.label : "Risk --";
  els.riskStatus.className = `status-pill ${risk ? `risk-${level}` : "muted"}`;
  els.nextAction.textContent = actions?.primary || "No next action yet.";
  els.pathClearance.textContent = result.environment?.path_clearance ? prettyStatus(result.environment.path_clearance) : "Path --";
  renderActionSteps(actions);
}

function renderNavigation(result, options = {}) {
  state.lastNavigation = result;
  setMode("Navigation");
  const tracked = updateTrackedObjects(result.objects || []);
  const stable = stableObjects();
  const displayObjects = stable.length ? stable : tracked;
  els.sceneSummary.textContent = result.scene?.summary || "No scene summary.";
  renderHazards(result.hazards);
  renderObjects(displayObjects);
  renderRisk(result);
  renderMarkers(els.environmentCue, result.environment?.markers || [], "No environment markers yet.");
  renderMarkers(els.socialCue, [result.social_cues?.details].filter(Boolean), "No social cue yet.");

  if (result.current_location_tag) {
    els.locationMatch.textContent = result.current_location_tag.name;
  } else {
    els.locationMatch.textContent = "No place match";
  }

  const target = result.target;
  const targetTrack = target ? tracked.find((object) => object.name.toLowerCase() === target.name.toLowerCase()) : null;
  const primary = targetTrack || target || displayObjects[0];
  els.distanceValue.textContent = primary?.distance ? `${primary.distance} m` : "--";
  els.directionValue.textContent = primary?.direction || "--";
  els.confidenceValue.textContent = primary?.stable ? `${primary.confidence_band} stable` : primary?.confidence_band || "--";
  drawBoxes(displayObjects, target?.box || null);
  if (!options.silent) {
    playNavigationCue({ ...result, objects: displayObjects, target: targetTrack || target });
    announce(result.speech, result.priority);
  }
}

function renderObjectGuidance(result) {
  setMode("Find");
  setResult(els.objectResult, result);
  els.distanceValue.textContent = result.guidance ? `${result.guidance.distance}` : "--";
  els.directionValue.textContent = result.guidance?.direction || "--";
  els.confidenceValue.textContent = result.box?.confidence ? String(result.box.confidence) : "--";
  drawBoxes([], result.box);
  vibrate(result.guidance?.vibration_pattern);
  announce(result.spoken, result.found ? "medium" : "low");
}

function renderMicro(result) {
  setMode("Precision");
  const lines = [
    `Target: ${result.target}`,
    `Action: ${result.action}`,
    `Vector: x ${result.x}, y ${result.y}`,
    `Tone: ${result.tone_hz} Hz`,
    `Pulse: ${result.pulse}`,
  ];
  els.microVector.textContent = lines.join("\n");
  drawBoxes([], result.box);
  vibrate(result.guidance?.vibration_pattern || [70, 70]);
  playMicroCue(result);
  announce(result.guidance_speech, result.found ? "medium" : "low");
}

async function runNavigation(options = {}) {
  initAudio();
  if (!options.useLastFrame) captureFrame();
  const result = await postFrame("/api/analyze/navigation", {
    goal: els.targetObject.value.trim(),
    landmarks: getLandmarks(),
  });
  renderNavigation(result);
}

async function runObject() {
  initAudio();
  captureFrame();
  const result = await postFrame("/api/analyze/object", { target: els.targetObject.value.trim() });
  renderObjectGuidance(result);
}

async function runMicro() {
  initAudio();
  captureFrame();
  const result = await postFrame("/api/analyze/micro", { target: els.targetObject.value.trim() });
  renderMicro(result);
}

async function runScene() {
  captureFrame();
  const result = await postFrame("/api/analyze/scene");
  setMode("Scene");
  els.sceneSummary.textContent = result.summary;
  drawBoxes([], result.salient_region);
  announce(result.summary, "low");
}

async function runOcr() {
  const image = state.lastFrame || captureFrame();
  try {
    if ("TextDetector" in window) {
      const blob = await (await fetch(image)).blob();
      const bitmap = await createImageBitmap(blob);
      const detector = new TextDetector();
      const detections = await detector.detect(bitmap);
      const text = detections.map((item) => item.rawValue).filter(Boolean).join("\n");
      if (text.trim()) {
        const result = { status: "recognized", text };
        setResult(els.ocrResult, result);
        announce(text, "medium");
        return;
      }
    }
  } catch {
    // Browser OCR is experimental. Fall back to local text-region detection.
  }
  const result = await postFrame("/api/analyze/ocr");
  setResult(els.ocrResult, result);
  announce(result.tts, "low");
}

async function runSocial() {
  captureFrame();
  const result = await postFrame("/api/analyze/social");
  setMode("Social");
  renderMarkers(els.socialCue, [result.cue], "No social cue yet.");
  drawBoxes([], result.box);
  announce(result.cue, result.person_detected ? "medium" : "low");
}

async function runInquiry(question = "") {
  captureFrame();
  const prompt = question || els.commandInput.value.trim() || "What is around me?";
  const result = await postFrame("/api/inquire", {
    question: prompt,
    landmarks: getLandmarks(),
  });
  setMode("Inquiry");
  setResult(els.answerResult, {
    question: result.question,
    answer: result.answer,
    confidence: result.confidence,
    evidence: result.evidence,
  });
  if (result.navigation) renderNavigation(result.navigation, { silent: true });
  announce(result.answer, result.navigation?.priority || "medium");
}

async function planTask(taskName = "") {
  const task = taskName || els.customTask.value.trim() || els.taskSelect.value;
  const result = await postJson("/api/task/plan", { task });
  state.activeTask = result.task;
  state.taskTitle = result.title || task;
  state.stepIndex = 0;
  state.taskSteps = result.steps;
  renderSteps();
  setResult(els.taskResult, result);
  announce(`Task ready. ${currentTaskStatus()}`, "medium");
}

function fallbackPlan(key) {
  return (fallbackTasks[key] || fallbackTasks.tea).map((instruction, index) => ({
    id: index + 1,
    instruction,
    completed: false,
  }));
}

function saveTaskState() {
  const payload = {
    activeTask: state.activeTask,
    taskTitle: state.taskTitle,
    stepIndex: state.stepIndex,
    taskSteps: state.taskSteps,
    customTask: els.customTask.value,
    updatedAt: new Date().toISOString(),
  };
  localStorage.setItem(TASK_STORAGE_KEY, JSON.stringify(payload));
}

function loadTaskState() {
  try {
    const payload = JSON.parse(localStorage.getItem(TASK_STORAGE_KEY) || "null");
    if (!payload || !Array.isArray(payload.taskSteps) || !payload.taskSteps.length) return false;
    state.activeTask = payload.activeTask || "tea";
    state.taskTitle = payload.taskTitle || payload.activeTask || "Task";
    state.stepIndex = Math.min(Math.max(Number(payload.stepIndex) || 0, 0), payload.taskSteps.length - 1);
    state.taskSteps = payload.taskSteps;
    els.customTask.value = payload.customTask || "";
    if (fallbackTasks[state.activeTask]) els.taskSelect.value = state.activeTask;
    return true;
  } catch {
    return false;
  }
}

function clearTaskState() {
  state.activeTask = els.taskSelect.value || "tea";
  state.taskTitle = els.taskSelect.options[els.taskSelect.selectedIndex]?.textContent || "Task";
  state.stepIndex = 0;
  state.taskSteps = fallbackPlan(state.activeTask);
  localStorage.removeItem(TASK_STORAGE_KEY);
  renderSteps({ persist: false });
}

function renderSteps(options = {}) {
  const persist = options.persist !== false;
  if (!state.taskSteps.length) state.taskSteps = fallbackPlan(state.activeTask);
  const completed = state.taskSteps.filter((step) => step.completed).length;
  els.taskProgress.textContent = `${completed}/${state.taskSteps.length}`;
  els.taskProgress.title = `${state.taskTitle}: ${completed} of ${state.taskSteps.length} steps completed`;
  els.taskSteps.replaceChildren(
    ...state.taskSteps.map((step, index) => {
      const li = document.createElement("li");
      li.textContent = `${index + 1}. ${step.instruction}`;
      if (step.completed) li.classList.add("completed");
      if (index === state.stepIndex) li.classList.add("active");
      return li;
    }),
  );
  if (persist) saveTaskState();
}

function currentTaskStatus() {
  if (!state.taskSteps.length) return "No active task.";
  const current = state.taskSteps[state.stepIndex];
  const completed = state.taskSteps.filter((step) => step.completed).length;
  const index = Math.min(state.stepIndex + 1, state.taskSteps.length);
  return `${state.taskTitle}. Step ${index} of ${state.taskSteps.length}: ${current?.instruction || "Complete"}. ${completed} completed.`;
}

async function verifyStep() {
  if (!state.taskSteps.length) renderSteps();
  const step = state.taskSteps[state.stepIndex];
  if (!step) return;
  captureFrame();
  const result = await postFrame("/api/analyze/task", { step: step.instruction });
  if (result.verified) state.taskSteps[state.stepIndex].completed = true;
  renderSteps();
  setResult(els.taskResult, result);
  announce(`${currentTaskStatus()} ${result.feedback}`, result.verified ? "medium" : "low");
}

function getLandmarks() {
  try {
    return JSON.parse(localStorage.getItem("visio-netra-landmarks") || "[]");
  } catch {
    return [];
  }
}

function setLandmarks(items) {
  localStorage.setItem("visio-netra-landmarks", JSON.stringify(items));
  renderLandmarks();
}

function mergeLandmarkLists(...groups) {
  const byName = new Map();
  groups.flat().forEach((item) => {
    if (!item || !item.name) return;
    byName.set(item.name.trim().toLowerCase(), item);
  });
  return [...byName.values()];
}

async function loadMemoryFromServer() {
  try {
    const response = await fetch("/api/memory");
    if (!response.ok) return;
    const memory = await response.json();
    const merged = mergeLandmarkLists(getLandmarks(), memory.locations || []);
    setLandmarks(merged);
  } catch {
    renderLandmarks();
  }
}

function renderLandmarks() {
  const items = getLandmarks();
  if (!items.length) {
    const li = document.createElement("li");
    li.textContent = "No landmarks saved.";
    els.landmarkList.replaceChildren(li);
    return;
  }
  els.landmarkList.replaceChildren(
    ...items.map((item) => {
      const li = document.createElement("li");
      const name = document.createElement("strong");
      name.textContent = item.name;
      const meta = document.createElement("span");
      meta.className = "landmark-meta";
      meta.textContent = [item.note, item.description].filter(Boolean).join(" | ");
      li.append(name, meta);
      return li;
    }),
  );
}

async function saveLandmark() {
  const name = els.landmarkName.value.trim();
  const note = els.landmarkNote.value.trim();
  if (!name || !note) {
    announce("Add both place and note before saving.", "low");
    return;
  }
  const description = state.lastNavigation?.scene?.summary || els.sceneSummary.textContent;
  const localItem = { name, note, description, createdAt: new Date().toISOString() };
  try {
    const result = await postJson("/api/memory/save", localItem);
    setLandmarks(mergeLandmarkLists(getLandmarks(), result.memory?.locations || [result.landmark]));
  } catch {
    setLandmarks(mergeLandmarkLists(getLandmarks(), [localItem]));
  }
  els.landmarkName.value = "";
  els.landmarkNote.value = "";
  announce(`Saved ${name}.`, "medium");
}

async function clearLandmarks() {
  try {
    await postJson("/api/memory/clear", {});
  } catch {
    // Local fallback still clears the browser copy.
  }
  setLandmarks([]);
  announce("All landmarks cleared.", "low");
}

function toggleLive() {
  initAudio();
  if (state.liveTimer) {
    clearInterval(state.liveTimer);
    state.liveTimer = null;
    document.querySelector("#toggleLive").textContent = "Live";
    setMode("Standby");
    announce("Live guidance stopped.", "low");
    return;
  }
  document.querySelector("#toggleLive").textContent = "Stop";
  announce("Live guidance started.", "medium");
  state.liveTimer = setInterval(async () => {
    if (state.liveBusy) return;
    state.liveBusy = true;
    try {
      await runNavigation();
    } catch (error) {
      showError(error);
    } finally {
      state.liveBusy = false;
    }
  }, 1600);
}

async function startCamera() {
  initAudio();
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" },
      audio: false,
    });
    els.camera.srcObject = state.stream;
    await els.camera.play();
    els.cameraFallback.classList.add("hidden");
    els.cameraFallback.classList.remove("demo-active");
    els.cameraFallback.style.backgroundImage = "";
    clearOverlay();
    announce("Camera started.", "low");
    setTimeout(() => runNavigation().catch(showError), 450);
  } catch {
    els.cameraFallback.textContent = "Camera unavailable. Demo frame is ready.";
    captureFrame();
    announce("Camera unavailable. Demo mode is ready.", "low");
    runNavigation().catch(showError);
  }
}

async function runCommand(text = "") {
  initAudio();
  const command = (text || els.commandInput.value).trim();
  if (!command) {
    announce("Type or speak a command first.", "low");
    return;
  }
  els.commandInput.value = command;
  const result = await postJson("/api/command", { command });
  await applyCommand(result);
}

async function applyCommand(command) {
  announce(command.speech, command.intent === "stop" ? "high" : "medium");
  if (command.target) els.targetObject.value = command.target;

  switch (command.intent) {
    case "find":
      await runObject();
      break;
    case "micro":
      await runMicro();
      break;
    case "navigate":
      await runNavigation();
      break;
    case "task":
      els.customTask.value = command.task || "";
      await planTask(command.task);
      break;
    case "task_next":
      if (state.taskSteps[state.stepIndex]) state.taskSteps[state.stepIndex].completed = true;
      state.stepIndex = Math.min(state.taskSteps.length - 1, state.stepIndex + 1);
      renderSteps();
      break;
    case "task_previous":
      state.stepIndex = Math.max(0, state.stepIndex - 1);
      renderSteps();
      break;
    case "task_repeat":
      announce(currentTaskStatus(), "medium");
      break;
    case "tag":
      els.landmarkName.value = command.name || "";
      els.landmarkNote.focus();
      break;
    case "ocr":
      await runOcr();
      break;
    case "scene":
      await runScene();
      break;
    case "social":
      await runSocial();
      break;
    case "inquiry":
      await runInquiry(command.question);
      break;
    case "stop":
      window.speechSynthesis?.cancel();
      navigator.vibrate?.(0);
      if (state.liveTimer) toggleLive();
      clearTaskState();
      break;
    default:
      break;
  }
}

function listenForCommand() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    announce("Voice command is not supported in this browser.", "low");
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.addEventListener("result", (event) => {
    const text = event.results[0][0].transcript;
    announce(`Heard: ${text}`, "low");
    runCommand(text).catch(showError);
  });
  recognition.start();
}

function showError(error) {
  announce(error.message, "high");
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    els.serviceStatus.textContent = health.ok ? "Ready" : "Offline";
    if (health.model_profile) els.modelStatus.textContent = health.model_profile;
    if (health.ok) setMode("Standby");
  } catch {
    els.serviceStatus.textContent = "Offline";
  }
}

function renderModelStatus(status) {
  els.modelStatus.textContent = status.active_profile || status.mode || "Local";
  const rows = Object.entries(status.adapters || {}).map(([name, adapter]) => ({
    name,
    provider: adapter.provider,
    status: adapter.status,
    available: adapter.available,
    configured: adapter.configured,
  }));
  setResult(els.modelDetails, {
    profile: status.active_profile,
    mode: status.mode,
    adapters: rows,
    note: status.note,
  });
}

async function checkModelStatus() {
  try {
    const response = await fetch("/api/model/status");
    if (!response.ok) return;
    renderModelStatus(await response.json());
  } catch {
    els.modelStatus.textContent = "Local";
  }
}

function setupInstallPrompt() {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    state.installPrompt = event;
    if (els.installApp) {
      els.installApp.hidden = false;
      els.installApp.textContent = "Install";
    }
    if (els.installHint) {
      els.installHint.textContent = "Install VISIO-NETRA to launch it full-screen from your home screen.";
    }
  });

  window.addEventListener("appinstalled", () => {
    state.installPrompt = null;
    if (els.installApp) els.installApp.hidden = true;
    if (els.installHint) els.installHint.textContent = "VISIO-NETRA is installed.";
  });
}

async function installApp() {
  if (!state.installPrompt) {
    announce("Use your browser menu to add VISIO-NETRA to the home screen.", "low");
    return;
  }
  state.installPrompt.prompt();
  await state.installPrompt.userChoice;
  state.installPrompt = null;
  if (els.installApp) els.installApp.hidden = true;
}

function bindEvents() {
  document.querySelector("#startCamera").addEventListener("click", startCamera);
  document.querySelector("#captureFrame").addEventListener("click", () => {
    captureFrame({ advanceDemo: true });
    runNavigation({ useLastFrame: true }).catch(showError);
  });
  document.querySelector("#toggleLive").addEventListener("click", toggleLive);
  document.querySelector("#voiceCommand").addEventListener("click", listenForCommand);
  document.querySelector("#voiceCommandPanel").addEventListener("click", listenForCommand);
  document.querySelector("#runCommand").addEventListener("click", () => runCommand().catch(showError));
  document.querySelectorAll("[data-command]").forEach((button) => {
    button.addEventListener("click", () => {
      const command = button.dataset.command || "";
      els.commandInput.value = command;
      runCommand(command).catch(showError);
    });
  });
  els.commandInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") runCommand().catch(showError);
  });
  document.querySelector("#stopSpeech").addEventListener("click", () => {
    window.speechSynthesis?.cancel();
    navigator.vibrate?.(0);
  });
  document.querySelector("#runNavigation").addEventListener("click", () => runNavigation().catch(showError));
  document.querySelector("#runNavigationPanel")?.addEventListener("click", () => runNavigation().catch(showError));
  document.querySelector("#runObject").addEventListener("click", () => runObject().catch(showError));
  document.querySelector("#runMicro").addEventListener("click", () => runMicro().catch(showError));
  document.querySelector("#runScene").addEventListener("click", () => runScene().catch(showError));
  document.querySelector("#runOcr").addEventListener("click", () => runOcr().catch(showError));
  document.querySelector("#runSocial").addEventListener("click", () => runSocial().catch(showError));
  document.querySelector("#speakManual").addEventListener("click", () => announce(els.manualText.value, "medium"));
  document.querySelector("#planTask").addEventListener("click", () => planTask().catch(showError));
  document.querySelector("#verifyStep").addEventListener("click", () => verifyStep().catch(showError));
  document.querySelector("#prevStep").addEventListener("click", () => {
    state.stepIndex = Math.max(0, state.stepIndex - 1);
    renderSteps();
  });
  document.querySelector("#nextStep").addEventListener("click", () => {
    if (state.taskSteps[state.stepIndex]) state.taskSteps[state.stepIndex].completed = true;
    state.stepIndex = Math.min(state.taskSteps.length - 1, state.stepIndex + 1);
    renderSteps();
  });
  els.taskSelect.addEventListener("change", () => {
    state.activeTask = els.taskSelect.value;
    state.taskTitle = els.taskSelect.options[els.taskSelect.selectedIndex]?.textContent || state.activeTask;
    els.customTask.value = "";
    state.stepIndex = 0;
    state.taskSteps = fallbackPlan(state.activeTask);
    renderSteps();
  });
  document.querySelector("#saveLandmark").addEventListener("click", () => saveLandmark().catch(showError));
  document.querySelector("#clearLandmarks").addEventListener("click", () => clearLandmarks().catch(showError));
  els.installApp?.addEventListener("click", () => installApp().catch(showError));
}

setupInstallPrompt();
bindEvents();
if (!loadTaskState()) {
  state.taskSteps = fallbackPlan(state.activeTask);
  state.taskTitle = els.taskSelect.options[els.taskSelect.selectedIndex]?.textContent || "Make tea";
}
renderSteps({ persist: false });
renderLandmarks();
checkHealth();
checkModelStatus();
loadMemoryFromServer();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/service-worker.js").catch(() => {});
}
