"""脸部细节属性提取器（基于 dlib 68 点关键点检测）。"""

from __future__ import annotations

import json
import logging
import ssl
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import cv2
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import dlib
except Exception:  # pragma: no cover - optional dependency
    dlib = None

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency
    np = None

_logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "dlib-68-landmarks-v2"
MODEL_DIR = Path.home() / ".dlib" / "models"
DEFAULT_PREDICTOR_PATH = MODEL_DIR / "shape_predictor_68_face_landmarks.dat"
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 8.0
MIN_FACE_EDGE_PX = 80
MIN_FACE_AREA_RATIO = 0.03

_detector = None
_predictor = None


def _source_kind(photo_source: str) -> str:
    parsed = urlparse(str(photo_source or "").strip())
    if parsed.scheme in {"http", "https"}:
        return "url"
    return "local_path"


def _load_dlib_models(predictor_path: str | Path | None = None):
    global _detector, _predictor

    if dlib is None:
        return None, None, "missing_dlib_dependency"
    if cv2 is None or np is None:
        return None, None, "missing_cv2_or_numpy_dependency"

    if _detector is None:
        _detector = dlib.get_frontal_face_detector()
        _logger.info("dlib 人脸检测器已加载")

    if _predictor is None:
        model_path = Path(predictor_path or DEFAULT_PREDICTOR_PATH)
        if not model_path.exists():
            _logger.error("dlib 模型文件不存在: %s", model_path)
            return None, None, "missing_landmark_model"
        _predictor = dlib.shape_predictor(str(model_path))
        _logger.info("dlib 关键点预测器已加载: %s", model_path)

    return _detector, _predictor, None


def _load_image_from_source(photo_source: str) -> tuple[Any | None, str | None]:
    normalized = str(photo_source or "").strip()
    if not normalized:
        return None, "empty_photo_source"
    if cv2 is None or np is None:
        return None, "missing_cv2_or_numpy_dependency"
    if _source_kind(normalized) == "local_path":
        image = cv2.imread(normalized)
        return image, None if image is not None else "image_load_failed"

    request = Request(
        normalized,
        headers={
            "User-Agent": "her-face-attribute-extractor/1.0",
        },
    )
    try:
        with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            content = response.read(MAX_DOWNLOAD_BYTES + 1)
    except URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS, context=ssl._create_unverified_context()) as response:
                content = response.read(MAX_DOWNLOAD_BYTES + 1)
        else:
            raise
    if len(content) > MAX_DOWNLOAD_BYTES:
        return None, "image_too_large"
    image_array = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    return image, None if image is not None else "image_decode_failed"


def _select_primary_face(faces: Any) -> tuple[Any | None, int]:
    candidates = list(faces or [])
    if not candidates:
        return None, -1

    def _score(face: Any) -> tuple[int, int]:
        width = max(0, int(face.right()) - int(face.left()))
        height = max(0, int(face.bottom()) - int(face.top()))
        return width * height, min(width, height)

    indexed = list(enumerate(candidates))
    indexed.sort(key=lambda item: _score(item[1]), reverse=True)
    selected_index, selected_face = indexed[0]
    return selected_face, int(selected_index)


def _extract_points(landmarks: Any) -> list[tuple[int, int]]:
    return [(int(landmarks.part(i).x), int(landmarks.part(i).y)) for i in range(68)]


def _compute_bbox(face: Any) -> dict[str, int]:
    left = int(face.left())
    top = int(face.top())
    right = int(face.right())
    bottom = int(face.bottom())
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
    }


