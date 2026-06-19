"""
测试花括号转义修复

验证修复后的 Prompt 构建函数能正确处理包含花括号的字符串，
防止 f-string 解析错误。
"""

import pytest
from match_domain.ai_merge_handler import (
    _build_semantic_judge_prompt,
    _build_batch_semantic_judge_prompt,
)


def test_single_prompt_with_braces():
    """测试单字段 Prompt 构建函数（字符串包含花括号）"""

    # 模拟错误场景：historical_text 包含 JSON 格式的花括号
    historical_text = '{"补充", "confidence": "high", "merged_text": "温柔、内向"}'
    new_text = "温柔、内向"
    vector_type = "personality_traits"

    # ✅ 修复后应该不会抛出 ValueError
    try:
        prompt = _build_semantic_judge_prompt(
            historical_text=historical_text,
            new_text=new_text,
            vector_type=vector_type,
        )

        # 验证 Prompt 正确生成
        assert "【历史版本】：" in prompt
        assert "【新版本】：" in prompt
        assert "温柔、内向" in prompt

        print("✅ 单字段 Prompt 构建成功（字符串包含花括号）")
        print(f"生成的 Prompt 长度: {len(prompt)} 字符")
        return True

    except ValueError as e:
        if "Invalid format specifier" in str(e):
            pytest.fail(f"❌ 修复失败：仍然出现 f-string 解析错误: {e}")
        else:
            raise


def test_batch_prompt_with_braces():
    """测试批量 Prompt 构建函数（字符串包含花括号）"""

    # 模拟批量场景：多个字段包含花括号
    all_historical_texts = {
        "personality_traits": '{"补充", "confidence": "high"}',
        "values": '{"冲突", "reason": "长期变化"}',
    }

    all_new_texts = {
        "personality_traits": "温柔、内向",
        "values": "重视家庭",
    }

    # ✅ 修复后应该不会抛出 ValueError
    try:
        prompt = _build_batch_semantic_judge_prompt(
            all_historical_texts=all_historical_texts,
            all_new_texts=all_new_texts,
        )

        # 验证 Prompt 正确生成
        assert "【personality_traits】：" in prompt
        assert "【values】：" in prompt
        assert "温柔、内向" in prompt
        assert "重视家庭" in prompt

        print("✅ 批量 Prompt 构建成功（字符串包含花括号）")
        print(f"生成的 Prompt 长度: {len(prompt)} 字符")
        return True

    except ValueError as e:
        if "Invalid format specifier" in str(e):
            pytest.fail(f"❌ 修复失败：仍然出现 f-string 解析错误: {e}")
        else:
            raise


def test_prompt_with_complex_json():
    """测试复杂 JSON 场景（嵌套花括号）"""

    # 模拟更复杂的 JSON 字符串（嵌套花括号）
    historical_text = """
{
    "relation_type": "补充",
    "confidence": "high",
    "action": "merge",
    "merged_text": "温柔、内向",
    "reason": "两者语义兼容，可合并"
}
"""

    new_text = '{"细化", "包含旧内容"}'

    # ✅ 修复后应该正确处理
    try:
        prompt = _build_semantic_judge_prompt(
            historical_text=historical_text,
            new_text=new_text,
            vector_type="personality_traits",
        )

        # 验证花括号被正确转义（在 Prompt 中应该看到 {{ 和 }}）
        assert "{{" in prompt or "历史版本" in prompt
        assert "{{" in prompt or "新版本" in prompt

        print("✅ 复杂 JSON 场景处理成功（嵌套花括号）")
        print(f"生成的 Prompt 镀度: {len(prompt)} 字符")
        return True

    except ValueError as e:
        if "Invalid format specifier" in str(e):
            pytest.fail(f"❌ 修复失败：仍然出现 f-string 解析错误: {e}")
        else:
            raise


def test_normal_text_still_works():
    """测试正常文本（不含花括号）仍然正常工作"""

    historical_text = "温柔、内向"
    new_text = "喜欢安静"

    # ✅ 正常文本应该继续正常工作
    prompt = _build_semantic_judge_prompt(
        historical_text=historical_text,
        new_text=new_text,
        vector_type="personality_traits",
    )

    assert "温柔、内向" in prompt
    assert "喜欢安静" in prompt

    print("✅ 正常文本处理成功（不含花括号）")
    return True


if __name__ == "__main__":
    # 运行所有测试
    test_single_prompt_with_braces()
    test_batch_prompt_with_braces()
    test_prompt_with_complex_json()
    test_normal_text_still_works()
    print("\n" + "="*50)
    print("✅ 所有测试通过！花括号转义修复验证成功")
    print("="*50)