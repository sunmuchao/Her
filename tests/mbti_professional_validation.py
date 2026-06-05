"""专业 MBTI 理论验证脚本

验证维度:
1. 荗格人格理论 - 认知功能栈验证
2. MBTI 理论框架 - 类型描述与匹配理论
3. 语言表达检查 - 语句通顺性与易懂性

理论基础:
- Carl Jung《心理类型》(1921)
- Isabel Briggs Myers《MBTI Manual》(1985)
- John Beebe《类型与原型》(2004)
- Linda Berens《多人格类型系统》(2005)
"""

import sys
import os
import re
from typing import Dict, List, Tuple, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assessment.mbti_questions import (
    MBTI_TYPE_LABELS,
    get_type_info,
    _type_code_from_scores,
    xiaoya_message_from_result,
    _build_professional_dimension_summary,
)

# ==================== 荗格认知功能理论 ====================

# 荗格八维认知功能栈（基于 Beebe 模型）
JUNG_COGNITIVE_STACKS = {
    # NT系列（分析家）- 理性功能主导
    "INTJ": ["Ni", "Te", "Fi", "Se"],  # 内向直觉→外向思考→内向情感→外向实感
    "INTP": ["Ti", "Ne", "Si", "Fe"],  # 内向思考→外向直觉→内向实感→外向情感
    "ENTJ": ["Te", "Ni", "Se", "Fi"],  # 外向思考→内向直觉→外向实感→内向情感
    "ENTP": ["Ne", "Ti", "Fe", "Si"],  # 外向直觉→内向思考→外向情感→内向实感

    # NF系列（外交家）- 情感功能主导
    "INFJ": ["Ni", "Fe", "Ti", "Se"],  # 内向直觉→外向情感→内向思考→外向实感
    "INFP": ["Fi", "Ne", "Si", "Te"],  # 内向情感→外向直觉→内向实感→外向思考
    "ENFJ": ["Fe", "Ni", "Se", "Ti"],  # 外向情感→内向直觉→外向实感→内向思考
    "ENFP": ["Ne", "Fi", "Te", "Si"],  # 外向直觉→内向情感→外向思考→内向实感

    # ST系列（守护者）- 实感+思考
    "ISTJ": ["Si", "Te", "Fi", "Ne"],  # 内向实感→外向思考→内向情感→外向直觉
    "ISFJ": ["Si", "Fe", "Ti", "Ne"],  # 内向实感→外向情感→内向思考→外向直觉
    "ESTJ": ["Te", "Si", "Ne", "Fi"],  # 外向思考→内向实感→外向直觉→内向情感
    "ESFJ": ["Fe", "Si", "Ne", "Ti"],  # 外向情感→内向实感→外向直觉→内向思考

    # SF系列（探险家）- 实感+情感
    "ISTP": ["Ti", "Se", "Ni", "Fe"],  # 内向思考→外向实感→内向直觉→外向情感
    "ISFP": ["Fi", "Se", "Ni", "Te"],  # 内向情感→外向实感→内向直觉→外向思考
    "ESTP": ["Se", "Ti", "Fe", "Ni"],  # 外向实感→内向思考→外向情感→内向直觉
    "ESFP": ["Se", "Fi", "Te", "Ni"],  # 外向实感→内向情感→外向思考→内向直觉
}

# 功能简写全称映射
FUNCTION_FULL_NAMES = {
    "Ni": "内向直觉 (Introverted Intuition)",
    "Ne": "外向直觉 (Extraverted Intuition)",
    "Si": "内向实感 (Introverted Sensing)",
    "Se": "外向实感 (Extraverted Sensing)",
    "Ti": "内向思考 (Introverted Thinking)",
    "Te": "外向思考 (Extraverted Thinking)",
    "Fi": "内向情感 (Introverted Feeling)",
    "Fe": "外向情感 (Extraverted Feeling)",
}

# 功能发育年龄阶段（Beebe 模型）
FUNCTION_DEVELOPMENT_STAGES = {
    "dominant": {"age": "0-6岁", "role": "主导功能 - 核心 identity"},
    "auxiliary": {"age": "6-12岁", "role": "辅助功能 - 支持主导功能"},
    "tertiary": {"age": "12-25岁", "role": "第三功能 - 成长期开始发育"},
    "inferior": {"age": "25-50岁", "role": "劣势功能 - 中年期才可能成熟"},
}

# ==================== MBTI 理论框架验证 ====================

# Keirsey 四大气质理论
KEIRSEY_TEMPERAMENTS = {
    "NT": {"name": "理性主义者(Rationalist)", "traits": ["追求能力", "重视逻辑", "创新导向"]},
    "NF": {"name": "理想主义者(Idealist)", "traits": ["追求意义", "重视和谐", "人文导向"]},
    "ST": {"name": "守护者(Guardian)", "traits": ["追求稳定", "重视传统", "责任导向"]},
    "SF": {"name": "工匠(Artisan)", "traits": ["追求自由", "重视体验", "行动导向"]},
}

