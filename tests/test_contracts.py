import tempfile
import unittest
from pathlib import Path

from app.services.memory import PrivacySafeMemory
from app.services.speech import SpeechGate
from app.utils import distance_to_words, parse_json_object, semantic_key


class UtilityContractTests(unittest.TestCase):
    def test_parse_json_object_accepts_code_fences(self):
        self.assertEqual(parse_json_object("```json\n{\"ok\": true}\n```", {}), {"ok": True})

    def test_distance_words_are_human_readable(self):
        self.assertEqual(distance_to_words(0.42), "42 centimeters")
        self.assertEqual(distance_to_words(2.25), "2.2 meters")

    def test_semantic_key_ignores_visual_adjectives(self):
        self.assertEqual(semantic_key("large white Door", "ahead", "navigation"), "door|ahead|navigation")


class PrivacyMemoryTests(unittest.TestCase):
    def test_memory_stores_summaries_not_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PrivacySafeMemory(Path(tmp) / "memory.json")
            store.add_location("Kitchen", "Counter and sink ahead")
            store.log_object("Mug", "Kitchen", "Mug near sink", 92)
            text = (Path(tmp) / "memory.json").read_text(encoding="utf-8")
            self.assertIn("Mug".lower(), text)
            self.assertIn("raw_media_stored", text)
            self.assertNotIn("data:image", text)
            self.assertNotIn("audio/webm", text)


class SpeechGateTests(unittest.TestCase):
    def test_repeated_noncritical_speech_is_throttled(self):
        gate = SpeechGate()
        first, _ = gate.should_speak("low", "chair", "ahead", "object", 2.0, "Chair ahead")
        self.assertTrue(first)
        gate.record("low", "chair", "ahead", "object", 2.0, "Chair ahead")
        second, reason = gate.should_speak("low", "chair", "ahead", "object", 2.0, "Chair ahead")
        self.assertFalse(second)
        self.assertIn(reason, {"speaking", "same_context", "subject_cooldown"})


if __name__ == "__main__":
    unittest.main()

