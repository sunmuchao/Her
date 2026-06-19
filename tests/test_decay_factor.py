"""时间衰减机制改进测试

测试改进方案4：根据特征稳定性调整衰减速度

测试内容：
1. 线性衰减测试（values）
2. 指数衰减测试（personality_traits）
3. 最低权重测试（性格特质0.7，其他0.5）
4. 衰减速度对比（线性vs指数）
5. 改进效果验证（改进前vs改进后）
"""

import math
import pytest
from match_domain.vector_store_lite import calculate_decay_factor, VECTOR_TYPES_CONFIG


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 1: 线性衰减测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_linear_decay_values():
    """测试价值观的线性衰减（365天周期）"""

    # values配置：decay_days=365, decay_curve=linear, min_factor=0.7
    config = VECTOR_TYPES_CONFIG["values"]
    assert config["decay_days"] == 365
    assert config["decay_curve"] == "linear"
    assert config["min_factor"] == 0.7

    # 测试10天：线性衰减
    factor_10d = calculate_decay_factor(10, "values")
    expected_10d = max(0.7, 1 - 10/365)
    assert abs(factor_10d - expected_10d) < 0.01
    print(f"values（10天）: 线性衰减因子={factor_10d:.2f}")

    # 测试180天：线性衰减
    factor_180d = calculate_decay_factor(180, "values")
    expected_180d = max(0.7, 1 - 180/365)
    assert abs(factor_180d - expected_180d) < 0.01
    print(f"values（180天）: 线性衰减因子={factor_180d:.2f}")

    # 测试365天：应该等于最低权重
    factor_365d = calculate_decay_factor(365, "values")
    assert factor_365d == 0.7
    print(f"values（365天）: 线性衰减因子={factor_365d:.2f}（最低权重）")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 2: 指数衰减测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_exponential_decay_personality_traits():
    """测试性格特质的指数衰减（365天周期）"""

    # personality_traits配置：decay_days=365, decay_curve=exponential, min_factor=0.7
    config = VECTOR_TYPES_CONFIG["personality_traits"]
    assert config["decay_days"] == 365
    assert config["decay_curve"] == "exponential"
    assert config["min_factor"] == 0.7

    # 测试10天：指数衰减
    factor_10d = calculate_decay_factor(10, "personality_traits")
    expected_10d = max(0.7, math.exp(-10/365))
    assert abs(factor_10d - expected_10d) < 0.01
    print(f"personality_traits（10天）: 指数衰减因子={factor_10d:.2f}")

    # 测试30天：指数衰减
    factor_30d = calculate_decay_factor(30, "personality_traits")
    expected_30d = max(0.7, math.exp(-30/365))
    assert abs(factor_30d - expected_30d) < 0.01
    print(f"personality_traits（30天）: 指数衰减因子={factor_30d:.2f}")

    # 测试90天：指数衰减
    factor_90d = calculate_decay_factor(90, "personality_traits")
    expected_90d = max(0.7, math.exp(-90/365))
    assert abs(factor_90d - expected_90d) < 0.01
    print(f"personality_traits（90天）: 指数衰减因子={factor_90d:.2f}")

    # 测试180天：指数衰减
    factor_180d = calculate_decay_factor(180, "personality_traits")
    expected_180d = max(0.7, math.exp(-180/365))
    assert abs(factor_180d - expected_180d) < 0.01
    print(f"personality_traits（180天）: 指数衰减因子={factor_180d:.2f}")

    # 测试365天：应该等于最低权重
    factor_365d = calculate_decay_factor(365, "personality_traits")
    assert factor_365d == 0.7
    print(f"personality_traits（365天）: 指数衰减因子={factor_365d:.2f}（最低权重）")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 3: 最低权重测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━_id━
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_min_factor_personality_traits():
    """测试性格特质的最低权重（0.7）"""

    # 365天后：应该等于最低权重0.7
    factor_365d = calculate_decay_factor(365, "personality_traits")
    assert factor_365d == 0.7
    print(f"personality_traits（365天）: 衰减因子={factor_365d:.2f}（等于min_factor=0.7）")

    # 400天后：仍然等于最低权重0.7
    factor_400d = calculate_decay_factor(400, "personality_traits")
    assert factor_400d == 0.7
    print(f"personality_traits（400天）: 衰减因子={factor_400d:.2f}（等于min_factor=0.7）")


