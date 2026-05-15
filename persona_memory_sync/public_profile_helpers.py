from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class PublicProfileRuntime:
    as_int: Callable[[Any], Optional[int]]
    clean_text: Callable[[Any], Optional[str]]
    normalize_boolish: Callable[[Any], Optional[int]]
    split_multi_value: Callable[[Any], List[str]]
    unique_ordered: Callable[[Iterable[str]], List[str]]
    items_from_csv: Callable[[Any], List[str]]
    build_public_location_note: Callable[[Dict[str, Any]], Optional[str]]
    split_text_segments: Callable[[Any], List[str]]
    has_location_signal: Callable[[Any, Optional[Iterable[str]]], bool]
    public_safe_tag_map: Dict[str, str]
    public_job_patterns: Sequence[tuple[re.Pattern[str], str]]
    public_value_priority_tags: Sequence[str]
    public_safe_negative_notes: Dict[str, str]
    safe_public_personality_patterns: Sequence[tuple[re.Pattern[str], str]]
    safe_structured_personality_labels: set[str]
    observation_field_labels: Dict[str, str]


class PublicProfileHelpers:
    def __init__(self, runtime: PublicProfileRuntime) -> None:
        self.runtime = runtime

    def public_safe_tag(self, tag: str) -> str:
        return self.runtime.public_safe_tag_map.get(tag, tag)

    def build_public_job_title(self, job: Any) -> Optional[str]:
        title = self.runtime.clean_text(job)
        if not title:
            return None
        for pattern, safe_title in self.runtime.public_job_patterns:
            if pattern.search(title):
                return safe_title
        return title

    def build_public_education(self, education: Any) -> Optional[str]:
        text = self.runtime.clean_text(education)
        if not text:
            return None

        normalized = text.lower()
        if any(token in normalized for token in ("博士", "博士后", "phd")):
            return "博士"
        if any(token in normalized for token in ("研究生", "硕士", "mba", "emba", "本硕")):
            return "硕士"
        if any(token in normalized for token in ("本科", "学士", "专升本")):
            return "本科"
        if any(token in normalized for token in ("大专", "专科", "高职", "高专")):
            return "大专/高职"
        if any(token in normalized for token in ("高中", "中专", "职高", "技校")):
            return "高中/中专"
        if any(token in normalized for token in ("初中", "小学")):
            return "高中以下"
        return "已做模糊展示"

    def build_public_display_name(self, profile_id: Any) -> Optional[str]:
        profile_id_int = self.runtime.as_int(profile_id)
        if profile_id_int is None:
            return None
        return f"用户{profile_id_int % 10000:04d}"

    def sanitize_internal_profile_summary(
        self,
        summary: Any,
        persona: Dict[str, Any],
    ) -> Optional[str]:
        text = self.runtime.clean_text(summary)
        if not text:
            return None

        city_text = self.runtime.clean_text(persona.get("self_city"))
        if city_text:
            text = text.replace(f"{city_text}本地", f"现居{city_text}")

        text = re.sub(r"[，,]?\s*(?:年收入约?\s*\d+\s*万|\d+\s*-\s*\d+\s*万/年|收入信息已隐藏)\s*", "，", text)
        text = re.sub(
            r"离异已育[，,]\s*(?:有一个|有一位|有孩子|孩子)\S{0,8}?(?:但不随身|不随身|不跟自己住|不跟自己生活)",
            "离异已育",
            text,
        )
        text = re.sub(
            r"(?:有一个|有一位)(?:儿子|女儿|孩子)\S{0,8}?(?:但不随身|不随身|不跟自己住|不跟自己生活)",
            "有孩子",
            text,
        )
        text = re.sub(r"(现居[\u4e00-\u9fffA-Za-z0-9]+)[，,]?\1", r"\1", text)
        text = re.sub(r"(离异已育)[，,]?有孩子", r"\1", text)
        text = re.sub(r"[，,]{2,}", "，", text)
        return text.strip("，, ")

    def build_legacy_public_personality(self, persona: Dict[str, Any]) -> Optional[str]:
        fragments = []
        if persona.get("self_city"):
            fragments.append(f"{persona['self_city']}本地")
        if persona.get("self_relationship_goal"):
            fragments.append(f"{persona['self_relationship_goal']}导向")
        if self.runtime.clean_text(persona.get("self_smoking")) == "否":
            fragments.append("生活方式相对稳定")
        legacy = "，".join(fragments)
        return legacy or None

    def build_public_city_phrase(self, city: Any) -> Optional[str]:
        city_text = self.runtime.clean_text(city)
        if not city_text:
            return None
        return f"现居{city_text}"

    def build_public_relationship_goal(self, goal: Any) -> Optional[str]:
        goal_text = self.runtime.clean_text(goal)
        if not goal_text:
            return None
        has_timeline = bool(
            re.search(r"\d+\s*(?:-|到|至|~)\s*\d+年内", goal_text)
            or re.search(r"\d+年内", goal_text)
            or re.search(r"[一二两三四五六七八九十]+年内", goal_text)
        )
        has_non_rushed_tone = any(
            marker in goal_text
            for marker in ("不着急", "不仓促", "不想仓促", "先看相处", "先看相处质量", "慢慢来")
        )
        has_marriage_intent = "结婚" in goal_text or "婚姻" in goal_text
        has_remarriage_intent = "再婚" in goal_text
        has_long_term_intent = "长期关系" in goal_text or "长期" in goal_text

        if has_non_rushed_tone and has_remarriage_intent:
            return "认真相处，先看关系质量，合适再往婚姻走"
        if has_non_rushed_tone and has_long_term_intent and has_marriage_intent:
            return "认真相处，先看长期关系，合适再考虑婚姻"
        if has_non_rushed_tone and has_long_term_intent:
            return "认真相处，长期关系方向明确，不仓促推进"
        if has_non_rushed_tone and has_marriage_intent:
            return "认真相处，方向明确，不仓促推进"
        if "现实关系" in goal_text:
            return "认真相处，长期现实关系方向明确"
        if "认真找长期关系" in goal_text and "会考虑结婚" in goal_text:
            return "认真相处，先看长期关系，合适再考虑婚姻"
        if has_remarriage_intent:
            if has_timeline:
                return "认真相处，合适就认真往后走"
            return "认真相处，合适再往婚姻走"
        if has_long_term_intent and has_marriage_intent:
            if has_timeline:
                return "认真相处，合适就认真往后走"
            return "认真相处，长期关系稳定了再往婚姻走"
        if "稳定结婚" in goal_text:
            return "认真相处，长期关系稳定了再往婚姻走"
        if "结婚" in goal_text or "结婚导向" in goal_text:
            if has_timeline:
                return "认真相处，合适就认真往后走"
            return "认真相处，合适再往婚姻走"
        if "认真找长期关系" in goal_text:
            return "认真相处，重视长期稳定关系"
        if any(marker in goal_text for marker in ("认真恋爱", "长期", "稳定")):
            return "认真相处，重视长期稳定关系"
        return goal_text

    def sanitize_public_profile_summary(
        self,
        summary: Any,
        persona: Dict[str, Any],
    ) -> Optional[str]:
        text = self.runtime.clean_text(summary)
        if not text:
            return None

        city_text = self.runtime.clean_text(persona.get("self_city"))
        if city_text:
            text = text.replace(f"{city_text}本地", f"现居{city_text}")

        goal_text = self.runtime.clean_text(persona.get("self_relationship_goal"))
        goal_fragment = self.build_public_relationship_goal(goal_text)
        replacements = [
            (re.compile(r"[一二两三四五六七八九十]+年内[^，。；]*?再婚导向?"), "认真了解，合适就认真往后走"),
            (re.compile(r"\d+\s*(?:-|到|至|~)\s*\d+年内[^，。；]*?再婚导向?"), "认真了解，合适就认真往后走"),
            (re.compile(r"\d+年内[^，。；]*?再婚导向?"), "认真了解，合适就认真往后走"),
            (re.compile(r"[一二两三四五六七八九十]+年内[^，。；]*?(?:结婚|再婚)导向?"), "认真了解，合适就认真往后走"),
            (re.compile(r"\d+\s*(?:-|到|至|~)\s*\d+年内[^，。；]*?(?:结婚|再婚)导向?"), "认真了解，合适就认真往后走"),
            (re.compile(r"\d+年内[^，。；]*?(?:结婚|再婚)导向?"), "认真了解，合适就认真往后走"),
            (re.compile(r"认真以结婚为导向"), "认真了解，婚姻方向明确"),
            (re.compile(r"以结婚为导向"), "认真了解，婚姻方向明确"),
            (re.compile(r"结婚导向"), "认真了解，婚姻方向明确"),
            (re.compile(r"以再婚为导向"), "认真了解，再婚方向明确"),
            (re.compile(r"再婚导向"), "认真了解，再婚方向明确"),
        ]
        if goal_text and goal_fragment:
            replacements.append((re.compile(re.escape(goal_text) + r"导向"), goal_fragment))
            replacements.append(
                (
                    re.compile(r"(?:认真了解，)?再婚方向明确(?:，合适会稳步推进)?"),
                    goal_fragment,
                )
            )
            replacements.append(
                (
                    re.compile(r"(?:认真了解，)?长期关系与婚姻方向明确(?:，合适会稳步推进)?"),
                    goal_fragment,
                )
            )
            replacements.append(
                (
                    re.compile(r"(?:认真了解，)?婚姻方向明确(?:，合适会稳步推进)?"),
                    goal_fragment,
                )
            )
        for pattern, replacement in replacements:
            text = pattern.sub(replacement, text)

        text = re.sub(r"认真\s*认真了解", "认真了解", text)
        text = re.sub(r"认真\s*认真相处", "认真相处", text)
        text = re.sub(r"(现居[\u4e00-\u9fffA-Za-z0-9]+)[，,]?\1", r"\1", text)
        text = re.sub(r"(认真了解，婚姻方向明确(?:，合适会稳步推进)?)[，,]?\1", r"\1", text)
        text = re.sub(r"(认真了解，再婚方向明确(?:，合适会稳步推进)?)[，,]?\1", r"\1", text)
        text = re.sub(r"(认真相处，方向明确，不仓促推进)[，,]?\1", r"\1", text)
        text = re.sub(r"(认真相处，合适就认真往后走)[，,]?\1", r"\1", text)
        text = re.sub(r"(认真相处，合适再往婚姻走)[，,]?\1", r"\1", text)
        text = re.sub(r"(认真相处，先看关系质量，合适再往婚姻走)[，,]?\1", r"\1", text)
        text = re.sub(r"(认真相处，先看长期关系，合适再考虑婚姻)[，,]?\1", r"\1", text)
        text = re.sub(r"(认真相处，长期关系稳定了再往婚姻走)[，,]?\1", r"\1", text)
        text = re.sub(r"(认真相处，长期关系方向明确，不仓促推进)[，,]?\1", r"\1", text)
        text = re.sub(r"[，,]{2,}", "，", text)
        return text.strip("，, ")

    def sanitize_public_preference_summary(
        self,
        summary: Any,
        persona: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        text = self.runtime.clean_text(summary)
        if not text:
            return None
        replacements = [
            ("更适合同城稳定发展的关系", "更适合同城或近距离相处"),
            ("更适合同城或近距离稳定推进的关系", "更适合同城或近距离认真相处"),
            ("更适合同城或近距离认真推进的关系", "更适合同城或近距离认真相处"),
            ("对生活方式和习惯有较明确要求", "更偏好生活习惯相近的人"),
            ("消费观正常", "消费观相近"),
            ("接受孩子现实", "能承接现实关系"),
            ("能接受孩子现实", "能承接现实关系"),
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        known_cities = self.runtime.split_multi_value((persona or {}).get("target_cities"))
        location_note = self.runtime.build_public_location_note(persona or {"target_location_semantics": text})
        segments = self.runtime.split_text_segments(text)
        location_segments = [
            segment
            for segment in segments
            if self.runtime.has_location_signal(segment, known_cities=known_cities)
        ]
        if location_segments:
            non_location_segments = [
                segment for segment in segments if segment not in set(location_segments)
            ]
            rebuilt_segments: List[str] = []
            if location_note:
                rebuilt_segments.append(location_note)
            else:
                rebuilt_segments.append("更适合同城或近距离认真相处")
            rebuilt_segments.extend(non_location_segments)
            text = "，".join(self.runtime.unique_ordered(rebuilt_segments))
        text = re.sub(r"(更适合同城或近距离认真相处)[，,]?\1", r"\1", text)
        text = re.sub(r"[，,]{2,}", "，", text)
        return text.strip("，, ")

    def observation_field_label(self, field_name: Any) -> str:
        return self.runtime.observation_field_labels.get(str(field_name), str(field_name))

    def summarize_observation_evidence(
        self,
        field_name: Any,
        field_value: Any,
        evidence_text: Any,
        *,
        max_length: int = 120,
    ) -> Optional[str]:
        label = self.observation_field_label(field_name)
        value_text = self.runtime.clean_text(field_value) or ""
        if len(value_text) > 32:
            value_text = value_text[:29].rstrip() + "..."
        base = f"对话中明确提到{label}"
        if value_text:
            base += f"={value_text}"

        evidence = re.sub(r"\s+", " ", str(evidence_text or "")).strip()
        if not evidence:
            return base

        lowered = evidence.lower()
        looks_like_transcript = (
            "\n" in str(evidence_text)
            or "interviewer:" in lowered
            or "user:" in lowered
            or len(evidence) > max_length
        )
        if looks_like_transcript:
            return base

        if value_text and evidence == value_text:
            return base

        if len(evidence) > max_length:
            evidence = evidence[: max_length - 3].rstrip() + "..."
        return f"{base}；证据摘要: {evidence}"

    def sanitize_persona_summary_fields(self, persona: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = deepcopy(persona)
        internal_summary = self.sanitize_internal_profile_summary(
            sanitized.get("persona_summary_internal"),
            sanitized,
        )
        if internal_summary:
            sanitized["persona_summary_internal"] = internal_summary
        public_profile = self.sanitize_public_profile_summary(
            sanitized.get("public_profile_summary_draft"),
            sanitized,
        )
        if public_profile:
            sanitized["public_profile_summary_draft"] = public_profile
        public_pref = self.sanitize_public_preference_summary(
            sanitized.get("public_preference_summary_draft"),
            sanitized,
        )
        if public_pref:
            sanitized["public_preference_summary_draft"] = public_pref
        return sanitized

    def extract_safe_public_personality_traits(self, persona: Dict[str, Any]) -> List[str]:
        fragments: List[str] = []
        for field_name in ("self_life_rhythm", "self_work_pattern", "self_expression_style"):
            label = self.runtime.clean_text(persona.get(field_name))
            if (
                label
                and label in self.runtime.safe_structured_personality_labels
                and label not in fragments
            ):
                fragments.append(label)
        for summary in (
            self.runtime.clean_text(persona.get("public_profile_summary_draft")),
            self.runtime.clean_text(persona.get("persona_summary_internal")),
        ):
            if not summary:
                continue
            for pattern, label in self.runtime.safe_public_personality_patterns:
                if pattern.search(summary) and label not in fragments:
                    fragments.append(label)
        return fragments[:2]

    def build_public_profile(self, persona: Dict[str, Any]) -> Dict[str, Optional[str]]:
        must_have = [
            self.public_safe_tag(tag)
            for tag in self.runtime.items_from_csv(persona.get("must_have_tags"))
        ]
        must_not_have = self.runtime.items_from_csv(persona.get("must_not_have_tags"))
        preferred_traits = [
            self.public_safe_tag(tag)
            for tag in self.runtime.items_from_csv(persona.get("preferred_traits"))
        ]

        public_personality = self.sanitize_public_profile_summary(
            persona.get("public_profile_summary_draft"),
            persona,
        )
        public_values = self.sanitize_public_preference_summary(
            persona.get("public_preference_summary_draft"),
            persona,
        )
        location_note = self.runtime.build_public_location_note(persona)

        if not public_personality:
            fragments = []
            city_fragment = self.build_public_city_phrase(persona.get("self_city"))
            if city_fragment:
                fragments.append(city_fragment)
            fragments.extend(self.extract_safe_public_personality_traits(persona))
            goal_fragment = self.build_public_relationship_goal(persona.get("self_relationship_goal"))
            if (
                goal_fragment == "认真相处，方向明确，不仓促推进"
                and "长期稳定关系" in (self.runtime.clean_text(persona.get("persona_summary_internal")) or "")
            ):
                goal_fragment = "认真相处，长期关系方向明确，不仓促推进"
            if goal_fragment:
                fragments.append(goal_fragment)
            public_personality = "，".join(self.runtime.unique_ordered(fragments)) or "资料在持续完善中"

        if not public_values:
            key_tags = [
                tag
                for tag in self.runtime.unique_ordered(must_have + preferred_traits)
                if tag not in {"稳定留沪"}
            ]
            if self.runtime.normalize_boolish(persona.get("target_requires_partner_accept_my_children")) == 1:
                key_tags = self.runtime.unique_ordered(key_tags + ["能承接现实关系"])
            prioritized_tags = [
                tag for tag in self.runtime.public_value_priority_tags if tag in key_tags
            ]
            trailing_tags = [tag for tag in key_tags if tag not in set(prioritized_tags)]
            key_tags = self.runtime.unique_ordered(prioritized_tags + trailing_tags)[:6]
            if key_tags:
                public_values = "看重" + "、".join(key_tags)
            else:
                public_values = "看重稳定、真诚和可持续的相处方式"
            if (
                self.runtime.normalize_boolish(persona.get("target_requires_partner_accept_my_children")) == 1
                and "孩子现实" not in public_values
            ):
                public_values += "，也要尊重孩子现实"
            if location_note and location_note == "更适合同城或近距离认真相处":
                public_values += "，" + location_note

        notes = []
        if location_note and location_note not in str(public_values):
            notes.append(location_note)
        for raw_tag in must_not_have:
            safe_note = self.runtime.public_safe_negative_notes.get(raw_tag)
            if safe_note and safe_note not in notes:
                notes.append(safe_note)
        for raw_tag in self.runtime.items_from_csv(persona.get("disliked_traits")):
            safe_note = self.runtime.public_safe_negative_notes.get(raw_tag)
            if safe_note and safe_note not in notes:
                notes.append(safe_note)
        public_notes = "；".join(notes[:3]) if notes else None

        return {
            "public_education": self.build_public_education(persona.get("self_education")),
            "public_job": self.build_public_job_title(persona.get("self_job")),
            "public_personality": public_personality,
            "public_values": public_values,
            "public_notes": public_notes,
        }
