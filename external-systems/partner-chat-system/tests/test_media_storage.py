import pathlib
import sys
import unittest


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system.media_storage import _generate_object_key


class MediaStorageTests(unittest.TestCase):
    def test_generate_object_key_uses_audio_extensions(self):
        cases = {
            "audio/mpeg": ".mp3",
            "audio/wav": ".wav",
            "audio/ogg": ".ogg",
            "audio/mp4": ".m4a",
        }

        for content_type, suffix in cases.items():
            with self.subTest(content_type=content_type):
                object_key = _generate_object_key("xiaoya", content_type)
                self.assertTrue(object_key.startswith("chat/xiaoya/"))
                self.assertTrue(object_key.endswith(suffix))


if __name__ == "__main__":
    unittest.main()
