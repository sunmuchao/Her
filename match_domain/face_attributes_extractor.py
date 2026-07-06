"""脸部细节属性提取器（基于dlib人脸关键点检测）"""

from __future__ import annotations

import cv2
import dlib
import json
import logging
import numpy as np
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

# dlib模型文件路径
MODEL_DIR = Path.home() / ".dlib" / "models"
DEFAULT_PREDICTOR_PATH = MODEL_DIR / "shape_predictor_68_face_landmarks.dat"

# 全局检测器和预测器（延迟加载）
_detector = None
_predictor = None


def _load_dlib_models(predictor_path: str | Path | None = None):
    """
    加载dlib模型（人脸检测器和关键点预测器）
    """
    global _detector, _predictor

    if _detector is None:
        _detector = dlib.get_frontal_face_detector()
        _logger.info("✅ dlib人脸检测器已加载")

    if _predictor is None:
        model_path = Path(predictor_path or DEFAULT_PREDICTOR_PATH)

        if not model_path.exists():
            _logger.error(f"❌ 模型文件不存在: {model_path}")
            _logger.error(f"   请运行: python scripts/download_dlib_model.py")
            return None, None

        _predictor = dlib.shape_predictor(str(model_path))
        _logger.info(f"✅ dlib关键点预测器已加载: {model_path}")

    return _detector, _predictor


def extract_face_attributes(photo_url: str) -> dict[str, Any]:
    """
    从照片中提取脸部细节属性（基于dlib 68个关键点）

    Args:
        photo_url: 照片URL或本地路径

    Returns:
        dict: 包含眼睛大小、鼻子高度、脸型等属性
    """
    detector, predictor = _load_dlib_models()

    if detector is None or predictor is None:
        return {
            "error": "dlib模型未加载",
            "success": False
        }

    try:
        # 读取照片
        image = cv2.imread(photo_url)
        if image is None:
            return {
                "error": "无法加载照片",
                "success": False
            }

        # 检测人脸
        faces = detector(image, 1)
        if len(faces) == 0:
            return {
                "error": "未检测到人脸",
                "success": False
            }

        # 提取第一个检测到的人脸
        face = faces[0]

        # 提取68个关键点
        landmarks = predictor(image, face)

        # 转换为坐标列表
        points = []
        for i in range(68):
            x = landmarks.part(i).x
            y = landmarks.part(i).y
            points.append((x, y))

        # 计算脸部细节属性
        attributes = {
            # 眼睛相关
            "eye_size_score": _compute_eye_size(points),
            "eye_shape_type": _classify_eye_shape(points),
            "eye_distance_score": _compute_eye_distance(points),

            # 鼻子相关
            "nose_height_score": _compute_nose_height(points),
            "nose_width_score": _compute_nose_width(points),
            "nose_shape_type": _classify_nose_shape(points),

            # 嘴唇相关
            "lip_thickness_score": _compute_lip_thickness(points),
            "lip_width_score": _compute_lip_width(points),
            "lip_shape_type": _classify_lip_shape(points),

            # 脸型相关
            "face_shape_type": _classify_face_shape(points),
            "jawline_definition_score": _compute_jawline_definition(points),

            # 其他
            "forehead_height_score": _compute_forehead_height(points),
            "chin_prominence_score": _compute_chin_prominence(points),
            "cheekbone_prominence_score": _compute_cheekbone_prominence(points),
        }

        _logger.info(f"✅ 脸部细节提取完成: face_shape={attributes['face_shape_type']}, eye_size={attributes['eye_size_score']}")

        return {
            "attributes": attributes,
            "face_landmarks": points,
            "face_landmarks_json": json.dumps(points),
            "face_attributes_model": "dlib-68-landmarks-v1",
            "success": True
        }

    except Exception as e:
        _logger.error(f"脸部细节提取失败: {e}")
        return {
            "error": str(e),
            "success": False
        }