def _compute_face_quality_signals(*, image: Any, bbox: dict[str, int], points: list[tuple[int, int]]) -> dict[str, Any]:
    image_height, image_width = image.shape[:2]
    face_width = max(0, int(bbox.get("width") or 0))
    face_height = max(0, int(bbox.get("height") or 0))
    image_area = max(1, image_width * image_height)
    face_area_ratio = (face_width * face_height) / image_area
    left_eye_y = sum(point[1] for point in points[36:42]) / 6
    right_eye_y = sum(point[1] for point in points[42:48]) / 6
    eye_tilt = abs(left_eye_y - right_eye_y) / max(1.0, float(face_width))
    confidence = 0.95
    confidence -= max(0.0, 0.12 - min(0.12, face_area_ratio)) * 1.4
    confidence -= min(0.22, eye_tilt)
    too_small = min(face_width, face_height) < MIN_FACE_EDGE_PX
    too_far = face_area_ratio < MIN_FACE_AREA_RATIO
    return {
        "image_width": image_width,
        "image_height": image_height,
        "face_width": face_width,
        "face_height": face_height,
        "face_area_ratio": round(face_area_ratio, 4),
        "eye_tilt_ratio": round(eye_tilt, 4),
        "too_small": too_small,
        "too_far": too_far,
        "confidence": round(max(0.0, min(0.99, confidence)), 4),
    }


