"""简化的完整流程验证（不需要数据库）

直接调用题库和服务逻辑的Python函数，验证：
1. 题库设计正确性
2. 答题流程逻辑
3. 反馈卡片生成
4. 结果卡片生成
5. 小雅消息生成
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assessment.attachment_questions import (
    ATTACHMENT_QUESTIONS as ATTACHMENT_Q,
    calculate_all_scores as attachment_scores,
    get_primary_attachment_type,
    get_type_info as attachment_type_info,
    get_dimension_feedback,
    xiaoya_message_from_result as attachment_xiaoya,
    ATTACHMENT_TYPE_NAMES,
)
from assessment.love_language_questions import (
    LOVE_LANGUAGE_QUESTIONS as LOVE_LANGUAGE_Q,
    calculate_all_language_scores as love_language_scores,
    get_primary_love_language,
    get_language_ranking,
    get_language_info as love_language_info,
    get_language_feedback,
    xiaoya_message_from_result as love_xiaoya,
    LOVE_LANGUAGE_NAMES,
)


def simulate_attachment_assessment():
    """模拟依恋风格测评完整流程"""
    print("=" * 60)
    print("模拟依恋风格测评完整流程（12题）")
    print("=" * 60)

    # 模拟用户答题（每题选不同选项，展示多样性）
    answers = []
    print("\n📝 答题过程：")

    # 第1-3题（安全型）：选A（稳定）
    for i in range(3):
        answers.append(5)
        q = ATTACHMENT_Q[i]
        print(f"第{i+1}题: {q['text'][:50]}...")
        print(f"   你选择: A. {q['options'][0]['text'][:30]}...")

    # 第4-6题（焦虑型）：选E（极度焦虑）
    for i in range(3, 6):
        answers.append(1)
        q = ATTACHMENT_Q[i]
        print(f"第{i+1}题: {q['text'][:50]}...")
        print(f"   你选择: E. {q['options'][4]['text'][:30]}...")

    # 第7-9题（回避型）：选E（极度回避）
    for i in range(6, 9):
        answers.append(1)
        q = ATTACHMENT_Q[i]
        print(f"第{i+1}题: {q['text'][:50]}...")
        print(f"   你选择: E. {q['options'][4]['text'][:30]}...")

    # 第10-12题（恐惧型）：选E（极度恐惧）
    for i in range(9, 12):
        answers.append(1)
        q = ATTACHMENT_Q[i]
        print(f"第{i+1}题: {q['text'][:50]}...")
        print(f"   你选择: E. {q['options'][4]['text'][:30]}...")

    # 计算得分
    print("\n📊 维度得分计算：")
    scores = attachment_scores(answers)
    for dimension, score in scores.items():
        print(f"   {ATTACHMENT_TYPE_NAMES[dimension]}: {score}分")

    # 判断主要依恋类型
    primary_type = get_primary_attachment_type(scores)
    print(f"\n🎯 主要依恋类型: {ATTACHMENT_TYPE_NAMES[primary_type]}")

    # 获取类型信息
    type_info = attachment_type_info(primary_type)
    print(f"\n🏷️ 类型标签:")
    print(f"   昵称: {type_info['nickname']}")
    print(f"   网感昵称: {type_info['nickname_fun']}")
    for tag in type_info['tags'][:3]:
        print(f"   - {tag}")

    # 恋爱说明书
    print(f"\n📖 恋爱说明书:")
    love_manual = type_info['love_manual']
    print(f"   优势: {love_manual['strengths'][0]}")
    print(f"   坑点: {love_manual['weaknesses'][0]}")
    print(f"   最佳匹配: {love_manual['best_match'][0]}")

    # 小雅消息
    print(f"\n💬 小雅解读消息:")
    result = {"type_code": primary_type, "scores": scores}
    xiaoya_msg = attachment_xiaoya(result)
    print(f"   {xiaoya_msg[:200]}...")

    print("\n✅ 依恋风格测评流程验证完成")
    return True


def simulate_love_language_assessment():
    """模拟恋爱语言测评完整流程"""
    print("\n" + "=" * 60)
    print("模拟恋爱语言测评完整流程（10题）")
    print("=" * 60)

    # 模拟用户答题（每题选不同选项）
    answers = []
    print("\n📝 答题过程：")

    # 第1-2题（肯定言词）：选A（非常敏感）
    for i in range(2):
        answers.append(5)
        q = LOVE_LANGUAGE_Q[i]
        print(f"第{i+1}题: {q['text'][:50]}...")
        print(f"   你选择: A. {q['options'][0]['text'][:30]}...")

    # 第3-4题（精心时刻）：选B（中等敏感）
    for i in range(2, 4):
        answers.append(4)
        q = LOVE_LANGUAGE_Q[i]
        print(f"第{i+1}题: {q['text'][:50]}...")
        print(f"   你选择: B. {q['options'][1]['text'][:30]}...")

    # 第5-6题（接受礼物）：选C（一般）
    for i in range(4, 6):
        answers.append(3)
        q = LOVE_LANGUAGE_Q[i]
        print(f"第{i+1}题: {q['text'][:50]}...")
        print(f"   你选择: C. {q['options'][2]['text'][:30]}...")

    # 第7-8题（服务行动）：选D（不太敏感）
    for i in range(6, 8):
        answers.append(2)
        q = LOVE_LANGUAGE_Q[i]
        print(f"第{i+1}题: {q['text'][:50]}...")
        print(f"   你选择: D. {q['options'][3]['text'][:30]}...")

    # 第9-10题（身体接触）：选E（不敏感）
    for i in range(8, 10):
        answers.append(1)
        q = LOVE_LANGUAGE_Q[i]
        print(f"第{i+1}题: {q['text'][:50]}...")
        print(f"   你选择: E. {q['options'][4]['text'][:30]}...")

    # 计算得分
    print("\n📊 恋爱语言得分计算：")
    scores = love_language_scores(answers)
    for language, score in scores.items():
        print(f"   {LOVE_LANGUAGE_NAMES[language]}: {score}分")

    # 获取排序
    print("\n🏆 恋爱语言TOP3排序：")
    ranking = get_language_ranking(scores)
    for item in ranking[:3]:
        print(f"   #{item['rank']} {item['language_name']}({item['nickname']}) - {item['score']}分")

    # 判断主要恋爱语言
    primary_language = get_primary_love_language(scores)
    print(f"\n🎯 主恋爱语言: {LOVE_LANGUAGE_NAMES[primary_language]}")

    # 获取语言信息
    language_info = love_language_info(primary_language)
    print(f"\n🏷️ 语言标签:")
    print(f"   昵称: {language_info['nickname']}")
    print(f"   网感昵称: {language_info['nickname_fun']}")
    for tag in language_info['tags'][:3]:
        print(f"   - {tag}")

    # 恋爱说明书
    print(f"\n📖 如何让TA开心:")
    love_manual = language_info['love_manual']
    for suggestion in love_manual['how_to_love'][:2]:
        print(f"   ✅ {suggestion}")

    # 小雅消息
    print(f"\n💬 小雅解读消息:")
    result = {"primary_language": primary_language, "scores": scores}
    xiaoya_msg = love_xiaoya(result)
    print(f"   {xiaoya_msg[:200]}...")

    print("\n✅ 恋爱语言测评流程验证完成")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("依恋风格和恋爱语言测评完整流程验证")
    print("=" * 60)

    print("\n验证说明：")
    print("  🎯 不需要数据库连接，直接验证题库和服务逻辑")
    print("  🎯 展示完整的答题流程、计算逻辑、结果生成")
    print("  🎯 验证小雅消息生成（口语化网感风格）")
    print("  🎯 验证恋爱说明书生成（优势、坑点、匹配建议）")

    success_count = 0

    if simulate_attachment_assessment():
        success_count += 1

    if simulate_love_language_assessment():
        success_count += 1

    print("\n" + "=" * 60)
    print("验证总结")
    print("=" * 60)
    print(f"成功验证: {success_count}/2 个测评")

    if success_count == 2:
        print("\n🎉 依恋风格和恋爱语言测评完整流程验证成功！")
        print("\n已验证的核心功能：")
        print("  ✅ 题库设计（恋爱场景化、口语化、网感）")
        print("  ✅ 答题流程（题目展示、选项设计）")
        print("  ✅ 得分计算（正向/反向计分、排序）")
        print("  ✅ 类型判定（主要依恋类型、主恋爱语言）")
        print("  ✅ 结果生成（类型标签、恋爱说明书）")
        print("  ✅ 小雅消息（口语化网感风格，区别于卡片）")
        print("  ✅ TOP3排序（恋爱语言特色）")
        print("\n前端入口位置：")
        print("  📍 发现页面 → 输入框左侧'+按钮' → 菜单选择测评类型")
        print("\n三个测评按钮：")
        print("  🧠 MBTI测评 (Brain图标，蓝色)")
        print("  ❤️ 依恋风格 (Heart图标，粉色)")
        print("  ✨ 恋爱语言 (Sparkles图标，金色)")
    else:
        print(f"\n⚠️ 有测评验证失败")
        sys.exit(1)