"""Local open-source live-video analysis using Silent-Face and faster-whisper."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import threading
import tempfile
import urllib.request
import wave
from pathlib import Path
from typing import Any

import av
import cv2
import numpy as np
import torch
import torch.nn.functional as torch_functional
from torch.nn import (
    AdaptiveAvgPool2d,
    BatchNorm1d,
    BatchNorm2d,
    Conv2d,
    Linear,
    Module,
    PReLU,
    ReLU,
    Sequential,
    Sigmoid,
)

LOCAL_OSS_PROVIDER = "local_oss"
LOCAL_OSS_PROVIDER_VERSION = "silent-face+faster-whisper-v1"

_SILENT_FACE_REPO_ROOT = "https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/master"
_SILENT_FACE_ASSETS = {
    "resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth": (
        f"{_SILENT_FACE_REPO_ROOT}/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth"
    ),
    "resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth": (
        f"{_SILENT_FACE_REPO_ROOT}/resources/anti_spoof_models/4_0_0_80x80_MiniFASNetV1SE.pth"
    ),
    "resources/detection_model/Widerface-RetinaFace.caffemodel": (
        f"{_SILENT_FACE_REPO_ROOT}/resources/detection_model/Widerface-RetinaFace.caffemodel"
    ),
    "resources/detection_model/deploy.prototxt": (
        f"{_SILENT_FACE_REPO_ROOT}/resources/detection_model/deploy.prototxt"
    ),
}
_FACE_MATCH_ASSETS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
}
_DEFAULT_SAMPLE_FRAME_COUNT = 7
_DEFAULT_REFERENCE_FACE_LIMIT = 3
_DEFAULT_DEEPFAKE_SAMPLE_FRAME_COUNT = 10
_DEEPFAKE_FACE_SIZE = 192
_DEFAULT_PHOTO_EDIT_VIDEO_FRAME_COUNT = 6
_DEFAULT_PROFILE_PHOTO_SOURCE_LIMIT = 6
_SYNC_AUDIO_WINDOW_MS = 80
_SYNC_AUDIO_HOP_MS = 40
_SYNC_VIDEO_TARGET_FPS = 12.0
_SYNC_MAX_VIDEO_FRAMES = 96
_SYNC_WINDOW_PADDING_MS = 240
_SYNC_MAX_SHIFT_MS = 240
_SYNC_SHIFT_STEP_MS = 40

_ENGINE_LOCK = threading.Lock()
_ENGINE_CACHE: tuple[tuple[str, str], "_SilentFaceEngine"] | None = None
_FACE_MATCH_LOCK = threading.Lock()
_FACE_MATCH_CACHE: tuple[str, "_OpenCvFaceMatchEngine"] | None = None
_DEEPFAKE_MASK_CACHE: dict[tuple[int, int], dict[str, np.ndarray]] = {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _cache_root() -> Path:
    raw = str(os.environ.get("HER_VERIFICATION_LOCAL_CACHE_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _repo_root() / "tmp" / "verification_models"


def _silent_face_root() -> Path:
    raw = str(os.environ.get("HER_VERIFICATION_SILENT_FACE_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _cache_root() / "silent_face_repo"


def _whisper_cache_root() -> Path:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_CACHE_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _cache_root() / "whisper"


def _torch_device_name() -> str:
    raw = str(os.environ.get("HER_VERIFICATION_LOCAL_TORCH_DEVICE") or "").strip().lower()
    if raw:
        if raw.startswith("cuda") and not torch.cuda.is_available():
            return "cpu"
        return raw
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def _whisper_device_name() -> str:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_DEVICE") or "").strip().lower()
    if raw:
        if raw == "cuda" and not torch.cuda.is_available():
            return "cpu"
        return raw
    return "cuda" if torch.cuda.is_available() else "cpu"


def _whisper_compute_type() -> str:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_COMPUTE_TYPE") or "").strip()
    if raw:
        return raw
    return "float16" if torch.cuda.is_available() else "int8"


def _whisper_model_source() -> tuple[str, bool]:
    raw_dir = str(os.environ.get("HER_VERIFICATION_WHISPER_MODEL_DIR") or "").strip()
    if raw_dir:
        return str(Path(raw_dir).expanduser().resolve()), True
    return _whisper_model_name(), False


def _whisper_model_name() -> str:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_MODEL") or "").strip()
    return raw or "tiny"


def _reference_face_limit() -> int:
    try:
        value = int(os.environ.get("HER_VERIFICATION_REFERENCE_FACE_LIMIT", _DEFAULT_REFERENCE_FACE_LIMIT))
    except (TypeError, ValueError):
        value = _DEFAULT_REFERENCE_FACE_LIMIT
    return max(1, min(value, 5))


def _sample_frame_count() -> int:
    try:
        value = int(os.environ.get("HER_VERIFICATION_LOCAL_SAMPLE_FRAMES", _DEFAULT_SAMPLE_FRAME_COUNT))
    except (TypeError, ValueError):
        value = _DEFAULT_SAMPLE_FRAME_COUNT
    return max(3, min(value, 12))


def _deepfake_sample_frame_count() -> int:
    try:
        value = int(
            os.environ.get(
                "HER_VERIFICATION_DEEPFAKE_SAMPLE_FRAMES",
                _DEFAULT_DEEPFAKE_SAMPLE_FRAME_COUNT,
            )
        )
    except (TypeError, ValueError):
        value = _DEFAULT_DEEPFAKE_SAMPLE_FRAME_COUNT
    return max(6, min(value, 18))


def _photo_edit_video_frame_count() -> int:
    try:
        value = int(
            os.environ.get(
                "HER_VERIFICATION_PHOTO_EDIT_VIDEO_FRAMES",
                _DEFAULT_PHOTO_EDIT_VIDEO_FRAME_COUNT,
            )
        )
    except (TypeError, ValueError):
        value = _DEFAULT_PHOTO_EDIT_VIDEO_FRAME_COUNT
    return max(4, min(value, 12))


def _profile_photo_source_limit() -> int:
    try:
        value = int(
            os.environ.get(
                "HER_PROFILE_PHOTO_AUTH_SOURCE_LIMIT",
                _DEFAULT_PROFILE_PHOTO_SOURCE_LIMIT,
            )
        )
    except (TypeError, ValueError):
        value = _DEFAULT_PROFILE_PHOTO_SOURCE_LIMIT
    return max(1, min(value, 10))


def _download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return
    partial_path = destination.with_suffix(destination.suffix + ".part")
    partial_exists = partial_path.exists() and partial_path.stat().st_size > 0
    try:
        if partial_exists:
            raise RuntimeError("resume_partial_download_via_curl")
        with urllib.request.urlopen(url, timeout=300) as response, partial_path.open("wb") as handle:
            while True:
                chunk = response.read(128 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except Exception as exc:  # noqa: BLE001
        try:
            curl_command = [
                "curl",
                "-L",
                "--fail",
                "--retry",
                "3",
                "--connect-timeout",
                "30",
                "--max-time",
                "600",
            ]
            if partial_exists:
                curl_command.extend(["-C", "-"])
            curl_command.extend(["-o", str(partial_path), url])
            subprocess.run(
                curl_command,
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:  # noqa: BLE001
            partial_path.unlink(missing_ok=True)
            raise exc
    partial_path.replace(destination)


def _ensure_silent_face_assets() -> Path:
    root = _silent_face_root()
    for relative_path, url in _SILENT_FACE_ASSETS.items():
        _download_file(url, root / relative_path)
    return root


def _face_match_root() -> Path:
    raw = str(os.environ.get("HER_VERIFICATION_FACE_MATCH_MODEL_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _cache_root() / "opencv_face_match"


def _ensure_face_match_assets() -> Path:
    root = _face_match_root()
    if str(os.environ.get("HER_VERIFICATION_FACE_MATCH_MODEL_DIR") or "").strip():
        return root
    root.mkdir(parents=True, exist_ok=True)
    for filename, url in _FACE_MATCH_ASSETS.items():
        _download_file(url, root / filename)
    return root


def _bounded_score(value: float | int) -> int:
    return max(0, min(int(round(float(value))), 100))


def _sample_indices(frame_count: int, sample_count: int) -> list[int]:
    if frame_count <= 0:
        return []
    if frame_count <= sample_count:
        return list(range(frame_count))
    start = max(0, int(round(frame_count * 0.15)))
    end = min(frame_count - 1, max(start, int(round(frame_count * 0.85))))
    return sorted(
        {
            int(round(start + ((end - start) * index / max(1, sample_count - 1))))
            for index in range(sample_count)
        }
    )


def _inspect_media_file(video_path: Path) -> dict[str, Any]:
    has_audio = False
    duration_ms: int | None = None
    try:
        with av.open(str(video_path)) as container:
            has_audio = any(stream.type == "audio" for stream in container.streams)
            if container.duration is not None:
                duration_ms = max(0, int(round(container.duration / 1000)))
    except Exception:  # noqa: BLE001
        has_audio = False
        duration_ms = None
    return {
        "has_audio_track": has_audio,
        "duration_ms": duration_ms,
    }


def _sample_indices_in_range(
    frame_count: int,
    sample_count: int,
    *,
    start_ratio: float = 0.15,
    end_ratio: float = 0.85,
) -> list[int]:
    if frame_count <= 0:
        return []
    if frame_count <= sample_count:
        return list(range(frame_count))
    clamped_start_ratio = max(0.0, min(float(start_ratio), 0.95))
    clamped_end_ratio = max(clamped_start_ratio, min(float(end_ratio), 1.0))
    start = max(0, int(round(frame_count * clamped_start_ratio)))
    end = min(frame_count - 1, max(start, int(round(frame_count * clamped_end_ratio))))
    return sorted(
        {
            int(round(start + ((end - start) * index / max(1, sample_count - 1))))
            for index in range(sample_count)
        }
    )


def _sample_video_frames_with_config(
    video_path: Path,
    *,
    sample_count: int,
    start_ratio: float = 0.15,
    end_ratio: float = 0.85,
) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError("unable to open uploaded video")
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frames: list[dict[str, Any]] = []
        if frame_count > 0:
            for frame_index in _sample_indices_in_range(
                frame_count,
                max(1, int(sample_count)),
                start_ratio=start_ratio,
                end_ratio=end_ratio,
            ):
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok or frame is None:
                    continue
                timestamp_ms = int(round((frame_index / fps) * 1000)) if fps > 0 else None
                frames.append(
                    {
                        "frame_index": frame_index,
                        "timestamp_ms": timestamp_ms,
                        "frame": frame,
                    }
                )
        else:
            current_index = 0
            stride = 5
            while len(frames) < _sample_frame_count():
                ok, frame = capture.read()
                if not ok or frame is None:
                    break
                if current_index % stride == 0:
                    frames.append(
                        {
                            "frame_index": current_index,
                            "timestamp_ms": int(round((current_index / fps) * 1000)) if fps > 0 else None,
                            "frame": frame,
                        }
                    )
                current_index += 1
            frame_count = current_index
        if not frames:
            raise ValueError("unable to decode frames from uploaded video")
        return {
            "fps": fps if fps > 0 else None,
            "frame_count": frame_count if frame_count > 0 else None,
            "frames": frames,
        }
    finally:
        capture.release()


def _sample_video_frames(video_path: Path) -> dict[str, Any]:
    return _sample_video_frames_with_config(video_path, sample_count=_sample_frame_count())


def _deepfake_region_masks(height: int, width: int) -> dict[str, np.ndarray]:
    cache_key = (int(height), int(width))
    cached = _DEEPFAKE_MASK_CACHE.get(cache_key)
    if cached is not None:
        return cached

    outer = np.zeros((height, width), dtype=np.uint8)
    inner = np.zeros((height, width), dtype=np.uint8)
    upper = np.zeros((height, width), dtype=np.uint8)
    lower = np.zeros((height, width), dtype=np.uint8)

    cv2.ellipse(
        outer,
        (int(round(width * 0.5)), int(round(height * 0.53))),
        (int(round(width * 0.42)), int(round(height * 0.47))),
        0,
        0,
        360,
        255,
        -1,
    )
    cv2.ellipse(
        inner,
        (int(round(width * 0.5)), int(round(height * 0.55))),
        (int(round(width * 0.30)), int(round(height * 0.35))),
        0,
        0,
        360,
        255,
        -1,
    )
    cv2.rectangle(
        upper,
        (int(round(width * 0.23)), int(round(height * 0.18))),
        (int(round(width * 0.77)), int(round(height * 0.54))),
        255,
        -1,
    )
    cv2.rectangle(
        lower,
        (int(round(width * 0.26)), int(round(height * 0.57))),
        (int(round(width * 0.74)), int(round(height * 0.83))),
        255,
        -1,
    )
    eye_band = np.zeros((height, width), dtype=np.uint8)
    mouth_band = np.zeros((height, width), dtype=np.uint8)
    cv2.rectangle(
        eye_band,
        (int(round(width * 0.22)), int(round(height * 0.26))),
        (int(round(width * 0.78)), int(round(height * 0.48))),
        255,
        -1,
    )
    cv2.rectangle(
        mouth_band,
        (int(round(width * 0.28)), int(round(height * 0.60))),
        (int(round(width * 0.72)), int(round(height * 0.82))),
        255,
        -1,
    )

    outer_mask = outer.astype(bool)
    inner_mask = inner.astype(bool)
    upper_mask = upper.astype(bool) & inner_mask
    lower_mask = lower.astype(bool) & outer_mask
    border_mask = outer_mask & ~inner_mask
    eye_band_mask = eye_band.astype(bool) & inner_mask
    mouth_band_mask = mouth_band.astype(bool) & inner_mask
    feature_band_mask = eye_band_mask | mouth_band_mask
    skin_core_mask = inner_mask & ~feature_band_mask
    kernel = np.ones((5, 5), dtype=np.uint8)
    seam_mask = (
        cv2.dilate(inner, kernel, iterations=1).astype(bool)
        & outer_mask
        & ~cv2.erode(inner, kernel, iterations=1).astype(bool)
    )
    cached = {
        "outer": outer_mask,
        "inner": inner_mask,
        "upper": upper_mask,
        "lower": lower_mask,
        "border": border_mask,
        "seam": seam_mask,
        "eye_band": eye_band_mask,
        "mouth_band": mouth_band_mask,
        "feature_band": feature_band_mask,
        "skin_core": skin_core_mask,
    }
    _DEEPFAKE_MASK_CACHE[cache_key] = cached
    return cached


def _masked_mean(array: np.ndarray, mask: np.ndarray) -> float:
    if array.shape[:2] != mask.shape:
        raise ValueError("mask shape does not match array")
    values = array[mask]
    if values.size <= 0:
        return 0.0
    return float(np.mean(values))


def _masked_std(array: np.ndarray, mask: np.ndarray) -> float:
    if array.shape[:2] != mask.shape:
        raise ValueError("mask shape does not match array")
    values = array[mask]
    if values.size <= 0:
        return 0.0
    return float(np.std(values))


def _extract_deepfake_face_crop(frame: np.ndarray, bbox: list[int]) -> np.ndarray | None:
    left, top, width, height = [int(value) for value in bbox]
    frame_height, frame_width = frame.shape[:2]
    expand_x = int(round(width * 0.24))
    expand_y = int(round(height * 0.30))
    x0 = max(0, left - expand_x)
    y0 = max(0, top - expand_y)
    x1 = min(frame_width, left + width + expand_x)
    y1 = min(frame_height, top + height + expand_y)
    if x1 - x0 < 32 or y1 - y0 < 32:
        return None
    crop = frame[y0:y1, x0:x1]
    if crop.size <= 0:
        return None
    return cv2.resize(
        crop,
        (_DEEPFAKE_FACE_SIZE, _DEEPFAKE_FACE_SIZE),
        interpolation=cv2.INTER_LINEAR,
    )


def _deepfake_crop_metrics(crop: np.ndarray) -> dict[str, Any]:
    masks = _deepfake_region_masks(crop.shape[0], crop.shape[1])
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray_equalized = cv2.equalizeHist(gray).astype(np.float32) / 255.0
    blurred = cv2.GaussianBlur(gray_equalized, (3, 3), 0)
    laplacian = np.abs(cv2.Laplacian(blurred, cv2.CV_32F))
    sobel_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cv2.magnitude(sobel_x, sobel_y)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    detail_inner = _masked_mean(laplacian, masks["inner"])
    detail_border = _masked_mean(laplacian, masks["border"])
    detail_upper = _masked_mean(laplacian, masks["upper"])
    detail_lower = _masked_mean(laplacian, masks["lower"])
    mean_gradient_outer = _masked_mean(gradient, masks["outer"])
    seam_strength = _masked_mean(gradient, masks["seam"]) / max(mean_gradient_outer, 1e-6)
    inner_ab = np.asarray(
        [
            _masked_mean(lab[:, :, 1], masks["inner"]),
            _masked_mean(lab[:, :, 2], masks["inner"]),
        ],
        dtype=np.float32,
    )
    border_ab = np.asarray(
        [
            _masked_mean(lab[:, :, 1], masks["border"]),
            _masked_mean(lab[:, :, 2], masks["border"]),
        ],
        dtype=np.float32,
    )
    chroma_gap = float(np.linalg.norm(inner_ab - border_ab))
    return {
        "gray": gray_equalized,
        "detail_inner": detail_inner,
        "detail_border": detail_border,
        "detail_upper": detail_upper,
        "detail_lower": detail_lower,
        "detail_ratio": detail_inner / max(detail_border, 1e-6),
        "seam_strength": seam_strength,
        "chroma_gap": chroma_gap,
    }


def _deepfake_score_component(value: float, *, offset: float, scale: float) -> int:
    if scale <= 0:
        return 0
    normalized = max(0.0, (float(value) - float(offset)) / float(scale))
    return _bounded_score(normalized * 100.0)


def _deepfake_unavailable_result(
    reason: str,
    *,
    error_message: str | None = None,
    sampled_frame_count: int = 0,
    face_frame_count: int = 0,
) -> dict[str, Any]:
    out = {
        "analysis_status": "unavailable",
        "deepfake_risk_score": 0,
        "deepfake_temporal_score": 0,
        "deepfake_artifact_score": 0,
        "deepfake_sampled_frame_count": int(sampled_frame_count),
        "deepfake_face_frame_count": int(face_frame_count),
        "risk_flags": [],
        "analysis_reason": reason,
    }
    if error_message:
        out["error_message"] = error_message
    return out


def _analyze_deepfake_face_crops(face_crops: list[np.ndarray]) -> dict[str, Any]:
    if len(face_crops) < 4:
        return _deepfake_unavailable_result(
            "insufficient_face_frames",
            sampled_frame_count=len(face_crops),
            face_frame_count=len(face_crops),
        )

    metrics = [_deepfake_crop_metrics(crop) for crop in face_crops]
    masks = _deepfake_region_masks(face_crops[0].shape[0], face_crops[0].shape[1])
    temporal_excess_values: list[float] = []
    temporal_ratio_values: list[float] = []
    seam_delta_values: list[float] = []
    chroma_delta_values: list[float] = []
    for previous, current in zip(metrics, metrics[1:]):
        diff = np.abs(current["gray"] - previous["gray"])
        upper_delta = _masked_mean(diff, masks["upper"])
        lower_delta = _masked_mean(diff, masks["lower"])
        border_delta = _masked_mean(diff, masks["border"])
        core_delta = _masked_mean(diff, masks["inner"])
        temporal_excess = max(
            0.0,
            ((upper_delta * 0.72) + (core_delta * 0.20) + (lower_delta * 0.08))
            - (border_delta * 1.08),
        )
        temporal_excess_values.append(temporal_excess)
        temporal_ratio_values.append(
            ((upper_delta * 0.70) + (core_delta * 0.30)) / max(border_delta, 1e-6)
        )
        seam_delta_values.append(
            abs(float(current["seam_strength"]) - float(previous["seam_strength"]))
        )
        chroma_delta_values.append(
            abs(float(current["chroma_gap"]) - float(previous["chroma_gap"]))
        )

    seam_strength_values = [float(item["seam_strength"]) for item in metrics]
    detail_ratio_values = [float(item["detail_ratio"]) for item in metrics]
    mean_temporal_excess = float(sum(temporal_excess_values) / len(temporal_excess_values))
    mean_temporal_ratio = float(sum(temporal_ratio_values) / len(temporal_ratio_values))
    mean_seam_strength = float(sum(seam_strength_values) / len(seam_strength_values))
    seam_variation = float(np.std(seam_strength_values))
    chroma_gap_variation = float(np.std([float(item["chroma_gap"]) for item in metrics]))
    detail_ratio_variation = float(np.std(detail_ratio_values))
    seam_delta_mean = float(sum(seam_delta_values) / len(seam_delta_values)) if seam_delta_values else 0.0
    chroma_delta_mean = float(sum(chroma_delta_values) / len(chroma_delta_values)) if chroma_delta_values else 0.0

    temporal_score = _bounded_score(
        (_deepfake_score_component(mean_temporal_excess, offset=0.004, scale=0.020) * 0.18)
        + (_deepfake_score_component(abs(mean_temporal_ratio - 1.0), offset=0.10, scale=0.40) * 0.14)
        + (_deepfake_score_component(seam_delta_mean, offset=0.012, scale=0.080) * 0.30)
        + (_deepfake_score_component(chroma_delta_mean, offset=0.60, scale=3.60) * 0.38)
    )
    artifact_score = _bounded_score(
        (_deepfake_score_component(mean_seam_strength, offset=0.88, scale=0.22) * 0.25)
        + (_deepfake_score_component(seam_variation, offset=0.015, scale=0.060) * 0.15)
        + (_deepfake_score_component(chroma_gap_variation, offset=0.40, scale=2.20) * 0.30)
        + (_deepfake_score_component(detail_ratio_variation, offset=0.020, scale=0.100) * 0.30)
    )
    deepfake_risk_score = _bounded_score(max(artifact_score, (temporal_score * 0.25) + (artifact_score * 0.75)))
    risk_flags: list[str] = []
    if deepfake_risk_score >= 85:
        risk_flags.append("deepfake_risk")
    elif deepfake_risk_score >= 60:
        risk_flags.append("deepfake_uncertain")

    return {
        "analysis_status": "ok",
        "deepfake_risk_score": deepfake_risk_score,
        "deepfake_temporal_score": temporal_score,
        "deepfake_artifact_score": artifact_score,
        "deepfake_sampled_frame_count": len(face_crops),
        "deepfake_face_frame_count": len(face_crops),
        "mean_temporal_excess": round(mean_temporal_excess, 4),
        "mean_temporal_ratio": round(mean_temporal_ratio, 4),
        "mean_seam_strength": round(mean_seam_strength, 4),
        "seam_variation": round(seam_variation, 4),
        "chroma_gap_variation": round(chroma_gap_variation, 4),
        "detail_ratio_variation": round(detail_ratio_variation, 4),
        "seam_delta_mean": round(seam_delta_mean, 4),
        "chroma_delta_mean": round(chroma_delta_mean, 4),
        "risk_flags": risk_flags,
    }


def _analyze_deepfake_video(video_path: Path) -> dict[str, Any]:
    detector = _silent_face_engine().detector
    sampled_video = _sample_video_frames_with_config(
        video_path,
        sample_count=_deepfake_sample_frame_count(),
        start_ratio=0.18,
        end_ratio=0.88,
    )
    sampled_frames = list(sampled_video.get("frames") or [])
    face_crops: list[np.ndarray] = []
    for frame_item in sampled_frames:
        detection = detector.detect(frame_item["frame"])
        bbox = detection.get("bbox")
        face_count = int(detection.get("face_count") or 0)
        if not bbox or face_count != 1:
            continue
        crop = _extract_deepfake_face_crop(frame_item["frame"], bbox)
        if crop is None:
            continue
        face_crops.append(crop)
    analyzed = _analyze_deepfake_face_crops(face_crops)
    analyzed["deepfake_sampled_frame_count"] = int(len(sampled_frames))
    analyzed["deepfake_face_frame_count"] = int(len(face_crops))
    return analyzed


def _safe_analyze_deepfake_video(video_path: Path) -> dict[str, Any]:
    try:
        return _analyze_deepfake_video(video_path)
    except Exception as exc:  # noqa: BLE001
        return _deepfake_unavailable_result("analysis_exception", error_message=str(exc) or type(exc).__name__)


def _photo_edit_unavailable_result(
    reason: str,
    *,
    reference_face_source_count: int,
    live_face_frame_count: int = 0,
    reference_face_count: int = 0,
    error_message: str | None = None,
) -> dict[str, Any]:
    out = {
        "analysis_status": "unavailable",
        "photo_edit_risk_score": 0,
        "skin_smoothing_risk_score": 0,
        "beauty_filter_risk_score": 0,
        "face_shape_delta_score": 0,
        "photo_edit_reference_face_count": int(reference_face_count),
        "photo_edit_live_face_frame_count": int(live_face_frame_count),
        "photo_edit_reference_source_count": int(reference_face_source_count),
        "photo_edit_edited_reference_count": 0,
        "risk_flags": [],
        "analysis_reason": reason,
    }
    if error_message:
        out["error_message"] = error_message
    return out


def _photo_edit_crop_metrics(crop: np.ndarray, *, face_aspect_ratio: float) -> dict[str, Any]:
    masks = _deepfake_region_masks(crop.shape[0], crop.shape[1])
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    gray_blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    laplacian = np.abs(cv2.Laplacian(gray_blurred, cv2.CV_32F))
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).astype(np.float32)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    skin_detail = _masked_mean(laplacian, masks["skin_core"])
    feature_detail = _masked_mean(laplacian, masks["feature_band"])
    skin_detail_std = _masked_std(laplacian, masks["skin_core"])
    skin_lightness_std = _masked_std(lab[:, :, 0], masks["skin_core"])
    skin_chroma_std = float(
        np.linalg.norm(
            np.asarray(
                [
                    _masked_std(lab[:, :, 1], masks["skin_core"]),
                    _masked_std(lab[:, :, 2], masks["skin_core"]),
                ],
                dtype=np.float32,
            )
        )
    )
    skin_saturation_mean = _masked_mean(hsv[:, :, 1] / 255.0, masks["skin_core"])
    skin_saturation_std = _masked_std(hsv[:, :, 1] / 255.0, masks["skin_core"])
    skin_brightness_mean = _masked_mean(hsv[:, :, 2] / 255.0, masks["skin_core"])
    return {
        "skin_detail": skin_detail,
        "feature_detail": feature_detail,
        "feature_skin_gap": feature_detail / max(skin_detail, 1e-6),
        "skin_detail_std": skin_detail_std,
        "skin_lightness_std": skin_lightness_std,
        "skin_chroma_std": skin_chroma_std,
        "skin_saturation_mean": skin_saturation_mean,
        "skin_saturation_std": skin_saturation_std,
        "skin_brightness_mean": skin_brightness_mean,
        "face_aspect_ratio": float(face_aspect_ratio),
    }


def _mean_metric(metrics_list: list[dict[str, Any]], key: str) -> float:
    values = [float(item.get(key) or 0.0) for item in metrics_list]
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _photo_edit_score_component(value: float, *, offset: float, scale: float) -> int:
    if scale <= 0:
        return 0
    normalized = max(0.0, (float(value) - float(offset)) / float(scale))
    return _bounded_score(normalized * 100.0)


def _photo_edit_reference_score(
    reference_metrics: dict[str, Any],
    *,
    live_metrics: dict[str, Any],
) -> dict[str, Any]:
    detail_ratio = float(live_metrics["skin_detail"]) / max(float(reference_metrics["skin_detail"]), 1e-6)
    detail_std_ratio = float(live_metrics["skin_detail_std"]) / max(float(reference_metrics["skin_detail_std"]), 1e-6)
    feature_gap_delta = float(reference_metrics["feature_skin_gap"]) - float(live_metrics["feature_skin_gap"])
    lightness_uniformity_gap = max(0.0, float(live_metrics["skin_lightness_std"]) - float(reference_metrics["skin_lightness_std"]))
    chroma_uniformity_gap = max(0.0, float(live_metrics["skin_chroma_std"]) - float(reference_metrics["skin_chroma_std"]))
    saturation_gap = max(0.0, float(reference_metrics["skin_saturation_mean"]) - float(live_metrics["skin_saturation_mean"]))
    brightness_gap = max(0.0, float(reference_metrics["skin_brightness_mean"]) - float(live_metrics["skin_brightness_mean"]))
    aspect_ratio_gap = abs(float(reference_metrics["face_aspect_ratio"]) - float(live_metrics["face_aspect_ratio"]))

    smoothing_score = _bounded_score(
        (_photo_edit_score_component(detail_ratio, offset=1.05, scale=0.65) * 0.55)
        + (_photo_edit_score_component(detail_std_ratio, offset=1.04, scale=0.75) * 0.20)
        + (_photo_edit_score_component(feature_gap_delta, offset=0.06, scale=0.50) * 0.25)
    )
    beauty_filter_score = _bounded_score(
        (_photo_edit_score_component(lightness_uniformity_gap, offset=1.5, scale=7.0) * 0.28)
        + (_photo_edit_score_component(chroma_uniformity_gap, offset=1.2, scale=8.0) * 0.22)
        + (_photo_edit_score_component(saturation_gap, offset=0.02, scale=0.14) * 0.25)
        + (_photo_edit_score_component(brightness_gap, offset=0.02, scale=0.16) * 0.25)
    )
    face_shape_delta_score = _photo_edit_score_component(aspect_ratio_gap, offset=0.05, scale=0.22)
    combined_score = _bounded_score(
        max(
            ((smoothing_score * 0.48) + (beauty_filter_score * 0.37) + (face_shape_delta_score * 0.15)) * 1.8,
            smoothing_score * 1.55,
            beauty_filter_score * 1.55,
            face_shape_delta_score * 1.35,
        )
    )
    return {
        "photo_edit_risk_score": combined_score,
        "skin_smoothing_risk_score": smoothing_score,
        "beauty_filter_risk_score": beauty_filter_score,
        "face_shape_delta_score": face_shape_delta_score,
        "detail_ratio": round(detail_ratio, 4),
        "detail_std_ratio": round(detail_std_ratio, 4),
        "feature_gap_delta": round(feature_gap_delta, 4),
        "lightness_uniformity_gap": round(lightness_uniformity_gap, 4),
        "chroma_uniformity_gap": round(chroma_uniformity_gap, 4),
        "saturation_gap": round(saturation_gap, 4),
        "brightness_gap": round(brightness_gap, 4),
        "aspect_ratio_gap": round(aspect_ratio_gap, 4),
    }


def _collect_reference_photo_edit_metrics(
    reference_image_sources: list[str],
) -> tuple[list[dict[str, Any]], list[str], int]:
    detector = _silent_face_engine().detector
    metrics_list: list[dict[str, Any]] = []
    risk_flags: list[str] = []
    loaded_source_count = 0
    for source in reference_image_sources[: max(_reference_face_limit() * 2, _reference_face_limit())]:
        image = _load_image_from_source(source)
        if image is None:
            continue
        loaded_source_count += 1
        detection = detector.detect(image)
        bbox = detection.get("bbox")
        face_count = int(detection.get("face_count") or 0)
        if not bbox or face_count != 1:
            if face_count > 1 and "multiple_reference_faces" not in risk_flags:
                risk_flags.append("multiple_reference_faces")
            continue
        crop = _extract_deepfake_face_crop(image, bbox)
        if crop is None:
            continue
        metrics_list.append(
            _photo_edit_crop_metrics(
                crop,
                face_aspect_ratio=float(bbox[2]) / max(float(bbox[3]), 1.0),
            )
        )
        if len(metrics_list) >= _reference_face_limit():
            break
    return metrics_list, risk_flags, loaded_source_count


def _collect_live_photo_edit_metrics(video_path: Path) -> list[dict[str, Any]]:
    detector = _silent_face_engine().detector
    sampled_video = _sample_video_frames_with_config(
        video_path,
        sample_count=_photo_edit_video_frame_count(),
        start_ratio=0.22,
        end_ratio=0.82,
    )
    metrics_list: list[dict[str, Any]] = []
    for frame_item in list(sampled_video.get("frames") or []):
        detection = detector.detect(frame_item["frame"])
        bbox = detection.get("bbox")
        face_count = int(detection.get("face_count") or 0)
        if not bbox or face_count != 1:
            continue
        crop = _extract_deepfake_face_crop(frame_item["frame"], bbox)
        if crop is None:
            continue
        metrics_list.append(
            _photo_edit_crop_metrics(
                crop,
                face_aspect_ratio=float(bbox[2]) / max(float(bbox[3]), 1.0),
            )
        )
    return metrics_list


def _analyze_photo_edit_face_sets(
    reference_metrics_list: list[dict[str, Any]],
    live_metrics_list: list[dict[str, Any]],
    *,
    reference_face_source_count: int,
    reference_risk_flags: list[str] | None = None,
) -> dict[str, Any]:
    normalized_reference_risk_flags = list(reference_risk_flags or [])
    if not reference_metrics_list:
        return _photo_edit_unavailable_result(
            "reference_photo_unavailable",
            reference_face_source_count=reference_face_source_count,
            live_face_frame_count=len(live_metrics_list),
            reference_face_count=0,
        ) | {"risk_flags": list(dict.fromkeys(normalized_reference_risk_flags))}
    if len(live_metrics_list) < 2:
        return _photo_edit_unavailable_result(
            "live_face_unavailable",
            reference_face_source_count=reference_face_source_count,
            live_face_frame_count=len(live_metrics_list),
            reference_face_count=len(reference_metrics_list),
        ) | {"risk_flags": list(dict.fromkeys(normalized_reference_risk_flags))}

    live_metrics = {
        key: _mean_metric(live_metrics_list, key)
        for key in (
            "skin_detail",
            "feature_detail",
            "feature_skin_gap",
            "skin_detail_std",
            "skin_lightness_std",
            "skin_chroma_std",
            "skin_saturation_mean",
            "skin_saturation_std",
            "skin_brightness_mean",
            "face_aspect_ratio",
        )
    }
    per_reference_scores = [
        _photo_edit_reference_score(reference_metrics, live_metrics=live_metrics)
        for reference_metrics in reference_metrics_list
    ]
    ranked_scores = sorted(
        per_reference_scores,
        key=lambda item: int(item.get("photo_edit_risk_score") or 0),
        reverse=True,
    )
    top_scores = ranked_scores[: min(2, len(ranked_scores))]
    combined_score = float(sum(int(item["photo_edit_risk_score"]) for item in top_scores)) / max(len(top_scores), 1)
    edited_reference_count = sum(1 for item in per_reference_scores if int(item.get("photo_edit_risk_score") or 0) >= 60)
    photo_edit_risk_score = _bounded_score(combined_score + (5 if edited_reference_count >= 2 else 0))
    skin_smoothing_risk_score = _bounded_score(
        sum(int(item["skin_smoothing_risk_score"]) for item in top_scores) / max(len(top_scores), 1)
    )
    beauty_filter_risk_score = _bounded_score(
        sum(int(item["beauty_filter_risk_score"]) for item in top_scores) / max(len(top_scores), 1)
    )
    face_shape_delta_score = _bounded_score(
        sum(int(item["face_shape_delta_score"]) for item in top_scores) / max(len(top_scores), 1)
    )
    risk_flags = list(normalized_reference_risk_flags)
    if photo_edit_risk_score >= 85:
        risk_flags.append("photo_heavily_edited")
    elif photo_edit_risk_score >= 60:
        risk_flags.append("photo_edit_uncertain")

    return {
        "analysis_status": "ok",
        "photo_edit_risk_score": photo_edit_risk_score,
        "skin_smoothing_risk_score": skin_smoothing_risk_score,
        "beauty_filter_risk_score": beauty_filter_risk_score,
        "face_shape_delta_score": face_shape_delta_score,
        "photo_edit_reference_face_count": len(reference_metrics_list),
        "photo_edit_live_face_frame_count": len(live_metrics_list),
        "photo_edit_reference_source_count": int(reference_face_source_count),
        "photo_edit_edited_reference_count": edited_reference_count,
        "risk_flags": list(dict.fromkeys(risk_flags)),
        "top_reference_detail_ratio": ranked_scores[0].get("detail_ratio") if ranked_scores else None,
        "top_reference_saturation_gap": ranked_scores[0].get("saturation_gap") if ranked_scores else None,
        "top_reference_brightness_gap": ranked_scores[0].get("brightness_gap") if ranked_scores else None,
    }


def _analyze_photo_edit_risk(
    video_path: Path,
    *,
    reference_image_sources: list[str] | None,
) -> dict[str, Any]:
    normalized_sources = [str(item or "").strip() for item in list(reference_image_sources or []) if str(item or "").strip()]
    if not normalized_sources:
        return _photo_edit_unavailable_result(
            "reference_photo_unavailable",
            reference_face_source_count=0,
        )

    reference_metrics_list, reference_risk_flags, loaded_source_count = _collect_reference_photo_edit_metrics(normalized_sources)
    live_metrics_list = _collect_live_photo_edit_metrics(video_path)
    return _analyze_photo_edit_face_sets(
        reference_metrics_list,
        live_metrics_list,
        reference_face_source_count=max(len(reference_metrics_list), loaded_source_count),
        reference_risk_flags=reference_risk_flags,
    )


def _safe_analyze_photo_edit_risk(
    video_path: Path,
    *,
    reference_image_sources: list[str] | None,
) -> dict[str, Any]:
    try:
        return _analyze_photo_edit_risk(
            video_path,
            reference_image_sources=reference_image_sources,
        )
    except Exception as exc:  # noqa: BLE001
        return _photo_edit_unavailable_result(
            "analysis_exception",
            reference_face_source_count=len(list(reference_image_sources or [])),
            error_message=str(exc) or type(exc).__name__,
        )


def _difference_hash(image: np.ndarray, *, hash_size: int = 8) -> int | None:
    if image is None or image.size <= 0:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    value = 0
    for bit in diff.reshape(-1):
        value = (value << 1) | int(bool(bit))
    return int(value)


def _hash_hamming_distance(hash_a: int | None, hash_b: int | None) -> int | None:
    if hash_a is None or hash_b is None:
        return None
    diff = int(hash_a) ^ int(hash_b)
    return int(bin(diff).count("1"))


def _median_metric(metrics_list: list[dict[str, Any]], key: str) -> float:
    values = [float(item.get(key) or 0.0) for item in metrics_list]
    if not values:
        return 0.0
    return float(np.median(np.asarray(values, dtype=np.float32)))


def _profile_photo_same_person_unavailable_result(reason: str, *, photo_face_count: int) -> dict[str, Any]:
    return {
        "analysis_status": "unavailable",
        "same_person_score": 0,
        "pair_count": 0,
        "matched_pair_count": 0,
        "average_similarity": None,
        "min_similarity": None,
        "photo_face_count": int(photo_face_count),
        "risk_flags": [reason],
        "analysis_reason": reason,
    }


def _analyze_same_person_photo_entries(photo_entries: list[dict[str, Any]]) -> dict[str, Any]:
    valid_entries = [
        item
        for item in photo_entries
        if int(item.get("face_count") or 0) == 1 and item.get("embedding") is not None
    ]
    if len(valid_entries) < 2:
        return _profile_photo_same_person_unavailable_result(
            "insufficient_profile_face_photos",
            photo_face_count=len(valid_entries),
        )

    engine = _face_match_engine()
    pair_scores: list[float] = []
    for left_index, left in enumerate(valid_entries):
        for right in valid_entries[left_index + 1 :]:
            pair_scores.append(
                float(
                    engine.match(
                        np.asarray(left["embedding"], dtype=np.float32),
                        np.asarray(right["embedding"], dtype=np.float32),
                    )
                )
            )
    if not pair_scores:
        return _profile_photo_same_person_unavailable_result(
            "insufficient_profile_face_pairs",
            photo_face_count=len(valid_entries),
        )

    average_similarity = float(sum(pair_scores) / len(pair_scores))
    min_similarity = float(min(pair_scores))
    matched_pair_count = sum(1 for value in pair_scores if value >= 0.363)
    same_person_score = _face_similarity_to_score(
        average_similarity,
        matched_frame_count=matched_pair_count,
        analyzed_frame_count=len(pair_scores),
    )
    risk_flags: list[str] = []
    if min_similarity < 0.28 or same_person_score < 45:
        same_person_score = min(same_person_score, 40)
        risk_flags.append("mixed_identity_photos")
    elif matched_pair_count < len(pair_scores):
        risk_flags.append("same_person_uncertain")
    return {
        "analysis_status": "ok",
        "same_person_score": same_person_score,
        "pair_count": len(pair_scores),
        "matched_pair_count": matched_pair_count,
        "average_similarity": round(average_similarity, 4),
        "min_similarity": round(min_similarity, 4),
        "photo_face_count": len(valid_entries),
        "risk_flags": risk_flags,
    }


def _profile_photo_edit_unavailable_result(reason: str, *, photo_face_count: int) -> dict[str, Any]:
    return {
        "analysis_status": "unavailable",
        "photo_edit_risk_score": 0,
        "skin_smoothing_risk_score": 0,
        "beauty_filter_risk_score": 0,
        "face_shape_delta_score": 0,
        "edited_photo_count": 0,
        "photo_face_count": int(photo_face_count),
        "risk_flags": [],
        "analysis_reason": reason,
    }


def _analyze_profile_photo_edit_metrics(photo_entries: list[dict[str, Any]]) -> dict[str, Any]:
    metrics_list = [
        item["photo_edit_metrics"]
        for item in photo_entries
        if int(item.get("face_count") or 0) == 1 and item.get("photo_edit_metrics") is not None
    ]
    if len(metrics_list) < 2:
        return _profile_photo_edit_unavailable_result(
            "insufficient_profile_face_photos",
            photo_face_count=len(metrics_list),
        )

    cohort_metrics = {
        key: _median_metric(metrics_list, key)
        for key in (
            "skin_detail",
            "feature_detail",
            "feature_skin_gap",
            "skin_detail_std",
            "skin_lightness_std",
            "skin_chroma_std",
            "skin_saturation_mean",
            "skin_saturation_std",
            "skin_brightness_mean",
            "face_aspect_ratio",
        )
    }
    per_photo_scores = [
        _photo_edit_reference_score(photo_metrics, live_metrics=cohort_metrics)
        for photo_metrics in metrics_list
    ]
    ranked_scores = sorted(
        per_photo_scores,
        key=lambda item: int(item.get("photo_edit_risk_score") or 0),
        reverse=True,
    )
    top_scores = ranked_scores[: min(2, len(ranked_scores))]
    combined_score = float(sum(int(item["photo_edit_risk_score"]) for item in top_scores)) / max(len(top_scores), 1)
    edited_photo_count = sum(1 for item in per_photo_scores if int(item.get("photo_edit_risk_score") or 0) >= 60)
    photo_edit_risk_score = _bounded_score(combined_score + (5 if edited_photo_count >= 2 else 0))
    skin_smoothing_risk_score = _bounded_score(
        sum(int(item["skin_smoothing_risk_score"]) for item in top_scores) / max(len(top_scores), 1)
    )
    beauty_filter_risk_score = _bounded_score(
        sum(int(item["beauty_filter_risk_score"]) for item in top_scores) / max(len(top_scores), 1)
    )
    face_shape_delta_score = _bounded_score(
        sum(int(item["face_shape_delta_score"]) for item in top_scores) / max(len(top_scores), 1)
    )
    risk_flags: list[str] = []
    if photo_edit_risk_score >= 85:
        risk_flags.append("photo_heavily_edited")
    elif photo_edit_risk_score >= 60:
        risk_flags.append("photo_edit_uncertain")
    return {
        "analysis_status": "ok",
        "photo_edit_risk_score": photo_edit_risk_score,
        "skin_smoothing_risk_score": skin_smoothing_risk_score,
        "beauty_filter_risk_score": beauty_filter_risk_score,
        "face_shape_delta_score": face_shape_delta_score,
        "edited_photo_count": edited_photo_count,
        "photo_face_count": len(metrics_list),
        "risk_flags": risk_flags,
    }


def _profile_photo_deepfake_unavailable_result(reason: str, *, photo_face_count: int) -> dict[str, Any]:
    return {
        "analysis_status": "unavailable",
        "deepfake_risk_score": 0,
        "deepfake_artifact_score": 0,
        "deepfake_consistency_score": 0,
        "photo_face_count": int(photo_face_count),
        "risk_flags": [],
        "analysis_reason": reason,
    }


def _analyze_profile_photo_deepfake_metrics(photo_entries: list[dict[str, Any]]) -> dict[str, Any]:
    metrics_list = [
        item["deepfake_metrics"]
        for item in photo_entries
        if int(item.get("face_count") or 0) == 1 and item.get("deepfake_metrics") is not None
    ]
    if not metrics_list:
        return _profile_photo_deepfake_unavailable_result(
            "profile_face_unavailable",
            photo_face_count=0,
        )

    per_photo_artifact_scores = [
        _bounded_score(
            (_deepfake_score_component(float(metric["seam_strength"]), offset=0.92, scale=0.26) * 0.42)
            + (_deepfake_score_component(float(metric["chroma_gap"]), offset=7.5, scale=16.0) * 0.33)
            + (
                _deepfake_score_component(
                    abs(float(metric["detail_ratio"]) - 1.0),
                    offset=0.10,
                    scale=0.28,
                )
                * 0.25
            )
        )
        for metric in metrics_list
    ]
    top_artifact_scores = sorted(per_photo_artifact_scores, reverse=True)[: min(2, len(per_photo_artifact_scores))]
    artifact_score = _bounded_score(sum(top_artifact_scores) / max(len(top_artifact_scores), 1))
    seam_variation = float(np.std([float(item["seam_strength"]) for item in metrics_list])) if len(metrics_list) >= 2 else 0.0
    chroma_gap_variation = float(np.std([float(item["chroma_gap"]) for item in metrics_list])) if len(metrics_list) >= 2 else 0.0
    detail_ratio_variation = float(np.std([float(item["detail_ratio"]) for item in metrics_list])) if len(metrics_list) >= 2 else 0.0
    consistency_score = _bounded_score(
        (_deepfake_score_component(seam_variation, offset=0.025, scale=0.090) * 0.34)
        + (_deepfake_score_component(chroma_gap_variation, offset=0.55, scale=3.20) * 0.33)
        + (_deepfake_score_component(detail_ratio_variation, offset=0.030, scale=0.120) * 0.33)
    )
    deepfake_risk_score = _bounded_score(max(artifact_score, (artifact_score * 0.70) + (consistency_score * 0.30)))
    risk_flags: list[str] = []
    if deepfake_risk_score >= 85:
        risk_flags.append("deepfake_risk")
    elif deepfake_risk_score >= 60:
        risk_flags.append("deepfake_uncertain")
    return {
        "analysis_status": "ok",
        "deepfake_risk_score": deepfake_risk_score,
        "deepfake_artifact_score": artifact_score,
        "deepfake_consistency_score": consistency_score,
        "photo_face_count": len(metrics_list),
        "risk_flags": risk_flags,
    }


def _profile_photo_duplicate_unavailable_result(reason: str, *, loaded_source_count: int, comparison_source_count: int) -> dict[str, Any]:
    return {
        "analysis_status": "unavailable",
        "stolen_media_risk_score": 0,
        "duplicate_photo_count": 0,
        "cross_profile_duplicate_count": 0,
        "exact_cross_profile_duplicate_count": 0,
        "loaded_source_count": int(loaded_source_count),
        "comparison_source_count": int(comparison_source_count),
        "risk_flags": [],
        "analysis_reason": reason,
    }


def _analyze_profile_photo_duplicates(
    photo_entries: list[dict[str, Any]],
    *,
    comparison_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    target_hash_entries = [item for item in photo_entries if item.get("image_hash") is not None]
    if not target_hash_entries:
        return _profile_photo_duplicate_unavailable_result(
            "profile_photo_unavailable",
            loaded_source_count=len(photo_entries),
            comparison_source_count=len(comparison_entries),
        )

    duplicate_photo_count = 0
    for left_index, left in enumerate(target_hash_entries):
        for right in target_hash_entries[left_index + 1 :]:
            distance = _hash_hamming_distance(left.get("image_hash"), right.get("image_hash"))
            if distance is not None and distance <= 4:
                duplicate_photo_count += 1

    exact_cross_profile_duplicate_count = 0
    cross_profile_duplicate_count = 0
    comparison_sources = {
        str(item.get("source") or "").strip()
        for item in comparison_entries
        if str(item.get("source") or "").strip()
    }
    for target in target_hash_entries:
        target_source = str(target.get("source") or "").strip()
        matched_cross_profile = False
        if target_source and target_source in comparison_sources:
            exact_cross_profile_duplicate_count += 1
            cross_profile_duplicate_count += 1
            continue
        for candidate in comparison_entries:
            distance = _hash_hamming_distance(target.get("image_hash"), candidate.get("image_hash"))
            if distance is None or distance > 4:
                continue
            matched_cross_profile = True
            if distance == 0:
                exact_cross_profile_duplicate_count += 1
            break
        if matched_cross_profile:
            cross_profile_duplicate_count += 1

    stolen_media_risk_score = 0
    if exact_cross_profile_duplicate_count > 0:
        stolen_media_risk_score = _bounded_score(90 + min(exact_cross_profile_duplicate_count * 3, 8))
    elif cross_profile_duplicate_count > 0:
        stolen_media_risk_score = _bounded_score(76 + min(cross_profile_duplicate_count * 4, 12))
    elif duplicate_photo_count > 0:
        stolen_media_risk_score = _bounded_score(52 + min(duplicate_photo_count * 8, 20))

    risk_flags: list[str] = []
    if stolen_media_risk_score >= 85:
        risk_flags.append("stolen_media_risk")
    elif stolen_media_risk_score >= 60 or duplicate_photo_count >= 1:
        risk_flags.append("duplicate_profile_photo")
    return {
        "analysis_status": "ok",
        "stolen_media_risk_score": stolen_media_risk_score,
        "duplicate_photo_count": duplicate_photo_count,
        "cross_profile_duplicate_count": cross_profile_duplicate_count,
        "exact_cross_profile_duplicate_count": exact_cross_profile_duplicate_count,
        "loaded_source_count": len(target_hash_entries),
        "comparison_source_count": len(comparison_entries),
        "risk_flags": risk_flags,
    }


def _collect_profile_photo_entries(image_sources: list[str]) -> list[dict[str, Any]]:
    detector = _silent_face_engine().detector
    face_engine = _face_match_engine()
    entries: list[dict[str, Any]] = []
    for source in image_sources[: _profile_photo_source_limit()]:
        image = _load_image_from_source(source)
        if image is None:
            continue
        detection = detector.detect(image)
        bbox = detection.get("bbox")
        extracted = face_engine.extract_face_embedding(image)
        face_count = max(int(detection.get("face_count") or 0), int(extracted.get("face_count") or 0))
        face_crop = _extract_deepfake_face_crop(image, bbox) if bbox and face_count == 1 else None
        photo_edit_metrics = None
        deepfake_metrics = None
        if face_crop is not None:
            photo_edit_metrics = _photo_edit_crop_metrics(
                face_crop,
                face_aspect_ratio=float(bbox[2]) / max(float(bbox[3]), 1.0),
            )
            deepfake_metrics = _deepfake_crop_metrics(face_crop)
        entries.append(
            {
                "source": str(source),
                "image_hash": _difference_hash(image),
                "face_count": face_count,
                "detection_score": int(extracted.get("detection_score") or 0),
                "embedding": extracted.get("embedding") if face_count == 1 else None,
                "photo_edit_metrics": photo_edit_metrics,
                "deepfake_metrics": deepfake_metrics,
            }
        )
    return entries


def _serialize_photo_entry_features(entry: dict[str, Any]) -> dict[str, Any]:
    embedding = entry.get("embedding")
    embedding_vector = None
    if embedding is not None:
        try:
            embedding_vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        except Exception:  # noqa: BLE001
            embedding_vector = None
    image_hash_hex = None
    image_hash = entry.get("image_hash")
    if image_hash is not None:
        try:
            image_hash_hex = format(int(image_hash), "016x")
        except (TypeError, ValueError):
            image_hash_hex = str(image_hash)
    return {
        "source": str(entry.get("source") or ""),
        "face_count": int(entry.get("face_count") or 0),
        "face_detection_score": int(entry.get("detection_score") or 0),
        "image_hash_hex": image_hash_hex,
        "embedding_available": bool(embedding_vector is not None and int(embedding_vector.size) > 0),
        "embedding_dim": int(embedding_vector.size) if embedding_vector is not None else 0,
        "embedding_preview": (
            [round(float(item), 6) for item in embedding_vector[:16].tolist()]
            if embedding_vector is not None
            else []
        ),
        "photo_edit_metrics": dict(entry.get("photo_edit_metrics") or {}) if isinstance(entry.get("photo_edit_metrics"), dict) else None,
        "deepfake_metrics": dict(entry.get("deepfake_metrics") or {}) if isinstance(entry.get("deepfake_metrics"), dict) else None,
    }


def _analyze_profile_photo_authenticity_bundle(
    image_sources: list[str] | None,
    *,
    comparison_image_sources: list[str] | None = None,
) -> dict[str, Any]:
    normalized_sources = [
        str(item or "").strip()
        for item in list(image_sources or [])
        if str(item or "").strip()
    ]
    if not normalized_sources:
        return {
            "review": {
                "analysis_status": "unavailable",
                "photo_authenticity_score": 0,
                "risk_flags": [],
                "analysis_reason": "profile_photo_unavailable",
                "source_count": 0,
                "loaded_source_count": 0,
                "valid_face_photo_count": 0,
                "multiple_face_photo_count": 0,
            },
            "photo_entries": [],
            "comparison_entries": [],
        }

    photo_entries = _collect_profile_photo_entries(normalized_sources)
    if not photo_entries:
        return {
            "review": {
                "analysis_status": "unavailable",
                "photo_authenticity_score": 0,
                "risk_flags": [],
                "analysis_reason": "profile_photo_load_failed",
                "source_count": len(normalized_sources),
                "loaded_source_count": 0,
                "valid_face_photo_count": 0,
                "multiple_face_photo_count": 0,
            },
            "photo_entries": [],
            "comparison_entries": [],
        }

    normalized_comparison_sources = [
        str(item or "").strip()
        for item in list(comparison_image_sources or [])
        if str(item or "").strip()
    ]
    comparison_entries = _collect_profile_photo_entries(normalized_comparison_sources) if normalized_comparison_sources else []
    same_person_result = _analyze_same_person_photo_entries(photo_entries)
    photo_edit_result = _analyze_profile_photo_edit_metrics(photo_entries)
    deepfake_result = _analyze_profile_photo_deepfake_metrics(photo_entries)
    duplicate_result = _analyze_profile_photo_duplicates(
        photo_entries,
        comparison_entries=comparison_entries,
    )

    valid_face_photo_count = sum(1 for item in photo_entries if int(item.get("face_count") or 0) == 1)
    multiple_face_photo_count = sum(1 for item in photo_entries if int(item.get("face_count") or 0) > 1)
    risk_flags: list[str] = []
    for result in (same_person_result, photo_edit_result, deepfake_result, duplicate_result):
        for flag in list(result.get("risk_flags") or []):
            if flag not in risk_flags:
                risk_flags.append(flag)
    if multiple_face_photo_count > 0 and "multiple_faces_in_profile_photos" not in risk_flags:
        risk_flags.append("multiple_faces_in_profile_photos")
    if valid_face_photo_count <= 0 and "profile_face_unavailable" not in risk_flags:
        risk_flags.append("profile_face_unavailable")

    same_person_score = int(same_person_result.get("same_person_score") or 0)
    photo_authenticity_score = _bounded_score(
        max(
            (same_person_score * 0.38)
            + ((100 - int(photo_edit_result.get("photo_edit_risk_score") or 0)) * 0.18)
            + ((100 - int(deepfake_result.get("deepfake_risk_score") or 0)) * 0.20)
            + ((100 - int(duplicate_result.get("stolen_media_risk_score") or 0)) * 0.24),
            same_person_score * 0.65,
        )
    )
    if "stolen_media_risk" in risk_flags or "mixed_identity_photos" in risk_flags or "deepfake_risk" in risk_flags:
        photo_authenticity_score = min(photo_authenticity_score, 38)
    elif "photo_heavily_edited" in risk_flags:
        photo_authenticity_score = min(photo_authenticity_score, 58)

    return {
        "review": {
            "analysis_status": "ok",
            "photo_authenticity_score": photo_authenticity_score,
            "source_count": len(normalized_sources),
            "loaded_source_count": len(photo_entries),
            "valid_face_photo_count": valid_face_photo_count,
            "multiple_face_photo_count": multiple_face_photo_count,
            "same_person_score": same_person_score,
            "same_person_analysis_status": same_person_result.get("analysis_status"),
            "same_person_pair_count": int(same_person_result.get("pair_count") or 0),
            "same_person_matched_pair_count": int(same_person_result.get("matched_pair_count") or 0),
            "same_person_average_similarity": same_person_result.get("average_similarity"),
            "same_person_min_similarity": same_person_result.get("min_similarity"),
            "photo_edit_risk_score": int(photo_edit_result.get("photo_edit_risk_score") or 0),
            "photo_edit_analysis_status": photo_edit_result.get("analysis_status"),
            "skin_smoothing_risk_score": int(photo_edit_result.get("skin_smoothing_risk_score") or 0),
            "beauty_filter_risk_score": int(photo_edit_result.get("beauty_filter_risk_score") or 0),
            "face_shape_delta_score": int(photo_edit_result.get("face_shape_delta_score") or 0),
            "edited_photo_count": int(photo_edit_result.get("edited_photo_count") or 0),
            "deepfake_risk_score": int(deepfake_result.get("deepfake_risk_score") or 0),
            "deepfake_analysis_status": deepfake_result.get("analysis_status"),
            "deepfake_artifact_score": int(deepfake_result.get("deepfake_artifact_score") or 0),
            "deepfake_consistency_score": int(deepfake_result.get("deepfake_consistency_score") or 0),
            "stolen_media_risk_score": int(duplicate_result.get("stolen_media_risk_score") or 0),
            "stolen_media_analysis_status": duplicate_result.get("analysis_status"),
            "duplicate_photo_count": int(duplicate_result.get("duplicate_photo_count") or 0),
            "cross_profile_duplicate_count": int(duplicate_result.get("cross_profile_duplicate_count") or 0),
            "exact_cross_profile_duplicate_count": int(duplicate_result.get("exact_cross_profile_duplicate_count") or 0),
            "comparison_source_count": int(duplicate_result.get("comparison_source_count") or 0),
            "risk_flags": risk_flags,
        },
        "photo_entries": [_serialize_photo_entry_features(item) for item in photo_entries],
        "comparison_entries": [_serialize_photo_entry_features(item) for item in comparison_entries],
    }


def analyze_profile_photo_authenticity(
    image_sources: list[str] | None,
    *,
    comparison_image_sources: list[str] | None = None,
) -> dict[str, Any]:
    try:
        return _analyze_profile_photo_authenticity_bundle(
            image_sources,
            comparison_image_sources=comparison_image_sources,
        )["review"]
    except Exception as exc:  # noqa: BLE001
        return {
            "analysis_status": "unavailable",
            "photo_authenticity_score": 0,
            "risk_flags": [],
            "analysis_reason": "analysis_exception",
            "error_message": str(exc) or type(exc).__name__,
            "source_count": len(list(image_sources or [])),
            "loaded_source_count": 0,
            "valid_face_photo_count": 0,
            "multiple_face_photo_count": 0,
        }


def analyze_profile_photo_authenticity_detailed(
    image_sources: list[str] | None,
    *,
    comparison_image_sources: list[str] | None = None,
) -> dict[str, Any]:
    try:
        return _analyze_profile_photo_authenticity_bundle(
            image_sources,
            comparison_image_sources=comparison_image_sources,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "review": {
                "analysis_status": "unavailable",
                "photo_authenticity_score": 0,
                "risk_flags": [],
                "analysis_reason": "analysis_exception",
                "error_message": str(exc) or type(exc).__name__,
                "source_count": len(list(image_sources or [])),
                "loaded_source_count": 0,
                "valid_face_photo_count": 0,
                "multiple_face_photo_count": 0,
            },
            "photo_entries": [],
            "comparison_entries": [],
        }


def _speech_window_bounds_ms(
    speech_result: dict[str, Any],
    *,
    media_duration_ms: int | None = None,
) -> tuple[int, int] | None:
    segments = speech_result.get("transcript_segments") if isinstance(speech_result.get("transcript_segments"), list) else []
    segment_bounds = [
        (
            max(0, int(item.get("start_ms"))),
            max(0, int(item.get("end_ms"))),
        )
        for item in segments
        if isinstance(item, dict) and item.get("start_ms") is not None and item.get("end_ms") is not None
    ]
    started_at_ms = speech_result.get("speech_started_at_ms")
    ended_at_ms = speech_result.get("speech_ended_at_ms")
    try:
        start_ms = max(0, int(started_at_ms)) if started_at_ms is not None else None
    except (TypeError, ValueError):
        start_ms = None
    try:
        end_ms = max(0, int(ended_at_ms)) if ended_at_ms is not None else None
    except (TypeError, ValueError):
        end_ms = None
    if segment_bounds:
        first_segment_start, _ = segment_bounds[0]
        _, last_segment_end = segment_bounds[-1]
        if start_ms is None:
            start_ms = first_segment_start
        if end_ms is None:
            end_ms = last_segment_end
    if start_ms is None or end_ms is None:
        return None
    if media_duration_ms is not None:
        start_ms = min(start_ms, max(0, int(media_duration_ms)))
        end_ms = min(end_ms, max(0, int(media_duration_ms)))
    if end_ms <= start_ms:
        if media_duration_ms is not None and start_ms < int(media_duration_ms):
            end_ms = min(int(media_duration_ms), start_ms + 800)
        else:
            return None
    if end_ms - start_ms < 280:
        end_ms = start_ms + 280
        if media_duration_ms is not None:
            end_ms = min(end_ms, int(media_duration_ms))
    if end_ms <= start_ms:
        return None
    return start_ms, end_ms


def _video_frame_timestamp_ms(frame: av.VideoFrame) -> int | None:
    if frame.time is not None:
        return max(0, int(round(float(frame.time) * 1000.0)))
    if frame.pts is not None and frame.time_base is not None:
        return max(0, int(round(float(frame.pts * frame.time_base) * 1000.0)))
    return None


def _sample_video_frames_for_sync(
    video_path: Path,
    *,
    speech_start_ms: int,
    speech_end_ms: int,
) -> list[dict[str, Any]]:
    start_ms = max(0, int(speech_start_ms) - _SYNC_WINDOW_PADDING_MS)
    end_ms = max(start_ms, int(speech_end_ms) + _SYNC_WINDOW_PADDING_MS)
    frames: list[dict[str, Any]] = []
    frame_interval_seconds = 1.0 / max(_SYNC_VIDEO_TARGET_FPS, 1.0)
    next_sample_seconds = start_ms / 1000.0
    with av.open(str(video_path)) as container:
        if not any(stream.type == "video" for stream in container.streams):
            return []
        for frame in container.decode(video=0):
            timestamp_ms = _video_frame_timestamp_ms(frame)
            if timestamp_ms is None or timestamp_ms < start_ms:
                continue
            if timestamp_ms > end_ms:
                break
            timestamp_seconds = timestamp_ms / 1000.0
            if timestamp_seconds + 1e-6 < next_sample_seconds:
                continue
            frames.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "frame": frame.to_ndarray(format="bgr24"),
                }
            )
            next_sample_seconds = timestamp_seconds + frame_interval_seconds
            if len(frames) >= _SYNC_MAX_VIDEO_FRAMES:
                break
    return frames


def _extract_face_region(
    frame: np.ndarray,
    bbox: list[int],
    *,
    x_start_ratio: float,
    x_end_ratio: float,
    y_start_ratio: float,
    y_end_ratio: float,
) -> np.ndarray | None:
    left, top, width, height = [int(value) for value in bbox]
    frame_height, frame_width = frame.shape[:2]
    x0 = max(0, min(frame_width, int(round(left + (width * x_start_ratio)))))
    x1 = max(0, min(frame_width, int(round(left + (width * x_end_ratio)))))
    y0 = max(0, min(frame_height, int(round(top + (height * y_start_ratio)))))
    y1 = max(0, min(frame_height, int(round(top + (height * y_end_ratio)))))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    region = frame[y0:y1, x0:x1]
    if region.size <= 0:
        return None
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.resize(gray, (48, 32), interpolation=cv2.INTER_LINEAR)


def _extract_mouth_motion_points(
    video_path: Path,
    *,
    speech_start_ms: int,
    speech_end_ms: int,
) -> dict[str, Any]:
    detector = _silent_face_engine().detector
    sampled_frames = _sample_video_frames_for_sync(
        video_path,
        speech_start_ms=speech_start_ms,
        speech_end_ms=speech_end_ms,
    )
    previous_mouth_region: np.ndarray | None = None
    previous_upper_region: np.ndarray | None = None
    face_frame_count = 0
    motion_points: list[dict[str, Any]] = []
    for frame_item in sampled_frames:
        detection = detector.detect(frame_item["frame"])
        bbox = detection.get("bbox")
        face_count = int(detection.get("face_count") or 0)
        if not bbox or face_count != 1:
            previous_mouth_region = None
            previous_upper_region = None
            continue
        mouth_region = _extract_face_region(
            frame_item["frame"],
            bbox,
            x_start_ratio=0.22,
            x_end_ratio=0.78,
            y_start_ratio=0.58,
            y_end_ratio=0.92,
        )
        upper_region = _extract_face_region(
            frame_item["frame"],
            bbox,
            x_start_ratio=0.22,
            x_end_ratio=0.78,
            y_start_ratio=0.18,
            y_end_ratio=0.48,
        )
        if mouth_region is None or upper_region is None:
            previous_mouth_region = None
            previous_upper_region = None
            continue
        face_frame_count += 1
        if previous_mouth_region is not None and previous_upper_region is not None:
            mouth_delta = float(np.mean(cv2.absdiff(mouth_region, previous_mouth_region))) / 255.0
            upper_delta = float(np.mean(cv2.absdiff(upper_region, previous_upper_region))) / 255.0
            relative_motion = max(0.0, mouth_delta - (upper_delta * 0.35))
            motion_points.append(
                {
                    "timestamp_ms": int(frame_item["timestamp_ms"]),
                    "value": relative_motion,
                    "mouth_delta": mouth_delta,
                    "upper_delta": upper_delta,
                }
            )
        previous_mouth_region = mouth_region
        previous_upper_region = upper_region
    if len(motion_points) >= 3:
        raw_values = np.asarray([float(item["value"]) for item in motion_points], dtype=np.float32)
        smoothed = np.convolve(raw_values, np.asarray([0.25, 0.5, 0.25], dtype=np.float32), mode="same")
        for item, smoothed_value in zip(motion_points, smoothed.tolist()):
            item["value"] = max(0.0, float(smoothed_value))
    return {
        "sampled_frame_count": len(sampled_frames),
        "face_frame_count": face_frame_count,
        "points": motion_points,
    }


def _load_wav_pcm(audio_path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(audio_path), "rb") as wav_file:
        sample_rate = int(wav_file.getframerate() or 0)
        channel_count = int(wav_file.getnchannels() or 1)
        sample_width = int(wav_file.getsampwidth() or 0)
        frame_count = int(wav_file.getnframes() or 0)
        payload = wav_file.readframes(frame_count)
    if sample_rate <= 0 or sample_width != 2:
        raise RuntimeError("unsupported extracted audio format")
    pcm = np.frombuffer(payload, dtype="<i2").astype(np.float32, copy=False)
    if channel_count > 1:
        pcm = pcm.reshape(-1, channel_count).mean(axis=1)
    if pcm.size <= 0:
        raise RuntimeError("extracted audio is empty")
    return pcm / 32768.0, sample_rate


def _extract_audio_energy_points(
    audio_path: Path,
    *,
    speech_start_ms: int,
    speech_end_ms: int,
) -> list[dict[str, Any]]:
    pcm, sample_rate = _load_wav_pcm(audio_path)
    window_samples = max(1, int(round(sample_rate * (_SYNC_AUDIO_WINDOW_MS / 1000.0))))
    hop_samples = max(1, int(round(sample_rate * (_SYNC_AUDIO_HOP_MS / 1000.0))))
    region_start_ms = max(0, int(speech_start_ms) - _SYNC_WINDOW_PADDING_MS)
    region_end_ms = int(speech_end_ms) + _SYNC_WINDOW_PADDING_MS
    start_sample = max(0, int(round(region_start_ms / 1000.0 * sample_rate)))
    end_sample = min(pcm.size, int(round(region_end_ms / 1000.0 * sample_rate)))
    region_pcm = pcm[start_sample:end_sample]
    if region_pcm.size <= 0:
        raise RuntimeError("audio region for sync is empty")
    points: list[dict[str, Any]] = []
    if region_pcm.size <= window_samples:
        rms = float(np.sqrt(np.mean(np.square(region_pcm, dtype=np.float32))))
        midpoint_ms = int(round(((start_sample + (region_pcm.size / 2.0)) / sample_rate) * 1000.0))
        points.append({"timestamp_ms": midpoint_ms, "value": rms})
        return points
    for offset in range(0, max(region_pcm.size - window_samples, 0) + 1, hop_samples):
        window = region_pcm[offset : offset + window_samples]
        if window.size <= 0:
            continue
        rms = float(np.sqrt(np.mean(np.square(window, dtype=np.float32))))
        center_sample = start_sample + offset + (window_samples / 2.0)
        points.append(
            {
                "timestamp_ms": int(round((center_sample / sample_rate) * 1000.0)),
                "value": rms,
            }
        )
    if len(points) >= 3:
        raw_values = np.asarray([float(item["value"]) for item in points], dtype=np.float32)
        smoothed = np.convolve(raw_values, np.asarray([0.25, 0.5, 0.25], dtype=np.float32), mode="same")
        for item, smoothed_value in zip(points, smoothed.tolist()):
            item["value"] = max(0.0, float(smoothed_value))
    return points


def _normalize_curve(values: np.ndarray) -> np.ndarray:
    if values.size <= 0:
        return values
    baseline = float(np.percentile(values, 15))
    peak = float(np.percentile(values, 90))
    if peak - baseline <= 1e-6:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - baseline) / (peak - baseline), 0.0, 1.0).astype(np.float32, copy=False)


def _pearson_correlation(left: np.ndarray, right: np.ndarray) -> float:
    if left.size != right.size or left.size <= 1:
        return 0.0
    left_std = float(np.std(left))
    right_std = float(np.std(right))
    if left_std <= 1e-6 or right_std <= 1e-6:
        return 0.0
    matrix = np.corrcoef(left, right)
    if matrix.shape != (2, 2) or np.isnan(matrix[0, 1]):
        return 0.0
    return float(matrix[0, 1])


def _score_audio_video_sync_curves(
    audio_points: list[dict[str, Any]],
    visual_points: list[dict[str, Any]],
    *,
    speech_start_ms: int,
    speech_end_ms: int,
) -> dict[str, Any]:
    if len(audio_points) < 5:
        raise RuntimeError("insufficient audio windows for lip-sync analysis")
    if len(visual_points) < 3:
        raise RuntimeError("insufficient mouth-motion frames for lip-sync analysis")
    audio_times = np.asarray([int(item["timestamp_ms"]) for item in audio_points], dtype=np.float32)
    audio_values = np.asarray([float(item["value"]) for item in audio_points], dtype=np.float32)
    visual_times = np.asarray([int(item["timestamp_ms"]) for item in visual_points], dtype=np.float32)
    visual_values = np.asarray([float(item["value"]) for item in visual_points], dtype=np.float32)
    in_window_mask = (audio_times >= float(speech_start_ms)) & (audio_times <= float(speech_end_ms))
    if int(np.count_nonzero(in_window_mask)) < 4:
        raise RuntimeError("speech window is too short for lip-sync analysis")
    audio_curve = _normalize_curve(audio_values)
    visual_curve = _normalize_curve(visual_values)
    if float(np.max(audio_curve[in_window_mask])) < 0.18:
        raise RuntimeError("insufficient speech energy for lip-sync analysis")
    best_candidate: dict[str, Any] | None = None
    for shift_ms in range(-_SYNC_MAX_SHIFT_MS, _SYNC_MAX_SHIFT_MS + _SYNC_SHIFT_STEP_MS, _SYNC_SHIFT_STEP_MS):
        shifted_visual_curve = np.interp(
            audio_times,
            visual_times + float(shift_ms),
            visual_curve,
            left=0.0,
            right=0.0,
        )
        speech_audio_curve = audio_curve[in_window_mask]
        speech_visual_curve = shifted_visual_curve[in_window_mask]
        correlation = _pearson_correlation(speech_audio_curve, speech_visual_curve)
        active_audio_mask = speech_audio_curve >= 0.35
        if not bool(np.any(active_audio_mask)):
            audio_activity_threshold = max(0.2, float(np.percentile(speech_audio_curve, 75)))
            active_audio_mask = speech_audio_curve >= audio_activity_threshold
        active_visual_mask = speech_visual_curve >= 0.25
        overlap_ratio = (
            float(np.count_nonzero(active_audio_mask & active_visual_mask)) / float(np.count_nonzero(active_audio_mask))
            if bool(np.any(active_audio_mask))
            else 0.0
        )
        window_motion_mean = float(np.mean(speech_visual_curve))
        context_mask = ~in_window_mask
        context_motion_mean = float(np.mean(shifted_visual_curve[context_mask])) if bool(np.any(context_mask)) else 0.0
        focus_ratio = float(np.clip((window_motion_mean - context_motion_mean + 0.05) / 0.55, 0.0, 1.0))
        motion_peak = float(np.max(speech_visual_curve))
        motion_peak_ratio = float(np.clip((motion_peak - 0.15) / 0.55, 0.0, 1.0))
        correlation_ratio = float(np.clip((correlation + 0.2) / 0.9, 0.0, 1.0))
        score = (
            (correlation_ratio * 45.0)
            + (overlap_ratio * 30.0)
            + (focus_ratio * 15.0)
            + (motion_peak_ratio * 10.0)
        )
        candidate = {
            "audio_video_sync_score": _bounded_score(score),
            "best_shift_ms": int(shift_ms),
            "correlation": round(correlation, 4),
            "overlap_ratio": round(overlap_ratio, 4),
            "focus_ratio": round(focus_ratio, 4),
            "motion_peak_ratio": round(motion_peak_ratio, 4),
            "window_motion_mean": round(window_motion_mean, 4),
            "context_motion_mean": round(context_motion_mean, 4),
        }
        if best_candidate is None or int(candidate["audio_video_sync_score"]) > int(best_candidate["audio_video_sync_score"]):
            best_candidate = candidate
    assert best_candidate is not None
    if float(best_candidate["motion_peak_ratio"]) < 0.18:
        best_candidate["audio_video_sync_score"] = min(int(best_candidate["audio_video_sync_score"]), 45)
    if float(best_candidate["overlap_ratio"]) < 0.35:
        best_candidate["audio_video_sync_score"] = min(int(best_candidate["audio_video_sync_score"]), 55)
    best_candidate["audio_video_sync_score"] = _bounded_score(best_candidate["audio_video_sync_score"])
    return best_candidate


def _compute_audio_video_sync_result(
    video_path: Path,
    *,
    audio_path: Path,
    speech_result: dict[str, Any],
    media_info: dict[str, Any],
) -> dict[str, Any]:
    speech_window = _speech_window_bounds_ms(
        speech_result,
        media_duration_ms=int(media_info.get("duration_ms") or 0) if media_info.get("duration_ms") is not None else None,
    )
    if speech_window is None:
        raise RuntimeError("speech timing is unavailable for lip-sync analysis")
    speech_start_ms, speech_end_ms = speech_window
    audio_points = _extract_audio_energy_points(
        audio_path,
        speech_start_ms=speech_start_ms,
        speech_end_ms=speech_end_ms,
    )
    visual_result = _extract_mouth_motion_points(
        video_path,
        speech_start_ms=speech_start_ms,
        speech_end_ms=speech_end_ms,
    )
    sync_metrics = _score_audio_video_sync_curves(
        audio_points,
        list(visual_result.get("points") or []),
        speech_start_ms=speech_start_ms,
        speech_end_ms=speech_end_ms,
    )
    return {
        "audio_video_sync_score": int(sync_metrics["audio_video_sync_score"]),
        "audio_video_sync_status": "ok",
        "audio_video_sync_offset_ms": int(sync_metrics["best_shift_ms"]),
        "audio_video_sync_correlation": sync_metrics["correlation"],
        "audio_video_sync_overlap_ratio": sync_metrics["overlap_ratio"],
        "speech_visual_frame_count": int(visual_result.get("face_frame_count") or 0),
        "speech_visual_sampled_frame_count": int(visual_result.get("sampled_frame_count") or 0),
        "speech_audio_window_count": len(audio_points),
    }


def _safe_compute_audio_video_sync_result(
    video_path: Path,
    *,
    audio_path: Path,
    speech_result: dict[str, Any],
    media_info: dict[str, Any],
) -> dict[str, Any]:
    try:
        return _compute_audio_video_sync_result(
            video_path,
            audio_path=audio_path,
            speech_result=speech_result,
            media_info=media_info,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "audio_video_sync_status": "unavailable",
            "audio_video_sync_error_type": type(exc).__name__,
            "audio_video_sync_error_message": str(exc) or type(exc).__name__,
        }


class _Flatten(Module):
    def forward(self, input_tensor):
        return input_tensor.view(input_tensor.size(0), -1)


class _ConvBlock(Module):
    def __init__(self, in_channels, out_channels, kernel=(1, 1), stride=(1, 1), padding=(0, 0), groups=1):
        super().__init__()
        self.conv = Conv2d(
            in_channels,
            out_channels,
            kernel_size=kernel,
            groups=groups,
            stride=stride,
            padding=padding,
            bias=False,
        )
        self.bn = BatchNorm2d(out_channels)
        self.prelu = PReLU(out_channels)

    def forward(self, input_tensor):
        output = self.conv(input_tensor)
        output = self.bn(output)
        output = self.prelu(output)
        return output


class _LinearBlock(Module):
    def __init__(self, in_channels, out_channels, kernel=(1, 1), stride=(1, 1), padding=(0, 0), groups=1):
        super().__init__()
        self.conv = Conv2d(
            in_channels,
            out_channels=out_channels,
            kernel_size=kernel,
            groups=groups,
            stride=stride,
            padding=padding,
            bias=False,
        )
        self.bn = BatchNorm2d(out_channels)

    def forward(self, input_tensor):
        output = self.conv(input_tensor)
        output = self.bn(output)
        return output


class _DepthWise(Module):
    def __init__(
        self,
        c1,
        c2,
        c3,
        *,
        residual=False,
        kernel=(3, 3),
        stride=(2, 2),
        padding=(1, 1),
        groups=1,
    ):
        super().__init__()
        c1_in, c1_out = c1
        c2_in, c2_out = c2
        c3_in, c3_out = c3
        self.conv = _ConvBlock(c1_in, c1_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.conv_dw = _ConvBlock(c2_in, c2_out, groups=c2_in, kernel=kernel, padding=padding, stride=stride)
        self.project = _LinearBlock(c3_in, c3_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.residual = residual

    def forward(self, input_tensor):
        if self.residual:
            shortcut = input_tensor
        output = self.conv(input_tensor)
        output = self.conv_dw(output)
        output = self.project(output)
        if self.residual:
            output = shortcut + output
        return output


class _Residual(Module):
    def __init__(self, c1, c2, c3, *, num_block, groups, kernel=(3, 3), stride=(1, 1), padding=(1, 1)):
        super().__init__()
        modules = []
        for index in range(num_block):
            modules.append(
                _DepthWise(
                    c1[index],
                    c2[index],
                    c3[index],
                    residual=True,
                    kernel=kernel,
                    padding=padding,
                    stride=stride,
                    groups=groups,
                )
            )
        self.model = Sequential(*modules)

    def forward(self, input_tensor):
        return self.model(input_tensor)


class _SEModule(Module):
    def __init__(self, channels, reduction):
        super().__init__()
        self.avg_pool = AdaptiveAvgPool2d(1)
        self.fc1 = Conv2d(channels, channels // reduction, kernel_size=1, padding=0, bias=False)
        self.bn1 = BatchNorm2d(channels // reduction)
        self.relu = ReLU(inplace=True)
        self.fc2 = Conv2d(channels // reduction, channels, kernel_size=1, padding=0, bias=False)
        self.bn2 = BatchNorm2d(channels)
        self.sigmoid = Sigmoid()

    def forward(self, input_tensor):
        output = self.avg_pool(input_tensor)
        output = self.fc1(output)
        output = self.bn1(output)
        output = self.relu(output)
        output = self.fc2(output)
        output = self.bn2(output)
        output = self.sigmoid(output)
        return input_tensor * output


class _DepthWiseSE(Module):
    def __init__(
        self,
        c1,
        c2,
        c3,
        *,
        residual=False,
        kernel=(3, 3),
        stride=(2, 2),
        padding=(1, 1),
        groups=1,
        se_reduct=8,
    ):
        super().__init__()
        c1_in, c1_out = c1
        c2_in, c2_out = c2
        c3_in, c3_out = c3
        self.conv = _ConvBlock(c1_in, c1_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.conv_dw = _ConvBlock(c2_in, c2_out, groups=c2_in, kernel=kernel, padding=padding, stride=stride)
        self.project = _LinearBlock(c3_in, c3_out, kernel=(1, 1), padding=(0, 0), stride=(1, 1))
        self.residual = residual
        self.se_module = _SEModule(c3_out, se_reduct)

    def forward(self, input_tensor):
        if self.residual:
            shortcut = input_tensor
        output = self.conv(input_tensor)
        output = self.conv_dw(output)
        output = self.project(output)
        if self.residual:
            output = self.se_module(output)
            output = shortcut + output
        return output


class _ResidualSE(Module):
    def __init__(
        self,
        c1,
        c2,
        c3,
        *,
        num_block,
        groups,
        kernel=(3, 3),
        stride=(1, 1),
        padding=(1, 1),
        se_reduct=4,
    ):
        super().__init__()
        modules = []
        for index in range(num_block):
            if index == num_block - 1:
                modules.append(
                    _DepthWiseSE(
                        c1[index],
                        c2[index],
                        c3[index],
                        residual=True,
                        kernel=kernel,
                        padding=padding,
                        stride=stride,
                        groups=groups,
                        se_reduct=se_reduct,
                    )
                )
            else:
                modules.append(
                    _DepthWise(
                        c1[index],
                        c2[index],
                        c3[index],
                        residual=True,
                        kernel=kernel,
                        padding=padding,
                        stride=stride,
                        groups=groups,
                    )
                )
        self.model = Sequential(*modules)

    def forward(self, input_tensor):
        return self.model(input_tensor)


class _MiniFASNet(Module):
    def __init__(self, keep, embedding_size, *, conv6_kernel=(7, 7), drop_p=0.0, num_classes=3, img_channel=3):
        super().__init__()
        self.embedding_size = embedding_size

        self.conv1 = _ConvBlock(img_channel, keep[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1))
        self.conv2_dw = _ConvBlock(
            keep[0],
            keep[1],
            kernel=(3, 3),
            stride=(1, 1),
            padding=(1, 1),
            groups=keep[1],
        )

        c1 = [(keep[1], keep[2])]
        c2 = [(keep[2], keep[3])]
        c3 = [(keep[3], keep[4])]
        self.conv_23 = _DepthWise(c1[0], c2[0], c3[0], kernel=(3, 3), stride=(2, 2), padding=(1, 1), groups=keep[3])

        c1 = [(keep[4], keep[5]), (keep[7], keep[8]), (keep[10], keep[11]), (keep[13], keep[14])]
        c2 = [(keep[5], keep[6]), (keep[8], keep[9]), (keep[11], keep[12]), (keep[14], keep[15])]
        c3 = [(keep[6], keep[7]), (keep[9], keep[10]), (keep[12], keep[13]), (keep[15], keep[16])]
        self.conv_3 = _Residual(c1, c2, c3, num_block=4, groups=keep[4], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [(keep[16], keep[17])]
        c2 = [(keep[17], keep[18])]
        c3 = [(keep[18], keep[19])]
        self.conv_34 = _DepthWise(
            c1[0],
            c2[0],
            c3[0],
            kernel=(3, 3),
            stride=(2, 2),
            padding=(1, 1),
            groups=keep[19],
        )

        c1 = [
            (keep[19], keep[20]),
            (keep[22], keep[23]),
            (keep[25], keep[26]),
            (keep[28], keep[29]),
            (keep[31], keep[32]),
            (keep[34], keep[35]),
        ]
        c2 = [
            (keep[20], keep[21]),
            (keep[23], keep[24]),
            (keep[26], keep[27]),
            (keep[29], keep[30]),
            (keep[32], keep[33]),
            (keep[35], keep[36]),
        ]
        c3 = [
            (keep[21], keep[22]),
            (keep[24], keep[25]),
            (keep[27], keep[28]),
            (keep[30], keep[31]),
            (keep[33], keep[34]),
            (keep[36], keep[37]),
        ]
        self.conv_4 = _Residual(c1, c2, c3, num_block=6, groups=keep[19], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [(keep[37], keep[38])]
        c2 = [(keep[38], keep[39])]
        c3 = [(keep[39], keep[40])]
        self.conv_45 = _DepthWise(
            c1[0],
            c2[0],
            c3[0],
            kernel=(3, 3),
            stride=(2, 2),
            padding=(1, 1),
            groups=keep[40],
        )

        c1 = [(keep[40], keep[41]), (keep[43], keep[44])]
        c2 = [(keep[41], keep[42]), (keep[44], keep[45])]
        c3 = [(keep[42], keep[43]), (keep[45], keep[46])]
        self.conv_5 = _Residual(c1, c2, c3, num_block=2, groups=keep[40], kernel=(3, 3), stride=(1, 1), padding=(1, 1))
        self.conv_6_sep = _ConvBlock(keep[46], keep[47], kernel=(1, 1), stride=(1, 1), padding=(0, 0))
        self.conv_6_dw = _LinearBlock(
            keep[47],
            keep[48],
            groups=keep[48],
            kernel=conv6_kernel,
            stride=(1, 1),
            padding=(0, 0),
        )
        self.conv_6_flatten = _Flatten()
        self.linear = Linear(512, embedding_size, bias=False)
        self.bn = BatchNorm1d(embedding_size)
        self.drop = torch.nn.Dropout(p=drop_p)
        self.prob = Linear(embedding_size, num_classes, bias=False)

    def forward(self, input_tensor):
        output = self.conv1(input_tensor)
        output = self.conv2_dw(output)
        output = self.conv_23(output)
        output = self.conv_3(output)
        output = self.conv_34(output)
        output = self.conv_4(output)
        output = self.conv_45(output)
        output = self.conv_5(output)
        output = self.conv_6_sep(output)
        output = self.conv_6_dw(output)
        output = self.conv_6_flatten(output)
        if self.embedding_size != 512:
            output = self.linear(output)
        output = self.bn(output)
        output = self.drop(output)
        output = self.prob(output)
        return output


class _MiniFASNetSE(_MiniFASNet):
    def __init__(self, keep, embedding_size, *, conv6_kernel=(7, 7), drop_p=0.75, num_classes=3, img_channel=3):
        super().__init__(
            keep=keep,
            embedding_size=embedding_size,
            conv6_kernel=conv6_kernel,
            drop_p=drop_p,
            num_classes=num_classes,
            img_channel=img_channel,
        )

        c1 = [(keep[4], keep[5]), (keep[7], keep[8]), (keep[10], keep[11]), (keep[13], keep[14])]
        c2 = [(keep[5], keep[6]), (keep[8], keep[9]), (keep[11], keep[12]), (keep[14], keep[15])]
        c3 = [(keep[6], keep[7]), (keep[9], keep[10]), (keep[12], keep[13]), (keep[15], keep[16])]
        self.conv_3 = _ResidualSE(c1, c2, c3, num_block=4, groups=keep[4], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [
            (keep[19], keep[20]),
            (keep[22], keep[23]),
            (keep[25], keep[26]),
            (keep[28], keep[29]),
            (keep[31], keep[32]),
            (keep[34], keep[35]),
        ]
        c2 = [
            (keep[20], keep[21]),
            (keep[23], keep[24]),
            (keep[26], keep[27]),
            (keep[29], keep[30]),
            (keep[32], keep[33]),
            (keep[35], keep[36]),
        ]
        c3 = [
            (keep[21], keep[22]),
            (keep[24], keep[25]),
            (keep[27], keep[28]),
            (keep[30], keep[31]),
            (keep[33], keep[34]),
            (keep[36], keep[37]),
        ]
        self.conv_4 = _ResidualSE(c1, c2, c3, num_block=6, groups=keep[19], kernel=(3, 3), stride=(1, 1), padding=(1, 1))

        c1 = [(keep[40], keep[41]), (keep[43], keep[44])]
        c2 = [(keep[41], keep[42]), (keep[44], keep[45])]
        c3 = [(keep[42], keep[43]), (keep[45], keep[46])]
        self.conv_5 = _ResidualSE(c1, c2, c3, num_block=2, groups=keep[40], kernel=(3, 3), stride=(1, 1), padding=(1, 1))


_KEEP_DICT = {
    "1.8M": [
        32,
        32,
        103,
        103,
        64,
        13,
        13,
        64,
        26,
        26,
        64,
        13,
        13,
        64,
        52,
        52,
        64,
        231,
        231,
        128,
        154,
        154,
        128,
        52,
        52,
        128,
        26,
        26,
        128,
        52,
        52,
        128,
        26,
        26,
        128,
        26,
        26,
        128,
        308,
        308,
        128,
        26,
        26,
        128,
        26,
        26,
        128,
        512,
        512,
    ],
    "1.8M_": [
        32,
        32,
        103,
        103,
        64,
        13,
        13,
        64,
        13,
        13,
        64,
        13,
        13,
        64,
        13,
        13,
        64,
        231,
        231,
        128,
        231,
        231,
        128,
        52,
        52,
        128,
        26,
        26,
        128,
        77,
        77,
        128,
        26,
        26,
        128,
        26,
        26,
        128,
        308,
        308,
        128,
        26,
        26,
        128,
        26,
        26,
        128,
        512,
        512,
    ],
}


def _mini_fasnet_v1(*, embedding_size=128, conv6_kernel=(7, 7), drop_p=0.2, num_classes=3, img_channel=3):
    return _MiniFASNet(
        _KEEP_DICT["1.8M"],
        embedding_size,
        conv6_kernel=conv6_kernel,
        drop_p=drop_p,
        num_classes=num_classes,
        img_channel=img_channel,
    )


def _mini_fasnet_v2(*, embedding_size=128, conv6_kernel=(7, 7), drop_p=0.2, num_classes=3, img_channel=3):
    return _MiniFASNet(
        _KEEP_DICT["1.8M_"],
        embedding_size,
        conv6_kernel=conv6_kernel,
        drop_p=drop_p,
        num_classes=num_classes,
        img_channel=img_channel,
    )


def _mini_fasnet_v1_se(*, embedding_size=128, conv6_kernel=(7, 7), drop_p=0.75, num_classes=3, img_channel=3):
    return _MiniFASNetSE(
        _KEEP_DICT["1.8M"],
        embedding_size,
        conv6_kernel=conv6_kernel,
        drop_p=drop_p,
        num_classes=num_classes,
        img_channel=img_channel,
    )


def _mini_fasnet_v2_se(*, embedding_size=128, conv6_kernel=(7, 7), drop_p=0.75, num_classes=3, img_channel=3):
    return _MiniFASNetSE(
        _KEEP_DICT["1.8M_"],
        embedding_size,
        conv6_kernel=conv6_kernel,
        drop_p=drop_p,
        num_classes=num_classes,
        img_channel=img_channel,
    )


_MODEL_MAPPING = {
    "MiniFASNetV1": _mini_fasnet_v1,
    "MiniFASNetV2": _mini_fasnet_v2,
    "MiniFASNetV1SE": _mini_fasnet_v1_se,
    "MiniFASNetV2SE": _mini_fasnet_v2_se,
}


def _get_kernel(height: int, width: int) -> tuple[int, int]:
    return ((height + 15) // 16, (width + 15) // 16)


def _parse_model_name(model_name: str) -> tuple[int, int, str, float | None]:
    info = model_name.split("_")[0:-1]
    h_input, w_input = info[-1].split("x")
    model_type = model_name.split(".pth")[0].split("_")[-1]
    scale = None if info[0] == "org" else float(info[0])
    return int(h_input), int(w_input), model_type, scale


def _frame_to_tensor(image: np.ndarray) -> torch.Tensor:
    if image.ndim == 2:
        image = image.reshape((image.shape[0], image.shape[1], 1))
    tensor = torch.from_numpy(image.transpose((2, 0, 1))).float()
    return tensor.unsqueeze(0)


class _CropImage:
    @staticmethod
    def _get_new_box(src_w: int, src_h: int, bbox: list[int], scale: float) -> tuple[int, int, int, int]:
        x, y, box_w, box_h = bbox
        scale = min((src_h - 1) / box_h, min((src_w - 1) / box_w, scale))
        new_width = box_w * scale
        new_height = box_h * scale
        center_x = (box_w / 2) + x
        center_y = (box_h / 2) + y
        left_top_x = center_x - (new_width / 2)
        left_top_y = center_y - (new_height / 2)
        right_bottom_x = center_x + (new_width / 2)
        right_bottom_y = center_y + (new_height / 2)
        if left_top_x < 0:
            right_bottom_x -= left_top_x
            left_top_x = 0
        if left_top_y < 0:
            right_bottom_y -= left_top_y
            left_top_y = 0
        if right_bottom_x > src_w - 1:
            left_top_x -= right_bottom_x - src_w + 1
            right_bottom_x = src_w - 1
        if right_bottom_y > src_h - 1:
            left_top_y -= right_bottom_y - src_h + 1
            right_bottom_y = src_h - 1
        return int(left_top_x), int(left_top_y), int(right_bottom_x), int(right_bottom_y)

    def crop(self, *, org_img: np.ndarray, bbox: list[int], scale: float, out_w: int, out_h: int, crop: bool = True) -> np.ndarray:
        if not crop:
            return cv2.resize(org_img, (out_w, out_h))
        src_h, src_w, _ = np.shape(org_img)
        left_top_x, left_top_y, right_bottom_x, right_bottom_y = self._get_new_box(src_w, src_h, bbox, scale)
        image = org_img[left_top_y : right_bottom_y + 1, left_top_x : right_bottom_x + 1]
        return cv2.resize(image, (out_w, out_h))


class _Detection:
    def __init__(self, repo_root: Path):
        caffemodel = repo_root / "resources" / "detection_model" / "Widerface-RetinaFace.caffemodel"
        deploy = repo_root / "resources" / "detection_model" / "deploy.prototxt"
        self.detector = cv2.dnn.readNetFromCaffe(str(deploy), str(caffemodel))
        self.detector_confidence = 0.6

    def detect(self, image: np.ndarray) -> dict[str, Any]:
        height, width = image.shape[0], image.shape[1]
        aspect_ratio = width / max(height, 1)
        detection_image = image
        if image.shape[1] * image.shape[0] >= 192 * 192:
            detection_image = cv2.resize(
                image,
                (
                    int(192 * math.sqrt(aspect_ratio)),
                    int(192 / max(math.sqrt(aspect_ratio), 1e-6)),
                ),
                interpolation=cv2.INTER_LINEAR,
            )
        blob = cv2.dnn.blobFromImage(detection_image, 1, mean=(104, 117, 123))
        self.detector.setInput(blob, "data")
        output = self.detector.forward("detection_out").squeeze()
        if output.size == 0:
            return {"bbox": None, "confidence": 0.0, "face_count": 0}
        if output.ndim == 1:
            output = output.reshape(1, -1)
        valid_rows = output[output[:, 2] >= self.detector_confidence]
        if valid_rows.size == 0:
            return {"bbox": None, "confidence": 0.0, "face_count": 0}
        best_index = int(np.argmax(valid_rows[:, 2]))
        best_row = valid_rows[best_index]
        left = int(max(0, round(best_row[3] * width)))
        top = int(max(0, round(best_row[4] * height)))
        right = int(min(width, round(best_row[5] * width)))
        bottom = int(min(height, round(best_row[6] * height)))
        bbox = [left, top, max(1, right - left + 1), max(1, bottom - top + 1)]
        return {
            "bbox": bbox,
            "confidence": float(best_row[2]),
            "face_count": int(valid_rows.shape[0]),
        }


class _SilentFaceEngine:
    def __init__(self, repo_root: Path, device_name: str):
        self.repo_root = repo_root
        self.device = torch.device(device_name if device_name.startswith("cuda") and torch.cuda.is_available() else "cpu")
        self.detector = _Detection(repo_root)
        self.cropper = _CropImage()
        self.models = self._load_models()

    def _load_models(self) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = []
        model_dir = self.repo_root / "resources" / "anti_spoof_models"
        for model_path in sorted(model_dir.glob("*.pth")):
            model_name = model_path.name
            h_input, w_input, model_type, scale = _parse_model_name(model_name)
            kernel_size = _get_kernel(h_input, w_input)
            model_factory = _MODEL_MAPPING[model_type]
            model = model_factory(conv6_kernel=kernel_size).to(self.device)
            state_dict = torch.load(str(model_path), map_location=self.device)
            first_key = next(iter(state_dict))
            if first_key.startswith("module."):
                cleaned_state_dict = {key[7:]: value for key, value in state_dict.items()}
                state_dict = cleaned_state_dict
            model.load_state_dict(state_dict)
            model.eval()
            models.append(
                {
                    "path": model_path,
                    "scale": scale,
                    "out_w": w_input,
                    "out_h": h_input,
                    "model": model,
                }
            )
        if not models:
            raise RuntimeError("no Silent-Face models were found")
        return models

    def analyze_frame(self, frame: np.ndarray, *, timestamp_ms: int | None = None) -> dict[str, Any]:
        detection = self.detector.detect(frame)
        bbox = detection.get("bbox")
        if not bbox:
            return {
                "timestamp_ms": timestamp_ms,
                "bbox": None,
                "face_count": int(detection.get("face_count") or 0),
                "detection_confidence": _bounded_score(float(detection.get("confidence") or 0.0) * 100),
            }
        prediction_sum: np.ndarray | None = None
        preview_crop: np.ndarray | None = None
        for entry in self.models:
            should_crop = entry["scale"] is not None
            patch = self.cropper.crop(
                org_img=frame,
                bbox=bbox,
                scale=float(entry["scale"] or 1.0),
                out_w=int(entry["out_w"]),
                out_h=int(entry["out_h"]),
                crop=should_crop,
            )
            if preview_crop is None:
                preview_crop = cv2.resize(patch, (80, 80))
            tensor = _frame_to_tensor(patch).to(self.device)
            with torch.no_grad():
                prediction = torch_functional.softmax(entry["model"](tensor), dim=1).cpu().numpy()[0]
            prediction_sum = prediction if prediction_sum is None else prediction_sum + prediction
        assert prediction_sum is not None
        averaged = prediction_sum / max(len(self.models), 1)
        real_prob = float(averaged[1]) if averaged.shape[0] > 1 else 0.0
        fake_prob = 1.0 - real_prob if averaged.shape[0] == 2 else float(max(averaged[0], averaged[2]))
        return {
            "timestamp_ms": timestamp_ms,
            "bbox": bbox,
            "face_count": int(detection.get("face_count") or 0),
            "detection_confidence": _bounded_score(float(detection.get("confidence") or 0.0) * 100),
            "real_score": _bounded_score(real_prob * 100),
            "fake_score": _bounded_score(fake_prob * 100),
            "label": int(np.argmax(averaged)),
            "crop": preview_crop,
            "frame_shape": frame.shape[:2],
            "center": (
                float(bbox[0] + (bbox[2] / 2.0)),
                float(bbox[1] + (bbox[3] / 2.0)),
            ),
        }


def _silent_face_engine() -> _SilentFaceEngine:
    global _ENGINE_CACHE
    repo_root = _ensure_silent_face_assets()
    cache_key = (str(repo_root), _torch_device_name())
    with _ENGINE_LOCK:
        if _ENGINE_CACHE and _ENGINE_CACHE[0] == cache_key:
            return _ENGINE_CACHE[1]
        engine = _SilentFaceEngine(repo_root, cache_key[1])
        _ENGINE_CACHE = (cache_key, engine)
        return engine


class _OpenCvFaceMatchEngine:
    def __init__(self, model_root: Path):
        detector_model = model_root / "face_detection_yunet_2023mar.onnx"
        recognizer_model = model_root / "face_recognition_sface_2021dec.onnx"
        if not detector_model.exists():
            raise RuntimeError(f"face detector model is missing: {detector_model}")
        if not recognizer_model.exists():
            raise RuntimeError(f"face recognizer model is missing: {recognizer_model}")
        self.detector = cv2.FaceDetectorYN_create(str(detector_model), "", (320, 320), 0.75, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF_create(str(recognizer_model), "")

    def _detect_faces(self, image: np.ndarray) -> list[np.ndarray]:
        height, width = image.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(image)
        if faces is None:
            return []
        if faces.ndim == 1:
            faces = faces.reshape(1, -1)
        return [np.asarray(row, dtype=np.float32).copy() for row in faces]

    def extract_face_embedding(self, image: np.ndarray) -> dict[str, Any]:
        faces = self._detect_faces(image)
        if not faces:
            return {"face_count": 0, "embedding": None, "detection_score": 0}
        best_face = max(faces, key=lambda row: float(row[-1]) if len(row) else 0.0)
        try:
            aligned = self.recognizer.alignCrop(image, best_face)
            embedding = np.asarray(self.recognizer.feature(aligned)).reshape(-1).astype(np.float32)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"face recognizer failed to extract embedding: {exc}") from exc
        return {
            "face_count": len(faces),
            "embedding": embedding,
            "detection_score": _bounded_score(float(best_face[-1]) * 100.0),
        }

    def match(self, feature_a: np.ndarray, feature_b: np.ndarray) -> float:
        return float(
            self.recognizer.match(
                np.asarray(feature_a, dtype=np.float32).reshape(1, -1),
                np.asarray(feature_b, dtype=np.float32).reshape(1, -1),
                cv2.FaceRecognizerSF_FR_COSINE,
            )
        )


class _LightweightFaceMatchEngine:
    def __init__(self, detector: _Detection):
        self.detector = detector

    def extract_face_embedding(self, image: np.ndarray) -> dict[str, Any]:
        detection = self.detector.detect(image)
        face_count = int(detection.get("face_count") or 0)
        bbox = detection.get("bbox")
        if not bbox or face_count <= 0:
            return {"face_count": 0, "embedding": None, "detection_score": 0}
        if face_count != 1:
            return {
                "face_count": face_count,
                "embedding": None,
                "detection_score": _bounded_score(float(detection.get("confidence") or 0.0) * 100.0),
            }
        crop = _extract_deepfake_face_crop(image, bbox)
        if crop is None:
            return {"face_count": 1, "embedding": None, "detection_score": 0}
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        resized = cv2.resize(gray, (48, 48), interpolation=cv2.INTER_AREA)
        feature = resized.astype(np.float32).reshape(-1)
        feature -= float(np.mean(feature))
        norm = float(np.linalg.norm(feature))
        if norm > 1e-6:
            feature /= norm
        return {
            "face_count": 1,
            "embedding": feature.astype(np.float32),
            "detection_score": _bounded_score(float(detection.get("confidence") or 0.0) * 100.0),
        }

    def match(self, feature_a: np.ndarray, feature_b: np.ndarray) -> float:
        vector_a = np.asarray(feature_a, dtype=np.float32).reshape(-1)
        vector_b = np.asarray(feature_b, dtype=np.float32).reshape(-1)
        norm_a = float(np.linalg.norm(vector_a))
        norm_b = float(np.linalg.norm(vector_b))
        if norm_a <= 1e-6 or norm_b <= 1e-6:
            return 0.0
        return float(np.dot(vector_a, vector_b) / (norm_a * norm_b))


def _face_match_engine() -> _OpenCvFaceMatchEngine:
    global _FACE_MATCH_CACHE
    model_root = _face_match_root()
    detector_model = model_root / "face_detection_yunet_2023mar.onnx"
    recognizer_model = model_root / "face_recognition_sface_2021dec.onnx"
    use_lightweight_fallback = not detector_model.exists() or not recognizer_model.exists()
    cache_key = f"{model_root}|{'lightweight' if use_lightweight_fallback else 'opencv'}"
    with _FACE_MATCH_LOCK:
        if _FACE_MATCH_CACHE and _FACE_MATCH_CACHE[0] == cache_key:
            return _FACE_MATCH_CACHE[1]
        if use_lightweight_fallback:
            engine = _LightweightFaceMatchEngine(_silent_face_engine().detector)
        else:
            engine = _OpenCvFaceMatchEngine(model_root)
        _FACE_MATCH_CACHE = (cache_key, engine)
        return engine


def _load_image_from_source(source: str) -> np.ndarray | None:
    raw = str(source or "").strip()
    if not raw:
        return None
    try:
        if raw.startswith(("http://", "https://")):
            with urllib.request.urlopen(raw, timeout=120) as response:
                payload = response.read()
        else:
            path = Path(raw).expanduser().resolve()
            if not path.exists():
                return None
            payload = path.read_bytes()
    except Exception:  # noqa: BLE001
        return None
    if not payload:
        return None
    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.size <= 0:
        return None
    return image


def _fallback_face_match_score(*, face_presence_score: int, detected_face_count_max: int) -> int:
    if detected_face_count_max > 1:
        return 25
    if face_presence_score >= 85:
        return 48
    if face_presence_score >= 65:
        return 42
    return 35


def _face_similarity_to_score(similarity: float, *, matched_frame_count: int, analyzed_frame_count: int) -> int:
    if similarity <= 0.20:
        base_score = 20.0
    elif similarity < 0.363:
        base_score = 20.0 + ((similarity - 0.20) / 0.163) * 50.0
    elif similarity < 0.55:
        base_score = 70.0 + ((similarity - 0.363) / 0.187) * 25.0
    else:
        base_score = 95.0 + min((similarity - 0.55) / 0.10, 1.0) * 5.0
    stability_ratio = min(matched_frame_count, 3) / max(min(analyzed_frame_count, 3), 1)
    stability_bonus = stability_ratio * 5.0
    return _bounded_score(base_score + stability_bonus)


def _same_person_unavailable_result(
    *,
    face_presence_score: int,
    detected_face_count_max: int,
    reference_face_source_count: int,
    reason: str,
    error_message: str | None = None,
) -> dict[str, Any]:
    out = {
        "analysis_status": "unavailable",
        "face_match_score": _fallback_face_match_score(
            face_presence_score=face_presence_score,
            detected_face_count_max=detected_face_count_max,
        ),
        "same_person_score": _fallback_face_match_score(
            face_presence_score=face_presence_score,
            detected_face_count_max=detected_face_count_max,
        ),
        "reference_face_source_count": int(reference_face_source_count),
        "reference_face_count": 0,
        "analyzed_frame_count": 0,
        "matched_frame_count": 0,
        "best_similarity": None,
        "risk_flags": [reason],
    }
    if error_message:
        out["error_message"] = error_message
    return out


def _analyze_same_person_faces(
    video_path: Path,
    *,
    reference_image_sources: list[str] | None,
    face_presence_score: int,
    detected_face_count_max: int,
) -> dict[str, Any]:
    normalized_sources = [str(item or "").strip() for item in list(reference_image_sources or []) if str(item or "").strip()]
    if not normalized_sources:
        return _same_person_unavailable_result(
            face_presence_score=face_presence_score,
            detected_face_count_max=detected_face_count_max,
            reference_face_source_count=0,
            reason="reference_face_unavailable",
        )
    try:
        engine = _face_match_engine()
    except Exception as exc:  # noqa: BLE001
        return _same_person_unavailable_result(
            face_presence_score=face_presence_score,
            detected_face_count_max=detected_face_count_max,
            reference_face_source_count=len(normalized_sources),
            reason="face_match_analysis_unavailable",
            error_message=str(exc) or type(exc).__name__,
        )

    reference_embeddings: list[np.ndarray] = []
    reference_risk_flags: list[str] = []
    for source in normalized_sources[: max(_reference_face_limit() * 2, _reference_face_limit())]:
        image = _load_image_from_source(source)
        if image is None:
            continue
        extracted = engine.extract_face_embedding(image)
        face_count = int(extracted.get("face_count") or 0)
        if face_count != 1:
            if face_count > 1 and "multiple_reference_faces" not in reference_risk_flags:
                reference_risk_flags.append("multiple_reference_faces")
            continue
        embedding = extracted.get("embedding")
        if embedding is None:
            continue
        reference_embeddings.append(np.asarray(embedding, dtype=np.float32))
        if len(reference_embeddings) >= _reference_face_limit():
            break
    if not reference_embeddings:
        return _same_person_unavailable_result(
            face_presence_score=face_presence_score,
            detected_face_count_max=detected_face_count_max,
            reference_face_source_count=len(normalized_sources),
            reason="reference_face_unavailable",
        ) | {"risk_flags": list(dict.fromkeys(reference_risk_flags + ["reference_face_unavailable"]))}

    sampled_video = _sample_video_frames(video_path)
    frame_scores: list[float] = []
    analyzed_frame_count = 0
    matched_frame_count = 0
    video_risk_flags: list[str] = []
    for frame_item in list(sampled_video.get("frames") or []):
        extracted = engine.extract_face_embedding(frame_item["frame"])
        face_count = int(extracted.get("face_count") or 0)
        if face_count == 0:
            continue
        if face_count > 1:
            if "multiple_faces" not in video_risk_flags:
                video_risk_flags.append("multiple_faces")
            continue
        embedding = extracted.get("embedding")
        if embedding is None:
            continue
        analyzed_frame_count += 1
        best_similarity = max(engine.match(np.asarray(embedding, dtype=np.float32), item) for item in reference_embeddings)
        frame_scores.append(float(best_similarity))
        if best_similarity >= 0.363:
            matched_frame_count += 1
    if not frame_scores:
        return _same_person_unavailable_result(
            face_presence_score=face_presence_score,
            detected_face_count_max=detected_face_count_max,
            reference_face_source_count=len(normalized_sources),
            reason="face_match_analysis_unavailable",
        ) | {"risk_flags": list(dict.fromkeys(reference_risk_flags + video_risk_flags + ["face_match_analysis_unavailable"]))}

    sorted_scores = sorted(frame_scores, reverse=True)
    top_scores = sorted_scores[: min(3, len(sorted_scores))]
    aggregate_similarity = float(sum(top_scores) / len(top_scores))
    best_similarity = float(sorted_scores[0])
    face_match_score = _face_similarity_to_score(
        aggregate_similarity,
        matched_frame_count=matched_frame_count,
        analyzed_frame_count=analyzed_frame_count,
    )
    risk_flags = list(dict.fromkeys(reference_risk_flags + video_risk_flags))
    if matched_frame_count <= 0 and "face_mismatch" not in risk_flags:
        risk_flags.append("face_mismatch")
    elif matched_frame_count == 1 and analyzed_frame_count >= 2 and "face_match_low_confidence" not in risk_flags:
        risk_flags.append("face_match_low_confidence")
    return {
        "analysis_status": "ok",
        "face_match_score": face_match_score,
        "same_person_score": face_match_score,
        "reference_face_source_count": len(normalized_sources),
        "reference_face_count": len(reference_embeddings),
        "analyzed_frame_count": analyzed_frame_count,
        "matched_frame_count": matched_frame_count,
        "best_similarity": round(best_similarity, 4),
        "average_similarity": round(aggregate_similarity, 4),
        "risk_flags": risk_flags,
    }


def _safe_analyze_same_person_faces(
    video_path: Path,
    *,
    reference_image_sources: list[str] | None,
    face_presence_score: int,
    detected_face_count_max: int,
) -> dict[str, Any]:
    try:
        return _analyze_same_person_faces(
            video_path,
            reference_image_sources=reference_image_sources,
            face_presence_score=face_presence_score,
            detected_face_count_max=detected_face_count_max,
        )
    except Exception as exc:  # noqa: BLE001
        return _same_person_unavailable_result(
            face_presence_score=face_presence_score,
            detected_face_count_max=detected_face_count_max,
            reference_face_source_count=len(list(reference_image_sources or [])),
            reason="face_match_analysis_unavailable",
            error_message=str(exc) or type(exc).__name__,
        )


def _compute_motion_score(frame_results: list[dict[str, Any]]) -> int:
    valid_results = [item for item in frame_results if item.get("crop") is not None and item.get("bbox")]
    if len(valid_results) < 2:
        return 0 if not valid_results else 25
    pixel_diffs: list[float] = []
    center_steps: list[float] = []
    size_steps: list[float] = []
    previous_crop: np.ndarray | None = None
    previous_center: tuple[float, float] | None = None
    previous_area: float | None = None
    for item in valid_results:
        crop_gray = cv2.cvtColor(item["crop"], cv2.COLOR_BGR2GRAY)
        crop_gray = cv2.resize(crop_gray, (64, 64))
        center = item["center"]
        bbox = item["bbox"]
        area = float(bbox[2] * bbox[3])
        frame_height, frame_width = item["frame_shape"]
        frame_scale = max(frame_height, frame_width, 1)
        if previous_crop is not None:
            pixel_diff = float(np.mean(cv2.absdiff(crop_gray, previous_crop))) / 255.0 * 100.0
            center_step = float(np.linalg.norm(np.array(center) - np.array(previous_center))) / frame_scale * 100.0
            area_step = abs(area - float(previous_area or area)) / max(area, float(previous_area or area), 1.0) * 100.0
            pixel_diffs.append(pixel_diff)
            center_steps.append(center_step)
            size_steps.append(area_step)
        previous_crop = crop_gray
        previous_center = center
        previous_area = area
    pixel_score = min(100.0, (sum(pixel_diffs) / len(pixel_diffs)) * 2.4) if pixel_diffs else 0.0
    center_score = min(100.0, (sum(center_steps) / len(center_steps)) * 5.0) if center_steps else 0.0
    size_score = min(100.0, (sum(size_steps) / len(size_steps)) * 1.6) if size_steps else 0.0
    return _bounded_score((pixel_score * 0.55) + (center_score * 0.25) + (size_score * 0.20))


def _analyze_silent_face_video(video_path: Path) -> dict[str, Any]:
    engine = _silent_face_engine()
    sampled_video = _sample_video_frames(video_path)
    frame_results = [
        engine.analyze_frame(item["frame"], timestamp_ms=item.get("timestamp_ms"))
        for item in list(sampled_video.get("frames") or [])
    ]
    valid_results = [item for item in frame_results if item.get("bbox")]
    if not valid_results:
        raise ValueError("Silent-Face could not detect a face in the uploaded video")
    real_scores = [int(item["real_score"]) for item in valid_results]
    face_presence_score = _bounded_score((len(valid_results) / max(len(frame_results), 1)) * 100)
    motion_score = _compute_motion_score(valid_results)
    base_real_score = float(sum(real_scores) / len(real_scores))
    liveness_score = _bounded_score((base_real_score * 0.82) + (face_presence_score * 0.18))
    spoofing_risk_score = _bounded_score(100 - base_real_score)
    static_risk = _bounded_score(100 - motion_score)
    replay_attack_score = _bounded_score((spoofing_risk_score * 0.70) + (static_risk * 0.30))
    screen_risk_score = _bounded_score((spoofing_risk_score * 0.85) + (static_risk * 0.15))
    risk_flags: list[str] = []
    if face_presence_score < 70:
        risk_flags.append("face_not_stable")
    if motion_score < 30:
        risk_flags.append("low_motion_evidence")
    if spoofing_risk_score >= 60:
        risk_flags.append("anti_spoof_uncertain")
    if replay_attack_score >= 60:
        risk_flags.append("replay_risk_medium")
    return {
        "liveness_score": liveness_score,
        "spoofing_risk_score": spoofing_risk_score,
        "replay_attack_score": replay_attack_score,
        "screen_risk_score": screen_risk_score,
        "motion_score": motion_score,
        "face_presence_score": face_presence_score,
        "sampled_frame_count": len(frame_results),
        "valid_face_frame_count": len(valid_results),
        "detected_face_count_max": max((int(item.get("face_count") or 0) for item in frame_results), default=0),
        "average_detection_confidence": _bounded_score(
            sum(int(item.get("detection_confidence") or 0) for item in valid_results) / len(valid_results)
        ),
        "risk_flags": risk_flags,
    }


def _extract_audio_track_to_wav(video_path: Path) -> Path | None:
    with av.open(str(video_path)) as container:
        if not any(stream.type == "audio" for stream in container.streams):
            return None
        resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=16000)
        with tempfile.NamedTemporaryFile(prefix="her-live-audio-", suffix=".wav", delete=False) as handle:
            wav_path = Path(handle.name)
        written_sample_count = 0
        try:
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                for frame in container.decode(audio=0):
                    for output in resampler.resample(frame):
                        pcm = output.to_ndarray()
                        if pcm.size <= 0:
                            continue
                        mono_pcm = np.ascontiguousarray(pcm).reshape(-1).astype("<i2", copy=False)
                        written_sample_count += int(mono_pcm.size)
                        wav_file.writeframes(mono_pcm.tobytes())
                for output in resampler.resample(None):
                    pcm = output.to_ndarray()
                    if pcm.size <= 0:
                        continue
                    mono_pcm = np.ascontiguousarray(pcm).reshape(-1).astype("<i2", copy=False)
                    written_sample_count += int(mono_pcm.size)
                    wav_file.writeframes(mono_pcm.tobytes())
        except Exception:  # noqa: BLE001
            wav_path.unlink(missing_ok=True)
            raise
        if written_sample_count <= 0:
            wav_path.unlink(missing_ok=True)
            return None
        return wav_path


def _transcribe_audio_with_whisper_worker(audio_path: Path, *, language: str | None) -> dict[str, Any]:
    worker_env = os.environ.copy()
    if language:
        worker_env["HER_VERIFICATION_WHISPER_LANGUAGE"] = language
    worker_env.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    system_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-m", "chat_system.live_video_whisper_worker", str(audio_path)],
        cwd=str(system_root),
        env=worker_env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise RuntimeError(f"faster-whisper worker failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(f"faster-whisper worker returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("faster-whisper worker returned a non-object payload")
    return payload


def _transcribe_video_audio(video_path: Path, *, media_info: dict[str, Any]) -> dict[str, Any]:
    if not bool(media_info.get("has_audio_track")):
        return {
            "provider": "faster_whisper",
            "transcript_text": None,
            "transcript_segments": [],
            "transcript_confidence": 0,
            "audio_duration_ms": int(media_info.get("duration_ms") or 0),
        }
    language = str(os.environ.get("HER_VERIFICATION_WHISPER_LANGUAGE") or "").strip() or None
    extracted_audio_path = _extract_audio_track_to_wav(video_path)
    if extracted_audio_path is None:
        return {
            "provider": "faster_whisper",
            "model_name": _whisper_model_name(),
            "transcript_text": None,
            "transcript_segments": [],
            "transcript_confidence": 0,
            "audio_duration_ms": int(media_info.get("duration_ms") or 0),
        }
    try:
        result = _transcribe_audio_with_whisper_worker(extracted_audio_path, language=language)
        result.update(
            _safe_compute_audio_video_sync_result(
                video_path,
                audio_path=extracted_audio_path,
                speech_result=result,
                media_info=media_info,
            )
        )
    finally:
        extracted_audio_path.unlink(missing_ok=True)
    if result.get("audio_duration_ms") is None:
        result["audio_duration_ms"] = int(media_info.get("duration_ms") or 0)
    return result


def _speech_analysis_unavailable_result(media_info: dict[str, Any], exc: Exception) -> dict[str, Any]:
    model_source, _ = _whisper_model_source()
    return {
        "provider": "faster_whisper",
        "model_name": model_source,
        "transcript_text": None,
        "transcript_segments": [],
        "transcript_confidence": 0,
        "audio_duration_ms": int(media_info.get("duration_ms") or 0),
        "analysis_status": "unavailable",
        "error_type": type(exc).__name__,
        "error_message": str(exc) or type(exc).__name__,
    }


def _safe_transcribe_video_audio(video_path: Path, *, media_info: dict[str, Any]) -> dict[str, Any]:
    # Speech is supplemental evidence. If Whisper bootstrap/transcribe fails,
    # keep the anti-spoof result and downgrade only the speech branch.
    try:
        return _transcribe_video_audio(video_path, media_info=media_info)
    except Exception as exc:  # noqa: BLE001
        return _speech_analysis_unavailable_result(media_info, exc)


def analyze_local_live_video(
    video_path: str | Path,
    *,
    spoken_code: str | None = None,
    face_match_score_hint: int | None = None,
    reference_image_sources: list[str] | None = None,
) -> dict[str, Any]:
    resolved_path = Path(video_path).expanduser().resolve()
    if not resolved_path.exists():
        raise ValueError("uploaded video file does not exist")
    media_info = _inspect_media_file(resolved_path)
    anti_spoof = _analyze_silent_face_video(resolved_path)
    deepfake_result = _safe_analyze_deepfake_video(resolved_path)
    photo_edit_result = _safe_analyze_photo_edit_risk(
        resolved_path,
        reference_image_sources=reference_image_sources,
    )
    speech_result = _safe_transcribe_video_audio(resolved_path, media_info=media_info) if spoken_code else {}
    face_presence_score = int(anti_spoof.get("face_presence_score") or 0)
    detected_face_count_max = int(anti_spoof.get("detected_face_count_max") or 0)
    same_person_result = _safe_analyze_same_person_faces(
        resolved_path,
        reference_image_sources=reference_image_sources,
        face_presence_score=face_presence_score,
        detected_face_count_max=detected_face_count_max,
    )
    face_match_score = int(same_person_result.get("face_match_score") or 0)
    if face_match_score_hint is not None:
        try:
            hinted_score = _bounded_score(face_match_score_hint)
        except (TypeError, ValueError):
            hinted_score = face_match_score
        face_match_score = max(face_match_score, hinted_score)
    same_person_score = int(same_person_result.get("same_person_score") or face_match_score)
    risk_flags = list(anti_spoof.get("risk_flags") or [])
    for flag in list(same_person_result.get("risk_flags") or []):
        if flag not in risk_flags:
            risk_flags.append(flag)
    for flag in list(deepfake_result.get("risk_flags") or []):
        if flag not in risk_flags:
            risk_flags.append(flag)
    for flag in list(photo_edit_result.get("risk_flags") or []):
        if flag not in risk_flags:
            risk_flags.append(flag)
    result = {
        "provider": LOCAL_OSS_PROVIDER,
        "provider_version": LOCAL_OSS_PROVIDER_VERSION,
        "liveness_score": int(anti_spoof.get("liveness_score") or 0),
        "face_match_score": face_match_score,
        "same_person_score": same_person_score,
        "replay_attack_score": int(anti_spoof.get("replay_attack_score") or 0),
        "screen_risk_score": int(anti_spoof.get("screen_risk_score") or 0),
        "spoofing_risk_score": int(anti_spoof.get("spoofing_risk_score") or 0),
        "deepfake_risk_score": int(deepfake_result.get("deepfake_risk_score") or 0),
        "deepfake_analysis_status": deepfake_result.get("analysis_status"),
        "deepfake_temporal_score": int(deepfake_result.get("deepfake_temporal_score") or 0),
        "deepfake_artifact_score": int(deepfake_result.get("deepfake_artifact_score") or 0),
        "deepfake_sampled_frame_count": int(deepfake_result.get("deepfake_sampled_frame_count") or 0),
        "deepfake_face_frame_count": int(deepfake_result.get("deepfake_face_frame_count") or 0),
        "photo_edit_risk_score": int(photo_edit_result.get("photo_edit_risk_score") or 0),
        "photo_edit_analysis_status": photo_edit_result.get("analysis_status"),
        "skin_smoothing_risk_score": int(photo_edit_result.get("skin_smoothing_risk_score") or 0),
        "beauty_filter_risk_score": int(photo_edit_result.get("beauty_filter_risk_score") or 0),
        "face_shape_delta_score": int(photo_edit_result.get("face_shape_delta_score") or 0),
        "photo_edit_reference_face_count": int(photo_edit_result.get("photo_edit_reference_face_count") or 0),
        "photo_edit_live_face_frame_count": int(photo_edit_result.get("photo_edit_live_face_frame_count") or 0),
        "photo_edit_reference_source_count": int(photo_edit_result.get("photo_edit_reference_source_count") or 0),
        "photo_edit_edited_reference_count": int(photo_edit_result.get("photo_edit_edited_reference_count") or 0),
        "motion_score": int(anti_spoof.get("motion_score") or 0),
        "face_presence_score": face_presence_score,
        "sampled_frame_count": int(anti_spoof.get("sampled_frame_count") or 0),
        "valid_face_frame_count": int(anti_spoof.get("valid_face_frame_count") or 0),
        "detected_face_count_max": detected_face_count_max,
        "average_detection_confidence": int(anti_spoof.get("average_detection_confidence") or 0),
        "media_duration_ms": media_info.get("duration_ms"),
        "has_audio_track": bool(media_info.get("has_audio_track")),
        "reference_face_source_count": int(same_person_result.get("reference_face_source_count") or 0),
        "reference_face_count": int(same_person_result.get("reference_face_count") or 0),
        "matched_face_frame_count": int(same_person_result.get("matched_frame_count") or 0),
        "best_face_similarity": same_person_result.get("best_similarity"),
        "face_match_analysis_status": same_person_result.get("analysis_status"),
        "risk_flags": risk_flags,
    }
    if speech_result:
        result["speech_challenge_result"] = speech_result
        if speech_result.get("analysis_status") == "unavailable":
            result["risk_flags"].append("speech_analysis_unavailable")
    return result
