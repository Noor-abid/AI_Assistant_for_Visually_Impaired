"""Internal state models."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any, Deque, Dict, List, Literal, Optional
from collections import deque

ModeName = Literal["navigation", "object_find", "precision", "task", "ocr"]


@dataclass
class TaskState:
    is_active: bool = False
    name: str = ""
    plan: List[Dict[str, Any]] = field(default_factory=list)
    current_step_index: int = 0

    @property
    def current_step(self) -> Optional[Dict[str, Any]]:
        if not self.is_active or not self.plan:
            return None
        if self.current_step_index >= len(self.plan):
            return None
        return self.plan[self.current_step_index]

    def clear(self) -> None:
        self.is_active = False
        self.name = ""
        self.plan = []
        self.current_step_index = 0


@dataclass
class ObjectSighting:
    name: str
    category: str
    confidence: float
    distance: float
    direction: str
    last_seen: float = field(default_factory=time)
    frames_seen: int = 1

    def update(self, distance: float, direction: str, confidence: float) -> None:
        self.distance = (self.distance * 0.65) + (distance * 0.35)
        self.direction = direction
        self.confidence = max(self.confidence, confidence)
        self.last_seen = time()
        self.frames_seen += 1


@dataclass
class SessionState:
    mode: ModeName = "navigation"
    active_target: Optional[str] = None
    latest_frame: Optional[bytes] = None
    latest_heading: int = 0
    is_processing: bool = False
    frames_received: int = 0
    frames_processed: int = 0
    frames_skipped: int = 0
    last_mode_change: float = field(default_factory=time)
    recent_scene: Deque[str] = field(default_factory=lambda: deque(maxlen=5))
    recent_speech: Deque[str] = field(default_factory=lambda: deque(maxlen=6))
    tracked_objects: Dict[str, ObjectSighting] = field(default_factory=dict)
    task: TaskState = field(default_factory=TaskState)

    def set_mode(self, mode: ModeName, target: Optional[str] = None) -> None:
        self.mode = mode
        self.active_target = target
        self.last_mode_change = time()

    def clear_goal(self) -> None:
        self.mode = "navigation"
        self.active_target = None
        self.task.clear()

