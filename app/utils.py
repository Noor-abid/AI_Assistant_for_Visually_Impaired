"""Small helpers shared across services."""

from __future__ import annotations

import json
import re
from typing import Any


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_label(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def parse_json_object(text: str | None, fallback: Any) -> Any:
    if not text:
        return fallback
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.DOTALL)
        if not match:
            return fallback
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return fallback


def distance_to_words(distance_m: float) -> str:
    if distance_m <= 0:
        return ""
    if distance_m < 1:
        return f"{round(distance_m * 100)} centimeters"
    if distance_m < 10:
        return f"{distance_m:.1f} meters"
    return f"{round(distance_m)} meters"


def semantic_key(subject: str, direction: str, category: str) -> str:
    ignore = {
        "a",
        "an",
        "the",
        "small",
        "large",
        "big",
        "little",
        "red",
        "blue",
        "green",
        "black",
        "white",
        "gray",
        "grey",
        "open",
        "closed",
    }
    words = [word for word in normalize_label(subject).split() if word not in ignore]
    core = " ".join(words) or normalize_label(subject)
    return f"{core}|{normalize_label(direction)}|{normalize_label(category)}"

