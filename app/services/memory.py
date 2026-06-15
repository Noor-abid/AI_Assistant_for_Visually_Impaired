"""Privacy-safe memory storage."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import MEMORY_FILE, MEMORY_HISTORY_LIMIT, MEMORY_RETENTION_SECONDS, STORE_RAW_MEDIA
from app.utils import normalize_label


class PrivacySafeMemory:
    def __init__(self, path: Path = MEMORY_FILE):
        self.path = path
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"locations": {}, "history": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"locations": {}, "history": []}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def add_location(self, name: str, summary: str) -> None:
        key = normalize_label(name)
        if not key:
            return
        self.data.setdefault("locations", {})[key] = {
            "name": name.strip(),
            "summary": summary.strip()[:600],
            "timestamp": time.time(),
        }
        self.save()

    def log_object(self, name: str, location: Optional[str], scene: str, confidence: float) -> None:
        label = normalize_label(name)
        if not label or label in {"none", "unknown", "null"}:
            return
        entry = {
            "object": label,
            "location": normalize_label(location),
            "scene": scene.strip()[:500],
            "confidence": round(float(confidence or 0), 2),
            "timestamp": time.time(),
            "raw_media_stored": STORE_RAW_MEDIA,
        }
        history = self.data.setdefault("history", [])
        if history and history[-1].get("object") == label and time.time() - history[-1].get("timestamp", 0) < 8:
            return
        history.append(entry)
        self._prune()
        self.save()

    def context(self) -> str:
        self._prune()
        locations = self.data.get("locations", {})
        history = self.data.get("history", [])[-30:]
        parts = []
        if locations:
            loc_text = "; ".join(f"{v.get('name')}: {v.get('summary')}" for v in locations.values())
            parts.append(f"Known locations: {loc_text}")
        if history:
            object_text = "; ".join(
                f"{h.get('object')} near {h.get('location') or 'unknown place'}"
                for h in history[-15:]
            )
            parts.append(f"Recent objects: {object_text}")
        return "\n".join(parts) if parts else "No stored summaries."

    def clear(self) -> None:
        self.data = {"locations": {}, "history": []}
        self.save()

    def _prune(self) -> None:
        cutoff = time.time() - MEMORY_RETENTION_SECONDS
        history = [h for h in self.data.get("history", []) if h.get("timestamp", 0) >= cutoff]
        self.data["history"] = history[-MEMORY_HISTORY_LIMIT:]


memory_store = PrivacySafeMemory()

