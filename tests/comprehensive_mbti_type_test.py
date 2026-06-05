"""全面测试所有16种MBTI类型的表述一致性

测试目标:
1. 验证每种类型的维度表述与类型代码一致
2. 检查是否存在表述矛盾的情况
3. 测试所有边界值和中间值组合
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assessment.mbti_questions import (
    calculate_all_scores,
    _type_code_from_scores,
    get_type_info,
    _build_professional_dimension_summary,
    get_dimension_feedback,
    DIMENSION_NAMES,
    xiaoya_message_from_result,
)

# 定义所有16种MBTI类型及其典型分数范围
# 注意: S代表实感(Sensing),分数>=50; N代表直觉(Intuition),分数<50
MBTI_TYPES = {
    # 分析家系列 (NT)
    "INTJ": {"ei": 30, "sn": 30, "tf": 70, "jp": 70},  # I+N+T+J (N: sn<50)
    "INTP": {"ei": 30, "sn": 30, "tf": 70, "jp": 30},  # I+N+T+P
    "ENTJ": {"ei": 70, "sn": 30, "tf": 70, "jp": 70},  # E+N+T+J (N: sn<50)
    "ENTP": {"ei": 70, "sn": 30, "tf": 70, "jp": 30},  # E+N+T+P

    #外交家系列 (NF)
    "INFJ": {"ei": 30, "sn": 30, "tf": 30, "jp": 70},  # I+N+F+J
    "INFP": {"ei": 30, "sn": 30, "tf": 30, "jp": 30},  # I+N+F+P
    "ENFJ": {"ei": 70, "sn": 30, "tf": 30, "jp": 70},  # E+N+F+J
    "ENFP": {"ei": 70, "sn": 30, "tf": 30, "jp": 30},  # E+N+F+P

    # 守卫者系列 (SJ)
    "ISTJ": {"ei": 30, "sn": 70, "tf": 70, "jp": 70},  # I+S+T+J (S: sn>=50)
    "ISFJ": {"ei": 30, "sn": 70, "tf": 30, "jp": 70},  # I+S+F+J
    "ESTJ": {"ei": 70, "sn": 70, "tf": 70, "jp": 70},  # E+S+T+J
    "ESFJ": {"ei": 70, "sn": 70, "tf": 30, "jp": 70},  # E+S+F+J

    # 探险家系列 (SP)
    "ISTP": {"ei": 30, "sn": 70, "tf": 70, "jp": 30},  # I+S+T+P
    "ISFP": {"ei": 30, "sn": 70, "tf": 30, "jp": 30},  # I+S+F+P
    "ESTP": {"ei": 70, "sn": 70, "tf": 70, "jp": 30},  # E+S+T+P
    "ESFP": {"ei": 70, "sn": 70, "tf": 30, "jp": 30},  # E+S+F+P
}

def verify_dimension_consistency(type_code, scores):
    """验证维度表述与类型代码的一致性"""
    issues = []

    # 解析类型代码
    e_or_i = type_code[0]  # E或I
    s_or_n = type_code[1]  # S或N
    t_or_f = type_code[2]  # T或F
    j_or_p = type_code[3]  # J或P

    # 验证EI维度
    ei_score = scores['ei']
    ei_expected = 'E' if ei_score >= 50 else 'I'
    if e_or_i != ei_expected:
        issues.append(f"EI维度矛盾: 类型代码显示{e_or_i},但分数{ei_score}应该显示{ei_expected}")

    # 验证SN维度(关键!)
    sn_score = scores['sn']
    sn_expected = 'S' if sn_score >= 50 else 'N'
    if s_or_n != sn_expected:
        issues.append(f"SN维度矛盾: 类型代码显示{s_or_n},但分数{sn_score}应该显示{sn_expected}")

    # 检查维度表述是否与代码一致
    dimension_summary = _build_professional_dimension_summary(scores)
    sn_description = dimension_summary[1]  # 第二条是SN维度

    # SN维度表述检查
    if s_or_n == 'S':  # 实感型
        if '现实细节' not in sn_description and '实感' not in sn_description:
            issues.append(f"SN表述错误: 类型是S(实感),但表述'{sn_description}'没有提到现实细节")
        if '直觉' in sn_description or '可能性' in sn_description and '现实细节' not in sn_description:
            issues.append(f"SN表述矛盾: 类型是S(实感),但表述'{sn_description}'提到直觉/可能性")
    else:  # N型(直觉型)
        if '直觉' not in sn_description and '可能性' not in sn_description and '感觉' not in sn_description:
            issues.append(f"SN表述错误: 类型是N(直觉),但表述'{sn_description}'没有提到直觉/可能性")
        if '现实细节' in sn_description and '直觉' not in sn_description:
            issues.append(f"SN表述矛盾: 类型是N(直觉),但表述'{sn_description}'提到现实细节")

    # 验证TF维度
    tf_score = scores['tf']
    tf_expected = 'T' if tf_score >= 50 else 'F'
    if t_or_f != tf_expected:
        issues.append(f"TF维度矛盾: 类型代码显示{t_or_f},但分数{tf_score}应该显示{tf_expected}")

    # TF维度表述检查
    tf_description = dimension_summary[2]  # 第三条是TF维度
    if t_or_f == 'T':  # 思考型
        if '逻辑' not in tf_description and '标准' not in tf_description:
            issues.append(f"TF表述错误: 类型是T(思考),但表述'{tf_description}'没有提到逻辑/标准")
    else:  # F型(情感型)
        if '感受' not in tf_description and '关系' not in tf_description:
            issues.append(f"TF表述错误: 类型是F(情感),但表述'{tf_description}'没有提到感受/关系")

    # 验证JP维度
    jp_score = scores['jp']
    jp_expected = 'J' if jp_score >= 50 else 'P'
    if j_or_p != jp_expected:
        issues.append(f"JP维度矛盾: 类型代码显示{j_or_p},但分数{jp_score}应该显示{jp_expected}")

    # JP维度表述检查
    jp_description = dimension_summary[3]  # 第四条是JP维度
    if j_or_p == 'J':  # 判断型
        if '节奏' not in jp_description and '对齐' not in jp_description:
            issues.append(f"JP表述错误: 类型是J(判断),但表述'{jp_description}'没有提到节奏/对齐")
    else:  # P型(知觉型)
        if '感觉' not in jp_description and '发展' not in jp_description:
            issues.append(f"JP表述错误: 类型是P(知觉),但表述'{jp_description}'没有提到感觉/发展")

    return issues

def test_all_mbti_types():
    """测试所有16种MBTI类型"""
    print("=" * 80)
    print("全面测试所有16种MBTI类型的表述一致性")
    print("=" * 80)

    all_issues = {}
    success_count = 0

    for type_code, scores in MBTI_TYPES.items():
        print(f"\n{'='*60}")
        print(f"测试类型: {type_code}")
        print(f"{'='*60}")

        # 计算类型代码
        calculated_type = _type_code_from_scores(scores)
        print(f"  分数设置: EI={scores['ei']}, SN={scores['sn']}, TF={scores['tf']}, JP={scores['jp']}")
        print(f"  计算类型: {calculated_type}")

        # 检查类型代码是否匹配
        if calculated_type != type_code:
            print(f"  ❌ 类型代码不匹配! 预期{type_code}, 实际{calculated_type}")
            all_issues[type_code] = ["类型代码不匹配"]
            continue

        # 获取维度总结
        dimension_summary = _build_professional_dimension_summary(scores)
        print(f"  维度总结:")
        for i, item in enumerate(dimension_summary, 1):
            print(f"    {i}. {item}")

        # 获取维度反馈
        print(f"  维度反馈:")
        for dim in ['ei', 'sn', 'tf', 'jp']:
            feedback = get_dimension_feedback(dim, scores[dim])
            print(f"    {dim}({scores[dim]}分): {feedback}")

        # 验证一致性
        issues = verify_dimension_consistency(type_code, scores)

        if issues:
            print(f"  ❌ 发现问题:")
            for issue in issues:
                print(f"    - {issue}")
            all_issues[type_code] = issues
        else:
            print(f"  ✅ 表述一致,无问题")
            success_count += 1

    # 总结
    print(f"\n{'='*80}")
    print(f"测试总结")
    print(f"{'='*80}")
    print(f"成功类型: {success_count}/16")

    if all_issues:
        print(f"\n⚠️ 发现问题的类型({len(all_issues)}个):")
        for type_code, issues in all_issues.items():
            print(f"\n{type_code}:")
            for issue in issues:
                print(f"  - {issue}")
        return False
    else:
        print(f"\n🎉 所有16种MBTI类型表述一致!")
        return True

def test_boundary_cases():
    """测试边界值情况"""
    print(f"\n{'='*80}")
    print(f"测试边界值情况")
    print(f"{'='*80}")

    # 测试1: SN维度边界值(49分 vs 50分)
    print(f"\n1️⃣ SN维度边界值测试")

    # 49分应该是N(直觉)
    scores_49 = {'ei': 50, 'sn': 49, 'tf': 50, 'jp': 50}
    type_49 = _type_code_from_scores(scores_49)
    dim_sum_49 = _build_professional_dimension_summary(scores_49)
    print(f"  SN=49分:")
    print(f"    类型代码: {type_49} (第2字母: {type_49[1]})")
    print(f"    应该是: N(直觉),因为<50")
    print(f"    表述: {dim_sum_49[1]}")

    if type_49[1] != 'N':
        print(f"    ❌ 错误! 49分应该判定为N")
    elif '直觉' not in dim_sum_49[1] and '可能性' not in dim_sum_49[1]:
        print(f"    ❌ 表述错误! N型应该提到直觉/可能性")
    else:
        print(f"    ✅ 正确")

    # 50分应该是S(实感)
    scores_50 = {'ei': 50, 'sn': 50, 'tf': 50, 'jp': 50}
    type_50 = _type_code_from_scores(scores_50)
    dim_sum_50 = _build_professional_dimension_summary(scores_50)
    print(f"\n  SN=50分:")
    print(f"    类型代码: {type_50} (第2字母: {type_50[1]})")
    print(f"    应该是: S(实感),因为>=50")
    print(f"    表述: {dim_sum_50[1]}")

    if type_50[1] != 'S':
        print(f"    ❌ 错误! 50分应该判定为S")
    elif '现实细节' not in dim_sum_50[1]:
        print(f"    ❌ 表述错误! S型应该提到现实细节")
    else:
        print(f"    ✅ 正确")

    # 测试2: SN维度表述与N型T型的关系
    print(f"\n2️⃣ SN维度与TF维度的交互测试")

    # N型+T型:应该提到"思维的共鸣"或"未来的可能性"
    scores_nt = {'ei': 50, 'sn': 30, 'tf': 70, 'jp': 50}
    dim_sum_nt = _build_professional_dimension_summary(scores_nt)
    print(f"  N型(30分)+T型(70分):")
    print(f"    SN表述: {dim_sum_nt[1]}")
    print(f"    应该体现: 思维共鸣或未来可能性(T型影响N型)")

    if '思维的共鸣' in dim_sum_nt[1] or '未来的可能性' in dim_sum_nt[1]:
        print(f"    ✅ 正确体现T型影响")
    else:
        print(f"    ⚠️ 没有体现T型对N型的影响")

    # N型+F型:应该只提到"感觉和可能性"
    scores_nf = {'ei': 50, 'sn': 30, 'tf': 30, 'jp': 50}
    dim_sum_nf = _build_professional_dimension_summary(scores_nf)
    print(f"\n  N型(30分)+F型(30分):")
    print(f"    SN表述: {dim_sum_nf[1]}")
    print(f"    应该体现: 感觉和可能性(F型不影响N型)")

    if '思维的共鸣' in dim_sum_nf[1]:
        print(f"    ❌ 错误! F型不应该提到思维共鸣")
    else:
        print(f"    ✅ 正确")

    return True

if __name__ == "__main__":
    print("MBTI类型全面发散测试")
    print("=" * 80)

    success_count = 0
    total_tests = 2

    # 测试所有16种类型
    if test_all_mbti_types():
        success_count += 1

    # 测试边界值
    if test_boundary_cases():
        success_count += 1

    print(f"\n{'='*80}")
    print(f"最终总结")
    print(f"{'='*80}")
    print(f"成功测试: {success_count}/{total_tests}")

    if success_count == total_tests:
        print(f"\n🎉 所有MBTI类型和边界值测试通过!")
    else:
        print(f"\n⚠️ 发现问题,需要修复")
        sys.exit(1)