def _compute_eye_size(points: list[tuple[int, int]]) -> float:
    """计算眼睛大小评分（0-100）"""
    # 眼睛关键点：36-41（左眼），42-47（右眼）
    # 眼睛宽度：外角到内角的距离
    left_eye_width = points[39][0] - points[36][0]
    right_eye_width = points[45][0] - points[42][0]

    # 眼睛高度：上眼皮到下眼皮的垂直距离
    left_eye_height = (abs(points[37][1] - points[41][1]) + abs(points[38][1] - points[40][1])) / 2
    right_eye_height = (abs(points[43][1] - points[47][1]) + abs(points[44][1] - points[46][1])) / 2

    # 眼睛大小 = 宽度 + 高度的平均值
    eye_size = (left_eye_width + right_eye_width + left_eye_height + right_eye_height) / 4

    # 标准化为0-100评分（基于典型人脸尺寸）
    score = min(100.0, max(0.0, eye_size * 1.5))

    return round(score, 2)


def _classify_eye_shape(points: list[tuple[int, int]]) -> str:
    """分类眼型"""
    # 左眼宽高比
    left_eye_width = points[39][0] - points[36][0]
    left_eye_height = abs(points[37][1] - points[41][1])

    ratio = left_eye_width / left_eye_height if left_eye_height > 0 else 1.0

    if ratio > 3.5:
        return "almond"  # 杏眼（长而窄）
    elif ratio > 2.8:
        return "round"   # 圆眼（宽高接近）
    else:
        return "hooded"  # 眼皮较厚（高度较大）


def _compute_eye_distance(points: list[tuple[int, int]]) -> float:
    """计算眼距评分（0-100）"""
    # 眼距：左右眼内角的距离
    eye_distance = points[42][0] - points[39][0]

    # 标准化为0-100评分
    score = min(100.0, max(0.0, eye_distance * 0.8))

    return round(score, 2)


def _compute_nose_height(points: list[tuple[int, int]]) -> float:
    """计算鼻梁高度评分（0-100）"""
    # 鼻梁关键点：27（鼻梁顶部）到30（鼻尖）
    nose_height = abs(points[30][1] - points[27][1])

    # 标准化为0-100评分
    score = min(100.0, max(0.0, nose_height * 1.2))

    return round(score, 2)


def _compute_nose_width(points: list[tuple[int, int]]) -> float:
    """计算鼻子宽度评分（0-100）"""
    # 鼻翼关键点：31（左鼻翼）到35（右鼻翼）
    nose_width = points[35][0] - points[31][0]

    # 标准化为0-100评分
    score = min(100.0, max(0.0, nose_width * 1.0))

    return round(score, 2)


def _classify_nose_shape(points: list[tuple[int, int]]) -> str:
    """分类鼻型"""
    nose_height = abs(points[30][1] - points[27][1])
    nose_width = points[35][0] - points[31][0]

    ratio = nose_height / nose_width if nose_width > 0 else 1.0

    if ratio > 2.0:
        return "high"    # 高鼻梁
    elif ratio > 1.5:
        return "medium"  # 中等鼻梁
    else:
        return "flat"    # 扁鼻梁


def _compute_lip_thickness(points: list[tuple[int, int]]) -> float:
    """计算嘴唇厚度评分（0-100）"""
    # 嘴唇关键点：48-59（外唇），60-67（内唇）
    # 上嘴唇厚度
    upper_lip_thickness = abs(points[62][1] - points[51][1])
    # 下嘴唇厚度
    lower_lip_thickness = abs(points[66][1] - points[57][1])

    # 平均厚度
    lip_thickness = (upper_lip_thickness + lower_lip_thickness) / 2

    # 标准化为0-100评分
    score = min(100.0, max(0.0, lip_thickness * 3.0))

    return round(score, 2)


def _compute_lip_width(points: list[tuple[int, int]]) -> float:
    """计算嘴唇宽度评分（0-100）"""
    # 嘴角关键点：48（左嘴角）到54（右嘴角）
    lip_width = points[54][0] - points[48][0]

    # 标准化为0-100评分
    score = min(100.0, max(0.0, lip_width * 0.8))

    return round(score, 2)