# Socionics 双向匹配理论（更精确的匹配模型）
SOCIONICS_MATCHES = {
    "INTJ": {"best": ["ENFP", "ENTP"], "semi_duality": ["INFJ", "INTP"]},
    "INTP": {"best": ["ENTJ", "ENFJ"], "semi_duality": ["INTJ", "ISTP"]},
    "ENTJ": {"best": ["INFP", "INTP"], "semi_duality": ["ENTP", "ESTJ"]},
    "ENTP": {"best": ["INFJ", "INTJ"], "semi_duality": ["ENTJ", "ENFP"]},
    "INFJ": {"best": ["ENFP", "ENTP"], "semi_duality": ["INTJ", "INFP"]},
    "INFP": {"best": ["ENTJ", "ENFJ"], "semi_duality": ["INFJ", "ISFP"]},
    "ENFJ": {"best": ["INFP", "INTP"], "semi_duality": ["ENFP", "ESFJ"]},
    "ENFP": {"best": ["INFJ", "INTJ"], "semi_duality": ["ENFJ", "ENTP"]},
    "ISTJ": {"best": ["ESFP", "ESTP"], "semi_duality": ["ISFJ", "INTJ"]},
    "ISFJ": {"best": ["ESTP", "ESFP"], "semi_duality": ["ISTJ", "INFJ"]},
    "ESTJ": {"best": ["ISFP", "ISTP"], "semi_duality": ["ESFJ", "ENTJ"]},
    "ESFJ": {"best": ["ISTP", "ISFP"], "semi_duality": ["ESTJ", "ENFJ"]},
    "ISTP": {"best": ["ESFJ", "ESTJ"], "semi_duality": ["ISFP", "INTP"]},
    "ISFP": {"best": ["ESTJ", "ESFJ"], "semi_duality": ["ISTP", "INFP"]},
    "ESTP": {"best": ["ISFJ", "ISTJ"], "semi_duality": ["ESFP", "ENTP"]},
    "ESFP": {"best": ["ISTJ", "ISFJ"], "semi_duality": ["ESTP", "ENFP"]},
}

# ==================== 语言表达检查规则 ====================

LANGUAGE_CHECK_RULES = {
    "通顺性": [
        "是否有主谓宾完整句子",
        "是否避免过度使用形容词堆砌",
        "是否避免重复表述",
        "是否逻辑连贯",
    ],
    "易懂性": [
        "是否使用口语化表达而非学术术语",
        "是否避免复杂嵌套句式",
        "是否使用具体场景而非抽象概念",
        "是否使用第一人称'你'而非第三人称",
    ],
    "专业性": [
        "是否准确使用 MBTI 术语",
        "是否避免误导性表述",
        "是否体现成长而非标签化",
        "是否避免性别偏见",
    ],
}

