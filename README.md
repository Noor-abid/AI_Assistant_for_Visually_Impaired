# Assistive Vision Platform

Mobile-first assistive vision app for blind and low-vision users. It combines live camera guidance, object finding, OCR, scene questions, step-by-step task support, and tactile/audio feedback in one privacy-conscious interface.

## What It Does

- Live navigation alerts for nearby hazards, useful objects, distance, direction, and environmental state.
- Object finding with fast center-the-target feedback. Common objects such as cups, bottles, chairs, people, bags, phones, laptops, books, and utensils can be found in-browser without a Gemini key after the browser downloads the no-key detector.
- Find mode is voice-first: tap Find, say the object name, and guidance is spoken aloud.
- Precision guidance for small targets such as switches, buttons, handles, and plugs.
- OCR mode for reading visible text aloud.
- Scene question answering from voice plus camera context.
- Task guidance with visual step verification.
- Privacy-safe memory that stores text summaries only, never raw camera frames or recorded audio.

## Run Locally

```bash
pip install -r requirements.txt
python main.py
```

Open `http://localhost:5000`.

If dependencies are not installed yet, `python main.py` automatically starts a no-network local runner that serves the same interface and WebSocket contract with safe fallback responses. Install the requirements when you want the production FastAPI/Uvicorn server and live model SDK.

## Configuration

Create a `.env` file when using a hosted multimodal model:

```env
VISION_MODEL_KEY=your_key_here
VISION_MODEL_NAME=gemini-2.0-flash
LOG_LEVEL=INFO
```

The app still starts without a model key. Common-object finding can run in the browser without a key. OCR, open-ended scene questions, detailed social/environment reasoning, and task verification still need `VISION_MODEL_KEY` or `GEMINI_KEY` unless you replace them with another local model. Do not ask the end user to paste a key during use; configure it ahead of time in `.env` when those advanced features are needed.

## Implementation Notes

- The live camera UI sends compressed JPEG frames through a WebSocket.
- Control messages are JSON and include mode switches, voice inquiries, task controls, and privacy actions.
- Haptic feedback uses the browser Vibration API when available and falls back to spatial audio.
- Memory is capped and summary-only by default.
