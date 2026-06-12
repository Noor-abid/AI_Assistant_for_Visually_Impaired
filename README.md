# VISIO-NETRA

VISIO-NETRA is a mobile-first assistive vision project inspired by the Netra reference project and the AIDEN-style research paper in this workspace. It turns a phone or laptop browser into a local vision assistant for object finding, scene awareness, OCR support, social cues, step-by-step tasks, and saved spatial landmarks.

The app runs locally with Python and a browser. The default build does not need a cloud API key. It uses deterministic local image heuristics so the complete workflow can be demonstrated immediately, while the same API shape can later be connected to YOLOv8, Gemini, LLaVA, Tesseract, EasyOCR, or another production model.

## Safety Note

This is a research and demo project, not a certified mobility, medical, or safety device. It can miss objects and it can be wrong. Treat every answer as supportive guidance only. Confirm important movement or object-handling decisions with touch, sound, cane, guide dog, a trusted person, or your usual safe navigation method.

## What This Version Adds

Compared with the public Netra idea, this version is built as a fuller local product:

- Camera-first Netra-style interface with AI reasoning and detected-object overlays
- One-screen mobile PWA layout that also works on desktop
- Object finding with direction, distance estimate, confidence, vibration pattern, and speech
- Precision mode for centering small targets such as handles, labels, and cups
- Navigation analysis with hazards, stairs, handrails, social cues, environment markers, and saved-place matching
- New risk scoring that turns visual evidence into `Low caution`, `Caution`, or `High caution`
- New next-action guidance so the user gets a clear "what to do now" step
- Quick command chips for common actions such as finding a door or reading text
- Browser speech output, optional voice commands, vibration, and simple spatial audio cues
- OCR workflow with browser `TextDetector`, optional local Tesseract, and manual text fallback
- Social-awareness mode that avoids identity recognition and uses consent-aware language
- Task planner for tea, coffee, doors, labels, seats, elevators, stairs, medicine labels, and custom tasks
- Memory Palace that saves useful places locally in the browser and in a private local JSON file
- PWA install support with manifest, icons, and offline shell cache
- Unit tests for core guidance, detection, OCR fallback, tasks, memory, commands, and risk reasoning

## Quick Start

From this folder:

```powershell
.\run_visio_ai.cmd
```

Then open:

```text
http://127.0.0.1:8765
```

If port `8765` is already busy, the launcher automatically uses `8766` and opens that URL instead.

If you prefer to run Python directly, use the bundled Python on this machine:

```powershell
& "C:\Users\zaina\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" visio_ai_server.py
```

## Phone Testing

To test from a phone on the same Wi-Fi:

```powershell
.\run_visio_mobile.cmd
```

Open the URL shown by the script on your phone.

Mobile camera note: iPhone and Android browsers often require HTTPS for camera access unless the app is running on the device's own `localhost`. The app still works in demo-frame mode over local HTTP. For real phone-camera testing, host it behind HTTPS or wrap it with a mobile shell such as Capacitor.

## How To Demo It

1. Start the server and open `http://127.0.0.1:8765`.
2. Press **Frame** to cycle through built-in demo scenes, or press **Start Camera** if your browser allows camera access.
3. Press **Navigate** to get scene, hazard, object, social, risk, and next-action output.
4. Set the target to `door`, `stairs`, `cup`, `handle`, `text`, or `person`.
5. Try **Find**, **Precision**, **Read**, **Scene**, and **Social**.
6. Use command chips or type commands such as:

```text
find door
precision handle
navigate to stairs
what is around me?
is someone there?
read text
task make coffee
task read medicine
save place kitchen
stop
```

## Core Features

### Navigation

`POST /api/analyze/navigation` combines multiple local signals:

- scene summary
- target search
- detected objects
- hazards
- social cue
- saved-place match
- environment state
- risk score
- next actions

The risk score is intentionally simple and understandable. Dim lighting, low visual detail, stairs, nearby obstructions, and high-priority hazards increase caution. A usable target lock can reduce caution slightly, but the app still asks the user to confirm important actions.

### Find Object

The object finder normalizes targets such as `door`, `handle`, `cup`, `bottle`, `phone`, `laptop`, `text`, `person`, `stairs`, and `handrail`. It returns:

- whether the target was found
- a bounding box
- direction from center
- distance estimate
- confidence band
- vibration pattern
- spoken guidance

### Precision Mode

Precision mode gives micro-navigation output:

- x/y vector from the target to the frame center
- action such as `move_left`, `move_right`, `tilt_up`, `tilt_down`, or `hold`
- haptic pulse
- tone frequency
- spoken instruction

This is the closest match to the AIDEN paper's Geiger-counter-style object-centering idea.

### OCR

The reader uses the browser's native `TextDetector` when available. The backend can also use local Tesseract if it is installed or configured through `TESSERACT_CMD`. Without OCR software, the app still detects likely text regions and lets the user paste manual text to speak aloud.

### Social Awareness

The social mode only reports conservative person-like visual cues. It does not identify people, infer identity, or store biometric information.

### Task Guidance

The task system creates step-by-step flows and verifies the current step from the latest frame. Included presets:

- make tea
- make coffee
- approach a door
- read a product label
- find a seat
- use an elevator panel
- handle stairs
- read medicine
- custom local task plans

### Memory Palace

Saved places are stored in browser localStorage and in `visio_netra_memory.json` on the local server. Images are not stored. Later navigation scans can match the current scene to saved place descriptions.

