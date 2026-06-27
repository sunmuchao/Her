#!/usr/bin/env python3
"""
验证 Whisper 幻觉检测是否生效

测试场景：
1. 正常文本 → 应该通过检测
2. YouTube结尾词 → 应该被过滤
3. 字幕组标识 → 应该被过滤
"""

import re

# Whisper幻觉检测模式（扩展YouTube常见结尾词，包含简体和繁体中文）
SUSPICIOUS_HALLUCINATION_PATTERNS = (
    # 字幕组标识（简体+繁体）
    re.compile(r"字幕\s*by", re.IGNORECASE),
    re.compile(r"字幕組", re.IGNORECASE),  # 繁体
    re.compile(r"字幕制作", re.IGNORECASE),
    re.compile(r"字幕翻译", re.IGNORECASE),

    # 特定人物/栏目名称（简体+繁体）
    re.compile(r"索兰娅"),
    re.compile(r"明镜与点点", re.IGNORECASE),  # 简体
    re.compile(r"明鏡與點點", re.IGNORECASE),  # 繁体
    re.compile(r"一点点点", re.IGNORECASE),
    re.compile(r"一點點點", re.IGNORECASE),  # 繁体

    # YouTube视频结尾词（简体中文）
    re.compile(r"请不吝[点赞订阅转发打赏关注分享]+", re.IGNORECASE),
    re.compile(r"不吝点赞", re.IGNORECASE),
    re.compile(r"点赞订阅", re.IGNORECASE),
    re.compile(r"订阅转发", re.IGNORECASE),
    re.compile(r"转发打赏", re.IGNORECASE),
    re.compile(r"打赏支持", re.IGNORECASE),
    re.compile(r"支持[\w]+栏目", re.IGNORECASE),
    re.compile(r"点赞关注", re.IGNORECASE),
    re.compile(r"关注分享", re.IGNORECASE),
    re.compile(r"分享转发", re.IGNORECASE),

    # YouTube视频结尾词（繁体中文）- 最常见的幻觉！
    re.compile(r"請不吝[點贊訂閱轉發打賞關注分享]+", re.IGNORECASE),  # 繁体完整版
    re.compile(r"不吝點贊", re.IGNORECASE),  # 繁体
    re.compile(r"點贊訂閱", re.IGNORECASE),  # 繁体
    re.compile(r"訂閱轉發", re.IGNORECASE),  # 繁体
    re.compile(r"轉發打賞", re.IGNORECASE),  # 繁体
    re.compile(r"打賞支持", re.IGNORECASE),  # 繁体
    re.compile(r"支持[\w]+欄目", re.IGNORECASE),  # 繁体
    re.compile(r"點贊關注", re.IGNORECASE),  # 繁体
    re.compile(r"關注分享", re.IGNORECASE),  # 繁体
    re.compile(r"分享轉發", re.IGNORECASE),  # 繁体

    # YouTube常见感谢词（简体）
    re.compile(r"谢谢观看", re.IGNORECASE),
    re.compile(r"感谢观看", re.IGNORECASE),
    re.compile(r"感谢大家的观看", re.IGNORECASE),
    re.compile(r"感谢各位的观看", re.IGNORECASE),
    re.compile(r"谢谢大家", re.IGNORECASE),
    re.compile(r"谢谢各位", re.IGNORECASE),

    # YouTube常见感谢词（繁体）
    re.compile(r"謝謝觀看", re.IGNORECASE),  # 繁体
    re.compile(r"感謝觀看", re.IGNORECASE),  # 繁体
    re.compile(r"感謝大家的觀看", re.IGNORECASE),  # 繁体
    re.compile(r"感謝各位的觀看", re.IGNORECASE),  # 繁体
    re.compile(r"謝謝大家", re.IGNORECASE),  # 繁体
    re.compile(r"謝謝各位", re.IGNORECASE),  # 繁体

    # YouTube结尾再见词（简体）
    re.compile(r"下期再见", re.IGNORECASE),
    re.compile(r"我们下期再见", re.IGNORECASE),
    re.compile(r"朋友们再见", re.IGNORECASE),
    re.compile(r"下期视频", re.IGNORECASE),
    re.compile(r"下个视频", re.IGNORECASE),

    # YouTube结尾再见词（繁体）
    re.compile(r"下期再見", re.IGNORECASE),  # 繁体
    re.compile(r"我們下期再見", re.IGNORECASE),  # 繁体
    re.compile(r"朋友們再見", re.IGNORECASE),  # 繁体
    re.compile(r"下期視頻", re.IGNORECASE),  # 繁体
    re.compile(r"下個視頻", re.IGNORECASE),  # 繁体

    # 其他常见幻觉模式（简体+繁体）
    re.compile(r"谢谢您的收看", re.IGNORECASE),
    re.compile(r"感谢您的收看", re.IGNORECASE),
    re.compile(r"謝謝您的收看", re.IGNORECASE),  # 繁体
    re.compile(r"感謝您的收看", re.IGNORECASE),  # 繁体
)


