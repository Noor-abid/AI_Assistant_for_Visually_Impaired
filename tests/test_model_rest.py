import json
import unittest
from unittest.mock import patch

from app.services import processor


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "visible": True,
                                            "centered": True,
                                            "x": 0,
                                            "y": 0,
                                            "speech": "Cup centered.",
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        ).encode("utf-8")


class RestModelTests(unittest.TestCase):
    def test_runtime_key_uses_rest_without_sdk_client(self):
        original_key = processor.runtime_model_key
        processor.runtime_model_key = "test-key"
        try:
            with patch("urllib.request.urlopen", return_value=_FakeResponse()) as mocked:
                result = processor._rest_model_json(
                    "Find the cup",
                    image_bytes=b"not-a-real-image",
                    image_size=(320, 240),
                    audio_bytes=None,
                    fallback={},
                )
            self.assertTrue(result["visible"])
            request = mocked.call_args.args[0]
            self.assertIn("key=test-key", request.full_url)
            body = json.loads(request.data.decode("utf-8"))
            self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
            self.assertEqual(body["contents"][0]["parts"][0]["text"], "Find the cup")
        finally:
            processor.runtime_model_key = original_key


if __name__ == "__main__":
    unittest.main()

