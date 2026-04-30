import pathlib
import os
import types
import unittest
from unittest import mock


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "persona_memory_lib.py"
)
persona_memory_lib = types.ModuleType("persona_memory_lib")
persona_memory_lib.__file__ = str(SCRIPT_PATH)
exec(compile(SCRIPT_PATH.read_text(encoding="utf-8"), str(SCRIPT_PATH), "exec"), persona_memory_lib.__dict__)


class PersonaMemoryTests(unittest.TestCase):
    def test_insert_profile_stub_uses_database_generated_id(self):
        class FakeCursor:
            def __init__(self):
                self.lastrowid = 321
                self.executed = []

            def execute(self, query, params):
                self.executed.append((query, params))

        cursor = FakeCursor()
        profile_id = persona_memory_lib.insert_profile_stub(
            cursor,
            "profiles",
            {
                "name": "Demo",
                "profile_status": "active",
                "verified_level": "none",
                "source_channel": "persona-memory-sync",
                "last_active_at": "2026-04-29 12:00:00",
            },
        )
        self.assertEqual(profile_id, 321)
        self.assertEqual(len(cursor.executed), 1)

    def test_insert_profile_stub_falls_back_to_manual_id_when_profile_id_is_not_auto_increment(self):
        class FakeCursor:
            def __init__(self):
                self.lastrowid = None
                self.executed = []

            def execute(self, query, params=None):
                self.executed.append((query, params))
                if "INSERT INTO `profiles`" in query and "VALUES (%s, %s, %s, %s, %s)" in query:
                    raise Exception("(1364, \"Field 'id' doesn't have a default value\")")

            def fetchone(self):
                return {"next_id": 90123}

        cursor = FakeCursor()
        profile_id = persona_memory_lib.insert_profile_stub(
            cursor,
            "profiles",
            {
                "name": "Demo",
                "profile_status": "active",
                "verified_level": "none",
                "source_channel": "persona-memory-sync",
                "last_active_at": "2026-04-29 12:00:00",
            },
        )
        self.assertEqual(profile_id, 90123)
        self.assertEqual(len(cursor.executed), 3)

    def test_resolve_mysql_source_requires_explicit_config(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                persona_memory_lib.resolve_mysql_source()

    def test_resolve_mysql_source_reads_persona_env(self):
        with mock.patch.dict(
            os.environ,
            {"PERSONA_MEMORY_MYSQL_SOURCE": "mysql://demo@127.0.0.1:3306/her?table=profiles"},
            clear=True,
        ):
            self.assertEqual(
                persona_memory_lib.resolve_mysql_source(),
                "mysql://demo@127.0.0.1:3306/her?table=profiles",
            )

    def test_normalize_patch_supports_lists_and_ints(self):
        patch = persona_memory_lib.normalize_patch(
            {
                "self_age": "28岁",
                "self_has_children": "否",
                "must_have_tags": ["情绪稳定", "沟通", "情绪稳定"],
                "target_cities": "无锡,苏州",
            }
        )
        self.assertEqual(patch["self_age"], 28)
        self.assertEqual(patch["self_has_children"], 0)
        self.assertIsNone(patch["must_have_tags"])
        self.assertEqual(patch["preferred_traits"], "情绪稳定,沟通")
        self.assertEqual(patch["target_cities"], "无锡,苏州")

    def test_normalize_patch_moves_only_ambiguous_soft_tags_to_preferred(self):
        patch = persona_memory_lib.normalize_patch(
            {
                "must_have_tags": ["已购房", "聊得来", "情绪稳定"],
                "preferred_traits": ["真诚"],
            }
        )
        self.assertEqual(patch["must_have_tags"], "已购房")
        self.assertEqual(patch["preferred_traits"], "真诚,聊得来,情绪稳定")

    def test_merge_explicit_overwrites_hard_fields(self):
        existing = {"self_city": "上海", "must_have_tags": "情绪稳定"}
        patch = {"self_city": "无锡", "must_have_tags": "情绪稳定,消费观正常"}
        merged, field_results = persona_memory_lib.merge_persona(existing, patch, "explicit")
        self.assertEqual(merged["self_city"], "无锡")
        self.assertEqual(merged["must_have_tags"], "情绪稳定,消费观正常")
        self.assertEqual(field_results[0]["action_type"], "update")

    def test_strong_inference_does_not_override_explicit_hard_field(self):
        existing = {"self_city": "无锡", "preferred_traits": "稳定"}
        patch = {"self_city": "上海", "preferred_traits": "沟通顺畅"}
        merged, field_results = persona_memory_lib.merge_persona(existing, patch, "strong_inference")
        self.assertEqual(merged["self_city"], "无锡")
        self.assertEqual(merged["preferred_traits"], "稳定,沟通顺畅")
        city_result = [item for item in field_results if item["field_name"] == "self_city"][0]
        self.assertFalse(city_result["applied_to_persona"])
        self.assertEqual(city_result["note"], "explicit_only_scalar")

    def test_build_matcher_payload_normalizes_negative_terms(self):
        persona = {
            "must_have_tags": "情绪稳定,愿意沟通,消费观正常",
            "must_not_have_tags": "绿茶,拜金,冷暴力,暧昧不清",
            "target_cities": "无锡",
            "target_accept_long_distance": "不接受",
        }
        payload = persona_memory_lib.build_matcher_payload(persona)
        risks = payload["matcher_risks_json"]
        prefs = payload["matcher_preferences_json"]
        self.assertIn("boundary_clarity_risk", risks)
        self.assertIn("spending_values_mismatch_risk", risks)
        self.assertIn("communication_shutdown_risk", risks)
        self.assertIn("emotional_stability_priority", prefs)
        self.assertIn("communication_directness_preference", prefs)

    def test_build_public_profile_hides_raw_negative_labels(self):
        persona = {
            "self_city": "无锡",
            "self_relationship_goal": "结婚",
            "self_smoking": "否",
            "target_accept_long_distance": "不接受",
            "must_have_tags": "情绪稳定,愿意沟通,消费观正常",
            "must_not_have_tags": "绿茶,拜金,冷暴力,暧昧不清",
        }
        payload = persona_memory_lib.build_public_profile(persona)
        combined = " ".join(value for value in payload.values() if value)
        self.assertNotIn("绿茶", combined)
        self.assertNotIn("拜金", combined)
        self.assertIn("关系边界", combined)
        self.assertIn("消费观", combined)
        self.assertNotIn("对生活方式和习惯有较明确要求", combined)

    def test_merge_persona_sanitizes_summary_fields_with_city_and_goal_inference(self):
        merged, field_results = persona_memory_lib.merge_persona(
            {},
            {
                "self_city": "无锡",
                "self_relationship_goal": "结婚导向",
                "persona_summary_internal": "无锡本地，结婚导向，偏务实。",
            },
            "explicit",
        )
        self.assertEqual(merged["persona_summary_internal"], "现居无锡，结婚导向，偏务实。")
        summary_result = [item for item in field_results if item["field_name"] == "persona_summary_internal"][0]
        self.assertEqual(summary_result["stored_value"], "现居无锡，结婚导向，偏务实。")

    def test_build_profile_payload_maps_acceptance_fields(self):
        persona = {
            "user_key": "demo-user",
            "display_name": "Demo",
            "profile_id": 30074,
            "self_gender": "男",
            "self_age": 28,
            "self_city": "无锡",
            "self_education": "专升本",
            "self_job": "产品经理",
            "self_income_wan": 40,
            "self_relationship_goal": "结婚导向",
            "persona_summary_internal": "慢热但反馈稳定，认真推进关系。",
            "preference_summary_internal": "看重沟通效率，也看重情绪稳定。",
            "target_age_min": 24,
            "target_age_max": 30,
            "target_cities": "无锡",
            "target_accept_long_distance": "不接受",
            "target_accept_partner_children": "可协商",
            "target_accept_partner_children_strength": "谨慎接受",
            "target_marital_statuses": "未婚",
            "target_marital_status_strength": "谨慎接受",
            "must_have_tags": "情绪稳定,消费观正常",
        }
        payload = persona_memory_lib.build_profile_payload(persona)
        self.assertEqual(payload["gender"], "男")
        self.assertEqual(payload["preferred_age_min"], 24)
        self.assertEqual(payload["preferred_age_max"], 30)
        self.assertEqual(payload["preferred_cities"], "无锡")
        self.assertEqual(payload["accept_long_distance"], "不接受")
        self.assertEqual(payload["accept_partner_children"], "可协商")
        self.assertEqual(payload["accept_partner_children_strength"], "谨慎接受")
        self.assertEqual(payload["accept_partner_children_semantics"], "现阶段接受度偏低，需结合具体情况判断")
        self.assertEqual(payload["accept_marital_status"], "未婚")
        self.assertEqual(payload["accept_marital_status_strength"], "谨慎接受")
        self.assertEqual(payload["accept_marital_status_semantics"], "在可接受婚况范围内，但会更看具体人和相处质量")
        self.assertEqual(payload["income_range"], "36-45万/年")
        self.assertEqual(payload["education"], "专升本")
        self.assertEqual(payload["public_education"], "本科")
        self.assertEqual(payload["personality"], "慢热但反馈稳定，认真推进关系。")
        self.assertEqual(payload["values"], "看重沟通效率，也看重情绪稳定。")
        self.assertEqual(payload["public_job"], "产品经理")
        self.assertEqual(payload["public_display_name"], "用户0074")
        self.assertIn("matcher_traits_json", payload)
        self.assertIn("public_personality", payload)
        self.assertIn("你对对方孩子情况=现阶段接受度偏低，需结合具体情况判断", payload["notes"])

    def test_build_profile_payload_supports_guarded_children_negotiation(self):
        payload = persona_memory_lib.build_profile_payload(
            {
                "profile_id": 30074,
                "target_accept_partner_children": "现阶段不太接受",
                "target_accept_partner_children_strength": "谨慎接受",
            }
        )
        self.assertEqual(payload["accept_partner_children"], "现阶段不太接受")
        self.assertEqual(payload["accept_partner_children_strength"], "谨慎接受")
        self.assertEqual(payload["accept_partner_children_semantics"], "现阶段不太接受")
        self.assertIn("你对对方孩子情况=现阶段不太接受", payload["notes"])

    def test_normalize_patch_canonicalizes_legacy_guarded_children_alias(self):
        patch = persona_memory_lib.normalize_patch(
            {"target_accept_partner_children": "谨慎可协商"}
        )
        self.assertEqual(patch["target_accept_partner_children"], "现阶段不太接受")

    def test_normalize_patch_canonicalizes_guarded_children_phrase(self):
        patch = persona_memory_lib.normalize_patch(
            {"target_accept_partner_children": "优先不考虑对方已有孩子"}
        )
        self.assertEqual(patch["target_accept_partner_children"], "现阶段不太接受")

    def test_build_public_profile_masks_sensitive_job_titles(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "self_job": "医院药师",
                "self_city": "无锡",
            }
        )
        self.assertEqual(payload["public_job"], "医疗相关工作")

    def test_build_public_profile_masks_raw_education_to_coarse_band(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "self_education": "专升本",
            }
        )
        self.assertEqual(payload["public_education"], "本科")

    def test_build_public_profile_uses_current_city_not_native_and_softens_goal(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "self_city": "上海",
                "self_relationship_goal": "1-2年内往结婚推进",
            }
        )
        self.assertEqual(payload["public_personality"], "现居上海，认真了解，婚姻方向明确，合适会稳步推进")
        self.assertNotIn("上海本地", payload["public_personality"])
        self.assertNotIn("导向", payload["public_personality"])

    def test_normalize_patch_infers_child_reality_requirement_without_overloading_partner_children(self):
        patch = persona_memory_lib.normalize_patch(
            {
                "self_has_children": "是",
                "must_have_tags": ["收入稳定", "接受孩子现实"],
                "target_accept_partner_children": "接受",
                "persona_summary_internal": "35岁，离异，有一女但不随身。",
                "preference_summary_internal": "希望对方能接受孩子现实，原则上不接受异地。",
            }
        )
        self.assertEqual(patch["self_children_count"], 1)
        self.assertEqual(patch["self_children_living_with_self"], 0)
        self.assertEqual(patch["target_requires_partner_accept_my_children"], 1)
        self.assertIsNone(patch["target_accept_partner_children"])
        self.assertIn("原则上不接受异地", patch["target_location_semantics"])
        self.assertIsNone(patch["must_have_tags"])
        self.assertEqual(patch["preferred_traits"], "收入稳定,接受孩子现实")

    def test_normalize_patch_extracts_location_semantics_without_copying_full_preference_summary(self):
        patch = persona_memory_lib.normalize_patch(
            {
                "target_cities": "上海",
                "preference_summary_internal": "上海优先，也接受稳定留沪；短期异地可了解，但不接受长期不落地异地；也看重情绪稳定和沟通顺畅。",
            }
        )
        self.assertEqual(
            patch["target_location_semantics"],
            "上海优先；也接受稳定留沪；短期异地可了解；但不接受长期不落地异地",
        )
        self.assertNotIn("情绪稳定", patch["target_location_semantics"])

    def test_build_public_profile_uses_safe_internal_traits_and_masks_child_reality_phrase(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "self_city": "南京",
                "self_relationship_goal": "认真恋爱",
                "persona_summary_internal": "慢热但认真，生活安静稳定，希望长期稳定相处。",
                "must_have_tags": "接受孩子现实,边界清楚",
            }
        )
        self.assertEqual(payload["public_personality"], "现居南京，慢热但认真，生活安静稳定，认真了解，重视长期稳定关系")
        self.assertIn("能承接现实关系", payload["public_values"])
        self.assertNotIn("孩子现实", payload["public_values"])

    def test_build_profile_payload_maps_children_detail_and_partner_accepts_my_children_requirement(self):
        payload = persona_memory_lib.build_profile_payload(
            {
                "profile_id": 30100,
                "self_has_children": 1,
                "self_children_count": 1,
                "self_children_living_with_self": 0,
                "target_requires_partner_accept_my_children": 1,
                "persona_summary_internal": "有一女但不随身，认真找长期关系。",
            }
        )
        self.assertEqual(payload["has_children"], 1)
        self.assertEqual(payload["children_count"], 1)
        self.assertEqual(payload["children_living_with_self"], 0)
        self.assertEqual(payload["requires_partner_accept_my_children"], 1)
        self.assertIn("对方需能接受你的孩子现实", payload["notes"])

    def test_build_public_profile_keeps_remarriage_timeline_without_harsh_pressure(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "self_city": "苏州",
                "self_relationship_goal": "认真找对象，希望两年内推进到再婚",
            }
        )
        self.assertEqual(payload["public_personality"], "现居苏州，认真了解，再婚方向明确，合适会稳步推进")

    def test_build_public_profile_preserves_non_rushed_marriage_tone(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "self_city": "南京",
                "self_relationship_goal": "结婚不着急但方向明确",
                "persona_summary_internal": "慢热但认真，生活安静稳定，希望长期稳定相处。",
            }
        )
        self.assertEqual(
            payload["public_personality"],
            "现居南京，慢热但认真，生活安静稳定，认真了解，方向明确，不仓促推进",
        )

    def test_build_public_profile_surfaces_realistic_long_term_goal_and_distance_boundary(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "self_city": "杭州",
                "self_relationship_goal": "认真稳定、能走向长期现实关系",
                "target_accept_long_distance": "不接受",
                "target_location_semantics": "杭州或上海都可以，但原则上不接受异地；就算是上海也要能正常见面并推进关系。",
                "target_requires_partner_accept_my_children": 1,
                "preferred_traits": "情绪稳定,边界清楚,责任感,沟通顺畅,有分寸,接受孩子现实",
            }
        )
        self.assertEqual(payload["public_personality"], "现居杭州，认真了解，长期现实关系方向明确")
        self.assertEqual(
            payload["public_values"],
            "看重能承接现实关系、情绪稳定、边界清楚、责任感、沟通顺畅",
        )
        self.assertEqual(payload["public_notes"], "原则上不接受异地；需能正常见面并推进关系")

    def test_build_public_profile_does_not_infer_stable_lifestyle_from_non_smoking_alone(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "self_city": "无锡",
                "self_relationship_goal": "认真恋爱，合适就结婚",
                "self_smoking": "不抽烟",
            }
        )
        self.assertEqual(payload["public_personality"], "现居无锡，认真了解，婚姻方向明确")

    def test_build_public_profile_sanitizes_legacy_public_draft(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "self_city": "无锡",
                "self_relationship_goal": "结婚导向",
                "public_profile_summary_draft": "无锡本地，生活方式稳定，认真以结婚为导向。",
            }
        )
        self.assertEqual(payload["public_personality"], "现居无锡，生活方式稳定，认真了解，婚姻方向明确。")

    def test_build_public_profile_keeps_willingness_to_communicate_wording(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "must_have_tags": "边界清楚,愿意沟通,不暧昧",
            }
        )
        self.assertEqual(payload["public_values"], "看重边界清楚、愿意沟通、不暧昧")

    def test_build_public_profile_softens_preference_and_note_wording(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "target_accept_long_distance": "不接受",
                "must_not_have_tags": "抽烟,暧昧不清",
                "public_preference_summary_draft": "更适合同城或近距离稳定推进的关系，看重边界感、沟通顺畅和稳定性。",
            }
        )
        self.assertEqual(
            payload["public_values"],
            "更适合同城或近距离认真相处，看重边界感、沟通顺畅和稳定性",
        )
        self.assertIn("更偏好生活习惯相近的人", payload["public_notes"])
        self.assertIn("不喜欢关系里反复拉扯", payload["public_notes"])

    def test_build_public_profile_preserves_stronger_location_boundary_in_public_preference(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "target_location_semantics": "上海优先；稳定留沪；短期异地可了解；但不接受长期不落地异地",
                "public_preference_summary_draft": "上海优先，也接受稳定留沪；短期异地可了解，但不接受长期不落地异地；看重沟通顺畅。",
                "target_accept_long_distance": "不接受",
            }
        )
        self.assertEqual(
            payload["public_values"],
            "原则上不接受异地；如有短期过渡，需明确落地计划，上海优先，看重沟通顺畅",
        )

    def test_build_public_profile_prioritizes_child_reality_requirement_in_public_values(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "target_requires_partner_accept_my_children": 1,
                "preferred_traits": "情绪稳定,边界清楚,责任感,沟通顺畅,有分寸,接受孩子现实",
            }
        )
        self.assertEqual(
            payload["public_values"],
            "看重能承接现实关系、情绪稳定、边界清楚、责任感、沟通顺畅",
        )

    def test_build_public_profile_preserves_reality_execution_tag_in_public_values(self):
        payload = persona_memory_lib.build_public_profile(
            {
                "preferred_traits": "情绪稳定,婚姻诚意,消费观正常,沟通自然,现实推进能力,稳定留沪",
            }
        )
        self.assertEqual(
            payload["public_values"],
            "看重现实推进能力、长期关系诚意、情绪稳定、消费观清醒、沟通自然",
        )

    def test_summarize_observation_evidence_replaces_raw_transcript_with_field_summary(self):
        evidence = persona_memory_lib.summarize_observation_evidence(
            "self_job",
            "产品经理",
            "interviewer: 先简单了解一下\\nuser: 我现在在上海做产品经理，公司这边节奏挺快。",
        )
        self.assertEqual(evidence, "对话中明确提到职业=产品经理")

    def test_profile_columns_for_persona_patch_includes_nullable_profile_targets(self):
        columns = persona_memory_lib.profile_columns_for_persona_patch(
            {
                "target_education_min": None,
                "self_education": None,
                "self_job": None,
                "target_accept_partner_children_strength": "谨慎接受",
            }
        )
        self.assertIn("preferred_education_min", columns)
        self.assertIn("public_education", columns)
        self.assertIn("public_job", columns)
        self.assertIn("accept_partner_children_strength", columns)

    def test_build_profile_payload_can_force_null_persona_fields(self):
        payload = persona_memory_lib.build_profile_payload(
            {"target_education_min": None},
            include_null_persona_fields={"target_education_min"},
        )
        self.assertIn("preferred_education_min", payload)
        self.assertIsNone(payload["preferred_education_min"])

    def test_build_profile_payload_preserves_existing_internal_text_over_public_fallback(self):
        persona = {
            "user_key": "demo-user",
            "display_name": "Demo",
            "self_city": "无锡",
            "self_relationship_goal": "认真恋爱",
        }
        existing_profile = {
            "personality": "真实聊天里很会接话，也会主动推进。",
            "values": "看重沟通和现实执行感。",
            "notes": "明确不接受长期拉扯。",
        }
        payload = persona_memory_lib.build_profile_payload(persona, existing_profile=existing_profile)
        self.assertEqual(payload["personality"], existing_profile["personality"])
        self.assertEqual(payload["values"], existing_profile["values"])
        self.assertEqual(payload["notes"], existing_profile["notes"])
        self.assertNotEqual(payload["personality"], payload["public_personality"])

    def test_build_profile_payload_refreshes_legacy_generated_internal_personality(self):
        persona = {
            "self_city": "上海",
            "self_relationship_goal": "1-2年内往结婚推进",
            "self_smoking": "不抽烟",
        }
        existing_profile = {
            "personality": "上海本地，1-2年内往结婚推进导向",
        }
        payload = persona_memory_lib.build_profile_payload(persona, existing_profile=existing_profile)
        self.assertEqual(payload["personality"], "现居上海，认真了解，婚姻方向明确，合适会稳步推进")

    def test_build_profile_payload_sanitizes_existing_internal_personality_without_dropping_extra_context(self):
        persona = {
            "self_city": "无锡",
            "self_relationship_goal": "结婚导向",
        }
        existing_profile = {
            "personality": "无锡本地，结婚导向，偏务实，倾向稳定清晰的长期关系。",
        }
        payload = persona_memory_lib.build_profile_payload(persona, existing_profile=existing_profile)
        self.assertEqual(payload["personality"], "现居无锡，结婚导向，偏务实，倾向稳定清晰的长期关系。")

    def test_build_profile_payload_keeps_four_disliked_traits_in_internal_notes(self):
        payload = persona_memory_lib.build_profile_payload(
            {
                "disliked_traits": "控制欲强,长期回避沟通,消费观失衡,感情态度飘",
            }
        )
        self.assertIn("感情态度飘", payload["notes"])

    def test_build_profile_payload_deduplicates_must_not_and_disliked_notes(self):
        payload = persona_memory_lib.build_profile_payload(
            {
                "must_not_have_tags": "抽烟",
                "disliked_traits": "长期失联,抽烟",
            }
        )
        self.assertEqual(payload["notes"].count("抽烟"), 1)

    def test_mark_profile_sync_results_only_marks_profile_affecting_fields(self):
        field_results = [
            {"field_name": "self_city", "applied_to_persona": True},
            {"field_name": "profile_id", "applied_to_persona": True},
            {"field_name": "self_age", "applied_to_persona": False},
        ]
        persona_memory_lib.mark_profile_sync_results(field_results, synced_profile=True)
        self.assertTrue(field_results[0]["applied_to_profile"])
        self.assertFalse(field_results[1]["applied_to_profile"])
        self.assertFalse(field_results[2]["applied_to_profile"])

    def test_build_public_profile_view_sql_never_falls_back_to_internal_fields(self):
        sql = persona_memory_lib.build_public_profile_view_sql()
        self.assertIn("CAST(NULL AS CHAR(32)) AS income_range", sql)
        self.assertIn("public_display_name", sql)
        self.assertIn("CONCAT('用户'", sql)
        self.assertIn("public_education", sql)
        self.assertIn("AS education", sql)
        self.assertIn("public_job", sql)
        self.assertIn("CASE", sql)
        self.assertIn("认真了解，婚姻方向明确，合适会稳步推进", sql)
        self.assertIn("认真了解，再婚方向明确，合适会稳步推进", sql)
        self.assertIn("public_personality AS personality", sql)
        self.assertIn("public_values AS `values`", sql)
        self.assertIn("public_notes AS notes", sql)
        self.assertNotIn("\n  name,\n", sql)
        self.assertNotIn("\n  education,\n", sql)
        self.assertNotIn("COALESCE(public_personality, personality)", sql)
        self.assertNotIn("COALESCE(public_values, `values`)", sql)
        self.assertNotIn("COALESCE(public_notes, notes)", sql)


if __name__ == "__main__":
    unittest.main()