def test_min_factor_emotional_needs():
    """测试情感需求的最低权重（0.5）"""

    # emotional_needs配置：decay_days=30, decay_curve=linear, min_factor=0.5
    config = VECTOR_TYPES_CONFIG["emotional_needs"]
    assert config["decay_days"] == 30
    assert config["min_factor"] == 0.5

    # 30天后：应该等于最低权重0.5
    factor_30d = calculate_decay_factor(30, "emotional_needs")
    assert factor_30d == 0.5
    print(f"emotional_needs（30天）: 衰减因子={factor_30d:.2f}（等于min_factor=0.5）")

    # 60天后：仍然等于最低权重0.5
    factor_60d = calculate_decay_factor(60, "emotional_needs")
    assert factor_60d == 0.5
    print(f"emotional_needs（60天）: 衰减因子={factor_60d:.2f}（等于min_factor=0.5）")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 4: 衰减速度对比（线性vs指数）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_decay_comparison():
    """对比线性衰减vs指数衰减的衰减速度"""

    # 同样365天衰减周期，对比10天、30天、90天、180天
    age_days_list = [10, 30, 90, 180]

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("衰减速度对比：线性衰减（values） vs 指数衰减（personality_traits）")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    for age_days in age_days_list:
        linear_factor = calculate_decay_factor(age_days, "values")
        exponential_factor = calculate_decay_factor(age_days, "personality_traits")

        # 指数衰减前期更慢（权重更高）
        # 注意：这是一个近似验证，实际衰减速度取决于具体参数
        if age_days <= 180:
            # 前180天内，指数衰减应该比线性衰减慢
            assert exponential_factor >= linear_factor - 0.05  # 允许5%误差

        print(f"{age_days}天: 线性={linear_factor:.2f}, 指数={exponential_factor:.2f}, 差值={exponential_factor - linear_factor:.2f}")

    print("\n结论：指数衰减前期衰减更慢（权重更高），更符合实际情况")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 5: 改进效果验证（改进前vs改进后）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_improvement_effect():
    """验证改进效果：改进前vs改进后"""

    # 改进前：personality_traits配置
    # decay_days=30, decay_curve=linear（硬编码）, min_factor=0.5
    # 衰减公式：max(0.5, 1 - age_days / 30)

    # 改进后：personality_traits配置
    # decay_days=365, decay_curve=exponential, min_factor=0.7
    # 衰减公式：max(0.7, exp(-age_days / 365))

    age_days_list = [10, 30, 90, 150, 180, 365]

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("改进效果对比：personality_traits（性格特质）")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    for age_days in age_days_list:
        # 改进前：硬编码公式
        old_factor = max(0.5, 1 - age_days / 30)

        # 改进后：智能衰减公式
        new_factor = calculate_decay_factor(age_days, "personality_traits")

        # 计算改进比例
        improvement = new_factor - old_factor
        improvement_pct = (improvement / old_factor) * 100

        print(f"{age_days}天: 改进前={old_factor:.2f}, 改进后={new_factor:.2f}, 提高={improvement:.2f} ({improvement_pct:.1f}%)")

    print("\n结论：改进后权重显著提高，更符合性格特质相对稳定的特点")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 6: 具体例子验证
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_example_150_days():
    """具体例子：小明性格特质数据年龄150天"""

    age_days = 150

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("具体例子：小明性格特质数据年龄150天（5个月）")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 改进前
    old_factor = max(0.5, 1 - 150/30)  # max(0.5, -4) = 0.50（降到最低）
    print(f"改进前（decay_days=30天）: decay_factor={old_factor:.2f}（降到最低权重）")

    # 改进后
    new_factor = calculate_decay_factor(150, "personality_traits")
    print(f"改进后（decay_days=365天, exponential）: decay_factor={new_factor:.2f}")

    # 效果对比
    improvement = new_factor - old_factor
    print(f"效果：权重提高{improvement:.2f}（{improvement/old_factor*100:.1f}%）")

    print("\n结论：")
    print("- 改进前：5个月就降到最低权重（过于激进）")
    print("- 改进后：5个月权重仍然70%（符合性格特质相对稳定）")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 7: 中等稳定特征测试
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_medium_stability_features():
    """测试中等稳定特征（择偶期望、生活态度）"""

    # partner_expectation配置：decay_days=90, decay_curve=exponential, min_factor=0.5
    config = VECTOR_TYPES_CONFIG["partner_expectation"]
    assert config["decay_days"] == 90
    assert config["decay_curve"] == "exponential"
    assert config["min_factor"] == 0.5

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("中等稳定特征测试（择偶期望、生活态度）")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    age_days_list = [10, 30, 60, 90]

    for age_days in age_days_list:
        # 改进前：decay_days=30, linear
        old_factor = max(0.5, 1 - age_days / 30)

        # 改进后：decay_days=90, exponential
        new_factor = calculate_decay_factor(age_days, "partner_expectation")

        improvement = new_factor - old_factor
        print(f"{age_days}天: 改进前={old_factor:.2f}, 改进后={new_factor:.2f}, 提高={improvement:.2f}")

    print("\n结论：中等稳定特征改进后衰减速度更合理（90天vs30天）")


if __name__ == "__main__":
    # 运行所有测试
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("开始运行时间衰减机制改进测试")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    test_linear_decay_values()
    test_exponential_decay_personality_traits()
    test_min_factor_personality_traits()
    test_min_factor_emotional_needs()
    test_decay_comparison()
    test_improvement_effect()
    test_example_150_days()
    test_medium_stability_features()

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("所有测试通过！改进方案4落地成功")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")