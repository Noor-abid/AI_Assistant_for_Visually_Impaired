from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import math
import mimetypes
import os
import shlex
import shutil
import struct
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
MEMORY_FILE = ROOT / "visio_netra_memory.json"
HOST = os.environ.get("VISIO_AI_HOST", "127.0.0.1")
PORT = int(os.environ.get("VISIO_AI_PORT", "8765"))
WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_WS_MESSAGE_BYTES = 2_500_000
MAX_POST_BYTES = 3_500_000
MODEL_MODE = os.environ.get("VISIO_NETRA_MODEL_MODE", "local").strip().lower() or "local"
GEMINI_KEY = os.environ.get("GEMINI_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
YOLO_MODEL_PATH = os.environ.get("VISIO_NETRA_YOLO_MODEL", "").strip()
LLAVA_ENDPOINT = os.environ.get("VISIO_NETRA_LLAVA_ENDPOINT", "").strip()
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "").strip()
try:
    TESSERACT_TIMEOUT_SECONDS = float(os.environ.get("VISIO_NETRA_OCR_TIMEOUT", "8"))
except ValueError:
    TESSERACT_TIMEOUT_SECONDS = 8.0

TARGET_ALIASES = {
    "door": {"door", "gate", "entrance", "exit"},
    "handle": {"handle", "knob", "door handle"},
    "cup": {"cup", "mug", "glass", "bowl"},
    "bottle": {"bottle", "kettle", "flask"},
    "phone": {"phone", "mobile", "cellphone", "remote"},
    "laptop": {"laptop", "computer", "screen", "monitor"},
    "text": {"text", "label", "book", "paper", "document", "sign", "product label"},
    "person": {"person", "face", "human", "social subject"},
    "stairs": {"stairs", "stair", "staircase", "steps", "landing"},
    "handrail": {"handrail", "railing", "rail", "banister"},
}

TASK_LIBRARY = {
    "tea": ["Find the cup", "Locate the kettle", "Confirm water is poured", "Check the cup is safely placed"],
    "coffee": ["Find the mug", "Locate the coffee container", "Confirm water or milk is nearby", "Check the mug is stable"],
    "door": ["Face the nearest door", "Center the door handle", "Confirm the path is clear", "Approach slowly"],
    "label": ["Hold the product steady", "Center the label", "Read the text", "Confirm the item name"],
    "seat": ["Scan for a chair or bench", "Check if the seat appears occupied", "Locate the front edge", "Sit only after touch confirmation"],
    "elevator": ["Find the elevator panel", "Center the button area", "Use precision mode for the target button", "Confirm the door area is clear"],
    "stairs": ["Stop before moving forward", "Locate the handrail", "Find the first step edge", "Move one step at a time after physical confirmation"],
    "medicine": ["Center the medicine label", "Read the label text", "Confirm the medicine name aloud", "Ask for human confirmation before taking it"],
}


def split_command(command: str) -> list[str]:
    if not command.strip():
        return []
    try:
        return shlex.split(command)
    except ValueError:
        return [command.strip()]


def executable_available(command_parts: list[str]) -> bool:
    if not command_parts:
        return False
    executable = command_parts[0]
    return Path(executable).exists() or shutil.which(executable) is not None


def tesseract_command_parts() -> list[str]:
    if TESSERACT_CMD:
        return split_command(TESSERACT_CMD)
    found = shutil.which("tesseract")
    return [found] if found else []


