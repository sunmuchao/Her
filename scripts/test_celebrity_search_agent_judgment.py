#!/usr/bin/env python
"""
明星脸搜索Agent判断相似度功能测试脚本

测试目标：
验证Agent System Prompt中是否包含Agent判断相似度的指令

运行方式：
python scripts/test_celebrity_search_agent_judgment.py
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_agent_system_prompt():
    """测试Agent System Prompt是否包含Agent判断相似度的指令"""

    print("=" * 80)
    print("测试：Agent System Prompt中是否包含Agent判断相似度的指令")
    print("=" * 80)

    # 读取agent_runtime.py文件
    agent_runtime_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "external-systems/partner-discovery-system/discovery_system/agent_runtime.py"
    )

    with open(agent_runtime_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查关键指令是否存在
    checks = [
        ("Agent用Vision能力看候选人照片", "Step 5：Agent用Vision能力看候选人照片"),
        ("Agent判断长得像不像", "Step 6：Agent判断"),
        ("Agent筛选相似度≥80分的候选人", "Step 7：Agent筛选出真正像的候选人"),
        ("Agent判断相似度的方法", "Agent判断相似度的方法"),
        ("整体气质相似度", "整体气质相似度"),
        ("五官相似度", "五官相似度"),
        ("风格相似度", "风格相似度"),
    ]

    all_passed = True
    for check_name, check_string in checks:
        if check_string in content:
            print(f"✅ {check_name}: 找到指令")
        else:
            print(f"❌ {check_name}: 未找到指令")
            all_passed = False

    print("=" * 80)
    if all_passed:
        print("✅ 所有检查通过！Agent System Prompt已正确配置")
        return True
    else:
        print("❌ 部分检查失败！请检查Agent System Prompt")
        return False


def test_usage_scenario_table():
    """测试使用场景表格是否正确"""

    print("\n" + "=" * 80)
    print("测试：使用场景表格是否包含Agent判断相似度的说明")
    print("=" * 80)

    # 读取agent_runtime.py文件
    agent_runtime_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "external-systems/partner-discovery-system/discovery_system/agent_runtime.py"
    )

    with open(agent_runtime_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查使用场景表格
    checks = [
        ("表格中包含'找像田曦薇的女生'场景", "找像田曦薇的女生"),
        ("表格中包含Agent自己搜照片", "Agent自己搜照片"),
        ("表格中包含Agent看照片筛选", "Agent看照片筛选"),
        ("表格中包含Agent自己判断相似度", "Agent自己判断相似度"),
    ]

    all_passed = True
    for check_name, check_string in checks:
        if check_string in content:
            print(f"✅ {check_name}: 找到")
        else:
            print(f"❌ {check_name}: 未找到")
            all_passed = False

    print("=" * 80)
    if all_passed:
        print("✅ 使用场景表格检查通过！")
        return True
    else:
        print("❌ 使用场景表格检查失败！")
        return False


def main():
    """主测试函数"""

    print("\n" + "=" * 80)
    print("明星脸搜索Agent判断相似度功能测试")
    print("=" * 80 + "\n")

    # 测试1：Agent System Prompt
    test1_passed = test_agent_system_prompt()

    # 测试2：使用场景表格
    test2_passed = test_usage_scenario_table()

    # 总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)

    if test1_passed and test2_passed:
        print("✅ 所有测试通过！Agent已正确配置判断相似度功能")
        print("\n下一步：")
        print("1. 在前端测试完整流程")
        print("2. 输入：'我想找长得像田曦薇的女生'")
        print("3. 观察：Agent是否调用WebSearch搜照片")
        print("4. 观察：Agent是否调用search_partner_candidates工具")
        print("5. 观察：Agent是否用Vision能力判断相似度")
        print("6. 观察：Agent是否只返回真正像的候选人")
        return 0
    else:
        print("❌ 部分测试失败！请检查Agent System Prompt配置")
        return 1


if __name__ == "__main__":
    sys.exit(main())