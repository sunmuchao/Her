"""测试 Agent Prompt 改进：可量化判断标准

验证 Agent System Prompt 中是否包含正确的可量化判断标准。
"""

from pathlib import Path


def test_agent_prompt_has_quantifiable_section():
    """测试 Agent Prompt 是否包含可量化判断标准部分"""
    soul_file = Path("external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md")

    assert soul_file.exists(), "DISCOVERY_AGENT_SOUL.md 文件不存在"

    content = soul_file.read_text(encoding="utf-8")

    # 检查是否包含核心章节
    assert "### 5. 数据判断标准（核心）" in content, "缺少数据判断标准章节"

    # 检查是否包含可量化示例
    assert "✅ 可量化、无歧义（提取为结构化数据）" in content, "缺少可量化示例"
    assert "数值范围" in content, "缺少数值范围示例"
    assert "枚举类型" in content, "缺少枚举类型示例"
    assert "布尔值" in content, "缺少布尔值示例"
    assert "地理位置" in content, "缺少地理位置示例"

    # 检查是否包含主观描述示例
    assert "❌ 有歧义、主观描述（不要提取，让系统记到摘要）" in content, "缺少主观描述示例"
    assert "性格特质" in content, "缺少性格特质示例"
    assert "价值观" in content, "缺少价值观示例"
    assert "程度描述" in content, "缺少程度描述示例"
    assert "情感状态" in content, "缺少情感状态示例"

    # 检查是否包含判断原则
    assert "判断原则：" in content, "缺少判断原则"
    assert "SQL WHERE" in content, "缺少 SQL WHERE 判断示例"


def test_agent_prompt_has_correct_examples():
    """测试 Agent Prompt 是否包含正确的示例"""
    soul_file = Path("external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md")
    content = soul_file.read_text(encoding="utf-8")

    # 检查数值范围示例
    assert "age: 28" in content, "缺少年龄示例"
    assert "age_min: 26, age_max: 30" in content, "缺少年龄范围示例"

    # 检查枚举类型示例
    assert "mbti_type: \"INTJ\"" in content, "缺少 MBTI 示例"
    assert "marital_status: \"未婚\"" in content, "缺少婚姻状态示例"

    # 检查布尔值示例
    assert "smoking: false" in content, "缺少抽烟示例"
    assert "has_children: true" in content, "缺少孩子示例"

    # 检查地理位置示例
    assert "city: \"北京\"" in content, "缺少城市示例"
    assert "cities: [\"上海\", \"杭州\"]" in content, "缺少多城市示例"

    # 检查主观描述的反例
    assert "我性格温柔" in content, "缺少性格温柔反例"
    assert "❌ 不提取为结构化数据" in content, "缺少不提取示例"


def test_agent_prompt_has_sql_where_principle():
    """测试 Agent Prompt 是否包含 SQL WHERE 判断原则"""
    soul_file = Path("external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md")
    content = soul_file.read_text(encoding="utf-8")

    # 检查判断原则是否清晰
    assert "如果你能写出 SQL WHERE 条件" in content, "缺少 SQL WHERE 判断原则"
    assert "WHERE age BETWEEN 26 AND 30" in content, "缺少 SQL WHERE 示例"
    assert "那就是可量化 → 提取为结构化数据" in content, "缺少可量化判断结论"
    assert "如果你需要人工判断" in content, "缺少人工判断原则"
    assert "那就是主观描述 → 不提取，让系统记到摘要" in content, "缺少主观描述判断结论"


def test_agent_prompt_file_path():
    """测试 Agent Prompt 文件路径是否正确"""
    soul_file = Path("external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md")

    # 确认文件存在
    assert soul_file.exists(), f"文件不存在: {soul_file}"

    # 确认文件路径符合预期
    expected_path = "external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md"
    assert str(soul_file) == expected_path, f"文件路径不符合预期: {soul_file}"


if __name__ == "__main__":
    test_agent_prompt_has_quantifiable_section()
    test_agent_prompt_has_correct_examples()
    test_agent_prompt_has_sql_where_principle()
    test_agent_prompt_file_path()

    print("✅ Agent Prompt 改进测试全部通过")