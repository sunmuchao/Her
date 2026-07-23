from __future__ import annotations

import unittest
from unittest import mock

from match_domain.face_attributes_extractor import extract_face_attributes


class _FakeFace:
    def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
        self._left = left
        self._top = top
        self._right = right
        self._bottom = bottom

    def left(self) -> int:
        return self._left

    def top(self) -> int:
        return self._top

    def right(self) -> int:
        return self._right

    def bottom(self) -> int:
        return self._bottom


class _FakePart:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


class _FakeLandmarks:
    def __init__(self, points: list[tuple[int, int]]) -> None:
        self._points = points

    def part(self, index: int) -> _FakePart:
        x, y = self._points[index]
        return _FakePart(x, y)


def _build_points() -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for index in range(68):
        points.append((100 + index * 3, 120 + (index % 7) * 4))
    overrides = {
        0: (90, 230),
        1: (105, 210),
        8: (190, 290),
        15: (275, 210),
        16: (290, 230),
        17: (120, 130),
        18: (135, 125),
        19: (150, 122),
        20: (165, 124),
        21: (180, 129),
        27: (185, 160),
        30: (188, 205),
        31: (172, 208),
        35: (203, 208),
        36: (135, 180),
        37: (145, 172),
        38: (155, 171),
        39: (165, 180),
        40: (155, 188),
        41: (145, 189),
        42: (190, 180),
        43: (200, 171),
        44: (210, 171),
        45: (220, 180),
        46: (210, 188),
        47: (200, 189),
        48: (150, 238),
        51: (180, 230),
        54: (225, 238),
        57: (180, 252),
        62: (180, 236),
        66: (180, 247),
    }
    for index, point in overrides.items():
        points[index] = point
    return points


class FaceAttributesExtractorTests(unittest.TestCase):
    def test_extract_face_attributes_returns_error_when_models_unavailable(self):
        with mock.patch("match_domain.face_attributes_extractor._load_dlib_models", return_value=(None, None, "missing_landmark_model")):
            result = extract_face_attributes("https://img.her.local/a.jpg")

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "missing_landmark_model")

    def test_extract_face_attributes_returns_landmark_payload(self):
        fake_face = _FakeFace(100, 120, 280, 300)
        fake_points = _build_points()
        fake_detector = mock.Mock(return_value=[fake_face])
        fake_predictor = mock.Mock(return_value=_FakeLandmarks(fake_points))
        fake_image = mock.Mock()
        fake_image.shape = (400, 400, 3)

        with (
            mock.patch("match_domain.face_attributes_extractor._load_dlib_models", return_value=(fake_detector, fake_predictor, None)),
            mock.patch("match_domain.face_attributes_extractor._load_image_from_source", return_value=(fake_image, None)),
        ):
            result = extract_face_attributes("https://img.her.local/a.jpg")

        self.assertTrue(result["success"])
        self.assertEqual(result["face_count"], 1)
        self.assertEqual(result["selected_face_index"], 0)
        self.assertEqual(result["attributes"]["face_shape_type"], "round")
        self.assertIn("eye_size_score", result["attributes"])
        self.assertGreater(result["attribute_confidence"], 0)


if __name__ == "__main__":
    unittest.main()