def model_adapter_status() -> dict[str, Any]:
    def module_available(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except ModuleNotFoundError:
            return False

    google_genai_available = module_available("google.genai")
    ultralytics_available = module_available("ultralytics")
    yolo_path_exists = bool(YOLO_MODEL_PATH and Path(YOLO_MODEL_PATH).exists())
    tesseract_parts = tesseract_command_parts()
    tesseract_ready = executable_available(tesseract_parts)
    requested_cloud = MODEL_MODE in {"gemini", "hybrid", "cloud"}

    adapters = {
        "navigation_vlm": {
            "provider": "Gemini or LLaVA",
            "configured": bool(GEMINI_KEY or LLAVA_ENDPOINT),
            "available": bool((GEMINI_KEY and google_genai_available) or LLAVA_ENDPOINT),
            "status": "ready"
            if (GEMINI_KEY and google_genai_available) or LLAVA_ENDPOINT
            else "key_set_missing_package"
            if GEMINI_KEY and not google_genai_available
            else "endpoint_configured"
            if LLAVA_ENDPOINT
            else "not_configured",
        },
        "object_detector": {
            "provider": "YOLOv8 or compatible detector",
            "configured": bool(YOLO_MODEL_PATH),
            "available": bool(ultralytics_available and yolo_path_exists),
            "status": "ready"
            if ultralytics_available and yolo_path_exists
            else "model_path_missing"
            if YOLO_MODEL_PATH and not yolo_path_exists
            else "package_missing"
            if YOLO_MODEL_PATH and yolo_path_exists and not ultralytics_available
            else "not_configured",
        },
        "ocr_engine": {
            "provider": "Browser TextDetector or local Tesseract",
            "configured": bool(TESSERACT_CMD or tesseract_parts),
            "available": tesseract_ready,
            "status": "ready"
            if tesseract_ready
            else "configured_command_missing"
            if TESSERACT_CMD
            else "browser_fallback_only",
        },
    }
    active = "local-demo"
    if requested_cloud and adapters["navigation_vlm"]["available"]:
        active = "hybrid-vlm-ready" if MODEL_MODE == "hybrid" else "cloud-vlm-ready"
    elif requested_cloud:
        active = "local-demo-cloud-not-ready"

    return {
        "mode": MODEL_MODE,
        "active_profile": active,
        "adapters": adapters,
        "local_capabilities": [
            "heuristic object guidance",
            "scene statistics",
            "hazard cues",
            "risk scoring",
            "next-action guidance",
            "memory palace",
            "command parsing",
            "visual inquiry",
            "task planning",
        ],
        "environment": {
            "VISIO_NETRA_MODEL_MODE": MODEL_MODE,
            "GEMINI_KEY": "set" if GEMINI_KEY else "not_set",
            "VISIO_NETRA_YOLO_MODEL": YOLO_MODEL_PATH or "not_set",
            "VISIO_NETRA_LLAVA_ENDPOINT": LLAVA_ENDPOINT or "not_set",
            "TESSERACT_CMD": TESSERACT_CMD or "auto",
        },
        "note": "Default local mode makes no cloud requests. Configure adapters explicitly before production AI calls.",
    }


def empty_memory() -> dict[str, Any]:
    return {"locations": [], "history": []}


def load_memory() -> dict[str, Any]:
    if not MEMORY_FILE.exists():
        return empty_memory()
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_memory()
    locations = data.get("locations", [])
    history = data.get("history", [])
    return {
        "locations": locations if isinstance(locations, list) else [],
        "history": history if isinstance(history, list) else [],
    }


def save_memory(data: dict[str, Any]) -> None:
    safe = {
        "locations": data.get("locations", [])[-200:],
        "history": data.get("history", [])[-500:],
    }
    MEMORY_FILE.write_text(json.dumps(safe, indent=2), encoding="utf-8")


def normalize_landmark(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()[:80]
    note = str(payload.get("note", "")).strip()[:240]
    description = str(payload.get("description", "")).strip()[:500]
    if not name:
        raise ValueError("Landmark name is required.")
    return {
        "name": name,
        "note": note,
        "description": description,
        "createdAt": str(payload.get("createdAt", "")).strip() or datetime.now(timezone.utc).isoformat(),
    }


def save_landmark(payload: dict[str, Any]) -> dict[str, Any]:
    landmark = normalize_landmark(payload)
    memory = load_memory()
    locations = [item for item in memory["locations"] if item.get("name", "").lower() != landmark["name"].lower()]
    locations.append(landmark)
    memory["locations"] = locations
    save_memory(memory)
    return landmark


def clear_memory() -> dict[str, Any]:
    data = empty_memory()
    save_memory(data)
    return data


def persistent_landmarks() -> list[dict[str, Any]]:
    return load_memory().get("locations", [])


def merge_landmarks(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if name:
                merged[name.lower()] = item
    return list(merged.values())


def log_memory_sighting(subject: str, scene: str, location: dict[str, Any] | None = None) -> None:
    subject = subject.strip()[:80]
    if not subject:
        return
    memory = load_memory()
    history = memory["history"]
    entry = {
        "object": subject,
        "location": location.get("name") if location else None,
        "scene": scene[:500],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if history:
        last = history[-1]
        if last.get("object") == entry["object"] and last.get("scene") == entry["scene"]:
            return
    history.append(entry)
    memory["history"] = history[-500:]
    save_memory(memory)


@dataclass
class Guidance:
    distance: float
    direction: str
    pulse: str
    vibration_pattern: list[int]
    locked: bool


def decode_data_url(data_url: str) -> Image.Image:
    if not data_url or "," not in data_url:
        raise ValueError("Expected a browser data URL containing an image.")
    _, encoded = data_url.split(",", 1)
    raw = base64.b64decode(encoded)
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    image.thumbnail((960, 960))
    return image


def color_name(rgb: tuple[int, int, int]) -> str:
    palette = {
        "black": (20, 20, 20),
        "white": (238, 238, 232),
        "gray": (125, 125, 125),
        "red": (190, 45, 45),
        "green": (42, 145, 70),
        "blue": (55, 95, 190),
        "yellow": (220, 190, 40),
        "brown": (120, 75, 35),
        "orange": (220, 115, 35),
        "purple": (120, 70, 160),
    }
    return min(
        palette,
        key=lambda name: sum((rgb[i] - palette[name][i]) ** 2 for i in range(3)),
    )


def image_stats(image: Image.Image) -> dict[str, Any]:
    small = image.resize((64, 64))
    stat = ImageStat.Stat(small)
    mean_rgb = tuple(int(v) for v in stat.mean[:3])
    gray = np.asarray(small.convert("L"), dtype=np.float32)
    brightness = float(gray.mean())
    contrast = float(gray.std())
    return {
        "width": image.width,
        "height": image.height,
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "dominant_rgb": mean_rgb,
        "dominant_color": color_name(mean_rgb),
        "lighting": "bright" if brightness > 170 else "dim" if brightness < 75 else "moderate",
        "detail": "high" if contrast > 58 else "low" if contrast < 25 else "medium",
    }


def salient_box(image: Image.Image) -> dict[str, float]:
    gray_img = image.resize((160, 120)).convert("L")
    gray = np.asarray(gray_img, dtype=np.float32)
    median = float(np.median(gray))
    deviation = np.abs(gray - median)
    threshold = max(24.0, float(deviation.mean() + deviation.std()))
    mask = deviation > threshold

    if mask.sum() < 25:
        return {"x": 0.35, "y": 0.35, "w": 0.30, "h": 0.30, "confidence": 0.18}

    ys, xs = np.where(mask)
    x1, x2 = xs.min() / 160, (xs.max() + 1) / 160
    y1, y2 = ys.min() / 120, (ys.max() + 1) / 120
    area = float(mask.sum() / mask.size)
    confidence = min(0.95, max(0.25, area * 4))
    return {
        "x": round(float(x1), 3),
        "y": round(float(y1), 3),
        "w": round(float(x2 - x1), 3),
        "h": round(float(y2 - y1), 3),
        "confidence": round(confidence, 3),
    }


def box_center(box: dict[str, float]) -> tuple[float, float]:
    return box["x"] + box["w"] / 2, box["y"] + box["h"] / 2


def box_area(box: dict[str, float]) -> float:
    return max(0.0, box.get("w", 0.0) * box.get("h", 0.0))


def clock_position(box: dict[str, float]) -> str:
    cx, cy = box_center(box)
    dx = cx - 0.5
    dy = cy - 0.5
    if abs(dx) < 0.09 and abs(dy) < 0.09:
        return "center"
    if abs(dx) > abs(dy):
        return "9 o'clock" if dx < 0 else "3 o'clock"
    return "12 o'clock" if dy < 0 else "6 o'clock"


def region_name(box: dict[str, float]) -> str:
    cx, cy = box_center(box)
    horizontal = "left" if cx < 0.38 else "right" if cx > 0.62 else "center"
    vertical = "upper" if cy < 0.34 else "lower" if cy > 0.66 else "middle"
    if horizontal == "center" and vertical == "middle":
        return "center"
    if horizontal == "center":
        return vertical
    if vertical == "middle":
        return horizontal
    return f"{vertical} {horizontal}"


def distance_estimate(box: dict[str, float]) -> float:
    area = max(0.004, box_area(box))
    estimate = 0.35 + (1.0 / math.sqrt(area)) * 0.16
    return round(min(4.5, max(0.35, estimate)), 2)


def confidence_band(confidence: float) -> str:
    if confidence >= 0.78:
        return "high"
    if confidence >= 0.52:
        return "medium"
    return "low"


def normalize_target(target: str) -> str:
    words = target.strip().lower()
    for category, aliases in TARGET_ALIASES.items():
        if words in aliases or any(alias in words for alias in aliases):
            return category
    return "generic" if words else "generic"


def component_boxes(mask: np.ndarray, min_pixels: int = 18) -> list[dict[str, float]]:
    height, width = mask.shape
    visited = np.zeros(mask.shape, dtype=bool)
    boxes: list[dict[str, float]] = []
    for start_y, start_x in zip(*np.where(mask & ~visited)):
        if visited[start_y, start_x]:
            continue
        stack = [(int(start_y), int(start_x))]
        visited[start_y, start_x] = True
        xs: list[int] = []
        ys: list[int] = []
        while stack:
            y, x = stack.pop()
            xs.append(x)
            ys.append(y)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    stack.append((ny, nx))
        pixels = len(xs)
        if pixels < min_pixels:
            continue
        x1, x2 = min(xs), max(xs) + 1
        y1, y2 = min(ys), max(ys) + 1
        boxes.append(
            {
                "x": x1 / width,
                "y": y1 / height,
                "w": (x2 - x1) / width,
                "h": (y2 - y1) / height,
                "area": pixels / (width * height),
            }
        )
    return boxes


def target_masks(image: Image.Image) -> dict[str, Any]:
    small = image.resize((160, 120)).convert("RGB")
    rgb = np.asarray(small, dtype=np.float32)
    gray = np.asarray(small.convert("L"), dtype=np.float32)
    median = float(np.median(gray))
    deviation = np.abs(gray - median)
    contrast = deviation > max(22.0, float(deviation.mean() + deviation.std() * 0.75))
    dark = (gray < 95) & contrast
    bright = (gray > 160) & contrast
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    skin = (r > 95) & (g > 40) & (b > 20) & (r > g * 1.08) & (r > b * 1.18) & ((np.maximum.reduce([r, g, b]) - np.minimum.reduce([r, g, b])) > 15)
    return {"contrast": contrast, "dark": dark, "bright": bright, "skin": skin}


def boxed(box: dict[str, float], confidence: float, label: str, detector: str) -> dict[str, float | str]:
    return {
        "x": round(float(box["x"]), 3),
        "y": round(float(box["y"]), 3),
        "w": round(float(box["w"]), 3),
        "h": round(float(box["h"]), 3),
        "confidence": round(float(confidence), 3),
        "label": label,
        "detector": detector,
    }


def detect_target_box(image: Image.Image, target: str) -> dict[str, Any]:
    category = normalize_target(target)
    masks = target_masks(image)
    contrast_boxes = component_boxes(masks["contrast"], min_pixels=22)
    dark_boxes = component_boxes(masks["dark"], min_pixels=14)
    skin_boxes = component_boxes(masks["skin"], min_pixels=20)

    def best(candidates: list[tuple[float, dict[str, float], str]]) -> dict[str, Any]:
        if not candidates:
            return {"found": False, "supported": category != "generic", "category": category, "reason": f"No {category} candidate was detected."}
        score, box, detector = max(candidates, key=lambda item: item[0])
        return {"found": score >= 0.25, "supported": True, "category": category, "box": boxed(box, min(0.96, score), category, detector)}

    candidates: list[tuple[float, dict[str, float], str]] = []
    boxes = contrast_boxes + dark_boxes
    for box in boxes:
        w, h, area = box["w"], box["h"], box["area"]
        aspect = h / max(w, 0.001)
        wide = w / max(h, 0.001)
        if category == "door" and aspect > 1.45 and area > 0.025:
            candidates.append((min(0.92, 0.35 + area * 5 + min(aspect, 4) * 0.05), box, "vertical-object"))
        elif category == "handle" and 0.006 <= area <= 0.07 and 0.5 <= wide <= 2.8:
            candidates.append((min(0.8, 0.25 + area * 7), box, "small-contrast-object"))
        elif category == "bottle" and aspect > 1.8 and 0.004 <= area <= 0.13:
            candidates.append((min(0.88, 0.3 + area * 6 + min(aspect, 5) * 0.04), box, "tall-narrow-object"))
        elif category == "phone" and 1.25 <= aspect <= 2.8 and 0.003 <= area <= 0.12:
            candidates.append((min(0.82, 0.28 + area * 7), box, "phone-shaped-object"))
        elif category == "cup" and 0.65 <= aspect <= 1.65 and 0.004 <= area <= 0.12 and box["y"] > 0.18:
            candidates.append((min(0.78, 0.26 + area * 7), box, "cup-sized-object"))
        elif category == "laptop" and wide > 1.35 and 0.02 <= area <= 0.35:
            candidates.append((min(0.9, 0.3 + area * 4 + min(wide, 4) * 0.05), box, "wide-screen-object"))
        elif category == "handrail" and aspect > 2.1 and 0.003 <= area <= 0.09 and w <= 0.12 and (box["x"] < 0.42 or box["x"] > 0.58):
            candidates.append((min(0.86, 0.32 + area * 7 + min(aspect, 5) * 0.04), box, "rail-like-vertical-edge"))

    if category == "stairs":
        step_boxes = [
            box
            for box in boxes
            if box["y"] > 0.28
            and box["w"] > 0.2
            and 0.006 <= box["h"] <= 0.09
            and box["area"] >= 0.003
            and box["w"] / max(box["h"], 0.001) >= 2.6
        ]
        if len(step_boxes) >= 3:
            x1 = min(box["x"] for box in step_boxes)
            y1 = min(box["y"] for box in step_boxes)
            x2 = max(box["x"] + box["w"] for box in step_boxes)
            y2 = max(box["y"] + box["h"] for box in step_boxes)
            grouped = {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1, "area": sum(box["area"] for box in step_boxes)}
            if y2 > 0.58 and grouped["h"] > 0.14:
                confidence = 0.34 + len(step_boxes) * 0.055 + min(0.22, grouped["h"] * 0.35)
                candidates.append((min(0.9, confidence), grouped, "repeated-horizontal-step-edges"))

    if category == "text":
        text_boxes = [box for box in dark_boxes if box["w"] > 0.015 and box["h"] > 0.008 and box["area"] < 0.05]
        if len(text_boxes) >= 2:
            x1 = min(box["x"] for box in text_boxes)
            y1 = min(box["y"] for box in text_boxes)
            x2 = max(box["x"] + box["w"] for box in text_boxes)
            y2 = max(box["y"] + box["h"] for box in text_boxes)
            grouped = {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1, "area": sum(box["area"] for box in text_boxes)}
            candidates.append((min(0.86, 0.3 + len(text_boxes) * 0.05), grouped, "text-region-grouping"))
        candidates.extend((min(0.7, 0.24 + box["area"] * 8), box, "label-like-region") for box in dark_boxes if box["w"] / max(box["h"], 0.001) > 1.2)

    if category == "person":
        for box in skin_boxes:
            aspect = box["h"] / max(box["w"], 0.001)
            if 0.55 <= aspect <= 1.8 and 0.004 <= box["area"] <= 0.18:
                candidates.append((min(0.84, 0.32 + box["area"] * 8), box, "skin-tone-face-region"))

    if category == "generic":
        box = salient_box(image)
        if box["confidence"] >= 0.25:
            return {"found": True, "supported": False, "category": category, "box": {**box, "label": target.strip() or "object", "detector": "generic-saliency"}}
        return {"found": False, "supported": False, "category": category, "reason": "No visually distinct object was detected."}

    return best(candidates)


def guidance_from_box(box: dict[str, float]) -> Guidance:
    cx = box["x"] + box["w"] / 2
    cy = box["y"] + box["h"] / 2
    dx = cx - 0.5
    dy = cy - 0.5
    distance = min(1.0, math.sqrt(dx * dx + dy * dy) / math.sqrt(0.5))

    horizontal = "left" if dx < -0.09 else "right" if dx > 0.09 else ""
    vertical = "up" if dy < -0.09 else "down" if dy > 0.09 else ""
    if horizontal and vertical:
        direction = f"Move {horizontal} and tilt {vertical}."
    elif horizontal:
        direction = f"Move {horizontal}."
    elif vertical:
        direction = f"Tilt {vertical}."
    else:
        direction = "Target is centered."

    if distance < 0.05:
        pulse, pattern, locked = "locked", [40], True
    elif distance < 0.2:
        pulse, pattern, locked = "rapid", [60, 50, 60], False
    elif distance < 0.4:
        pulse, pattern, locked = "medium", [90, 120, 90], False
    else:
        pulse, pattern, locked = "slow", [120, 260], False
    return Guidance(round(distance, 3), direction, pulse, pattern, locked)


def describe_scene(image: Image.Image) -> dict[str, Any]:
    stats = image_stats(image)
    box = salient_box(image)
    center = (box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
    location = (
        "center"
        if 0.38 <= center[0] <= 0.62 and 0.34 <= center[1] <= 0.66
        else "left side"
        if center[0] < 0.38
        else "right side"
        if center[0] > 0.62
        else "upper area"
        if center[1] < 0.34
        else "lower area"
    )
    summary = (
        f"The frame is {stats['lighting']} with {stats['detail']} visual detail. "
        f"The dominant color is {stats['dominant_color']}. "
        f"The most visually distinct region is near the {location}."
    )
    return {"summary": summary, "stats": stats, "salient_region": box}


def build_object_item(category: str, detection: dict[str, Any]) -> dict[str, Any] | None:
    if not detection.get("found") or not detection.get("box"):
        return None
    box = detection["box"]
    confidence = float(box.get("confidence", 0.0))
    return {
        "name": category,
        "category": detection.get("category", category),
        "confidence": round(confidence, 3),
        "confidence_band": confidence_band(confidence),
        "direction": clock_position(box),
        "region": region_name(box),
        "distance": distance_estimate(box),
        "box": box,
        "detector": box.get("detector", "local-vision"),
    }


def detect_scene_objects(image: Image.Image) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for target in ("stairs", "handrail", "door", "handle", "cup", "bottle", "phone", "laptop", "text", "person"):
        item = build_object_item(target, detect_target_box(image, target))
        if item:
            objects.append(item)
    objects.sort(key=lambda item: (item["distance"], -item["confidence"]))
    return objects[:8]


def analyze_hazards(image: Image.Image, scene: dict[str, Any]) -> list[dict[str, Any]]:
    stats = scene["stats"]
    salient = scene["salient_region"]
    hazards: list[dict[str, Any]] = []

    if stats["brightness"] < 65:
        hazards.append(
            {
                "type": "low_light",
                "priority": "high",
                "message": "Lighting is too dim for dependable visual guidance.",
            }
        )

    if stats["contrast"] < 12:
        hazards.append(
            {
                "type": "low_detail",
                "priority": "medium",
                "message": "The frame has very little detail. Sweep slowly before trusting object guidance.",
            }
        )

    stairs = detect_target_box(image, "stairs")
    if stairs.get("found"):
        hazards.append(
            {
                "type": "stairs",
                "priority": "medium",
                "message": "Stairs or step edges may be ahead. Move slowly and confirm each step.",
            }
        )

    area = box_area(salient)
    cx, cy = box_center(salient)
    if area > 0.28 and cy > 0.48:
        hazards.append(
            {
                "type": "near_obstruction",
                "priority": "high",
                "message": f"A large visual region fills the {region_name(salient)} of the frame.",
            }
        )
    elif area > 0.16 and 0.32 <= cx <= 0.68:
        hazards.append(
            {
                "type": "center_obstruction",
                "priority": "medium",
                "message": "A prominent object is near the forward path.",
            }
        )

    return hazards


def match_landmark(scene_summary: str, landmarks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not landmarks:
        return None
    scene_words = {word.strip(".,:;!?").lower() for word in scene_summary.split() if len(word) > 3}
    best_score = 0
    best: dict[str, Any] | None = None
    for item in landmarks:
        haystack = f"{item.get('name', '')} {item.get('note', '')} {item.get('description', '')}"
        words = {word.strip(".,:;!?").lower() for word in haystack.split() if len(word) > 3}
        score = len(scene_words & words)
        if score > best_score:
            best_score = score
            best = item
    if best and best_score >= 2:
        return {"name": best.get("name", "Saved place"), "score": best_score, "note": best.get("note", "")}
    return None


def environment_state(stats: dict[str, Any], hazards: list[dict[str, Any]], objects: list[dict[str, Any]]) -> dict[str, Any]:
    person_seen = any(item["category"] == "person" for item in objects)
    text_seen = any(item["category"] == "text" for item in objects)
    markers = [hazard["message"] for hazard in hazards]
    if text_seen:
        markers.append("Text-like contrast is visible.")
    if person_seen:
        markers.append("A possible person-like region is visible.")

    occupancy = "occupied" if person_seen else "unknown"
    if not hazards and stats["lighting"] == "bright":
        state = "stable"
    elif any(h["priority"] == "high" for h in hazards):
        state = "caution"
    else:
        state = "mixed"

    return {
        "state": state,
        "occupancy": occupancy,
        "path_clearance": path_clearance(hazards, objects),
        "markers": markers[:4],
    }


def path_clearance(hazards: list[dict[str, Any]], objects: list[dict[str, Any]]) -> str:
    if any(hazard["priority"] == "high" for hazard in hazards):
        return "blocked_or_uncertain"
    if any(hazard["type"] in {"stairs", "center_obstruction"} for hazard in hazards):
        return "caution"
    for item in objects:
        if item["distance"] <= 0.9 and item["region"] in {"center", "lower", "middle"}:
            return "occupied_nearby"
    return "likely_clear"


def navigation_risk(
    scene: dict[str, Any],
    hazards: list[dict[str, Any]],
    objects: list[dict[str, Any]],
    goal_item: dict[str, Any] | None,
) -> dict[str, Any]:
    stats = scene["stats"]
    score = 8
    reasons: list[str] = []

    if stats["brightness"] < 65:
        score += 38
        reasons.append("lighting is too dim")
    elif stats["brightness"] < 95:
        score += 14
        reasons.append("lighting is limited")

    if stats["contrast"] < 12:
        score += 22
        reasons.append("the frame has very low detail")
    elif stats["contrast"] < 24:
        score += 8
        reasons.append("visual detail is limited")

    for hazard in hazards:
        score += 30 if hazard["priority"] == "high" else 16 if hazard["priority"] == "medium" else 8
        reasons.append(hazard["type"].replace("_", " "))

    if any(item["category"] == "stairs" for item in objects):
        score += 14
        reasons.append("possible stairs")

    nearest = min((item["distance"] for item in objects), default=None)
    if nearest is not None and nearest <= 0.75:
        score += 12
        reasons.append("object appears close")

    if goal_item and goal_item["confidence"] >= 0.52:
        score -= 8
        reasons.append("goal has a usable visual lock")

    score = max(0, min(100, int(score)))
    if score >= 70:
        level = "high"
        label = "High caution"
        pace = "pause"
    elif score >= 42:
        level = "medium"
        label = "Caution"
        pace = "slow"
    else:
        level = "low"
        label = "Low caution"
        pace = "normal"

    unique_reasons = list(dict.fromkeys(reasons))[:5]
    return {
        "score": score,
        "level": level,
        "label": label,
        "recommended_pace": pace,
        "stop_required": score >= 70 or any(hazard["priority"] == "high" for hazard in hazards),
        "reasons": unique_reasons,
        "confirm_methods": ["touch", "sound", "cane or guide", "trusted person"],
    }


def navigation_next_actions(
    risk: dict[str, Any],
    hazards: list[dict[str, Any]],
    goal: str,
    goal_item: dict[str, Any] | None,
    social: dict[str, Any],
) -> dict[str, Any]:
    steps: list[str] = []
    scan_pattern = "Sweep slowly from left to right, then tilt slightly down."

    if risk["stop_required"]:
        steps.append("Pause before moving forward.")
    if hazards:
        steps.append(hazards[0]["message"])
    if goal_item:
        target_name = goal or goal_item["name"]
        steps.append(f"Turn toward {goal_item['direction']} for {target_name}.")
        if goal_item["confidence"] < 0.52:
            steps.append("Use Precision mode before reaching for it.")
        else:
            steps.append("Move slowly and confirm the target before touching it.")
        scan_pattern = "Keep the target near the center of the camera."
    elif social.get("person_detected"):
        steps.append("A possible person is visible; ask before interpreting social details.")
    else:
        steps.append("Continue a slow scan until a stable object or saved place appears.")

    steps.append("Confirm important guidance with touch, sound, or your usual safety method.")
    unique_steps = list(dict.fromkeys(steps))[:4]
    return {
        "primary": unique_steps[0],
        "steps": unique_steps,
        "scan_pattern": scan_pattern,
        "mode_hint": "precision" if goal_item else "navigation",
    }


def priority_from_context(
    hazards: list[dict[str, Any]],
    goal_item: dict[str, Any] | None,
    social: dict[str, Any],
) -> str:
    if any(hazard["priority"] == "high" for hazard in hazards):
        return "high"
    if goal_item and goal_item["confidence"] >= 0.52:
        return "medium"
    if social.get("person_detected"):
        return "medium"
    return "low"


def navigation_speech(
    priority: str,
    hazards: list[dict[str, Any]],
    goal: str,
    goal_item: dict[str, Any] | None,
    scene: dict[str, Any],
    social: dict[str, Any],
) -> str:
    if hazards:
        return hazards[0]["message"] + " Move slowly and verify with touch or sound."
    if goal_item:
        band = goal_item["confidence_band"]
        return (
            f"Possible {goal or goal_item['name']} at {goal_item['direction']}, "
            f"about {goal_item['distance']} meters away. Confidence is {band}."
        )
    if social.get("person_detected"):
        return social["cue"]
    if priority == "low":
        return scene["summary"]
    return "Continue scanning slowly. I will report high priority changes first."


def navigation_analysis(image: Image.Image, goal: str = "", landmarks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    scene = describe_scene(image)
    objects = detect_scene_objects(image)
    hazards = analyze_hazards(image, scene)
    social = social_result(image)
    env = environment_state(scene["stats"], hazards, objects)
    goal_label = goal.strip()
    goal_item = None
    if goal_label:
        goal_detection = detect_target_box(image, goal_label)
        goal_item = build_object_item(goal_label, goal_detection)
    location = match_landmark(scene["summary"], landmarks or [])
    risk = navigation_risk(scene, hazards, objects, goal_item)
    next_actions = navigation_next_actions(risk, hazards, goal_label, goal_item, social)
    priority = priority_from_context(hazards, goal_item, social)
    speech = navigation_speech(priority, hazards, goal_label, goal_item, scene, social)
    stable_objects = [item for item in objects if item["confidence"] >= 0.45]
    return {
        "mode": "navigation",
        "priority": priority,
        "speech": speech,
        "scene": scene,
        "hazards": hazards,
        "objects": stable_objects,
        "goal": goal_label,
        "target_detected": bool(goal_item),
        "target": goal_item,
        "social_cues": {
            "intent": "possible_interaction" if social.get("person_detected") else "none",
            "details": social["cue"],
            "confidence": social.get("confidence", 0.0),
        },
        "environment": env,
        "risk": risk,
        "next_actions": next_actions,
        "current_location_tag": location,
        "disclaimer": "Local demo analysis uses deterministic visual heuristics. Treat guidance as supportive, not safety-critical.",
    }


def micro_navigation(image: Image.Image, target: str) -> dict[str, Any]:
    target_label = target.strip() or "target"
    detection = detect_target_box(image, target_label)
    if not detection.get("found"):
        return {
            "mode": "micro",
            "target": target_label,
            "found": False,
            "x": 0,
            "y": 0,
            "action": "scan",
            "pulse": "slow",
            "tone_hz": 360,
            "guidance_speech": f"I cannot verify {target_label}. Sweep slowly until it is visible.",
            "box": None,
        }
    box = detection["box"]
    cx, cy = box_center(box)
    x = round((cx - 0.5) * 200)
    y = round((0.5 - cy) * 200)
    guide = guidance_from_box(box)
    if abs(x) <= 12 and abs(y) <= 12:
        action = "hold"
        speech = f"{target_label} is centered. Hold steady and confirm before touching."
    elif abs(x) >= abs(y):
        action = "move_left" if x < 0 else "move_right"
        speech = f"Move {'left' if x < 0 else 'right'} for {target_label}."
    else:
        action = "tilt_up" if y > 0 else "tilt_down"
        speech = f"Tilt {'up' if y > 0 else 'down'} for {target_label}."
    proximity = max(0.0, 1.0 - min(1.0, math.sqrt(x * x + y * y) / 142))
    return {
        "mode": "micro",
        "target": target_label,
        "found": True,
        "x": x,
        "y": y,
        "action": action,
        "proximity": round(proximity, 3),
        "pulse": guide.pulse,
        "tone_hz": int(420 + proximity * 620),
        "guidance": asdict(guide),
        "guidance_speech": speech,
        "box": box,
    }


def task_plan(task_name: str) -> dict[str, Any]:
    normalized = normalize_target(task_name)
    text = task_name.strip().lower()
    key = ""
    for candidate in TASK_LIBRARY:
        if candidate in text or candidate == normalized:
            key = candidate
            break
    if key:
        steps = [{"id": index + 1, "instruction": step, "completed": False, "items": []} for index, step in enumerate(TASK_LIBRARY[key])]
        return {"task": key, "title": task_name.strip() or key.title(), "steps": steps, "source": "preset"}

    if "read" in text or "label" in text or "sign" in text:
        key = "label"
    elif "exit" in text or "door" in text:
        key = "door"
    if key:
        steps = [{"id": index + 1, "instruction": step, "completed": False, "items": []} for index, step in enumerate(TASK_LIBRARY[key])]
        return {"task": key, "title": task_name.strip() or key.title(), "steps": steps, "source": "inferred"}

    title = task_name.strip() or "Custom task"
    target_words = [
        word.strip(".,:;!?")
        for word in text.split()
        if word not in {"help", "me", "to", "the", "a", "an", "my", "please", "find", "locate", "get", "pick", "use", "make", "do", "task"}
    ]
    target = " ".join(target_words[:3]).strip() or "target item"
    target_verb = "are" if target.endswith("s") and not target.endswith("ss") else "is"
    custom_steps = [
        f"Scan slowly for {target}",
        f"Center the most likely {target} in the camera",
        f"Use precision mode if {target} {target_verb} small or partially hidden",
        f"Confirm {target} with touch, sound, or another safe method before acting",
    ]
    steps = [
        {"id": index + 1, "instruction": step, "completed": False, "items": [target]}
        for index, step in enumerate(custom_steps)
    ]
    return {
        "task": "custom",
        "title": title,
        "target": target,
        "steps": steps,
        "source": "local-rule-planner",
        "safety_note": "Custom task plans are local heuristics. Confirm each step before relying on it.",
    }


def strip_command_prefix(text: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix) :].strip(" .,:;")
    return ""


def parse_command(command: str) -> dict[str, Any]:
    raw = command.strip()
    text = raw.lower().strip()
    if not text:
        return {
            "intent": "empty",
            "mode": "standby",
            "speech": "Say or type a command such as find door, precision handle, task make coffee, or save place kitchen.",
        }

    question_starters = ("ask ", "question ", "what ", "where ", "who ", "is ", "are ", "can ", "do ", "does ", "how ")
    if text.endswith("?") or text.startswith(question_starters):
        question = strip_command_prefix(text, ("ask ", "question ")) or raw
        return {"intent": "inquiry", "mode": "inquiry", "question": question, "speech": "Answering from the current frame."}

    if any(word in text for word in ("stop", "cancel", "quiet", "mute")):
        return {"intent": "stop", "mode": "standby", "speech": "Stopping speech, live guidance, and active searches."}

    if any(word in text for word in ("next step", "skip step", "step done", "done with step")):
        return {"intent": "task_next", "mode": "task", "speech": "Marking this step complete and moving to the next one."}

    if any(word in text for word in ("previous step", "back step", "go back")):
        return {"intent": "task_previous", "mode": "task", "speech": "Moving back one task step."}

    if any(word in text for word in ("repeat step", "current step", "where am i in the task")):
        return {"intent": "task_repeat", "mode": "task", "speech": "Repeating the current task step."}

    target = strip_command_prefix(text, ("precision ", "micro ", "guide my hand to ", "guide me to "))
    if target:
        return {"intent": "micro", "mode": "precision", "target": target, "speech": f"Precision guidance for {target}."}

    target = strip_command_prefix(text, ("find ", "search for ", "locate ", "where is ", "look for "))
    if target:
        return {"intent": "find", "mode": "find", "target": target, "speech": f"Searching for {target}."}

    target = strip_command_prefix(text, ("navigate to ", "go to ", "take me to "))
    if target:
        return {"intent": "navigate", "mode": "navigation", "target": target, "speech": f"Navigating toward {target}."}

    task_name = strip_command_prefix(text, ("task ", "help me ", "walk me through ", "guide me through "))
    if task_name:
        return {"intent": "task", "mode": "task", "task": task_name, "speech": f"Planning task: {task_name}."}

    tag_name = strip_command_prefix(text, ("save place ", "tag place ", "remember this as ", "remember place "))
    if tag_name:
        return {"intent": "tag", "mode": "memory", "name": tag_name, "speech": f"Ready to save this place as {tag_name}."}

    if "read" in text or "ocr" in text or "text" in text:
        return {"intent": "ocr", "mode": "reader", "speech": "Reading visible text if available."}

    if "social" in text or "person" in text or "people" in text:
        return {"intent": "social", "mode": "social", "speech": "Checking for possible social cues."}

    if "scene" in text or "describe" in text or "what is around" in text:
        return {"intent": "scene", "mode": "scene", "speech": "Describing the scene."}

    return {"intent": "navigate", "mode": "navigation", "target": raw, "speech": f"Using {raw} as the navigation goal."}


def extract_question_target(question: str) -> str:
    text = question.lower().strip(" ?.")
    for prefix in ("where is ", "where are ", "find ", "locate ", "do you see ", "can you see ", "is there a ", "is there an ", "is there "):
        if text.startswith(prefix):
            target = text[len(prefix) :].strip(" ?.")
            for article in ("the ", "a ", "an ", "my "):
                if target.startswith(article):
                    target = target[len(article) :]
                    break
            return target
    return ""


def visual_inquiry(image: Image.Image, question: str, landmarks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    question_text = question.strip() or "What is around me?"
    lower = question_text.lower()
    nav = navigation_analysis(image, "", landmarks or [])
    evidence: list[str] = [nav["scene"]["summary"]]

    if nav["hazards"]:
        evidence.extend(hazard["message"] for hazard in nav["hazards"][:2])

    if any(word in lower for word in ("person", "people", "someone", "social", "face")):
        social = social_result(image)
        answer = social["cue"]
        evidence.append(social["privacy_note"])
        return {
            "mode": "inquiry",
            "question": question_text,
            "intent": "social",
            "answer": answer,
            "confidence": social.get("confidence", 0.0),
            "evidence": evidence,
            "navigation": nav,
        }

    if any(word in lower for word in ("read", "text", "label", "sign", "words")):
        ocr = ocr_result(image)
        answer = ocr["message"]
        evidence.append(f"OCR status: {ocr['status']}.")
        return {
            "mode": "inquiry",
            "question": question_text,
            "intent": "ocr",
            "answer": answer,
            "confidence": 0.45 if ocr["status"] == "text_region_detected" else 0.2,
            "evidence": evidence,
            "navigation": nav,
        }

    if any(word in lower for word in ("safe", "hazard", "obstacle", "clear", "path", "ahead")):
        if nav["hazards"]:
            answer = nav["hazards"][0]["message"] + " Move slowly and confirm with your usual safety method."
            confidence = 0.68
        else:
            answer = "No strong local hazard cue was detected, but this demo cannot certify that the path is safe."
            confidence = 0.42
        return {
            "mode": "inquiry",
            "question": question_text,
            "intent": "safety",
            "answer": answer,
            "confidence": confidence,
            "evidence": evidence,
            "navigation": nav,
        }

    if any(word in lower for word in ("where am i", "place", "location", "room")):
        location = nav.get("current_location_tag")
        if location:
            answer = f"This resembles the saved place {location['name']}."
            evidence.append(location.get("note", ""))
            confidence = min(0.85, 0.35 + location.get("score", 0) * 0.15)
        else:
            answer = "I cannot match this frame to a saved place yet. Save this location in Memory Palace if it is useful."
            confidence = 0.25
        return {
            "mode": "inquiry",
            "question": question_text,
            "intent": "location",
            "answer": answer,
            "confidence": round(confidence, 2),
            "evidence": [item for item in evidence if item],
            "navigation": nav,
        }

    target = extract_question_target(question_text)
    if target:
        detection = detect_target_box(image, target)
        item = build_object_item(target, detection)
        if item:
            answer = f"Possible {target} at {item['direction']}, about {item['distance']} meters away. Confidence is {item['confidence_band']}."
            evidence.append(f"Detector: {item['detector']}.")
            confidence = item["confidence"]
        else:
            answer = f"I cannot verify {target} in this frame. Sweep slowly or try precision mode if it is small."
            confidence = 0.2
        return {
            "mode": "inquiry",
            "question": question_text,
            "intent": "target",
            "target": target,
            "answer": answer,
            "confidence": confidence,
            "evidence": evidence,
            "navigation": nav,
        }

    object_names = [item["name"] for item in nav.get("objects", [])[:4]]
    if object_names:
        answer = f"{nav['scene']['summary']} I can also see possible " + ", ".join(object_names) + "."
    else:
        answer = nav["scene"]["summary"]
    return {
        "mode": "inquiry",
        "question": question_text,
        "intent": "scene",
        "answer": answer,
        "confidence": 0.45,
        "evidence": evidence,
        "navigation": nav,
    }


def object_guidance(image: Image.Image, target: str) -> dict[str, Any]:
    target_label = target.strip() or "selected object"
    detection = detect_target_box(image, target_label)
    if not detection["found"]:
        return {
            "target": target_label,
            "found": False,
            "supported": detection.get("supported", False),
            "category": detection.get("category", "generic"),
            "reason": detection.get("reason", "Target was not detected."),
            "box": None,
            "guidance": None,
            "spoken": f"I cannot verify {target_label} in this frame. Sweep the camera slowly or choose another target.",
        }
    box = detection["box"]
    guide = guidance_from_box(box)
    return {
        "target": target_label,
        "found": True,
        "supported": detection.get("supported", True),
        "category": detection.get("category", "generic"),
        "box": box,
        "guidance": asdict(guide),
        "spoken": f"Possible {target_label}: {guide.direction} Pulse is {guide.pulse}. Confirm before relying on it.",
    }


def tesseract_ocr(image: Image.Image) -> dict[str, Any] | None:
    command_parts = tesseract_command_parts()
    if not executable_available(command_parts):
        return None

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            temp_path = Path(handle.name)
        image.convert("RGB").save(temp_path)
        completed = subprocess.run(
            [*command_parts, str(temp_path), "stdout", "--psm", "6"],
            capture_output=True,
            text=True,
            timeout=max(1.0, TESSERACT_TIMEOUT_SECONDS),
            check=False,
        )
    except subprocess.TimeoutExpired:
        message = "Local Tesseract OCR timed out. Try centering the text and reading again."
        return {
            "text": "",
            "status": "ocr_timeout",
            "engine": "tesseract",
            "message": message,
            "tts": message,
            "box": None,
        }
    except OSError as exc:
        message = f"Local Tesseract OCR could not run: {exc}"
        return {
            "text": "",
            "status": "ocr_engine_error",
            "engine": "tesseract",
            "message": message,
            "tts": "Local OCR is configured but could not run.",
            "box": None,
        }
    finally:
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    text = completed.stdout.strip()
    warning = completed.stderr.strip()[:500]
    if text:
        return {
            "text": text,
            "status": "recognized",
            "engine": "tesseract",
            "message": "Text recognized by local Tesseract OCR.",
            "tts": text,
            "box": None,
            "warning": warning,
        }

    message = (
        "Local Tesseract OCR ran but did not recognize readable text. "
        "Move closer, improve lighting, and center the label."
    )
    if completed.returncode != 0:
        message = "Local Tesseract OCR returned an error. Check the configured Tesseract command."
    return {
        "text": "",
        "status": "no_text_recognized" if completed.returncode == 0 else "ocr_engine_error",
        "engine": "tesseract",
        "message": message,
        "tts": message,
        "box": None,
        "warning": warning,
    }


def ocr_result(image: Image.Image) -> dict[str, Any]:
    stats = image_stats(image)
    detection = detect_target_box(image, "text")
    likely_text = detection["found"] or (stats["contrast"] > 42 and stats["detail"] in {"medium", "high"})
    adapter = tesseract_ocr(image)
    if detection["found"]:
        message = (
            "A text or label region was detected and centered for reading. "
            "If your browser supports native TextDetector, VISIO-NETRA will speak the recognized words directly."
        )
    elif likely_text:
        message = (
            "Potential text-like high-contrast regions detected. "
            "Use browser OCR or the manual text fallback for exact reading on this local build."
        )
    else:
        message = "No strong text-like contrast was detected in this demo analysis."

    if adapter:
        adapter["box"] = detection.get("box")
        adapter["region_status"] = "text_region_detected" if likely_text else "no_text_region"
        if adapter["status"] != "recognized" and likely_text:
            adapter["message"] = f'{adapter["message"]} {message}'
            adapter["tts"] = adapter["message"]
        return adapter

    return {
        "text": "",
        "status": "text_region_detected" if likely_text else "no_text_region",
        "engine": "heuristic",
        "message": message,
        "tts": message,
        "box": detection.get("box"),
    }


def social_result(image: Image.Image) -> dict[str, Any]:
    scene = describe_scene(image)
    person = detect_target_box(image, "person")
    brightness = scene["stats"]["brightness"]
    if brightness < 65:
        cue = "The scene is too dim for reliable social cue reading."
    elif person["found"]:
        guide = guidance_from_box(person["box"])
        cue = f"A possible person-like region is visible. {guide.direction} Ask before interpreting social details."
    else:
        cue = "No clear social subject is visible in the frame."
    return {
        "cue": cue,
        "person_detected": bool(person["found"]),
        "box": person.get("box"),
        "confidence": person.get("box", {}).get("confidence", 0.0) if person["found"] else 0.0,
        "privacy_note": "No biometric identity is stored or inferred.",
    }


def verify_task_step(image: Image.Image, step: str) -> dict[str, Any]:
    scene = describe_scene(image)
    step_lower = step.lower()
    target = ""
    for candidate in ("cup", "kettle", "bottle", "door", "handle", "label", "text", "product", "item"):
        if candidate in step_lower:
            target = "text" if candidate in {"label", "product", "item"} else candidate
            break
    detection = detect_target_box(image, target) if target else {"found": scene["salient_region"]["confidence"] > 0.35, "box": scene["salient_region"]}
    ok = bool(detection["found"])
    return {
        "step": step,
        "verified": ok,
        "target_checked": target or "scene",
        "box": detection.get("box"),
        "feedback": "Visual evidence matches this step. Confirm with touch, sound, or common sense before continuing." if ok else "Move the camera slowly and center the required item for this step.",
        "scene": scene["summary"],
        "confidence": detection.get("box", {}).get("confidence", scene["salient_region"].get("confidence", 0.0)),
    }


class VisioHandler(SimpleHTTPRequestHandler):
    server_version = "VISIONETRA/2.0"

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        clean = parsed.path.lstrip("/")
        if not clean:
            clean = "index.html"
        return str((PUBLIC_DIR / clean).resolve())

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[VISIO-NETRA] {self.address_string()} - {format % args}")

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
        super().end_headers()

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/ws/guidance":
            self.handle_guidance_websocket()
            return
        if route == "/api/health":
            model_status = model_adapter_status()
            self.send_json(
                {
                    "ok": True,
                    "service": "VISIO-NETRA",
                    "mode": "local-netra-demo",
                    "model_profile": model_status["active_profile"],
                    "features": [
                        "navigation",
                        "find",
                        "micro",
                        "scene",
                        "ocr",
                        "social",
                        "task",
                        "memory",
                        "persistent-memory",
                        "command-intents",
                        "visual-inquiry",
                        "risk-scoring",
                        "next-actions",
                        "model-adapters",
                    ],
                }
            )
            return
        if route == "/api/model/status":
            self.send_json(model_adapter_status())
            return
        if route == "/api/memory":
            self.send_json(load_memory())
            return
        file_path = Path(self.translate_path(self.path))
        if file_path.is_dir():
            file_path = file_path / "index.html"
        if not file_path.exists() or PUBLIC_DIR not in file_path.parents:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type, _ = mimetypes.guess_type(str(file_path))
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("Expected a JSON request body.")
            if length > MAX_POST_BYTES:
                raise ValueError("Request body is too large for local analysis.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            route = urlparse(self.path).path
            if route == "/api/task/plan":
                result = task_plan(payload.get("task", ""))
                self.send_json(result)
                return
            if route == "/api/command":
                self.send_json(parse_command(payload.get("command", "")))
                return
            if route == "/api/memory/save":
                landmark = save_landmark(payload)
                self.send_json({"saved": True, "landmark": landmark, "memory": load_memory()})
                return
            if route == "/api/memory/clear":
                self.send_json({"cleared": True, "memory": clear_memory()})
                return

            image = decode_data_url(payload.get("image", ""))
            if route == "/api/analyze/navigation":
                landmarks = merge_landmarks(persistent_landmarks(), payload.get("landmarks", []))
                result = navigation_analysis(image, payload.get("goal", ""), landmarks)
                primary = result.get("target") or (result.get("objects") or [None])[0]
                if primary:
                    log_memory_sighting(primary.get("name", ""), result.get("scene", {}).get("summary", ""), result.get("current_location_tag"))
            elif route == "/api/inquire":
                landmarks = merge_landmarks(persistent_landmarks(), payload.get("landmarks", []))
                result = visual_inquiry(image, payload.get("question", ""), landmarks)
            elif route == "/api/analyze/micro":
                result = micro_navigation(image, payload.get("target", ""))
            elif route == "/api/analyze/scene":
                result = describe_scene(image)
            elif route == "/api/analyze/object":
                result = object_guidance(image, payload.get("target", ""))
            elif route == "/api/analyze/ocr":
                result = ocr_result(image)
            elif route == "/api/analyze/social":
                result = social_result(image)
            elif route == "/api/analyze/task":
                result = verify_task_step(image, payload.get("step", ""))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_json(result)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_guidance_websocket(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing WebSocket key")
            return
        accept = base64.b64encode(hashlib.sha1((key + WS_MAGIC).encode("ascii")).digest()).decode("ascii")
        self.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        while True:
            frame = self.read_ws_text()
            if frame is None:
                return
            try:
                payload = json.loads(frame)
                image = decode_data_url(payload.get("image", ""))
                result = object_guidance(image, payload.get("target", ""))
                self.write_ws_text(json.dumps(result))
            except Exception as exc:
                self.write_ws_text(json.dumps({"error": str(exc)}))

    def read_exact(self, count: int) -> bytes | None:
        data = self.rfile.read(count)
        return data if len(data) == count else None

    def read_ws_text(self) -> str | None:
        header = self.read_exact(2)
        if not header:
            return None
        first, second = header
        opcode = first & 0x0F
        if opcode == 0x8:
            return None
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            ext = self.read_exact(2)
            if not ext:
                return None
            length = struct.unpack("!H", ext)[0]
        elif length == 127:
            ext = self.read_exact(8)
            if not ext:
                return None
            length = struct.unpack("!Q", ext)[0]
        if length > MAX_WS_MESSAGE_BYTES:
            return None
        mask = self.read_exact(4) if masked else b""
        payload = self.read_exact(length)
        if payload is None:
            return None
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return payload.decode("utf-8")

    def write_ws_text(self, message: str) -> None:
        payload = message.encode("utf-8")
        length = len(payload)
        if length < 126:
            header = bytes([0x81, length])
        elif length < 65536:
            header = bytes([0x81, 126]) + struct.pack("!H", length)
        else:
            header = bytes([0x81, 127]) + struct.pack("!Q", length)
        self.wfile.write(header + payload)


def main() -> None:
    PUBLIC_DIR.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), VisioHandler)
    print(f"VISIO-NETRA running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
