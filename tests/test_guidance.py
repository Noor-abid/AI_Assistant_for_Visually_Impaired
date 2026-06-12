import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

import visio_ai_server
from visio_ai_server import (
    clear_memory,
    detect_target_box,
    guidance_from_box,
    load_memory,
    micro_navigation,
    model_adapter_status,
    navigation_analysis,
    object_guidance,
    ocr_result,
    parse_command,
    save_landmark,
    task_plan,
    visual_inquiry,
)


class GuidanceTests(unittest.TestCase):
    def test_centered_box_locks_target(self):
        guide = guidance_from_box({"x": 0.45, "y": 0.45, "w": 0.1, "h": 0.1})
        self.assertTrue(guide.locked)
        self.assertEqual(guide.pulse, "locked")

    def test_far_left_box_gives_left_direction(self):
        guide = guidance_from_box({"x": 0.05, "y": 0.45, "w": 0.1, "h": 0.1})
        self.assertIn("left", guide.direction)
        self.assertEqual(guide.pulse, "slow")

    def test_medium_distance_maps_to_medium_pulse(self):
        guide = guidance_from_box({"x": 0.25, "y": 0.45, "w": 0.1, "h": 0.1})
        self.assertEqual(guide.pulse, "medium")

    def test_detects_synthetic_door_as_door(self):
        image = Image.new("RGB", (320, 240), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 35, 105, 220), fill="black")
        detection = detect_target_box(image, "door")
        self.assertTrue(detection["found"])
        self.assertEqual(detection["category"], "door")

    def test_detects_synthetic_stairs_and_handrail(self):
        image = Image.new("RGB", (320, 240), "#7f888b")
        draw = ImageDraw.Draw(image)
        draw.rectangle((35, 55, 50, 210), fill="#111820")
        for y in (110, 130, 150, 170, 190):
            draw.rectangle((85, y, 290, y + 8), fill="#252b31")
        stairs = detect_target_box(image, "stairs")
        handrail = detect_target_box(image, "handrail")
        self.assertTrue(stairs["found"])
        self.assertTrue(handrail["found"])

    def test_navigation_flags_stairs_as_caution(self):
        image = Image.new("RGB", (320, 240), "#7f888b")
        draw = ImageDraw.Draw(image)
        for y in (105, 128, 151, 174, 197):
            draw.rectangle((70, y, 295, y + 8), fill="#20262c")
        result = navigation_analysis(image)
        self.assertTrue(any(hazard["type"] == "stairs" for hazard in result["hazards"]))

    def test_object_guidance_reports_not_found_for_missing_target(self):
        image = Image.new("RGB", (320, 240), "white")
        result = object_guidance(image, "door")
        self.assertFalse(result["found"])
        self.assertIsNone(result["guidance"])

    def test_ocr_reports_text_region_on_high_contrast_lines(self):
        image = Image.new("RGB", (320, 240), "white")
        draw = ImageDraw.Draw(image)
        for y in (70, 95, 120):
            draw.rectangle((40, y, 240, y + 12), fill="black")
        result = ocr_result(image)
        self.assertEqual(result.get("region_status", result["status"]), "text_region_detected")

    def test_tesseract_adapter_returns_recognized_text(self):
        original_cmd = visio_ai_server.TESSERACT_CMD
        with TemporaryDirectory() as tmp:
            fake_tesseract = Path(tmp) / "fake_tesseract.py"
            fake_tesseract.write_text("print('NETRA LABEL')\n", encoding="utf-8")
            visio_ai_server.TESSERACT_CMD = f'"{sys.executable}" "{fake_tesseract}"'
            try:
                image = Image.new("RGB", (320, 240), "white")
                result = ocr_result(image)
                self.assertEqual(result["status"], "recognized")
                self.assertEqual(result["engine"], "tesseract")
                self.assertEqual(result["text"], "NETRA LABEL")
            finally:
                visio_ai_server.TESSERACT_CMD = original_cmd

    def test_navigation_flags_low_light_hazard(self):
        image = Image.new("RGB", (320, 240), "black")
        result = navigation_analysis(image)
        self.assertEqual(result["priority"], "high")
        self.assertTrue(any(hazard["type"] == "low_light" for hazard in result["hazards"]))
        self.assertEqual(result["risk"]["level"], "high")
        self.assertTrue(result["risk"]["stop_required"])
        self.assertIn("Pause", result["next_actions"]["primary"])

    def test_navigation_returns_goal_next_action(self):
        image = Image.new("RGB", (320, 240), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((130, 30, 190, 220), fill="black")
        result = navigation_analysis(image, "door")
        self.assertTrue(result["target_detected"])
        self.assertEqual(result["next_actions"]["mode_hint"], "precision")
        self.assertIn("door", " ".join(result["next_actions"]["steps"]))

    def test_micro_navigation_reports_centered_target(self):
        image = Image.new("RGB", (320, 240), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((130, 30, 190, 220), fill="black")
        result = micro_navigation(image, "door")
        self.assertTrue(result["found"])
        self.assertEqual(result["action"], "hold")

    def test_task_plan_supports_netra_style_presets(self):
        result = task_plan("help me make coffee")
        self.assertEqual(result["task"], "coffee")
        self.assertGreaterEqual(len(result["steps"]), 4)

    def test_task_plan_supports_safety_presets(self):
        stairs = task_plan("help with stairs")
        medicine = task_plan("read medicine")
        self.assertEqual(stairs["task"], "stairs")
        self.assertEqual(medicine["task"], "medicine")

    def test_task_plan_creates_custom_find_workflow(self):
        result = task_plan("find my keys")
        self.assertEqual(result["task"], "custom")
        self.assertIn("keys", result["target"])
        self.assertEqual(result["source"], "local-rule-planner")

    def test_command_parser_supports_netra_intents(self):
        self.assertEqual(parse_command("find door")["intent"], "find")
        self.assertEqual(parse_command("precision handle")["intent"], "micro")
        self.assertEqual(parse_command("task make coffee")["intent"], "task")
        self.assertEqual(parse_command("save place kitchen")["intent"], "tag")
        self.assertEqual(parse_command("next step")["intent"], "task_next")
        self.assertEqual(parse_command("what is around me?")["intent"], "inquiry")

    def test_visual_inquiry_answers_target_question(self):
        image = Image.new("RGB", (320, 240), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((130, 30, 190, 220), fill="black")
        result = visual_inquiry(image, "Where is the door?")
        self.assertEqual(result["intent"], "target")
        self.assertIn("door", result["answer"])

    def test_model_adapter_status_reports_local_profile(self):
        status = model_adapter_status()
        self.assertIn("active_profile", status)
        self.assertIn("navigation_vlm", status["adapters"])
        self.assertIn("object_detector", status["adapters"])
        self.assertIn("ocr_engine", status["adapters"])

    def test_persistent_memory_save_and_clear(self):
        original_file = visio_ai_server.MEMORY_FILE
        with TemporaryDirectory() as tmp:
            visio_ai_server.MEMORY_FILE = Path(tmp) / "memory.json"
            try:
                landmark = save_landmark({"name": "Kitchen", "note": "Left of the sink"})
                self.assertEqual(landmark["name"], "Kitchen")
                self.assertEqual(load_memory()["locations"][0]["note"], "Left of the sink")
                clear_memory()
                self.assertEqual(load_memory()["locations"], [])
            finally:
                visio_ai_server.MEMORY_FILE = original_file


if __name__ == "__main__":
    unittest.main()
