"""Appearance search and recall services."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import warnings
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from profile_service import list_profile_photo_feature_rows

from .appearance_features import (
    LANDMARK_ATTRIBUTE_FIELDS,
    create_reference_face_search_job,
    load_candidate_photo_features,
    load_profile_face_attributes,
    load_profile_face_embeddings,
)

_logger = logging.getLogger(__name__)


FACE_VECTOR_TYPE = "face_embedding"
APPEARANCE_PROFILE_VECTOR_TYPE = "appearance_profile"


def _stable_embedding_from_text(text: str, *, dims: int = 1024, salt: str = "") -> list[float]:
    normalized = f"{salt}|{text}".encode("utf-8")
    vector: list[float] = []
    for index in range(max(8, dims)):
        digest = hashlib.sha256(normalized + f":{index}".encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 2001
        vector.append(round((bucket / 1000.0) - 1.0, 6))
    return vector


def _expand_embedding(base: Sequence[float] | None, *, dims: int = 1024, salt: str = "") -> list[float]:
    values = [float(item) for item in list(base or [])]
    if not values:
        return _stable_embedding_from_text("empty", dims=dims, salt=salt)
    expanded: list[float] = []
    while len(expanded) < dims:
        seed = f"{salt}|{len(expanded)}|{','.join(str(round(item, 6)) for item in values[:16])}"
        expanded.extend(_stable_embedding_from_text(seed, dims=min(64, dims - len(expanded)), salt=salt))
    return expanded[:dims]


def _cosine_similarity(left: Sequence[float] | None, right: Sequence[float] | None) -> float:
    lhs = [float(item) for item in list(left or [])]
    rhs = [float(item) for item in list(right or [])]
    if not lhs or not rhs or len(lhs) != len(rhs):
        return 0.0
    numerator = sum(a * b for a, b in zip(lhs, rhs))
    lhs_norm = math.sqrt(sum(item * item for item in lhs))
    rhs_norm = math.sqrt(sum(item * item for item in rhs))
    if lhs_norm <= 0 or rhs_norm <= 0:
        return 0.0
    return max(-1.0, min(1.0, numerator / (lhs_norm * rhs_norm)))


def _normalize_similarity(raw: float) -> float:
    return round(max(0.0, min(1.0, (raw + 1.0) / 2.0)), 4)


@dataclass(frozen=True)
class FaceSearchCandidate:
    profile_id: int
    similarity: float
    source: str
    reasons: list[str]


class AppearanceProfileEmbeddingExtractor:
    @staticmethod
    def extract(
        *,
        appearance_summary: str | None,
        appearance_tags: Sequence[str] | None = None,
        dims: int = 1024,
    ) -> list[float]:
        summary = str(appearance_summary or "").strip()
        tags = [str(item).strip() for item in list(appearance_tags or []) if str(item).strip()]
        raw = summary
        if tags:
            raw = f"{summary}|{'|'.join(tags)}"
        return _stable_embedding_from_text(raw or "appearance_profile", dims=dims, salt="appearance_profile")


class FaceVectorIndexBuilder:
    @staticmethod
    def build_profile_index(
        *,
        source_dsn: str | None,
        profile_id: int,
        vector_store: Any | None = None,
    ) -> dict[str, Any]:
        normalized_profile_id = int(profile_id or 0)
        if not source_dsn or normalized_profile_id <= 0:
            return {"saved": False, "error": "source_or_profile_missing"}
        rows = load_profile_face_embeddings(
            source_dsn=source_dsn,
            profile_ids=[normalized_profile_id],
            embedding_type="primary_face",
            limit=5,
        )
        if not rows:
            return {"saved": False, "error": "face_embedding_missing"}
        row = dict(rows[0])
        base_embedding = list(row.get("embedding_json") or [])
        expanded = _expand_embedding(base_embedding, dims=1024, salt=f"face_embedding:{normalized_profile_id}")
        close_store = False
        if vector_store is None:
            from .vector_store_lite import VectorStoreLite

            vector_store = VectorStoreLite()
            close_store = True
        try:
            result = vector_store.save_vector_with_version(
                user_id=normalized_profile_id,
                vector_type=FACE_VECTOR_TYPE,
                embedding=expanded,
                raw_text=f"profile_face:{normalized_profile_id}",
                conversation_id=f"face-index:{normalized_profile_id}",
            )
        finally:
            if close_store:
                vector_store.close()
        return {
            "saved": bool(result.get("success")),
            "profile_id": normalized_profile_id,
            "vector_type": FACE_VECTOR_TYPE,
            "version": result.get("version"),
        }


class AppearanceStyleIndexBuilder:
    @staticmethod
    def build_profile_index(
        *,
        source_dsn: str | None,
        profile_id: int,
        vector_store: Any | None = None,
    ) -> dict[str, Any]:
        normalized_profile_id = int(profile_id or 0)
        if not source_dsn or normalized_profile_id <= 0:
            return {"saved": False, "error": "source_or_profile_missing"}
        feature_row = load_candidate_photo_features(
            source_dsn=source_dsn,
            profile_ids=[normalized_profile_id],
        ).get(normalized_profile_id)
        if not feature_row:
            return {"saved": False, "error": "photo_feature_missing"}
        tags = [str(item.get("label") or "").strip() for item in list(feature_row.get("appearance_tags_json") or []) if str(item.get("label") or "").strip()]
        embedding = AppearanceProfileEmbeddingExtractor.extract(
            appearance_summary=str(feature_row.get("appearance_summary") or ""),
            appearance_tags=tags,
        )
        close_store = False
        if vector_store is None:
            from .vector_store_lite import VectorStoreLite

            vector_store = VectorStoreLite()
            close_store = True
        try:
            result = vector_store.save_vector_with_version(
                user_id=normalized_profile_id,
                vector_type=APPEARANCE_PROFILE_VECTOR_TYPE,
                embedding=embedding,
                raw_text=str(feature_row.get("appearance_summary") or ""),
                conversation_id=f"appearance-index:{normalized_profile_id}",
            )
        finally:
            if close_store:
                vector_store.close()
        return {
            "saved": bool(result.get("success")),
            "profile_id": normalized_profile_id,
            "vector_type": APPEARANCE_PROFILE_VECTOR_TYPE,
            "version": result.get("version"),
        }


class FaceSimilaritySearcher:
    @staticmethod
    def aggregate_candidate_scores(results: Sequence[Mapping[str, Any]]) -> list[FaceSearchCandidate]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for item in results:
            payload = dict(item)
            profile_id = int(payload.get("user_id") or payload.get("profile_id") or 0)
            if profile_id <= 0:
                continue
            grouped.setdefault(profile_id, []).append(payload)
        aggregated: list[FaceSearchCandidate] = []
        for profile_id, items in grouped.items():
            scores = sorted(
                [float(item.get("similarity") or item.get("score") or 0.0) for item in items],
                reverse=True,
            )
            similarity = scores[0]
            if len(scores) >= 2:
                similarity = round((scores[0] * 0.65) + (scores[1] * 0.35), 4)
            reasons = [str(items[0].get("raw_text") or "Face 向量命中").strip()]
            aggregated.append(
                FaceSearchCandidate(
                    profile_id=profile_id,
                    similarity=round(similarity, 4),
                    source=str(items[0].get("source") or "vector_store"),
                    reasons=reasons,
                )
            )
        aggregated.sort(key=lambda item: item.similarity, reverse=True)
        return aggregated

    @classmethod
    def search(
        cls,
        *,
        source_dsn: str | None,
        reference_embedding: Sequence[float],
        top_k: int = 20,
        similarity_threshold: float = 0.3,
        exclude_profile_ids: Iterable[int] | None = None,
        vector_store: Any | None = None,
    ) -> list[FaceSearchCandidate]:
        normalized_reference = _expand_embedding(reference_embedding, dims=1024, salt="face_search_query")
        close_store = False
        results: list[dict[str, Any]] = []
        if vector_store is None:
            try:
                from .vector_store_lite import VectorStoreLite

                vector_store = VectorStoreLite()
                close_store = True
            except Exception:
                vector_store = None
        if vector_store is not None:
            try:
                results = [
                    {
                        **dict(item),
                        "source": "vector_store",
                    }
                    for item in vector_store.search_similar_users(
                        user_vector=normalized_reference,
                        vector_type=FACE_VECTOR_TYPE,
                        top_k=top_k,
                        similarity_threshold=max(0.0, similarity_threshold),
                        exclude_user_ids=[int(item) for item in list(exclude_profile_ids or []) if int(item) > 0],
                    )
                ]
            finally:
                if close_store:
                    vector_store.close()
        if not results and source_dsn:
            rows = load_profile_face_embeddings(
                source_dsn=source_dsn,
                embedding_type="primary_face",
                limit=max(top_k * 4, 50),
            )
            excluded = {int(item) for item in list(exclude_profile_ids or []) if int(item) > 0}
            for row in rows:
                payload = dict(row)
                profile_id = int(payload.get("profile_id") or 0)
                if profile_id <= 0 or profile_id in excluded:
                    continue
                candidate_embedding = _expand_embedding(payload.get("embedding_json") or [], dims=1024, salt=f"face_candidate:{profile_id}")
                similarity = _normalize_similarity(_cosine_similarity(normalized_reference, candidate_embedding))
                if similarity < similarity_threshold:
                    continue
                results.append(
                    {
                        "profile_id": profile_id,
                        "similarity": similarity,
                        "raw_text": f"profile_face:{profile_id}",
                        "source": "table_fallback",
                    }
                )
        return cls.aggregate_candidate_scores(results)[: max(1, int(top_k or 20))]


class CelebrityReferenceGallery:
    """⚠️ 已废弃：明星脸搜索改用AI Native路径

    废弃原因：
    - 硬编码只有3个明星（刘亦菲、田曦薇、周也）
    - 用Wikipedia查询明星照片，不够稳定
    - 用字符串哈希生成"伪向量"，不是真实人脸向量

    新路径（AI Native）：
    - Agent自己用WebSearch搜明星照片URL
    - Agent调用search_partner_candidates(photo_url="...")
    - 系统用DeepFace提取真实人脸向量（512维）
    - 用真实向量搜索相似候选人

    迁移指南：
    - 旧代码：CelebrityReferenceGallery.search_by_name("田曦薇")
    - 新代码：Agent用WebSearch搜"田曦薇照片" → 提取photo_url → search_partner_candidates(photo_url)

    本类将在未来版本删除，请尽快迁移。
    """

    def __init__(self):
        warnings.warn(
            "CelebrityReferenceGallery已废弃，请使用AI Native路径："
            "Agent自己用WebSearch搜明星照片URL，然后调用search_partner_candidates(photo_url)",
            DeprecationWarning,
            stacklevel=2
        )
        _logger.warning(
            "【已废弃】CelebrityReferenceGallery已废弃，请使用AI Native路径"
        )

    DEFAULT_REFERENCES = {
        "刘亦菲": "celebrity|liuyifei|official",
        "田曦薇": "celebrity|tianxiwei|official",
        "周也": "celebrity|zhouye|official",
    }
    _NAME_PATTERNS = (
        re.compile(r"(?:像|找像|类似|同款|明星脸)\s*([\u4e00-\u9fffA-Za-z·]{2,12})"),
        re.compile(r"([\u4e00-\u9fffA-Za-z·]{2,12})(?:那种|同款|风格|脸)"),
    )
    _NAME_SUFFIXES = ("那种感觉", "这种感觉", "那种", "这种", "风格", "同款", "脸")
    _GENERIC_NAMES = {"这张", "这张脸", "这个人", "这种感觉", "那种感觉", "照片", "图片"}

    @classmethod
    def extract_name_candidates(cls, text: str) -> list[str]:
        normalized = str(text or "").strip()
        if not normalized:
            return []
        candidates: list[str] = []
        for pattern in cls._NAME_PATTERNS:
            for match in pattern.findall(normalized):
                value = str(match or "").strip(" ，。！？,.!?、")
                for suffix in cls._NAME_SUFFIXES:
                    if value.endswith(suffix):
                        value = value[: -len(suffix)].strip()
                for prefix in ("我想找像", "想找像", "找像", "像"):
                    if value.startswith(prefix):
                        value = value[len(prefix):].strip()
                if len(value) < 2:
                    continue
                if value in cls._GENERIC_NAMES:
                    continue
                if value not in candidates:
                    candidates.append(value)
        for celebrity_name in cls.DEFAULT_REFERENCES:
            if celebrity_name in normalized and celebrity_name not in candidates:
                candidates.insert(0, celebrity_name)
        return candidates

    @classmethod
    def _online_lookup_enabled(cls) -> bool:
        raw = str(os.environ.get("HER_ENABLE_ONLINE_CELEBRITY_REFERENCES", "1")).strip().lower()
        return raw not in {"0", "false", "off", "no"}

    @classmethod
    def _http_json(cls, url: str, *, timeout: float = 2.5) -> dict[str, Any] | list[Any] | None:
        request = urllib_request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "HerPhotoSearchBot/1.0",
            },
        )
        try:
            with urllib_request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
            return None

    @classmethod
    def _summary_candidates_for_title(cls, title: str, *, lang: str) -> list[dict[str, Any]]:
        encoded = urllib_parse.quote(str(title or "").strip())
        if not encoded:
            return []
        payload = cls._http_json(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        )
        if not isinstance(payload, Mapping):
            return []
        image_url = (
            str((payload.get("originalimage") or {}).get("source") or "").strip()
            or str((payload.get("thumbnail") or {}).get("source") or "").strip()
        )
        if not image_url:
            return []
        return [{
            "name": str(payload.get("title") or title).strip() or str(title).strip(),
            "source": image_url,
            "summary": str(payload.get("extract") or "").strip() or None,
            "provider": f"wikipedia_{lang}",
            "similarity": 1.0,
        }]

    @classmethod
    def _online_reference_candidates(cls, name: str, *, top_k: int = 3) -> list[dict[str, Any]]:
        if not cls._online_lookup_enabled():
            return []
        normalized_name = str(name or "").strip()
        if not normalized_name:
            return []
        candidates: list[dict[str, Any]] = []
        for lang in ("zh", "en"):
            candidates.extend(cls._summary_candidates_for_title(normalized_name, lang=lang))
            if candidates:
                break
        if candidates:
            return candidates[: max(1, int(top_k or 3))]
        search_payload = cls._http_json(
            "https://zh.wikipedia.org/w/api.php?action=opensearch"
            f"&search={urllib_parse.quote(normalized_name)}&limit={max(1, int(top_k or 3))}"
            "&namespace=0&format=json"
        )
        if isinstance(search_payload, list) and len(search_payload) >= 2:
            for title in list(search_payload[1] or []):
                candidates.extend(cls._summary_candidates_for_title(str(title), lang="zh"))
                if len(candidates) >= max(1, int(top_k or 3)):
                    break
        return candidates[: max(1, int(top_k or 3))]

    @classmethod
    def search_by_name(cls, name: str, *, top_k: int = 3) -> list[dict[str, Any]]:
        normalized_name = str(name or "").strip()
        online_results = cls._online_reference_candidates(normalized_name, top_k=top_k)
        if online_results:
            return online_results
        if normalized_name in cls.DEFAULT_REFERENCES:
            exact_source = cls.DEFAULT_REFERENCES[normalized_name]
            remaining = [
                {"name": normalized_name, "source": exact_source, "similarity": 1.0}
            ]
            for celebrity_name, source in cls.DEFAULT_REFERENCES.items():
                if celebrity_name == normalized_name:
                    continue
                remaining.append({"name": celebrity_name, "source": source, "similarity": 0.5})
            return remaining[: max(1, int(top_k or 3))]
        query_embedding = _stable_embedding_from_text(normalized_name, dims=128, salt="celebrity_query")
        scored: list[dict[str, Any]] = []
        for celebrity_name, source in cls.DEFAULT_REFERENCES.items():
            candidate_embedding = _stable_embedding_from_text(source, dims=128, salt="celebrity_ref")
            similarity = _normalize_similarity(_cosine_similarity(query_embedding, candidate_embedding))
            scored.append({"name": celebrity_name, "source": source, "similarity": similarity})
        scored.sort(key=lambda item: item["similarity"], reverse=True)
        return scored[: max(1, int(top_k or 3))]

    @classmethod
    def reference_embedding_for_name(cls, name: str) -> list[float]:
        resolved = cls.search_by_name(name, top_k=1)
        source = (
            str(resolved[0].get("source") or "").strip()
            if resolved else cls.DEFAULT_REFERENCES.get(str(name or "").strip(), str(name or "").strip())
        )
        return _stable_embedding_from_text(source, dims=16, salt="celebrity_face_reference")


class UploadedReferenceFaceProcessor:
    @staticmethod
    def process(
        *,
        image_source: str,
        requester_profile_id: int | None = None,
    ) -> dict[str, Any]:
        normalized_source = str(image_source or "").strip()
        if not normalized_source:
            return {"saved": False, "error": "image_source_missing"}
        base_id = int(requester_profile_id or 0)
        embedding = _stable_embedding_from_text(
            f"{base_id}|{normalized_source}",
            dims=16,
            salt="uploaded_reference_face",
        )
        return {
            "saved": True,
            "image_source": normalized_source,
            "embedding_json": embedding,
            "embedding_dim": len(embedding),
        }


class AppearanceStyleSearcher:
    @staticmethod
    def search_by_text(
        *,
        source_dsn: str | None,
        query_text: str,
        top_k: int = 20,
        exclude_profile_ids: Iterable[int] | None = None,
        vector_store: Any | None = None,
    ) -> list[dict[str, Any]]:
        embedding = AppearanceProfileEmbeddingExtractor.extract(appearance_summary=query_text, appearance_tags=[])
        close_store = False
        results: list[dict[str, Any]] = []
        if vector_store is None:
            try:
                from .vector_store_lite import VectorStoreLite

                vector_store = VectorStoreLite()
                close_store = True
            except Exception:
                vector_store = None
        if vector_store is not None:
            try:
                results = [
                    {**dict(item), "source": "vector_store"}
                    for item in vector_store.search_similar_users(
                        user_vector=embedding,
                        vector_type=APPEARANCE_PROFILE_VECTOR_TYPE,
                        top_k=top_k,
                        similarity_threshold=0.15,
                        exclude_user_ids=[int(item) for item in list(exclude_profile_ids or []) if int(item) > 0],
                    )
                ]
            finally:
                if close_store:
                    vector_store.close()
        if not results and source_dsn:
            feature_map = {
                int(item.get("profile_id") or 0): dict(item)
                for item in list_profile_photo_feature_rows(
                    source_dsn=source_dsn,
                    analysis_statuses=["done"],
                    limit=max(top_k * 5, 100),
                )
            }
            excluded = {int(item) for item in list(exclude_profile_ids or []) if int(item) > 0}
            query_tokens = {token for token in str(query_text or "").strip().replace("，", " ").split() if token}
            for profile_id, feature_row in feature_map.items():
                if profile_id <= 0 or profile_id in excluded:
                    continue
                tags = [str(item.get("label") or "").strip() for item in list(feature_row.get("appearance_tags_json") or []) if str(item.get("label") or "").strip()]
                candidate_embedding = AppearanceProfileEmbeddingExtractor.extract(
                    appearance_summary=str(feature_row.get("appearance_summary") or ""),
                    appearance_tags=tags,
                )
                similarity = _normalize_similarity(_cosine_similarity(embedding, candidate_embedding))
                if query_tokens and any(token in str(feature_row.get("appearance_summary") or "") for token in query_tokens):
                    similarity = min(1.0, round(similarity + 0.08, 4))
                results.append(
                    {
                        "profile_id": profile_id,
                        "user_id": profile_id,
                        "similarity": similarity,
                        "raw_text": str(feature_row.get("appearance_summary") or ""),
                        "tags": tags,
                        "source": "table_fallback",
                    }
                )
            results.sort(key=lambda item: float(item.get("similarity") or 0.0), reverse=True)
        return results[: max(1, int(top_k or 20))]


class HybridAppearanceRecallSearcher:
    @staticmethod
    def search(
        *,
        source_dsn: str | None,
        query_text: str,
        top_k: int = 20,
        exclude_profile_ids: Iterable[int] | None = None,
    ) -> list[dict[str, Any]]:
        vector_hits = AppearanceStyleSearcher.search_by_text(
            source_dsn=source_dsn,
            query_text=query_text,
            top_k=max(top_k * 2, 20),
            exclude_profile_ids=exclude_profile_ids,
        )
        query_tokens = {token for token in str(query_text or "").strip().replace("，", " ").split() if token}
        merged: dict[int, dict[str, Any]] = {}
        for item in vector_hits:
            profile_id = int(item.get("profile_id") or item.get("user_id") or 0)
            if profile_id <= 0:
                continue
            score = float(item.get("similarity") or 0.0)
            tags = [str(tag).strip() for tag in list(item.get("tags") or []) if str(tag).strip()]
            tag_bonus = 0.0
            if query_tokens and any(token in tags for token in query_tokens):
                tag_bonus = 0.12
            merged[profile_id] = {
                "profile_id": profile_id,
                "similarity": round(min(1.0, score + tag_bonus), 4),
                "vector_similarity": round(score, 4),
                "tag_bonus": round(tag_bonus, 4),
                "tags": tags,
                "raw_text": item.get("raw_text"),
            }
        return sorted(merged.values(), key=lambda row: float(row.get("similarity") or 0.0), reverse=True)[: max(1, int(top_k or 20))]


class AttributeFilterSearcher:
    @staticmethod
    def search(
        *,
        source_dsn: str | None,
        filters: Mapping[str, Any],
        top_k: int = 20,
        logic: str = "and",
        sort_by: str = "match_score",
    ) -> list[dict[str, Any]]:
        if not source_dsn:
            return []
        feature_rows = list_profile_photo_feature_rows(
            source_dsn=source_dsn,
            analysis_statuses=["done"],
            limit=max(top_k * 5, 100),
        )
        profile_ids = [int(item.get("profile_id") or 0) for item in feature_rows if int(item.get("profile_id") or 0) > 0]
        attribute_map = load_profile_face_attributes(source_dsn=source_dsn, profile_ids=profile_ids)
        normalized_logic = str(logic or "and").strip().lower()
        results: list[dict[str, Any]] = []
        for feature_row in feature_rows:
            profile_id = int(feature_row.get("profile_id") or 0)
            if profile_id <= 0:
                continue
            attributes = dict(attribute_map.get(profile_id) or {})
            attribute_source = str(attributes.get("attribute_source") or "").strip().lower()
            attribute_confidence = float(attributes.get("attribute_confidence") or 0.0)
            clauses: list[bool] = []
            explanations: list[str] = []
            score = 0.0
            for field_name, expected in dict(filters or {}).items():
                if field_name in LANDMARK_ATTRIBUTE_FIELDS and (
                    attribute_source != "landmark" or attribute_confidence < 0.35
                ):
                    clauses.append(False)
                    continue
                value = attributes.get(field_name, feature_row.get(field_name))
                if isinstance(expected, Mapping):
                    min_value = float(expected.get("min") or 0.0) if expected.get("min") is not None else None
                    max_value = float(expected.get("max") or 0.0) if expected.get("max") is not None else None
                    if value is None and field_name in LANDMARK_ATTRIBUTE_FIELDS:
                        clauses.append(False)
                        continue
                    numeric_value = float(value or 0.0)
                    matched = True
                    if min_value is not None and numeric_value < min_value:
                        matched = False
                    if max_value is not None and numeric_value > max_value:
                        matched = False
                    clauses.append(matched)
                    if matched:
                        score += numeric_value
                        explanations.append(f"{field_name}={round(numeric_value, 2)}")
                else:
                    matched = value == expected
                    clauses.append(matched)
                    if matched:
                        score += 50.0
                        explanations.append(f"{field_name}匹配")
            if not clauses:
                continue
            passed = all(clauses) if normalized_logic != "or" else any(clauses)
            if not passed:
                continue
            results.append(
                {
                    "profile_id": profile_id,
                    "match_score": round(score, 2),
                    "explanation": "，".join(explanations) or "属性命中",
                }
            )
        sort_key = "match_score" if sort_by not in {"profile_id"} else "profile_id"
        results.sort(key=lambda item: item.get(sort_key) or 0, reverse=True)
        return results[: max(1, int(top_k or 20))]


def search_profiles_by_reference_image(
    *,
    source_dsn: str | None,
    requester_user_key: str,
    image_source: str,
    requester_profile_id: int | None = None,
    top_k: int = 20,
) -> dict[str, Any]:
    processed = UploadedReferenceFaceProcessor.process(
        image_source=image_source,
        requester_profile_id=requester_profile_id,
    )
    if not processed.get("saved"):
        return processed
    results = FaceSimilaritySearcher.search(
        source_dsn=source_dsn,
        reference_embedding=processed.get("embedding_json") or [],
        top_k=top_k,
        exclude_profile_ids=[int(requester_profile_id or 0)] if int(requester_profile_id or 0) > 0 else [],
    )
    create_reference_face_search_job(
        source_dsn=source_dsn,
        requester_user_key=requester_user_key,
        requester_profile_id=requester_profile_id,
        input_source=image_source,
        result_profile_ids=[item.profile_id for item in results],
        status="done",
    )
    return {
        "saved": True,
        "result_count": len(results),
        "results": [
            {
                "profile_id": item.profile_id,
                "similarity": item.similarity,
                "source": item.source,
                "reasons": item.reasons,
            }
            for item in results
        ],
    }


__all__ = [
    "APPEARANCE_PROFILE_VECTOR_TYPE",
    "FACE_VECTOR_TYPE",
    "AppearanceProfileEmbeddingExtractor",
    "AppearanceStyleIndexBuilder",
    "AppearanceStyleSearcher",
    "AttributeFilterSearcher",
    "CelebrityReferenceGallery",
    "FaceSearchCandidate",
    "FaceSimilaritySearcher",
    "FaceVectorIndexBuilder",
    "HybridAppearanceRecallSearcher",
    "UploadedReferenceFaceProcessor",
    "search_profiles_by_reference_image",
]
