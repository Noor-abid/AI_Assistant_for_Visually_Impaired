import { CONFIG, STATE } from "./config.js";
import { setupInputs } from "./input.js";
import { findObjectInFrame, unsupportedTargetResult } from "./localVision.js";
import { connectSocket, closeSocket, handleServerMessage, sendFrame, sendHeading } from "./network.js";
import { speakStatus } from "./speech.js";
import { setStatus, showFeedback, UI, updateHeading } from "./ui.js";

setupInputs();

window.addEventListener("socket-ready", restartLoop);
window.addEventListener("vision-mode-change", restartLoop);
window.addEventListener("deviceorientation", (event) => {
  const heading = event.webkitCompassHeading || (event.alpha ? 360 - event.alpha : 0);
  STATE.heading = Math.round(heading || 0);
  updateHeading(STATE.heading);
  sendHeading(STATE.heading);
});

export async function toggleSystem() {
  if (STATE.active) stopSystem();
  else await startSystem();
}

export async function startSystem() {
  try {
    STATE.stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1920 },
        height: { ideal: 1080 },
        frameRate: { ideal: 30, max: 60 }
      },
      audio: false
    });
    UI.camera.srcObject = STATE.stream;
    await new Promise((resolve) => {
      UI.camera.onloadedmetadata = resolve;
    });
    STATE.active = true;
    UI.toggleBtn.textContent = "Stop";
    setStatus("Connecting", "active");
    showFeedback("Ready");
    speakStatus("Camera started. Guidance will be spoken aloud.");
    requestWakeLock();
    connectSocket();
  } catch {
    try {
      STATE.stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      UI.camera.srcObject = STATE.stream;
      await new Promise((resolve) => {
        UI.camera.onloadedmetadata = resolve;
      });
      STATE.active = true;
      UI.toggleBtn.textContent = "Stop";
      setStatus("Connecting", "active");
      showFeedback("Ready");
      speakStatus("Camera started.");
      requestWakeLock();
      connectSocket();
    } catch {
      setStatus("Camera blocked", "error");
      showFeedback("Camera blocked");
      speakStatus("Camera permission is blocked.");
    }
  }
}

export function stopSystem() {
  STATE.active = false;
  clearInterval(STATE.loop);
  STATE.loop = null;
  closeSocket();
  if (STATE.stream) {
    STATE.stream.getTracks().forEach((track) => track.stop());
    STATE.stream = null;
  }
  UI.camera.srcObject = null;
  UI.toggleBtn.textContent = "Start";
  setStatus("Ready", "");
  showFeedback("Stopped");
  speakStatus("Stopped.");
}

export function restartLoop() {
  if (!STATE.active) return;
  clearInterval(STATE.loop);
  const interval = CONFIG.intervals[STATE.mode] || CONFIG.intervals.navigation;
  STATE.loop = setInterval(captureAndSendFrame, interval);
  captureAndSendFrame();
}

export function captureDataUrl() {
  const canvas = drawCameraFrame(CONFIG.imgWidth);
  return canvas ? canvas.toDataURL("image/jpeg", 0.62) : "";
}

function captureAndSendFrame() {
  if (STATE.mode === "object_find" && STATE.target) {
    captureLocalObjectFind();
    return;
  }
  const canvas = drawCameraFrame(CONFIG.imgWidth);
  if (!canvas) return;
  canvas.toBlob((blob) => sendFrame(blob), "image/jpeg", CONFIG.jpegQuality);
}

async function captureLocalObjectFind() {
  const started = performance.now();
  try {
    const result = await findObjectInFrame(UI.camera, STATE.target);
    if (result.handled) {
      result.latency_ms = performance.now() - started;
      handleServerMessage(result);
      return;
    }
  } catch {
    const result = unsupportedTargetResult(STATE.target);
    result.speech = "Local detector is unavailable. Check internet once to load the no-key detector.";
    result.latency_ms = performance.now() - started;
    handleServerMessage(result);
    return;
  }
  const result = unsupportedTargetResult(STATE.target);
  result.latency_ms = performance.now() - started;
  handleServerMessage(result);
}

async function requestWakeLock() {
  try {
    if ("wakeLock" in navigator) {
      await navigator.wakeLock.request("screen");
    }
  } catch {
    // Wake lock is best-effort and unavailable on some browsers.
  }
}

function drawCameraFrame(width) {
  if (!UI.camera.videoWidth || !UI.camera.videoHeight) return null;
  const ratio = UI.camera.videoHeight / UI.camera.videoWidth;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = Math.round(width * ratio);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(UI.camera, 0, 0, canvas.width, canvas.height);
  return canvas;
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {});
  });
}
