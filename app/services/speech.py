"""Speech throttling and priority rules."""

from __future__ import annotations

import time
from typing import Dict, Tuple

from app.utils import semantic_key


class SpeechGate:
    def __init__(self) -> None:
        self.last_key = ""
        self.last_priority = "low"
        self.last_distance = 999.0
        self.last_spoken_at = 0.0
        self.busy_until = 0.0
        self.subject_cooldowns: Dict[str, float] = {}

    def should_speak(
        self,
        priority: str,
        subject: str,
        direction: str,
        category: str,
        distance: float,
        text: str,
    ) -> Tuple[bool, str]:
        if not text:
            return False, "empty"
        now = time.time()
        priority = (priority or "low").lower()
        if priority == "critical":
            return True, "critical"
        if now < self.busy_until:
            return False, "speaking"
        key = semantic_key(subject, direction, category)
        if key == self.last_key:
            cooldown = {"high": 2.0, "medium": 4.0, "low": 8.0}.get(priority, 5.0)
            if self.last_distance - distance > 0.4:
                return True, "closer"
            if now - self.last_spoken_at < cooldown:
                return False, "same_context"
        subject_key = (subject or "").lower()
        if subject_key and now - self.subject_cooldowns.get(subject_key, 0) < 8:
            return False, "subject_cooldown"
        return True, "new"

    def record(
        self,
        priority: str,
        subject: str,
        direction: str,
        category: str,
        distance: float,
        text: str,
    ) -> None:
        now = time.time()
        self.last_key = semantic_key(subject, direction, category)
        self.last_priority = priority
        self.last_distance = distance
        self.last_spoken_at = now
        self.busy_until = now + max(1.0, len(text.split()) / 2.6)
        if subject:
            self.subject_cooldowns[subject.lower()] = now

