"""Vision mode processing and control message handling."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
from typing import TYPE_CHECKING
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

from app.config import (
    FAST_IMAGE_SIZE,
    GEMINI_API_BASE,
    JPEG_MAX_BYTES,
    MODEL_TIMEOUT,
    NAV_IMAGE_SIZE,
    OCR_IMAGE_SIZE,
    VISION_MODEL_KEY,
    VISION_MODEL_NAME,
)
from app.models import ModeName, SessionState, TaskState
from app.prompts import (
    INQUIRY_PROMPT,
    NAVIGATION_PROMPT,
    OBJECT_FIND_PROMPT,
    OCR_PROMPT,
    PRECISION_PROMPT,
    TASK_PLANNER_PROMPT,
    TASK_VERIFY_PROMPT,
)
from app.services.memory import memory_store
from app.services.speech import SpeechGate
from app.utils import clamp, distance_to_words, normalize_label, parse_json_object

if TYPE_CHECKING:
    from fastapi import WebSocket
else:
    WebSocket = Any

try:  # Optional until dependencies are installed.
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

try:  # Optional until a model key and package are available.
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover
    genai = None
    types = None


ALLOWED_MODES: set[str] = {"navigation", "object_find", "precision", "task", "ocr"}
client = genai.Client(api_key=VISION_MODEL_KEY) if genai and VISION_MODEL_KEY else None
runtime_model_key: Optional[str] = None


async def safe_send_json(websocket: WebSocket, data: Dict[str, Any]) -> bool:
    try:
        await websocket.send_json(data)
        return True
    except RuntimeError:
        return False
    except Exception as exc:
        logging.warning("WebSocket send failed: %s", exc)
        return False


async def process_control_message(data: Dict[str, Any], state: SessionState, websocket: WebSocket) -> None:
    kind = data.get("type")
    if kind == "mode":
        await _handle_mode_message(data, state, websocket)
    elif kind == "heading":
        state.latest_heading = int(data.get("heading") or 0)
    elif kind == "task_control":
        speech = await _handle_task_control(str(data.get("action") or ""), state, websocket)
        await safe_send_json(websocket, {"type": "speak", "text": speech})
    elif kind == "privacy":
        if data.get("action") == "clear_memory":
            memory_store.clear()
            await safe_send_json(websocket, {"type": "speak", "text": "Stored summaries cleared."})
    elif kind == "model_key":
        await _handle_model_key(data, websocket)
    elif kind == "inquiry":
        await process_inquiry(data, state, websocket)
    else:
        await safe_send_json(websocket, {"type": "error", "message": "Unsupported command."})


async def process_frame(frame: bytes, state: SessionState, websocket: WebSocket) -> None:
    if not frame or len(frame) > JPEG_MAX_BYTES:
        await safe_send_json(websocket, {"type": "error", "message": "Camera frame could not be processed."})
        return

    if state.mode == "object_find":
        await _process_object_find(frame, state, websocket)
    elif state.mode == "precision":
        await _process_precision(frame, state, websocket)
    elif state.mode == "task":
        await _process_task(frame, state, websocket)
    elif state.mode == "ocr":
        await _process_ocr(frame, state, websocket)
    else:
        await _process_navigation(frame, state, websocket)


async def process_inquiry(data: Dict[str, Any], state: SessionState, websocket: WebSocket) -> None:
    image = _decode_data_url(data.get("image"))
    audio = _decode_data_url(data.get("audio"))
    text_hint = str(data.get("text") or "")
    task_context = _task_context(state)
    fallback = {
        "intent": "question",
        "target": "",
        "tag_name": "",
        "task_name": "",
        "scene_summary": "",
        "speech": "Add a model key to answer questions.",
        "needs_model_key": True,
    }
    prompt = INQUIRY_PROMPT.format(
        memory_context=memory_store.context(),
        mode=state.mode,
        target=state.active_target or "none",
        task_context=task_context,
    )
    if text_hint:
        prompt += f"\nAdditional typed request: {text_hint}"

    result = await _model_json(
        prompt=prompt,
        image_bytes=image,
        image_size=NAV_IMAGE_SIZE,
        audio_bytes=audio,
        fallback=fallback,
    )
    intent = str(result.get("intent") or "question")
    override = await _handle_intent(intent, result, state, websocket)
    speech = override or str(result.get("speech") or "I am ready.")
    await safe_send_json(
        websocket,
        {
            "type": "inquiry_result",
            "intent": intent,
            "mode": state.mode,
            "target": state.active_target,
            "task_active": state.task.is_active,
            "needs_model_key": bool(result.get("needs_model_key")),
        },
    )
    await safe_send_json(websocket, {"type": "speak", "text": speech})


async def _handle_mode_message(data: Dict[str, Any], state: SessionState, websocket: WebSocket) -> None:
    mode = str(data.get("mode") or "navigation")
    if mode not in ALLOWED_MODES:
        await safe_send_json(websocket, {"type": "error", "message": "Unknown mode."})
        return
    target = str(data.get("target") or "").strip() or None
    if mode in {"object_find", "precision"} and not target:
        await safe_send_json(websocket, {"type": "error", "message": "A target is required."})
        return
    state.set_mode(mode, target)
    label = {
        "navigation": "Navigation mode.",
        "object_find": f"Searching for {target}.",
        "precision": f"Precision guidance for {target}.",
        "task": "Task guidance mode.",
        "ocr": "Reading text.",
    }[mode]
    await safe_send_json(websocket, {"type": "status", "status": "mode_changed", "mode": mode, "target": target})
    await safe_send_json(websocket, {"type": "speak", "text": label})


async def _handle_model_key(data: Dict[str, Any], websocket: WebSocket) -> None:
    global runtime_model_key
    key = str(data.get("key") or "").strip()
    if not key:
        await safe_send_json(websocket, {"type": "error", "message": "Model key was empty."})
        return
    runtime_model_key = key
    await safe_send_json(websocket, {"type": "status", "status": "model_key_ready"})
    await safe_send_json(websocket, {"type": "speak", "text": "Vision model connected."})


async def _process_navigation(frame: bytes, state: SessionState, websocket: WebSocket) -> None:
    started = time.perf_counter()
    fallback = {
        "priority": "low",
        "category": "none",
        "subject": "",
        "distance": 0,
        "direction": "ahead",
        "confidence": 0,
        "target_detected": False,
        "speech": "",
        "scene": "Camera active. Add a model key for live guidance.",
        "social": {"intent": "none", "details": ""},
        "environment": {"state": "unknown", "details": "", "affordance": ""},
        "objects": [],
        "needs_model_key": True,
    }
    prompt = NAVIGATION_PROMPT.format(
        heading=state.latest_heading,
        target=state.active_target or "none",
        recent_scene=" | ".join(state.recent_scene) or "none",
        memory_context=memory_store.context(),
    )
    result = await _model_json(prompt, frame, NAV_IMAGE_SIZE, None, fallback)
    priority = str(result.get("priority") or "low").lower()
    category = str(result.get("category") or "none")
    subject = str(result.get("subject") or "")
    distance = _float(result.get("distance"), 0.0)
    direction = str(result.get("direction") or "ahead")
    confidence = _float(result.get("confidence"), 0.0)
    speech = _with_distance(str(result.get("speech") or ""), distance)
    scene = str(result.get("scene") or "")
    objects = _clean_objects(result.get("objects") or [])

    if scene:
        state.recent_scene.append(scene)
    if subject and confidence >= 55:
        memory_store.log_object(subject, None, scene, confidence)
    _update_tracking(state, objects)

    gate = _speech_gate(state)
    should_speak, reason = gate.should_speak(priority, subject, direction, category, distance, speech)
    if should_speak:
        gate.record(priority, subject, direction, category, distance, speech)
        state.recent_speech.append(speech)
        await safe_send_json(websocket, {"type": "speak", "text": speech})

    state.frames_processed += 1
    await safe_send_json(
        websocket,
        {
            "type": "result",
            "mode": state.mode,
            "priority": priority,
            "category": category,
            "subject": subject,
            "distance": distance,
            "direction": direction,
            "target_detected": bool(result.get("target_detected")),
            "scene": scene,
            "social": result.get("social") or {},
            "environment": result.get("environment") or {},
            "objects": objects[:8],
            "speech_reason": reason,
            "needs_model_key": bool(result.get("needs_model_key")),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "stats": _stats(state),
        },
    )


async def _process_object_find(frame: bytes, state: SessionState, websocket: WebSocket) -> None:
    started = time.perf_counter()
    target = state.active_target or "object"
    fallback = {
        "visible": False,
        "centered": False,
        "x": 0,
        "y": 0,
        "distance_hint": "unknown",
        "confidence": 0,
        "speech": f"Common-object search is local. Try cup, bottle, chair, person, phone, laptop, book, or bag.",
        "haptic_strength": 0,
        "needs_model_key": True,
    }
    result = await _model_json(
        OBJECT_FIND_PROMPT.format(target=target),
        frame,
        FAST_IMAGE_SIZE,
        None,
        fallback,
        timeout=min(MODEL_TIMEOUT, 8.0),
    )
    payload = _object_guidance_payload("object_find_result", result, state, target)
    payload["latency_ms"] = int((time.perf_counter() - started) * 1000)
    await _maybe_speak_guidance(payload, state, websocket, subject=target)
    state.frames_processed += 1
    await safe_send_json(websocket, payload)


async def _process_precision(frame: bytes, state: SessionState, websocket: WebSocket) -> None:
    started = time.perf_counter()
    target = state.active_target or "target"
    fallback = {
        "visible": False,
        "x": 0,
        "y": 0,
        "action": "not_visible",
        "guidance_speech": "Add a model key for precision guidance.",
        "haptic_strength": 0,
        "confidence": 0,
        "needs_model_key": True,
    }
    result = await _model_json(
        PRECISION_PROMPT.format(target=target),
        frame,
        FAST_IMAGE_SIZE,
        None,
        fallback,
        timeout=min(MODEL_TIMEOUT, 8.0),
    )
    speech = result.get("guidance_speech")
    if speech == "null":
        speech = ""
    payload = _object_guidance_payload("precision_result", result, state, target)
    payload["action"] = result.get("action") or "move"
    payload["speech"] = speech or payload.get("speech") or ""
    payload["latency_ms"] = int((time.perf_counter() - started) * 1000)
    await _maybe_speak_guidance(payload, state, websocket, subject=target)
    state.frames_processed += 1
    await safe_send_json(websocket, payload)


async def _process_ocr(frame: bytes, state: SessionState, websocket: WebSocket) -> None:
    started = time.perf_counter()
    fallback = {
        "text": "",
        "language": "unknown",
        "confidence": 0,
        "speech": "Add a model key to read text.",
        "needs_model_key": True,
    }
    result = await _model_json(OCR_PROMPT, frame, OCR_IMAGE_SIZE, None, fallback)
    speech = str(result.get("speech") or result.get("text") or "No reliable text found.")
    state.frames_processed += 1
    await safe_send_json(
        websocket,
        {
            "type": "ocr_result",
            "mode": "ocr",
            "text": str(result.get("text") or ""),
            "language": str(result.get("language") or "unknown"),
            "confidence": _float(result.get("confidence"), 0),
            "speech": speech,
            "needs_model_key": bool(result.get("needs_model_key")),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "stats": _stats(state),
        },
    )
    await safe_send_json(websocket, {"type": "speak", "text": speech})
    state.set_mode("navigation")
    await safe_send_json(websocket, {"type": "status", "status": "mode_changed", "mode": "navigation"})


async def _process_task(frame: bytes, state: SessionState, websocket: WebSocket) -> None:
    started = time.perf_counter()
    current = state.task.current_step
    if not current:
        state.set_mode("navigation")
        await safe_send_json(websocket, {"type": "status", "status": "mode_changed", "mode": state.mode})
        return
    fallback = {
        "step_completed": False,
        "speech": f"Current step: {current.get('instruction')}",
        "visual_feedback": "Waiting for visual confirmation.",
    }
    result = await _model_json(
        TASK_VERIFY_PROMPT.format(step=current.get("instruction", "")),
        frame,
        NAV_IMAGE_SIZE,
        None,
        fallback,
        timeout=min(MODEL_TIMEOUT, 10.0),
    )
    speech = str(result.get("speech") or "")
    if result.get("step_completed"):
        current["completed"] = True
        state.task.current_step_index += 1
        if state.task.current_step_index >= len(state.task.plan):
            speech = "Task complete."
            state.task.clear()
            state.set_mode("navigation")
        else:
            next_step = state.task.current_step
            speech = f"Step done. Next: {next_step.get('instruction')}"

    state.frames_processed += 1
    await safe_send_json(
        websocket,
        {
            "type": "task_update",
            "mode": state.mode,
            "plan": state.task.plan,
            "current_step_index": state.task.current_step_index,
            "visual_feedback": str(result.get("visual_feedback") or ""),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "stats": _stats(state),
        },
    )
    gate = _speech_gate(state)
    should_speak, _ = gate.should_speak("medium", "task", "ahead", "task", 1, speech)
    if should_speak:
        gate.record("medium", "task", "ahead", "task", 1, speech)
        await safe_send_json(websocket, {"type": "speak", "text": speech})


async def _handle_intent(
    intent: str,
    result: Dict[str, Any],
    state: SessionState,
    websocket: WebSocket,
) -> Optional[str]:
    target = str(result.get("target") or "").strip()
    if intent == "object_find" and target:
        state.set_mode("object_find", target)
        await safe_send_json(websocket, {"type": "status", "status": "mode_changed", "mode": state.mode, "target": target})
        return f"Searching for {target}."
    if intent == "precision" and target:
        state.set_mode("precision", target)
        await safe_send_json(websocket, {"type": "status", "status": "mode_changed", "mode": state.mode, "target": target})
        return f"Guiding to {target}."
    if intent == "ocr":
        state.set_mode("ocr")
        await safe_send_json(websocket, {"type": "status", "status": "mode_changed", "mode": "ocr"})
        return "Reading text."
    if intent == "tag_location":
        name = str(result.get("tag_name") or "").strip()
        summary = str(result.get("scene_summary") or "").strip()
        if name and summary:
            memory_store.add_location(name, summary)
            return f"Saved this place as {name}."
        return "I need a location name to save it."
    if intent == "task_start":
        return await _generate_task_plan(str(result.get("task_name") or ""), state, websocket)
    if intent.startswith("task_"):
        return await _handle_task_control(intent.replace("task_", ""), state, websocket)
    if intent == "clear_memory":
        memory_store.clear()
        return "Stored summaries cleared."
    if intent == "stop":
        state.clear_goal()
        await safe_send_json(websocket, {"type": "status", "status": "mode_changed", "mode": state.mode})
        return "Stopped current guidance."
    return None


async def _generate_task_plan(task_name: str, state: SessionState, websocket: WebSocket) -> str:
    task_name = task_name.strip()
    if not task_name:
        return "I need a task name."
    fallback = [
        {"step_id": 1, "instruction": f"Prepare for {task_name}.", "items": [], "completed": False},
        {"step_id": 2, "instruction": "Ask for the next specific action when ready.", "items": [], "completed": False},
    ]
    result = await _model_json(
        TASK_PLANNER_PROMPT.format(task_name=task_name, memory_context=memory_store.context()),
        None,
        NAV_IMAGE_SIZE,
        None,
        fallback,
    )
    plan = result if isinstance(result, list) else fallback
    state.task = TaskState(is_active=True, name=task_name, plan=plan, current_step_index=0)
    state.set_mode("task")
    await safe_send_json(websocket, {"type": "task_update", "plan": plan, "current_step_index": 0})
    return f"Task plan ready. First: {plan[0].get('instruction')}"


async def _handle_task_control(action: str, state: SessionState, websocket: WebSocket) -> str:
    action = normalize_label(action)
    if not state.task.is_active or not state.task.plan:
        return "No active task."
    if action in {"skip", "done"}:
        current = state.task.current_step
        if current:
            current["completed"] = True
        state.task.current_step_index += 1
        if state.task.current_step_index >= len(state.task.plan):
            state.task.clear()
            state.set_mode("navigation")
            speech = "Task complete."
        else:
            speech = f"Next: {state.task.current_step.get('instruction')}"
    elif action in {"back", "previous"}:
        state.task.current_step_index = max(0, state.task.current_step_index - 1)
        current = state.task.current_step
        if current:
            current["completed"] = False
            speech = f"Back to: {current.get('instruction')}"
        else:
            speech = "Already at the beginning."
    elif action == "repeat":
        current = state.task.current_step
        speech = f"Current step: {current.get('instruction')}" if current else "No current step."
    elif action == "status":
        speech = f"Step {state.task.current_step_index + 1} of {len(state.task.plan)}."
    elif action == "cancel":
        state.task.clear()
        state.set_mode("navigation")
        speech = "Task cancelled."
    else:
        speech = "Unknown task command."

    await safe_send_json(
        websocket,
        {"type": "task_update", "plan": state.task.plan, "current_step_index": state.task.current_step_index},
    )
    return speech


async def _model_json(
    prompt: str,
    image_bytes: Optional[bytes],
    image_size: tuple[int, int],
    audio_bytes: Optional[bytes],
    fallback: Any,
    timeout: Optional[float] = None,
) -> Any:
    if not client and not _active_model_key():
        return fallback
    contents: List[Any] = [prompt]
    if client:
        image = await asyncio.to_thread(_prepare_image, image_bytes, image_size) if image_bytes else None
        if image is not None:
            contents.append(image)
        if audio_bytes and types:
            contents.append(types.Part.from_bytes(data=audio_bytes, mime_type="audio/webm"))
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=VISION_MODEL_NAME,
                    contents=contents,
                    config=types.GenerateContentConfig(response_mime_type="application/json") if types else None,
                ),
                timeout=timeout or MODEL_TIMEOUT,
            )
            return parse_json_object(getattr(response, "text", ""), fallback)
        except asyncio.TimeoutError:
            logging.warning("Model request timed out.")
            return fallback
        except Exception as exc:
            logging.exception("SDK model request failed; trying REST fallback: %s", exc)

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_rest_model_json, prompt, image_bytes, image_size, audio_bytes, fallback),
            timeout=timeout or MODEL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logging.warning("REST model request timed out.")
    except Exception as exc:
        logging.exception("REST model request failed: %s", exc)
    return fallback


def _rest_model_json(
    prompt: str,
    image_bytes: Optional[bytes],
    image_size: tuple[int, int],
    audio_bytes: Optional[bytes],
    fallback: Any,
) -> Any:
    key = _active_model_key()
    if not key:
        return fallback
    model_path = VISION_MODEL_NAME if VISION_MODEL_NAME.startswith("models/") else f"models/{VISION_MODEL_NAME}"
    url = (
        f"{GEMINI_API_BASE.rstrip('/')}/{model_path}:generateContent?"
        + urllib.parse.urlencode({"key": key})
    )
    parts: List[Dict[str, Any]] = [{"text": prompt}]
    prepared_image = _prepare_image_bytes(image_bytes, image_size) if image_bytes else None
    if prepared_image:
        parts.append(
            {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(prepared_image).decode("ascii"),
                }
            }
        )
    if audio_bytes:
        parts.append(
            {
                "inline_data": {
                    "mime_type": "audio/webm",
                    "data": base64.b64encode(audio_bytes).decode("ascii"),
                }
            }
        )
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=MODEL_TIMEOUT) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logging.error("Gemini REST HTTP %s: %s", exc.code, detail[:500])
        return fallback
    data = json.loads(raw)
    text = _extract_rest_text(data)
    return parse_json_object(text, fallback)


def _active_model_key() -> Optional[str]:
    return runtime_model_key or VISION_MODEL_KEY


def _extract_rest_text(data: Dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    return "\n".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()


def _prepare_image(image_bytes: Optional[bytes], size: tuple[int, int]) -> Any:
    if not image_bytes or not Image:
        return None
    try:
        with io.BytesIO(image_bytes) as buffer:
            image = Image.open(buffer)
            image.load()
    except Exception:
        return None
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail(size)
    return image


def _prepare_image_bytes(image_bytes: Optional[bytes], size: tuple[int, int]) -> Optional[bytes]:
    if not image_bytes:
        return None
    if not Image:
        return image_bytes
    image = _prepare_image(image_bytes, size)
    if image is None:
        return None
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue()


def _decode_data_url(value: Any) -> Optional[bytes]:
    if not value or not isinstance(value, str):
        return None
    try:
        if "," in value:
            value = value.split(",", 1)[1]
        return base64.b64decode(value)
    except Exception:
        return None


def _object_guidance_payload(kind: str, result: Dict[str, Any], state: SessionState, target: str) -> Dict[str, Any]:
    x = int(clamp(_float(result.get("x"), 0), -100, 100))
    y = int(clamp(_float(result.get("y"), 0), -100, 100))
    visible = bool(result.get("visible"))
    centered = bool(result.get("centered")) or str(result.get("action")) in {"press", "turn", "pull"}
    confidence = _float(result.get("confidence"), 0)
    haptic = _float(result.get("haptic_strength"), 0)
    if haptic <= 0 and visible:
        haptic = 1 - min(1, ((x * x + y * y) ** 0.5) / 140)
    if centered:
        haptic = 1.0
    return {
        "type": kind,
        "mode": state.mode,
        "target": target,
        "visible": visible,
        "centered": centered,
        "x": x,
        "y": y,
        "confidence": confidence,
        "speech": str(result.get("speech") or result.get("guidance_speech") or ""),
        "haptic_strength": round(clamp(haptic, 0, 1), 2),
        "needs_model_key": bool(result.get("needs_model_key")),
        "stats": _stats(state),
    }


async def _maybe_speak_guidance(
    payload: Dict[str, Any],
    state: SessionState,
    websocket: WebSocket,
    subject: str,
) -> None:
    speech = str(payload.get("speech") or "")
    priority = "high" if payload.get("centered") else "medium"
    gate = _speech_gate(state)
    should_speak, _ = gate.should_speak(priority, subject, "ahead", "target", 1.0, speech)
    if should_speak:
        gate.record(priority, subject, "ahead", "target", 1.0, speech)
        await safe_send_json(websocket, {"type": "speak", "text": speech})


def _speech_gate(state: SessionState) -> SpeechGate:
    gate = getattr(state, "_speech_gate", None)
    if gate is None:
        gate = SpeechGate()
        setattr(state, "_speech_gate", gate)
    return gate


def _clean_objects(raw_objects: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_objects, list):
        return []
    clean = []
    for item in raw_objects:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        clean.append(
            {
                "name": name,
                "category": str(item.get("category") or "object"),
                "distance": _float(item.get("distance"), 0.0),
                "direction": str(item.get("direction") or "ahead"),
                "confidence": _float(item.get("confidence"), _float(item.get("confidence_score"), 0.0)),
            }
        )
    return clean


def _update_tracking(state: SessionState, objects: List[Dict[str, Any]]) -> None:
    for item in objects:
        key = normalize_label(item.get("name"))
        if not key:
            continue
        if key in state.tracked_objects:
            state.tracked_objects[key].update(
                _float(item.get("distance"), 0),
                str(item.get("direction") or "ahead"),
                _float(item.get("confidence"), 0),
            )
        else:
            from app.models import ObjectSighting

            state.tracked_objects[key] = ObjectSighting(
                name=str(item.get("name")),
                category=str(item.get("category") or "object"),
                confidence=_float(item.get("confidence"), 0),
                distance=_float(item.get("distance"), 0),
                direction=str(item.get("direction") or "ahead"),
            )


def _with_distance(speech: str, distance: float) -> str:
    if not speech or distance <= 0:
        return speech
    lower = speech.lower()
    if "meter" in lower or "centimeter" in lower or "away" in lower:
        return speech
    words = distance_to_words(distance)
    return f"{speech} {words} away." if words else speech


def _task_context(state: SessionState) -> str:
    if not state.task.is_active:
        return "No active task."
    current = state.task.current_step
    if not current:
        return "Task has no current step."
    return f"{state.task.name}: step {state.task.current_step_index + 1} of {len(state.task.plan)}: {current.get('instruction')}"


def _stats(state: SessionState) -> Dict[str, int]:
    return {
        "received": state.frames_received,
        "processed": state.frames_processed,
        "skipped": state.frames_skipped,
    }


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