def _classify_lip_shape(points: list[tuple[int, int]]) -> str:
    """分类嘴型"""
    lip_width = points[54][0] - points[48][0]
    lip_thickness = (abs(points[62][1] - points[51][1]) + abs(points[66][1] - points[57][1])) / 2

    ratio = lip_width / lip_thickness if lip_thickness > 0 else 1.0

    if ratio > 5.0:
        return "thin"    # 薄嘴唇
    elif ratio > 3.0:
        return "medium"  # 中等厚度
    else:
        return "full"    # 嘴唇丰满


def _classify_face_shape(points: list[tuple[int, int]]) -> str:
    """分类脸型"""
    # 脸型关键点：0-16（下巴轮廓）
    jaw_width = points[16][0] - points[0][0]

    # 脸高度：额头到下巴的距离
    forehead_y = min(points[17][1], points[18][1], points[19][1], points[20][1], points[21][1])
    chin_y = points[8][1]
    face_height = chin_y - forehead_y

    ratio = jaw_width / face_height if face_height > 0 else 1.0

    if ratio > 0.85:
        return "round"    # 圆脸（宽脸）
    elif ratio > 0.75:
        return "square"   # 方脸（宽下巴）
    elif ratio > 0.65:
        return "oval"     # 鹅蛋脸（标准比例）
    else:
        return "heart"    # 心形脸（窄下巴）


def _compute_jawline_definition(points: list[tuple[int, int]]) -> float:
    """计算下颌线清晰度评分（0-100）"""
    # 下颌线关键点：0-16（下巴轮廓）
    # 计算下巴轮廓的角度变化（越锐利越清晰）
    jaw_angles = []
    for i in range(1, 16):
        angle = _compute_angle(points[i-1], points[i], points[i+1] if i < 16 else points[8])
        jaw_angles.append(angle)

    # 平均角度变化（角度越大，下颌线越清晰）
    avg_angle_change = np.mean(jaw_angles) if jaw_angles else 0.0

    # 标准化为0-100评分
    score = min(100.0, max(0.0, avg_angle_change * 0.5))

    return round(score, 2)


def _compute_forehead_height(points: list[tuple[int, int]]) -> float:
    """计算额头高度评分（0-100）"""
    # 额头关键点：17-21（眉毛）
    forehead_top_y = min(points[17][1], points[18][1], points[19][1], points[20][1], points[21][1])
    forehead_bottom_y = max(points[17][1], points[18][1], points[19][1], points[20][1], points[21][1])

    forehead_height = forehead_bottom_y - forehead_top_y

    # 标准化为0-100评分
    score = min(100.0, max(0.0, forehead_height * 1.5))

    return round(score, 2)


def _compute_chin_prominence(points: list[tuple[int, int]]) -> float:
    """计算下巴突出度评分（0-100）"""
    # 下巴关键点：8（下巴中心）
    chin_y = points[8][1]

    # 下巴突出度 = 下巴到嘴的距离
    mouth_y = points[51][1]  # 上嘴唇中心
    chin_prominence = chin_y - mouth_y

    # 标准化为0-100评分
    score = min(100.0, max(0.0, chin_prominence * 1.2))

    return round(score, 2)


def _compute_cheekbone_prominence(points: list[tuple[int, int]]) -> float:
    """计算颧骨突出度评分（0-100）"""
    # 颧骨关键点：1-15（脸颊轮廓）
    # 计算脸颊宽度和脸宽的比例
    cheekbone_width = points[15][0] - points[1][0]
    face_width = points[16][0] - points[0][0]

    ratio = cheekbone_width / face_width if face_width > 0 else 0.0

    # 标准化为0-100评分
    score = min(100.0, max(0.0, ratio * 80.0))

    return round(score, 2)


def _compute_angle(p1: tuple[int, int], p2: tuple[int, int], p3: tuple[int, int]) -> float:
    """计算三个点形成的角度"""
    # 向量p2->p1和p2->p3
    v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
    v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])

    # 计算角度
    cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    angle = np.arccos(np.clip(cos_angle, -1.0, 1.0))

    return np.degrees(angle)


__all__ = [
    "extract_face_attributes",
]