def is_suspicious_hallucination(text: str) -> bool:
    """检测文本是否为Whisper的幻觉内容"""
    normalized = text.strip()
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in SUSPICIOUS_HALLUCINATION_PATTERNS)


def test_hallucination_detection():
    """测试幻觉检测功能"""

    # 测试用例
    test_cases = [
        # 正常文本（应该通过）
        ("你好，我想找对象", False, "正常对话内容"),
        ("我喜欢看书和运动", False, "正常兴趣爱好"),
        ("请问这个功能怎么用", False, "正常询问"),
        ("今天天气真好", False, "正常聊天"),

        # YouTube结尾词（简体中文，应该被过滤）
        ("请不吝点赞订阅转发打赏支持明镜与点点栏目", True, "YouTube结尾词（简体完整版）"),
        ("请不吝点赞订阅", True, "YouTube结尾词（简体简化版）"),
        ("不吝点赞", True, "YouTube结尾词（简体关键词）"),
        ("谢谢观看", True, "YouTube感谢词（简体）"),
        ("感谢大家的观看", True, "YouTube感谢词（简体完整版）"),
        ("下期再见", True, "YouTube再见词（简体）"),
        ("我们下期再见", True, "YouTube再见词（简体完整版）"),

        # YouTube结尾词（繁体中文，应该被过滤）- 最常见！
        ("請不吝點贊訂閱轉發打賞支持明鏡與點點欄目", True, "YouTube结尾词（繁体完整版）⚠️"),
        ("請不吝點贊訂閱", True, "YouTube结尾词（繁体简化版）"),
        ("不吝點贊", True, "YouTube结尾词（繁体关键词）"),
        ("謝謝觀看", True, "YouTube感谢词（繁体）"),
        ("感謝大家的觀看", True, "YouTube感谢词（繁体完整版）"),
        ("下期再見", True, "YouTube再见词（繁体）"),
        ("我們下期再見", True, "YouTube再见词（繁体完整版）"),

        # 字幕组标识（应该被过滤）
        ("字幕by某某", True, "字幕组标识"),
        ("字幕組制作", True, "字幕组标识（繁体）"),
        ("索兰娅", True, "特定人物名称"),

        # 边缘情况（应该通过）
        ("谢谢你的帮助", False, "正常感谢（不是YouTube结尾）"),
        ("感谢你的推荐", False, "正常感谢（不是YouTube结尾）"),
        ("謝謝你的幫助", False, "正常感谢（繁体，不是YouTube结尾）"),
        ("感謝你的推薦", False, "正常感谢（繁体，不是YouTube结尾）"),
    ]

    print("=" * 80)
    print("Whisper 幻觉检测测试")
    print("=" * 80)

    passed = 0
    failed = 0

    for text, expected_is_hallucination, description in test_cases:
        actual_is_hallucination = is_suspicious_hallucination(text)
        status = "✅ PASS" if actual_is_hallucination == expected_is_hallucination else "❌ FAIL"

        if actual_is_hallucination == expected_is_hallucination:
            passed += 1
        else:
            failed += 1

        result_text = "幻觉" if actual_is_hallucination else "正常"
        expected_text = "幻觉" if expected_is_hallucination else "正常"

        print(f"\n{status} [{description}]")
        print(f"  文本: {text}")
        print(f"  期望: {expected_text}")
        print(f"  实际: {result_text}")

        if actual_is_hallucination != expected_is_hallucination:
            # 显示匹配的模式
            matched_patterns = [
                p.pattern for p in SUSPICIOUS_HALLUCINATION_PATTERNS
                if p.search(text.strip())
            ]
            print(f"  匹配模式: {matched_patterns}")

    print("\n" + "=" * 80)
    print(f"测试结果: {passed}个通过, {failed}个失败")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = test_hallucination_detection()
    exit(0 if success else 1)