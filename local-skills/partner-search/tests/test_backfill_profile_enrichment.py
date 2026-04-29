import pathlib
import types
import unittest


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "backfill_profile_enrichment.py"
)
backfill_profile_enrichment = types.ModuleType("backfill_profile_enrichment")
backfill_profile_enrichment.__file__ = str(SCRIPT_PATH)
exec(
    compile(SCRIPT_PATH.read_text(encoding="utf-8"), str(SCRIPT_PATH), "exec"),
    backfill_profile_enrichment.__dict__,
)


class BackfillProfileEnrichmentTests(unittest.TestCase):
    def test_infer_structured_style_keeps_slow_warm_notes_out_of_cold_bucket(self):
        profile = {
            "relationship_goal": "结婚导向",
            "marriage_timeline": "1年内",
            "job": "药企招商主管",
            "education": "本科",
            "income_range": "20-32万/年",
            "personality": "情绪稳定, 真诚, 有耐心",
            "values": "简单真诚, 稳定踏实, 愿意共同经营生活",
            "lifestyle": "生活规律, 喜欢做饭, 偏宅",
            "hobbies": "散步, 桌游, 咖啡",
            "notes": "慢热但不冷场，能接住话，也不介意把关系慢慢聊稳，不会给人压迫感",
            "accept_marital_status_strength": "谨慎接受",
            "accept_partner_children_strength": "短期可聊",
            "accept_partner_children": "可协商",
        }

        enriched = backfill_profile_enrichment.infer_structured_style(profile)

        self.assertEqual(enriched["warmth_style"], "有温度会接话")
        self.assertNotEqual(enriched["lightness_humor"], "偏克制")

    def test_preserve_curated_backfill_keeps_existing_manual_labels(self):
        row = {
            "source_channel": "高质量补池",
            "warmth_style": "有温度会接话",
            "lightness_humor": "稳重有分寸",
            "career_intensity": "脑力投入型",
        }
        inferred = {
            "warmth_style": "偏克制",
            "lightness_humor": "偏克制",
            "career_intensity": "常规稳定",
        }

        merged = backfill_profile_enrichment.preserve_curated_backfill(row, inferred)

        self.assertEqual(merged["warmth_style"], "有温度会接话")
        self.assertEqual(merged["lightness_humor"], "稳重有分寸")
        self.assertEqual(merged["career_intensity"], "脑力投入型")

    def test_infer_structured_style_adds_consumption_chat_and_execution_fields(self):
        profile = {
            "relationship_goal": "认真恋爱",
            "marriage_timeline": "1年内",
            "job": "品牌策划",
            "values": "消费观正常, 不喜欢攀比, 对感情认真",
            "lifestyle": "喜欢做饭, 生活规律",
            "hobbies": "看展, 咖啡, 阅读",
            "notes": "聊天不端着，顺着聊不费劲，也愿意把长期打算说清楚，把见面安排说清楚",
        }

        enriched = backfill_profile_enrichment.infer_structured_style(profile)

        self.assertEqual(enriched["consumption_attitude"], "清醒务实")
        self.assertEqual(enriched["chat_texture"], "有梗也有内容")
        self.assertEqual(enriched["commitment_clarity"], "明确奔着长期")
        self.assertEqual(enriched["relationship_execution"], "会把安排说清")


if __name__ == "__main__":
    unittest.main()
