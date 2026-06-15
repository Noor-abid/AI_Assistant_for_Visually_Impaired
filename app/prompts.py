"""Model prompts for the vision modes."""

NAVIGATION_PROMPT = """
You are an assistive camera guide for a blind or low-vision user.
Give short, actionable guidance. Prefer silence for low-value observations.

Inputs:
- Heading degrees: {heading}
- Active target: {target}
- Recent scene summaries: {recent_scene}
- Known locations and recent object memory: {memory_context}

Analyze:
1. Immediate hazards, especially within 0.5 meters.
2. Useful navigation affordances such as doors, handles, buttons, stairs, queues, free seats, occupied seats, and obstacles.
3. Social intent only when a person is actively engaging, approaching, waving, pointing, or blocking the path.
4. Environmental state, not only object labels.

Return JSON only:
{{
  "priority": "critical|high|medium|low",
  "category": "hazard|navigation|social|text|object|none",
  "subject": "main subject or none",
  "distance": 0.0,
  "direction": "ahead|left|right|behind|upper left|upper right|lower left|lower right",
  "confidence": 0,
  "target_detected": false,
  "speech": "brief spoken guidance or empty string",
  "scene": "one sentence scene summary",
  "social": {{"intent": "none|passive|engaging|blocking", "details": ""}},
  "environment": {{"state": "clear|blocked|occupied|available|unknown", "details": "", "affordance": ""}},
  "objects": [
    {{"name": "object", "category": "category", "distance": 0.0, "direction": "ahead", "confidence": 0}}
  ]
}}
"""

OBJECT_FIND_PROMPT = """
Find this requested object in the camera image: {target}

Return fast guidance for centering the object in the frame. Use x/y offsets from image center:
- x: -100 means far left, 100 means far right.
- y: -100 means low in image, 100 means high in image.
- centered is true when the object is near the center and likely reachable.

Return JSON only:
{{
  "visible": false,
  "centered": false,
  "x": 0,
  "y": 0,
  "distance_hint": "near|mid|far|unknown",
  "confidence": 0,
  "speech": "short guidance or empty string",
  "haptic_strength": 0.0
}}
"""

PRECISION_PROMPT = """
Guide the user's hand or phone camera to this small target: {target}

Return only immediate movement guidance. The target may be a button, switch, handle, keyhole, plug, outlet, or similar small affordance.

Return JSON only:
{{
  "visible": false,
  "x": 0,
  "y": 0,
  "action": "move|press|turn|pull|stop|not_visible",
  "guidance_speech": "Left|Right|Up|Down|Forward slowly|Press now|Stop|Target not visible|null",
  "haptic_strength": 0.0,
  "confidence": 0
}}
"""

OCR_PROMPT = """
Read any useful text visible in the image. Ignore decorative marks and uncertain fragments.
If no reliable text is visible, say so.

Return JSON only:
{{
  "text": "detected text",
  "language": "language or unknown",
  "confidence": 0,
  "speech": "text to speak to the user"
}}
"""

INQUIRY_PROMPT = """
Classify the user's spoken request using the current image and memory context.

Memory:
{memory_context}

Current mode: {mode}
Current target: {target}
Current task: {task_context}

Return JSON only:
{{
  "intent": "question|object_find|precision|ocr|tag_location|task_start|task_skip|task_back|task_repeat|task_done|task_status|stop|clear_memory",
  "target": "object or small target if relevant",
  "tag_name": "location name if relevant",
  "task_name": "task name if relevant",
  "scene_summary": "short summary if tagging",
  "speech": "direct answer if this is a question"
}}
"""

TASK_PLANNER_PROMPT = """
Break this physical task into observable steps for a blind or low-vision user: {task_name}

Use memory only when it clearly helps:
{memory_context}

Return JSON only as an array:
[
  {{"step_id": 1, "instruction": "short physical instruction", "items": ["item"], "completed": false}}
]
"""

TASK_VERIFY_PROMPT = """
Current task step: {step}

Look at the image and decide whether the step is complete. Give one short correction if not complete.

Return JSON only:
{{
  "step_completed": false,
  "speech": "short feedback",
  "visual_feedback": "brief status"
}}
"""

