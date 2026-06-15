"""Configuration and runtime constants."""

from pathlib import Path
import logging
import os

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency during tests
    load_dotenv = None

if load_dotenv:
    load_dotenv()

APP_TITLE = "Assistive Vision Platform"
HOST = os.getenv("APP_HOST", "0.0.0.0")
PORT = int(os.getenv("APP_PORT", "5000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "app_data"
MEMORY_FILE = DATA_DIR / "memory.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)

VISION_MODEL_KEY = os.getenv("VISION_MODEL_KEY") or os.getenv("GEMINI_KEY")
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", "gemini-2.0-flash")
GEMINI_API_BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta")
MODEL_TIMEOUT = float(os.getenv("MODEL_TIMEOUT", "18.0"))

NAV_IMAGE_SIZE = (512, 384)
FAST_IMAGE_SIZE = (320, 240)
OCR_IMAGE_SIZE = (768, 576)
JPEG_MAX_BYTES = int(os.getenv("JPEG_MAX_BYTES", "3500000"))

SCAN_INTERVAL_MS = int(os.getenv("SCAN_INTERVAL_MS", "1000"))
FAST_INTERVAL_MS = int(os.getenv("FAST_INTERVAL_MS", "250"))
OCR_INTERVAL_MS = int(os.getenv("OCR_INTERVAL_MS", "2200"))

CRITICAL_DISTANCE_M = 0.5
DANGER_DISTANCE_M = 1.0
CAUTION_DISTANCE_M = 2.0

MEMORY_HISTORY_LIMIT = int(os.getenv("MEMORY_HISTORY_LIMIT", "600"))
MEMORY_RETENTION_SECONDS = int(os.getenv("MEMORY_RETENTION_SECONDS", str(60 * 60 * 24 * 14)))
STORE_RAW_MEDIA = False

if not VISION_MODEL_KEY:
    logging.warning("VISION_MODEL_KEY is not set; model-backed features will use safe fallbacks.")
