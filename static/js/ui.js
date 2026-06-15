export const UI = {
  camera: document.getElementById("camera"),
  announcer: document.getElementById("announcer"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  modeText: document.getElementById("modeText"),
  targetText: document.getElementById("targetText"),
  headingText: document.getElementById("headingText"),
  feedback: document.getElementById("mainFeedback"),
  vector: document.getElementById("guideVector"),
  vectorDot: document.querySelector("#guideVector span"),
  taskPanel: document.getElementById("taskPanel"),
  taskList: document.getElementById("taskList"),
  taskFeedback: document.getElementById("taskFeedback"),
  detailsPanel: document.getElementById("detailsPanel"),
  sceneText: document.getElementById("sceneText"),
  socialCue: document.getElementById("socialCue"),
  envCue: document.getElementById("envCue"),
  distanceText: document.getElementById("distanceText"),
  directionText: document.getElementById("directionText"),
  latencyText: document.getElementById("latencyText"),
  objectCount: document.getElementById("objectCount"),
  objectList: document.getElementById("objectList"),
  toggleBtn: document.getElementById("toggleBtn"),
  askBtn: document.getElementById("askBtn"),
  findBtn: document.getElementById("findBtn"),
  readBtn: document.getElementById("readBtn"),
  detailsBtn: document.getElementById("detailsBtn")
};

export function setStatus(text, type = "") {
  UI.statusText.textContent = text;
  UI.statusDot.className = `status-dot ${type}`;
  announce(text);
}

export function setMode(mode, target = "") {
  const labels = {
    navigation: "Navigation",
    object_find: "Finding",
    precision: "Precision",
    task: "Task",
    ocr: "Reading"
  };
  UI.modeText.textContent = labels[mode] || mode;
  UI.targetText.textContent = target || "";
}

export function showFeedback(text) {
  UI.feedback.textContent = text || "";
  UI.feedback.classList.toggle("long", Boolean(text && text.length > 36));
  UI.feedback.classList.toggle("visible", Boolean(text));
  clearTimeout(showFeedback.timer);
  if (text) {
    showFeedback.timer = setTimeout(() => {
      UI.feedback.classList.remove("visible");
    }, text.length > 36 ? 2600 : 1500);
  }
  if (text) announce(text);
}

export function updateNavigation(data) {
  hideVector();
  const priority = data.priority || "low";
  if (priority === "critical") setStatus("Critical", "error");
  else setStatus("Scanning", "active");
  UI.sceneText.textContent = data.scene || "Initializing...";
  UI.distanceText.textContent = data.distance ? formatDistance(data.distance) : "--";
  UI.directionText.textContent = directionToClock(data.direction);
  UI.latencyText.textContent = formatLatency(data.latency_ms || data.ms);
  updateCue(UI.socialCue, formatSocial(data.social || data.social_cues));
  updateCue(UI.envCue, formatEnvironment(data.environment), true);
  const objects = Array.isArray(data.objects) ? data.objects : [];
  UI.objectCount.textContent = String(objects.length);
  UI.objectList.innerHTML = objects.map((obj) => {
    const meta = obj.distance ? formatDistance(obj.distance) : confidenceText(obj.confidence);
    return `<li><span>${escapeHtml(obj.name)}</span><span>${escapeHtml(meta || "undefined")}</span></li>`;
  }).join("") || '<li><span>Scanning</span><span>--</span></li>';
  if (data.subject) {
    showFeedback(priority === "critical" ? `STOP: ${data.subject}` : data.subject);
  }
}

export function updateObjectGuidance(data) {
  setStatus(data.centered ? "Aligned" : data.visible ? "Guiding" : "Searching", data.visible ? "active" : "");
  showFeedback(data.speech || (data.visible ? "Move to center" : "Not visible"));
  UI.sceneText.textContent = data.visible
    ? `${data.target || "Target"} visible. ${data.speech || "Move to center."}`
    : `Searching for ${data.target || "target"}...`;
  UI.distanceText.textContent = data.centered ? "near" : data.visible ? "seen" : "--";
  UI.directionText.textContent = vectorToClock(data.x, data.y);
  UI.latencyText.textContent = formatLatency(data.latency_ms || data.ms);
  UI.objectCount.textContent = data.visible ? "1" : "0";
  UI.objectList.innerHTML = data.visible
    ? `<li><span>${escapeHtml(data.target || "target")}</span><span>${escapeHtml(confidenceText(data.confidence) || "seen")}</span></li>`
    : '<li><span>Searching</span><span>--</span></li>';
  UI.vector.classList.add("visible");
  UI.vector.classList.toggle("locked", Boolean(data.centered));
  const x = Math.max(-100, Math.min(100, Number(data.x) || 0));
  const y = Math.max(-100, Math.min(100, Number(data.y) || 0));
  UI.vectorDot.style.transform = `translate(calc(-50% + ${x * 0.8}px), calc(-50% + ${-y * 0.8}px))`;
}

export function updateOcr(data) {
  hideVector();
  setStatus("Text read", "active");
  showFeedback(data.speech || "No text found");
  UI.sceneText.textContent = data.text || "No reliable text found.";
  UI.latencyText.textContent = formatLatency(data.latency_ms || data.ms);
}

export function updateTask(data) {
  UI.taskPanel.hidden = false;
  const plan = Array.isArray(data.plan) ? data.plan : [];
  UI.taskList.innerHTML = plan.map((step, index) => {
    const cls = index < data.current_step_index ? "done" : index === data.current_step_index ? "active" : "";
    return `<li class="${cls}">${escapeHtml(step.instruction || "")}</li>`;
  }).join("");
  UI.taskFeedback.textContent = data.visual_feedback || "";
}

export function toggleDetails() {
  UI.detailsPanel.hidden = !UI.detailsPanel.hidden;
}

export function hideVector() {
  UI.vector.classList.remove("visible", "locked");
}

export function announce(text) {
  UI.announcer.textContent = text || "";
}

export function updateHeading(heading) {
  UI.headingText.textContent = `${Math.round(Number(heading) || 0)}°`;
}

function formatDistance(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "--";
  return n < 1 ? `${Math.round(n * 100)} cm` : `${n.toFixed(1)} m`;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function updateCue(node, text, warning = false) {
  if (!text) {
    node.hidden = true;
    node.textContent = "";
    return;
  }
  node.hidden = false;
  node.classList.toggle("warning", warning);
  node.textContent = text;
}

function formatSocial(social) {
  if (!social || social.intent === "none") return "";
  return `Social: ${social.details || social.intent}`;
}

function formatEnvironment(environment) {
  if (!environment) return "";
  const detail = environment.details || environment.affordance || environment.state;
  if (!detail || detail === "unknown") return "";
  return `Environment: ${detail}`;
}

function confidenceText(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "";
  return n > 1 ? `${Math.round(n)}%` : `${Math.round(n * 100)}%`;
}

function formatLatency(value) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? `${Math.round(n)}ms` : "--";
}

function directionToClock(direction) {
  const text = String(direction || "").toLowerCase();
  if (!text || text === "ahead") return "12";
  if (text.includes("left") && text.includes("upper")) return "10";
  if (text.includes("right") && text.includes("upper")) return "2";
  if (text.includes("left") && text.includes("lower")) return "8";
  if (text.includes("right") && text.includes("lower")) return "4";
  if (text.includes("left")) return "9";
  if (text.includes("right")) return "3";
  if (text.includes("behind")) return "6";
  return text;
}

function vectorToClock(xValue, yValue) {
  const x = Number(xValue) || 0;
  const y = Number(yValue) || 0;
  if (Math.abs(x) < 18 && Math.abs(y) < 18) return "12";
  if (Math.abs(x) > Math.abs(y)) return x < 0 ? "9" : "3";
  return y > 0 ? "12" : "6";
}