def _normalize_landmark_result(
    *,
    photo_source: str,
    attributes: dict[str, Any] | None = None,
    face_landmarks: list[tuple[int, int]] | None = None,
    face_count: int = 0,
    selected_face_index: int = -1,
    face_bbox: dict[str, Any] | None = None,
    quality_signals: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    success = bool(attributes) and not error_code
    payload = {
        "success": success,
        "source_kind": _source_kind(photo_source),
        "face_count": int(face_count or 0),
        "selected_face_index": int(selected_face_index if selected_face_index >= 0 else -1),
        "extractor_version": EXTRACTOR_VERSION,
        "face_attributes_model": EXTRACTOR_VERSION,
        "attributes": dict(attributes or {}),
        "face_landmarks": list(face_landmarks or []),
        "face_landmarks_json": json.dumps(face_landmarks or [], ensure_ascii=False),
        "face_bbox": dict(face_bbox or {}),
        "quality_signals": dict(quality_signals or {}),
        "attribute_confidence": float((quality_signals or {}).get("confidence") or 0.0),
        "error_code": str(error_code or "").strip() or None,
        "error_message": str(error_message or "").strip() or None,
    }
    return payload


@lru_cache(maxsize=512)
def _extract_face_attributes_cached(photo_url: str) -> dict[str, Any]:
    detector, predictor, model_error = _load_dlib_models()
    if detector is None or predictor is None:
        return _normalize_landmark_result(
            photo_source=photo_url,
            error_code=model_error or "landmark_models_unavailable",
            error_message="dlib 关键点模型不可用",
        )

    try:
        image, load_error = _load_image_from_source(photo_url)
        if image is None:
            return _normalize_landmark_result(
                photo_source=photo_url,
                error_code=load_error or "image_load_failed",
                error_message="无法加载照片",
            )

        faces = detector(image, 1)
        if not faces:
            return _normalize_landmark_result(
                photo_source=photo_url,
                error_code="no_face_detected",
                error_message="未检测到人脸",
            )

        face, selected_face_index = _select_primary_face(faces)
        if face is None:
            return _normalize_landmark_result(
                photo_source=photo_url,
                error_code="no_primary_face",
                error_message="无法选择主人脸",
            )

        landmarks = predictor(image, face)
        points = _extract_points(landmarks)
        bbox = _compute_bbox(face)
        quality_signals = _compute_face_quality_signals(image=image, bbox=bbox, points=points)
        if quality_signals.get("too_small"):
            return _normalize_landmark_result(
                photo_source=photo_url,
                face_count=len(faces),
                selected_face_index=selected_face_index,
                face_bbox=bbox,
                quality_signals=quality_signals,
                error_code="face_too_small",
                error_message="人脸区域太小，关键点结果不稳定",
            )

        attributes = {
            "eye_size_score": _compute_eye_size(points),
            "eye_shape_type": _classify_eye_shape(points),
            "eye_distance_score": _compute_eye_distance(points),
            "nose_height_score": _compute_nose_height(points),
            "nose_width_score": _compute_nose_width(points),
            "nose_shape_type": _classify_nose_shape(points),
            "lip_thickness_score": _compute_lip_thickness(points),
            "lip_width_score": _compute_lip_width(points),
            "lip_shape_type": _classify_lip_shape(points),
            "face_shape_type": _classify_face_shape(points),
            "face_roundness_score": _compute_face_roundness(points),
            "jawline_definition_score": _compute_jawline_definition(points),
            "forehead_height_score": _compute_forehead_height(points),
            "chin_prominence_score": _compute_chin_prominence(points),
            "cheekbone_prominence_score": _compute_cheekbone_prominence(points),
        }
        _logger.info(
            "脸部细节提取完成: face_shape=%s eye_size=%s confidence=%.2f",
            attributes["face_shape_type"],
            attributes["eye_size_score"],
            float(quality_signals.get("confidence") or 0.0),
        )
        return _normalize_landmark_result(
            photo_source=photo_url,
            attributes=attributes,
            face_landmarks=points,
            face_count=len(faces),
            selected_face_index=selected_face_index,
            face_bbox=bbox,
            quality_signals=quality_signals,
        )
    except Exception as exc:  # pragma: no cover - defensive
        _logger.error("脸部细节提取失败: %s", exc)
        return _normalize_landmark_result(
            photo_source=photo_url,
            error_code="extract_face_attributes_failed",
            error_message=str(exc),
        )


def extract_face_attributes(photo_url: str) -> dict[str, Any]:
    return deepcopy(_extract_face_attributes_cached(str(photo_url or "").strip()))


def _compute_eye_size(points: list[tuple[int, int]]) -> float:
    left_eye_area = _compute_polygon_area(points[36:42])
    right_eye_area = _compute_polygon_area(points[42:48])
    eye_area = (left_eye_area + right_eye_area) / 2
    face_area = _compute_polygon_area(points[0:17])
    eye_face_ratio = eye_area / face_area if face_area > 0 else 0
    min_ratio = 0.05
    max_ratio = 0.15
    if eye_face_ratio <= min_ratio:
        score = 0.0
    elif eye_face_ratio >= max_ratio:
        score = 100.0
    else:
        score = (eye_face_ratio - min_ratio) / (max_ratio - min_ratio) * 100
    return round(score, 2)


def _compute_polygon_area(points: list[tuple[int, int]]) -> float:
    n = len(points)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return abs(area) / 2.0


def _classify_eye_shape(points: list[tuple[int, int]]) -> str:
    left_eye_width = points[39][0] - points[36][0]
    left_eye_height = abs(points[37][1] - points[41][1])
    ratio = left_eye_width / left_eye_height if left_eye_height > 0 else 1.0
    if ratio > 3.5:
        return "almond"
    if ratio > 2.8:
        return "round"
    return "hooded"


def _compute_eye_distance(points: list[tuple[int, int]]) -> float:
    face_width = max(1, points[16][0] - points[0][0])
    eye_distance = max(0, points[42][0] - points[39][0])
    return round(min(100.0, max(0.0, (eye_distance / face_width) * 220.0)), 2)


def _compute_nose_height(points: list[tuple[int, int]]) -> float:
    face_height = max(1, points[8][1] - min(points[17][1], points[18][1], points[19][1], points[20][1], points[21][1]))
    nose_height = abs(points[30][1] - points[27][1])
    return round(min(100.0, max(0.0, (nose_height / face_height) * 320.0)), 2)


def _compute_nose_width(points: list[tuple[int, int]]) -> float:
    face_width = max(1, points[16][0] - points[0][0])
    nose_width = max(0, points[35][0] - points[31][0])
    return round(min(100.0, max(0.0, (nose_width / face_width) * 260.0)), 2)


def _classify_nose_shape(points: list[tuple[int, int]]) -> str:
    nose_height = abs(points[30][1] - points[27][1])
    nose_width = max(1, points[35][0] - points[31][0])
    ratio = nose_height / nose_width
    if ratio > 2.0:
        return "high"
    if ratio > 1.5:
        return "medium"
    return "flat"


def _compute_lip_thickness(points: list[tuple[int, int]]) -> float:
    upper = abs(points[62][1] - points[51][1])
    lower = abs(points[66][1] - points[57][1])
    lip_thickness = (upper + lower) / 2
    face_height = max(1, points[8][1] - min(points[17][1], points[18][1], points[19][1], points[20][1], points[21][1]))
    return round(min(100.0, max(0.0, (lip_thickness / face_height) * 520.0)), 2)


def _compute_lip_width(points: list[tuple[int, int]]) -> float:
    face_width = max(1, points[16][0] - points[0][0])
    lip_width = max(0, points[54][0] - points[48][0])
    return round(min(100.0, max(0.0, (lip_width / face_width) * 180.0)), 2)


def _classify_lip_shape(points: list[tuple[int, int]]) -> str:
    lip_width = max(1, points[54][0] - points[48][0])
    lip_thickness = (abs(points[62][1] - points[51][1]) + abs(points[66][1] - points[57][1])) / 2
    ratio = lip_width / max(1.0, lip_thickness)
    if ratio > 5.0:
        return "thin"
    if ratio > 3.0:
        return "medium"
    return "full"


def _classify_face_shape(points: list[tuple[int, int]]) -> str:
    jaw_width = points[16][0] - points[0][0]
    forehead_y = min(points[17][1], points[18][1], points[19][1], points[20][1], points[21][1])
    face_height = max(1, points[8][1] - forehead_y)
    ratio = jaw_width / face_height
    if ratio > 0.85:
        return "round"
    if ratio > 0.75:
        return "square"
    if ratio > 0.65:
        return "oval"
    return "heart"


def _compute_face_roundness(points: list[tuple[int, int]]) -> float:
    jaw_width = max(1, points[16][0] - points[0][0])
    forehead_y = min(points[17][1], points[18][1], points[19][1], points[20][1], points[21][1])
    face_height = max(1, points[8][1] - forehead_y)
    ratio = jaw_width / face_height
    return round(min(100.0, max(0.0, (ratio - 0.55) / 0.35 * 100.0)), 2)


def _compute_jawline_definition(points: list[tuple[int, int]]) -> float:
    jaw_angles = [_compute_angle(points[i - 1], points[i], points[i + 1]) for i in range(1, 16)]
    avg_angle_change = float(np.mean(jaw_angles)) if jaw_angles and np is not None else 0.0
    return round(min(100.0, max(0.0, avg_angle_change * 0.5)), 2)


def _compute_forehead_height(points: list[tuple[int, int]]) -> float:
    forehead_top_y = min(points[17][1], points[18][1], points[19][1], points[20][1], points[21][1])
    forehead_bottom_y = max(points[17][1], points[18][1], points[19][1], points[20][1], points[21][1])
    forehead_height = max(0, forehead_bottom_y - forehead_top_y)
    face_height = max(1, points[8][1] - forehead_top_y)
    return round(min(100.0, max(0.0, (forehead_height / face_height) * 500.0)), 2)


def _compute_chin_prominence(points: list[tuple[int, int]]) -> float:
    mouth_y = points[51][1]
    chin_y = points[8][1]
    face_height = max(1, chin_y - min(points[17][1], points[18][1], points[19][1], points[20][1], points[21][1]))
    return round(min(100.0, max(0.0, ((chin_y - mouth_y) / face_height) * 320.0)), 2)


def _compute_cheekbone_prominence(points: list[tuple[int, int]]) -> float:
    cheekbone_width = max(1, points[15][0] - points[1][0])
    face_width = max(1, points[16][0] - points[0][0])
    ratio = cheekbone_width / face_width
    return round(min(100.0, max(0.0, ratio * 100.0)), 2)


def _compute_angle(p1: tuple[int, int], p2: tuple[int, int], p3: tuple[int, int]) -> float:
    if np is None:
        return 0.0
    v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
    v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
    cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    angle = np.arccos(np.clip(cos_angle, -1.0, 1.0))
    return float(np.degrees(angle))


__all__ = ["extract_face_attributes", "EXTRACTOR_VERSION"]
