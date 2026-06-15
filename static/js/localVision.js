import { STATE } from "./config.js";

const MODEL_SCRIPTS = [
  "https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.22.0/dist/tf.min.js",
  "https://cdn.jsdelivr.net/npm/@tensorflow-models/coco-ssd@2.2.3/dist/coco-ssd.min.js"
];

const COCO_CLASSES = new Set([
  "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
  "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
  "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
  "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
  "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
  "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
  "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
  "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
  "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
  "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
  "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
  "hair drier", "toothbrush"
]);

const ALIASES = {
  mug: "cup",
  glass: "cup",
  tumbler: "cup",
  phone: "cell phone",
  mobile: "cell phone",
  cellphone: "cell phone",
  sofa: "couch",
  settee: "couch",
  television: "tv",
  bag: "handbag",
  plant: "potted plant",
  table: "dining table"
};

let modelPromise = null;
let model = null;

export function canTryLocalObjectFind(target) {
  return Boolean(normalizeTarget(target));
}

export async function findObjectInFrame(video, target) {
  const wanted = normalizeTarget(target);
  if (!wanted) {
    return unsupportedTargetResult(target);
  }
  if (!model && !modelPromise) {
    loadModel();
    return {
      handled: true,
      type: "object_find_result",
      mode: "object_find",
      target,
      visible: false,
      centered: false,
      x: 0,
      y: 0,
      confidence: 0,
      haptic_strength: 0,
      speech: "Loading local detector",
      local: true
    };
  }
  const detector = await loadModel();
  if (!detector) {
    return {
      handled: true,
      type: "object_find_result",
      mode: "object_find",
      target,
      visible: false,
      centered: false,
      x: 0,
      y: 0,
      confidence: 0,
      haptic_strength: 0,
      speech: "Local detector is still loading.",
      local: true
    };
  }

  const predictions = await detector.detect(video);
  const match = predictions
    .filter((item) => item.class === wanted && item.score >= 0.35)
    .sort((a, b) => b.score - a.score)[0];

  if (!match) {
    return {
      handled: true,
      type: "object_find_result",
      mode: "object_find",
      target,
      visible: false,
      centered: false,
      x: 0,
      y: 0,
      confidence: 0,
      haptic_strength: 0,
      speech: `Searching for ${target}`,
      local: true
    };
  }

  const [left, top, width, height] = match.bbox;
  const centerX = left + width / 2;
  const centerY = top + height / 2;
  const frameW = video.videoWidth || video.clientWidth || 1;
  const frameH = video.videoHeight || video.clientHeight || 1;
  const x = clamp(((centerX - frameW / 2) / (frameW / 2)) * 100, -100, 100);
  const y = clamp(-((centerY - frameH / 2) / (frameH / 2)) * 100, -100, 100);
  const distance = Math.sqrt(x * x + y * y);
  const centered = Math.abs(x) < 18 && Math.abs(y) < 18;
  const haptic = centered ? 1 : 1 - Math.min(1, distance / 140);

  return {
    handled: true,
    type: "object_find_result",
    mode: "object_find",
    target,
    visible: true,
    centered,
    x: Math.round(x),
    y: Math.round(y),
    confidence: Math.round(match.score * 100),
    haptic_strength: Number(haptic.toFixed(2)),
    speech: centered ? `${target} centered` : guidanceFromVector(x, y),
    bbox: match.bbox,
    local: true
  };
}

export function unsupportedTargetResult(target) {
  return {
    handled: true,
    type: "object_find_result",
    mode: "object_find",
    target,
    visible: false,
    centered: false,
    x: 0,
    y: 0,
    confidence: 0,
    haptic_strength: 0,
    speech: `I cannot find ${target} with the no-key detector. Try cup, bottle, chair, person, phone, laptop, book, or bag.`,
    local: true,
    unsupported: true
  };
}

async function loadModel() {
  if (model) return model;
  if (!modelPromise) {
    modelPromise = (async () => {
      for (const src of MODEL_SCRIPTS) {
        await loadScript(src);
      }
      if (!window.cocoSsd) return null;
      model = await window.cocoSsd.load({ base: "lite_mobilenet_v2" });
      return model;
    })().catch(() => null);
  }
  return modelPromise;
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      existing.addEventListener("load", resolve, { once: true });
      existing.addEventListener("error", reject, { once: true });
      if (src.includes("tfjs") && window.tf) resolve();
      if (src.includes("coco-ssd") && window.cocoSsd) resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

function normalizeTarget(target) {
  const clean = String(target || "").trim().toLowerCase();
  const normalized = ALIASES[clean] || clean;
  return COCO_CLASSES.has(normalized) ? normalized : "";
}

function guidanceFromVector(x, y) {
  if (Math.abs(x) > Math.abs(y)) {
    return x < 0 ? "Move left" : "Move right";
  }
  return y < 0 ? "Move down" : "Move up";
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}