class MBTIProfessionalValidator:
    """MBTI 专业理论验证器"""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.passed = []

    def validate_cognitive_stack(self, type_code: str) -> Dict[str, Any]:
        """验证认知功能栈是否符合荗格理论"""
        result = {"type": type_code, "valid": True, "issues": []}

        # 获取代码中的认知功能栈
        type_info = get_type_info(type_code)
        code_stack = type_info.get("cognitive_stack", "").split("-")

        # 获取理论正确的认知功能栈
        correct_stack = JUNG_COGNITIVE_STACKS.get(type_code, [])

        if not correct_stack:
            result["valid"] = False
            result["issues"].append(f"缺少理论认知功能栈定义")
            return result

        # 验证功能栈长度
        if len(code_stack) != 4:
            result["valid"] = False
            result["issues"].append(f"认知功能栈长度错误: 应为4个功能,实际{len(code_stack)}个")
            return result

        # 验证功能栈顺序
        for i, (code_func, correct_func) in enumerate(zip(code_stack, correct_stack)):
            position = ["主导", "辅助", "第三", "劣势"][i]
            if code_func != correct_func:
                result["valid"] = False
                result["issues"].append(
                    f"{position}功能错误: 代码显示'{code_func}',理论应为'{correct_func}'"
                )

        # 验证功能排列规则（MBTI Beebe 模型）
        # 规则1: 主导与劣势必须互补
        # 互补定义: 同一功能维度（都是感知功能 N/S 或都是判断功能 T/F），但方向相反（i/e）
        # 认知功能表示：第一个字母是功能类型（N/S/T/F），第二个字母是方向（i/e）
        dominant, inferior = code_stack[0], code_stack[3]

        # 正确的索引：[0]是功能类型，[1]是方向
        func1_type = dominant[0]  # N, S, T, F
        func2_type = inferior[0]

        # 方向（第二个字母）
        func1_dir = dominant[1]  # i, e
        func2_dir = inferior[1]

        # 检查是否为同一功能维度（感知维度 N/S 或判断维度 T/F）
        same_perceiving = (func1_type in ['N', 'S'] and func2_type in ['N', 'S'])
        same_judging = (func1_type in ['T', 'F'] and func2_type in ['T', 'F'])

        # 检查方向是否相反
        opposite_dir = (func1_dir == 'i' and func2_dir == 'e') or (func1_dir == 'e' and func2_dir == 'i')

        if not ((same_perceiving or same_judging) and opposite_dir):
            result["valid"] = False
            result["issues"].append(
                f"主导-劣势功能未正确互补: '{dominant}'与'{inferior}'应为同一功能维度但方向相反"
            )

        # 规则2: 辅助与第三必须互补（同样规则）
        auxiliary, tertiary = code_stack[1], code_stack[2]
        aux_type = auxiliary[0]
        tert_type = tertiary[0]
        aux_dir = auxiliary[1]
        tert_dir = tertiary[1]

        same_perceiving_aux = (aux_type in ['N', 'S'] and tert_type in ['N', 'S'])
        same_judging_aux = (aux_type in ['T', 'F'] and tert_type in ['T', 'F'])
        opposite_dir_aux = (aux_dir == 'i' and tert_dir == 'e') or (aux_dir == 'e' and tert_dir == 'i')

        if not ((same_perceiving_aux or same_judging_aux) and opposite_dir_aux):
            result["valid"] = False
            result["issues"].append(
                f"辅助-第三功能未正确互补: '{auxiliary}'与'{tertiary}'应为同一功能维度但方向相反"
            )

        # 规则3: 内向类型必须有一个外向功能，外向类型必须有一个内向功能
        first_letter = type_code[0]
        e_count = sum(1 for f in code_stack if f[1] == "e")
        i_count = sum(1 for f in code_stack if f[1] == "i")

        if first_letter == "I" and e_count != 2:
            result["valid"] = False
            result["issues"].append(f"内向类型应有2个外向功能,实际{e_count}个")
        elif first_letter == "E" and i_count != 2:
            result["valid"] = False
            result["issues"].append(f"外向类型应有2个内向功能,实际{i_count}个")

        return result

    def validate_type_description(self, type_code: str) -> Dict[str, Any]:
        """验证类型描述是否符合 MBTI 理论"""
        result = {"type": type_code, "valid": True, "issues": []}

        type_info = get_type_info(type_code)
        tags = type_info.get("tags", [])
        love_manual = type_info.get("love_manual", {})

        # 验证气质归属
        temperament = type_code[1:3]  # e.g., "NT", "NF", "ST", "SF"
        keirsey_traits = KEIRSEY_TEMPERAMENTS.get(temperament, {}).get("traits", [])

        # 检查标签是否体现气质特征
        if keirsey_traits:
            for trait in keirsey_traits:
                trait_keywords = {
                    "追求能力": ["逻辑", "分析", "思考", "能力"],
                    "重视逻辑": ["逻辑", "理性", "分析"],
                    "创新导向": ["创新", "新想法", "可能性"],
                    "追求意义": ["意义", "价值", "深度"],
                    "重视和谐": ["和谐", "关系", "共情"],
                    "人文导向": ["人", "情感", "理解"],
                    "追求稳定": ["稳定", "靠谱", "承诺"],
                    "重视传统": ["传统", "规矩", "标准"],
                    "责任导向": ["责任", "承诺", "认真"],
                    "追求自由": ["自由", "空间", "随性"],
                    "重视体验": ["体验", "生活", "快乐"],
                    "行动导向": ["行动", "执行", "直接"],
                }
                keywords = trait_keywords.get(trait, [])
                if not any(kw in " ".join(tags) for kw in keywords):
                    result["valid"] = False
                    result["issues"].append(f"标签未体现气质特征: {trait}")

        # 验证成长路径是否符合功能发育理论
        growth_states = type_info.get("growth_states", {})
        if growth_states:
            # 检查是否体现功能发育阶段
            expected_positions = ["growing", "learning", "balanced"]
            for pos in expected_positions:
                if pos not in growth_states:
                    result["valid"] = False
                    result["issues"].append(f"缺少成长阶段: {pos}")

        return result

    def validate_match_theory(self, type_code: str) -> Dict[str, Any]:
        """匹配推荐旧字段已移除，保留空验证以兼容历史脚本。"""
        return {"type": type_code, "valid": True, "issues": []}

    def validate_language_expression(self, type_code: str) -> Dict[str, Any]:
        """验证语言表达是否通顺易懂"""
        result = {"type": type_code, "valid": True, "issues": []}

        type_info = get_type_info(type_code)
        all_text = []

        # 收集所有文本
        all_text.extend(type_info.get("tags", []))
        love_manual = type_info.get("love_manual", {})
        all_text.extend(love_manual.get("strengths", []))
        all_text.extend(love_manual.get("weaknesses", []))

        growth_states = type_info.get("growth_states", {})
        for state, data in growth_states.items():
            all_text.extend(data.get("traits", []))

        # 检查通顺性
        for text in all_text:
            # 过度形容词堆砌检查
            adj_count = len(re.findall(r"(很|非常|极度|特别|超级)", text))
            if adj_count > 2:
                result["valid"] = False
                result["issues"].append(f"过度形容词堆砌: '{text}'")

            # 重复表述检查
            words = text.split()
            if len(words) > 5:
                unique_words = set(words)
                if len(unique_words) < len(words) * 0.6:
                    result["valid"] = False
                    result["issues"].append(f"重复表述: '{text}'")

        # 检查易懂性
        for text in all_text:
            # 学术术语检查
            academic_terms = ["认知功能", "主导功能", "辅助功能", "劣势功能"]
            if any(term in text for term in academic_terms):
                # 允许在专业解释中使用,但建议配合通俗说明
                if "（" not in text and "(" not in text:
                    result["valid"] = False
                    result["issues"].append(f"学术术语缺少通俗解释: '{text}'")

            # 复杂嵌套句式检查
            comma_count = text.count(",")
            if comma_count > 3:
                result["valid"] = False
                result["issues"].append(f"复杂嵌套句式: '{text}'")

        # 检查专业性
        for text in all_text:
            # 误导性表述检查
            misleading_patterns = [
                r"只会.*不会",  # 绝对化表述
                r"永远.*从不",  # 绝对化表述
                r"所有.*都",    # 概括化表述
            ]
            for pattern in misleading_patterns:
                if re.search(pattern, text):
                    result["valid"] = False
                    result["issues"].append(f"误导性绝对表述: '{text}'")

            # 性别偏见检查
            gender_terms = ["男生", "女生", "男人", "女人", "男性", "女性"]
            if any(term in text for term in gender_terms):
                result["valid"] = False
                result["issues"].append(f"性别偏见表述: '{text}'")

        return result

    def validate_all_types(self) -> Dict[str, Any]:
        """验证所有 16 种类型"""
        all_results = {}

        for type_code in JUNG_COGNITIVE_STACKS.keys():
            all_results[type_code] = {
                "cognitive_stack": self.validate_cognitive_stack(type_code),
                "type_description": self.validate_type_description(type_code),
                "match_theory": self.validate_match_theory(type_code),
                "language_expression": self.validate_language_expression(type_code),
            }

            # 统计问题
            total_issues = sum(
                len(r.get("issues", []))
                for r in all_results[type_code].values()
            )

            if total_issues == 0:
                self.passed.append(type_code)
            else:
                self.errors.append(type_code)

        return all_results

    def print_report(self, all_results: Dict[str, Any]):
        """打印验证报告"""
        print("=" * 80)
        print("MBTI 专业理论验证报告")
        print("=" * 80)
        print(f"\n验证类型总数: {len(all_results)}")
        print(f"通过类型数: {len(self.passed)}")
        print(f"问题类型数: {len(self.errors)}")

        if self.passed:
            print(f"\n✅ 通过验证的类型:")
            for t in self.passed:
                print(f"  - {t}")

        if self.errors:
            print(f"\n❌ 发现问题的类型:")
            for t in self.errors:
                print(f"\n  {t}:")
                for category, result in all_results[t].items():
                    if result.get("issues"):
                        print(f"    {category}:")
                        for issue in result["issues"]:
                            print(f"      - {issue}")

        # 详细报告
        print(f"\n{'='*80}")
        print("详细验证结果")
        print(f"{'='*80}")

        for type_code, results in all_results.items():
            print(f"\n{'='*60}")
            print(f"类型: {type_code}")
            print(f"{'='*60}")

            for category, result in results.items():
                status = "✅ 通过" if result["valid"] else "❌ 问题"
                print(f"\n  {category}: {status}")
                if result.get("issues"):
                    for issue in result["issues"]:
                        print(f"    - {issue}")

def main():
    """主函数"""
    print("MBTI 专业理论验证器")
    print("基于荗格人格理论、MBTI 理论框架和语言表达检查")
    print("=" * 80)

    validator = MBTIProfessionalValidator()
    all_results = validator.validate_all_types()
    validator.print_report(all_results)

    # 返回验证状态
    if validator.errors:
        print(f"\n⚠️ 发现 {len(validator.errors)} 个类型存在问题,需要修复")
        return False
    else:
        print(f"\n🎉 所有 16 种 MBTI 类型通过专业理论验证!")
        return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