## API Reference

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Service status and enabled features |
| `GET /api/model/status` | Local and optional model-adapter readiness |
| `POST /api/analyze/navigation` | Full Netra-style navigation payload |
| `POST /api/analyze/object` | Object guidance with haptic mapping |
| `POST /api/analyze/micro` | Precision target-centering guidance |
| `POST /api/analyze/scene` | Scene summary |
| `POST /api/analyze/ocr` | OCR or text-region analysis |
| `POST /api/analyze/social` | Consent-aware social cue check |
| `POST /api/analyze/task` | Visual verification for a task step |
| `POST /api/inquire` | Ask a question about the current frame |
| `POST /api/task/plan` | Generate a preset or custom task plan |
| `POST /api/command` | Parse typed or spoken commands |
| `GET /api/memory` | Read saved landmarks and object history |
| `POST /api/memory/save` | Save a Memory Palace landmark |
| `POST /api/memory/clear` | Clear local Memory Palace data |
| `GET /ws/guidance` | Compatibility WebSocket for object guidance |

Frame endpoints accept a browser image data URL:

```json
{
  "image": "data:image/jpeg;base64,...",
  "goal": "door",
  "landmarks": []
}
```

## Project Structure

```text
VISIO-NETRA
|-- visio_ai_server.py          Local web server and assistive-vision API
|-- public/
|   |-- index.html              Mobile-first interface
|   |-- styles.css              Responsive accessible styling
|   |-- app.js                  Camera, speech, tasks, memory, and UI logic
|   |-- manifest.webmanifest    PWA metadata
|   |-- service-worker.js       Offline shell cache
|   |-- icon.svg                App icon
|   |-- icon-192.png            PWA icon
|   `-- icon-512.png            PWA icon
|-- tests/
|   `-- test_guidance.py        Unit tests
|-- docs/
|   `-- project_solution.md     Research-style project write-up
|-- extracted/                  Extracted research-paper text
|-- run_visio_ai.cmd            Local desktop launcher
|-- run_visio_mobile.cmd        Same-Wi-Fi mobile launcher
|-- requirements.txt            Python dependencies
`-- VISIO-NETRA-project.zip     Packaged copy of the project
```

## Installable App Mode

The project includes:

- PWA manifest
- home-screen icons
- service worker
- portrait orientation
- mobile-safe layout
- install button when the browser exposes `beforeinstallprompt`

On Android Chrome or Edge, open the app and choose **Install app** or **Add to Home screen**. On iPhone Safari, use Share, then **Add to Home Screen**.

## Production AI Upgrade Path

The local demo is intentionally model-agnostic. To make it production-grade:

1. Replace `detect_target_box()` with YOLOv8, RT-DETR, MediaPipe, or another detector.
2. Replace `describe_scene()` and `navigation_analysis()` reasoning with Gemini, LLaVA, or an on-device VLM.
3. Replace `ocr_result()` with Tesseract, EasyOCR, PaddleOCR, or VLM transcription.
4. Keep `guidance_from_box()` and `micro_navigation()` output shapes so vibration and audio behavior remain stable.
5. Add calibrated confidence, latency logging, and real user-study evaluation before making safety claims.

Optional adapter environment variables:

```powershell
$env:VISIO_NETRA_MODEL_MODE = "local"   # local, hybrid, gemini, or cloud
$env:GEMINI_KEY = "your_key_here"       # or GOOGLE_API_KEY / GEMINI_API_KEY
$env:VISIO_NETRA_LLAVA_ENDPOINT = "http://localhost:11434/api/generate"
$env:VISIO_NETRA_YOLO_MODEL = "C:\models\yolov8n.pt"
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
$env:VISIO_NETRA_OCR_TIMEOUT = "8"
```

Check adapter readiness at:

```text
http://127.0.0.1:8765/api/model/status
```

## Testing

Run:

```powershell
& "C:\Users\zaina\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s tests
```

Current coverage includes:

- haptic pulse mapping
- synthetic object detection
- stairs and handrail detection
- low-light hazards
- navigation risk and next actions
- object guidance not-found handling
- OCR text-region fallback
- optional local Tesseract adapter
- precision guidance
- task planning
- command parsing
- visual inquiry
- model-adapter status
- persistent Memory Palace save and clear

## Privacy Model

- Camera frames are analyzed in memory.
- Uploaded frames are not written to disk.
- The default demo makes no cloud model calls.
- Memory Palace text is stored locally in browser storage and `visio_netra_memory.json`.
- Social mode does not identify people or store biometric data.

## Known Limitations

- The default vision engine is heuristic-based, not a real object detector.
- Distance values are rough estimates from bounding-box size and center position.
- Browser vibration support varies, especially on iOS.
- Browser `TextDetector` is experimental and not available everywhere.
- Real navigation safety requires stronger models, uncertainty calibration, latency testing, and user evaluation.

## Reference Inspiration

- Reference project: [ZentraHost/netra_project](https://github.com/ZentraHost/netra_project)
- Video reference: [YouTube demo](https://www.youtube.com/watch?v=Ax3SkwHOkkk)
- Research direction: AIDEN-style object guidance, OCR, scene description, haptic feedback, TAM evaluation, and privacy-aware assistive AI

VISIO-NETRA keeps the Netra-style experience but turns it into a clearer, more complete, locally runnable project that is easy to demonstrate and practical to upgrade.
