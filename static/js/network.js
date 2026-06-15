import { STATE } from "./config.js";
import { errorPulse, guidePulse, modePulse, successPulse } from "./haptics.js";
import { speak, speakGuidance, speakStatus } from "./speech.js";
import {
  setMode,
  setStatus,
  showFeedback,
  updateNavigation,
  updateObjectGuidance,
  updateOcr,
  updateTask
} from "./ui.js";

export function connectSocket() {
  if (!STATE.active) return;
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  STATE.ws = new WebSocket(`${proto}//${location.host}/ws`);

  STATE.ws.onopen = () => {
    STATE.wsRetries = 0;
    setStatus("Scanning", "active");
    window.dispatchEvent(new CustomEvent("socket-ready"));
  };

  STATE.ws.onmessage = (event) => {
    try {
      handleMessage(JSON.parse(event.data));
    } catch {
      setStatus("Message error", "error");
      errorPulse();
    }
  };

  STATE.ws.onclose = () => {
    if (!STATE.active) return;
    setStatus("Reconnecting", "error");
    const delay = Math.min(5000, 700 * Math.pow(1.5, STATE.wsRetries++));
    setTimeout(connectSocket, delay);
  };

  STATE.ws.onerror = () => {
    setStatus("Connection error", "error");
    errorPulse();
  };
}

export function closeSocket() {
  if (!STATE.ws) return;
  STATE.ws.onclose = null;
  STATE.ws.close();
  STATE.ws = null;
}

export function sendFrame(blob) {
  if (STATE.ws?.readyState === WebSocket.OPEN && blob) {
    STATE.ws.send(blob);
  }
}

export function sendMode(mode, target = "") {
  sendJson({ type: "mode", mode, target });
}

export function sendInquiry(image, audio, text = "") {
  sendJson({ type: "inquiry", image, audio, text });
}

export function sendTaskControl(action) {
  sendJson({ type: "task_control", action });
}

export function sendHeading(heading) {
  sendJson({ type: "heading", heading });
}

export function sendModelKey(key) {
  sendJson({ type: "model_key", key });
}

export function handleServerMessage(data) {
  handleMessage(data);
}

function sendJson(data) {
  if (STATE.ws?.readyState === WebSocket.OPEN) {
    STATE.ws.send(JSON.stringify(data));
  }
}

function handleMessage(data) {
  notifyMissingModelKey(data);

  const nextTarget = data.target || "";
  const modeChanged = data.mode && (data.mode !== STATE.mode || nextTarget !== STATE.target);
  if (modeChanged) {
    STATE.mode = data.mode;
    STATE.target = nextTarget;
    setMode(STATE.mode, STATE.target);
    modePulse();
    window.dispatchEvent(new CustomEvent("vision-mode-change"));
  }

  switch (data.type) {
    case "status":
      if (data.status === "connected") setStatus("Connected", "active");
      if (data.status === "connected") speakStatus("Camera assistant connected.");
      if (data.status === "model_key_ready") speakStatus("Vision model connected.");
      break;
    case "result":
      updateNavigation(data);
      break;
    case "object_find_result":
    case "precision_result":
      updateObjectGuidance(data);
      guidePulse(data.haptic_strength, data.centered);
      if (data.speech) {
        speakGuidance(data.speech, `find:${data.target || ""}`, data.centered ? 0 : 1200);
      }
      break;
    case "ocr_result":
      updateOcr(data);
      successPulse();
      break;
    case "task_update":
      updateTask(data);
      break;
    case "inquiry_result":
      setMode(data.mode || STATE.mode, data.target || STATE.target);
      break;
    case "speak":
      speak(data.text);
      break;
    case "error":
      setStatus("Error", "error");
      showFeedback(data.message || "Error");
      speak(data.message || "Error");
      errorPulse();
      break;
  }
}

function notifyMissingModelKey(data) {
  if (!data.needs_model_key || data.local || STATE.keyPrompted) return;
  STATE.keyPrompted = true;
  const message = "Advanced vision is not configured. Common object finding still works without a key.";
  showFeedback("Advanced vision off");
  speakStatus(message);
}
