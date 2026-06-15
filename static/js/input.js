import { STATE } from "./config.js";
import { captureDataUrl, toggleSystem } from "./main.js";
import { sendInquiry, sendMode, sendTaskControl } from "./network.js";
import { speakStatus } from "./speech.js";
import { setStatus, showFeedback, toggleDetails, UI } from "./ui.js";

export function setupInputs() {
  UI.toggleBtn.addEventListener("click", toggleSystem);
  UI.findBtn.addEventListener("click", startObjectFind);
  UI.readBtn.addEventListener("click", () => sendMode("ocr"));
  UI.detailsBtn.addEventListener("click", toggleDetails);

  UI.askBtn.addEventListener("pointerdown", startRecording);
  UI.askBtn.addEventListener("pointerup", stopRecording);
  UI.askBtn.addEventListener("pointercancel", stopRecording);
  UI.askBtn.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") startRecording();
  });
  UI.askBtn.addEventListener("keyup", (event) => {
    if (event.key === "Enter" || event.key === " ") stopRecording();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      sendTaskControl("cancel");
      sendMode("navigation");
    }
  });
}

function startObjectFind() {
  if (!STATE.active) {
    showFeedback("Start camera first");
    speakStatus("Start the camera first.");
    return;
  }
  listenForFindTarget();
}

function listenForFindTarget() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setStatus("Voice unavailable", "error");
    showFeedback("Voice unavailable");
    speakStatus("Speech recognition is not available in this browser. Use Chrome or Edge for voice object search.");
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = navigator.language || "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 3;

  recognition.onstart = () => {
    setStatus("Listening", "active");
    showFeedback("Say object");
    speakStatus("Say the object to find.");
  };

  recognition.onerror = () => {
    setStatus("Try again", "error");
    showFeedback("Try again");
    speakStatus("I did not catch that. Tap Find and say the object again.");
  };

  recognition.onresult = (event) => {
    const transcript = Array.from(event.results?.[0] || [])
      .map((item) => item.transcript)
      .find(Boolean);
    const target = cleanFindTarget(transcript);
    if (!target) {
      speakStatus("I did not hear an object name.");
      return;
    }
    beginObjectFind(target);
  };

  recognition.onend = () => {
    if (STATE.mode !== "object_find") setStatus("Scanning", "active");
  };

  recognition.start();
}

function beginObjectFind(target) {
  sendMode("object_find", target);
  showFeedback(`Finding ${target}`);
  speakStatus(`Searching for ${target}.`);
}

function cleanFindTarget(text) {
  const cleaned = String(text || "")
    .toLowerCase()
    .replace(/\b(find|search|for|the|a|an|please|look|locate)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const corrections = {
    cops: "cups",
    cub: "cup",
    cap: "cup",
    class: "glass",
    classes: "glass",
    bottle: "bottle",
    bottles: "bottle",
    chairs: "chair",
    persons: "person",
    people: "person",
    phones: "phone",
    mobiles: "phone"
  };
  return corrections[cleaned] || cleaned;
}

async function startRecording() {
  if (STATE.recording || !STATE.active) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    STATE.audioChunks = [];
    STATE.mediaRecorder = new MediaRecorder(stream);
    STATE.mediaRecorder.addEventListener("dataavailable", (event) => {
      if (event.data?.size) STATE.audioChunks.push(event.data);
    });
    STATE.mediaRecorder.start();
    STATE.recording = true;
    setStatus("Listening", "active");
    showFeedback("Listening");
  } catch {
    setStatus("Mic blocked", "error");
    showFeedback("Mic blocked");
  }
}

function stopRecording() {
  if (!STATE.recording || !STATE.mediaRecorder) return;
  STATE.recording = false;
  setStatus("Thinking", "active");
  showFeedback("Thinking");
  const recorder = STATE.mediaRecorder;
  recorder.addEventListener("stop", () => {
    const blob = new Blob(STATE.audioChunks, { type: "audio/webm" });
    const reader = new FileReader();
    reader.onloadend = () => {
      sendInquiry(captureDataUrl(), reader.result);
    };
    reader.readAsDataURL(blob);
    recorder.stream.getTracks().forEach((track) => track.stop());
  }, { once: true });
  recorder.stop();
}
