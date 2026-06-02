"""依恋风格和恋爱语言测评题库测试

验证：
1. 题库设计是否正确（题目、选项、维度）
2. 计算逻辑是否正确（得分计算、类型判断）
3. 数据结构是否正确（结果卡片、解读内容）
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assessment.attachment_questions import (
    ATTACHMENT_QUESTIONS,
    calculate_all_scores,
    get_primary_attachment_type,
    get_type_info,
    xiaoya_message_from_result,
    calculate_love_match,
)
from assessment.love_language_questions import (
    LOVE_LANGUAGE_QUESTIONS,
    calculate_all_language_scores,
    get_primary_love_language,
    get_language_ranking,
    get_language_info,
    xiaoya_message_from_result as love_xiaoya_message,
    calculate_love_language_match,
)
from assessment.mbti_questions import xiaoya_message_from_result as mbti_xiaoya_message


def test_attachment_questions():
    """测试依恋风格题库"""
    print("=" * 60)
    print("测试依恋风格题库")
    print("=" * 60)

    # 1. 验证题目数量
    print(f"\n题目数量: {len(ATTACHMENT_QUESTIONS)} 题")
    assert len(ATTACHMENT_QUESTIONS) == 12, "依恋风格题目数量应该是12题"

    # 2. 验证题目结构
    print("\n验证题目结构:")
    for i, question in enumerate(ATTACHMENT_QUESTIONS[:3]):
        print(f"第{i+1}题: {question['text'][:30]}...")
        assert len(question['options']) == 5, f"第{i+1}题应该有5个选项"
        assert question['dimension'] in ['secure', 'anxious', 'avoidant', 'fearful'], f"第{i+1}题维度不正确"

    # 3. 模拟答题（全部选C，得分3分）
    print("\n模拟答题（全部选C，得分3分）:")
    answers = [3] * 12
    scores = calculate_all_scores(answers)
    print(f"得分: {scores}")
    assert all(50 <= score <= 60 for score in scores.values()), "全部选C应该得到中等分数"

    # 4. 模拟答题（全部选A，得分5分）
    print("\n模拟答题（全部选A，得分5分）:")
    answers_a = [5] * 12
    scores_a = calculate_all_scores(answers_a)
    print(f"得分: {scores_a}")

    # 安全型得分应该高（正向计分）
    assert scores_a['secure'] >= 80, "全部选A，安全型得分应该高"
    # 焦虑、回避、恐惧得分应该低（反向计分）
    assert scores_a['anxious'] <= 30, "全部选A，焦虑型得分应该低"
    assert scores_a['avoidant'] <= 30, "全部选A，回避型得分应该低"
    assert scores_a['fearful'] <= 30, "全部选A，恐惧型得分应该低"

    # 5. 判断主要依恋类型
    primary_type = get_primary_attachment_type(scores_a)
    print(f"主要依恋类型: {primary_type}")
    assert primary_type == "secure", "全部选A应该判定为安全型"

    # 6. 获取类型信息
    type_info = get_type_info(primary_type)
    print(f"类型昵称: {type_info['nickname']}")
    print(f"类型标签: {type_info['tags'][:3]}")
    assert type_info['nickname'], "类型应该有昵称"
    assert len(type_info['tags']) > 0, "类型应该有标签"

    # 7. 测试匹配度计算
    print("\n测试匹配度计算:")
    user_a_scores = {"secure": 85, "anxious": 15, "avoidant": 10, "fearful": 5}
    user_b_scores = {"secure": 80, "anxious": 20, "avoidant": 15, "fearful": 10}
    match_result = calculate_love_match(user_a_scores, user_b_scores)
    print(f"匹配分数: {match_result['score']}")
    print(f"匹配分析: {match_result['analysis']}")
    assert match_result['score'] >= 80, "两个安全型匹配分数应该高"

    # 8. 测试小雅消息生成
    result = {
        "type_code": primary_type,
        "scores": scores_a,
    }
    xiaoya_msg = xiaoya_message_from_result(result)
    print(f"\n小雅消息（前100字）: {xiaoya_msg[:100]}...")
    assert "亲爱的" in xiaoya_msg, "小雅消息应该包含'亲爱的'"
    assert primary_type in xiaoya_msg or type_info['nickname'] in xiaoya_msg, "小雅消息应该包含类型信息"

    print("\n✅ 依恋风格题库测试通过！")


def test_love_language_questions():
    """测试恋爱语言题库"""
    print("\n" + "=" * 60)
    print("测试恋爱语言题库")
    print("=" * 60)

    # 1. 验证题目数量
    print(f"\n题目数量: {len(LOVE_LANGUAGE_QUESTIONS)} 题")
    assert len(LOVE_LANGUAGE_QUESTIONS) == 10, "恋爱语言题目数量应该是10题"

    # 2. 验证题目结构
    print("\n验证题目结构:")
    for i, question in enumerate(LOVE_LANGUAGE_QUESTIONS[:3]):
        print(f"第{i+1}题: {question['text'][:30]}...")
        assert len(question['options']) == 5, f"第{i+1}题应该有5个选项"
        assert question['dimension'] in ['words_of_affirmation', 'quality_time', 'receiving_gifts', 'acts_of_service', 'physical_touch'], f"第{i+1}题维度不正确"

    # 3. 模拟答题（全部选A，得分5分）
    print("\n模拟答题（全部选A，得分5分）:")
    answers_a = [5] * 10
    scores_a = calculate_all_language_scores(answers_a)
    print(f"得分: {scores_a}")
    assert all(score >= 80 for score in scores_a.values()), "全部选A应该得到高分"

    # 4. 模拟答题（全部选C，得分3分）
    print("\n模拟答题（全部选C，得分3分）:")
    answers_c = [3] * 10
    scores_c = calculate_all_language_scores(answers_c)
    print(f"得分: {scores_c}")
    assert all(50 <= score <= 60 for score in scores_c.values()), "全部选C应该得到中等分数"

    # 5. 判断主要恋爱语言
    primary_language = get_primary_love_language(scores_a)
    print(f"主要恋爱语言: {primary_language}")
    assert primary_language in ['words_of_affirmation', 'quality_time', 'receiving_gifts', 'acts_of_service', 'physical_touch'], "主要恋爱语言应该是五种之一"

    # 6. 获取恋爱语言排序
    ranking = get_language_ranking(scores_a)
    print(f"\n恋爱语言排序:")
    for item in ranking[:3]:
        print(f"#{item['rank']} {item['language_name']}({item['nickname']}) - {item['score']}分")
    assert len(ranking) == 5, "应该有5种语言的排序"
    assert ranking[0]['score'] >= ranking[1]['score'], "排序应该是降序"

    # 7. 获取语言信息
    language_info = get_language_info(primary_language)
    print(f"\n语言昵称: {language_info['nickname']}")
    print(f"语言标签: {language_info['tags'][:3]}")
    assert language_info['nickname'], "语言应该有昵称"
    assert len(language_info['tags']) > 0, "语言应该有标签"

    # 8. 测试匹配度计算
    print("\n测试匹配度计算:")
    user_a_scores = {"words_of_affirmation": 85, "quality_time": 70, "receiving_gifts": 60, "acts_of_service": 50, "physical_touch": 40}
    user_b_scores = {"words_of_affirmation": 80, "quality_time": 75, "receiving_gifts": 65, "acts_of_service": 55, "physical_touch": 45}
    match_result = calculate_love_language_match(user_a_scores, user_b_scores)
    print(f"匹配分数: {match_result['score']}")
    print(f"匹配分析: {match_result['analysis']}")
    assert match_result['score'] >= 80, "主语言相同匹配分数应该高"

    # 9. 测试小雅消息生成
    result = {
        "primary_language": primary_language,
        "scores": scores_a,
    }
    xiaoya_msg = love_xiaoya_message(result)
    print(f"\n小雅消息（前100字）: {xiaoya_msg[:100]}...")
    assert "亲爱的" in xiaoya_msg, "小雅消息应该包含'亲爱的'"
    assert language_info['nickname'] in xiaoya_msg, "小雅消息应该包含语言昵称"

    print("\n✅ 恋爱语言题库测试通过！")


def test_mbti_xiaoya_message_prioritizes_match_guidance():
    """测试 MBTI 小雅消息优先给出匹配建议和相处指导"""
    result = {
        "type_code": "ESTJ",
        "scores": {"ei": 80, "sn": 78, "tf": 82, "jp": 76},
    }

    message = mbti_xiaoya_message(result)

    assert "高匹配人格：ISTP、INTP" in message
    assert "次高匹配人格：ESTP、ESFJ、ISTJ" in message
    assert "需要重点磨合的人格：INFP、ENFP" in message
    assert "**相处建议：**" in message
    assert "**关系画像：**" in message
    assert "**风险提醒：**" in message


if __name__ == "__main__":
    try:
        test_attachment_questions()
        test_love_language_questions()
        print("\n" + "=" * 60)
        print("🎉 所有测试通过！依恋风格和恋爱语言测评已完整落地！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
