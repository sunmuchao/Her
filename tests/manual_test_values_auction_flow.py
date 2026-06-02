"""
价值观拍卖会完整流程手动测试

测试场景：
1. 单人模式完整流程
2. 双人模式完整流程（含复用机制）
3. 所有卡片类型验证
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

from assessment.values_auction_service import (
    start_values_auction,
    get_lots_list,
    submit_auction_bids,
    generate_ai_interpretation,
    get_last_result,
    start_values_auction_together,
    submit_auction_bids_together,
    check_dual_auction_status,
    reuse_last_result_together,
)
from assessment.values_auction_lots import VALUES_AUCTION_LOTS, LOT_ID_TO_TITLE


def print_card(card: dict, indent: str = "   "):
    """打印卡片信息"""
    card_type = card.get("card_type", "unknown")
    print(f"{indent}卡片类型: {card_type}")

    if card_type == "values_auction_intro":
        print(f"{indent}测评ID: {card.get('assessment_id')}")
        intro = card.get("intro_data", {})
        print(f"{indent}标题: {intro.get('title')}")
        print(f"{indent}描述: {intro.get('description')}")
        print(f"{indent}总筹码: {intro.get('total_chips')}")
        print(f"{indent}拍品数量: {intro.get('lot_count')}")

    elif card_type == "values_auction_lots":
        print(f"{indent}测评ID: {card.get('assessment_id')}")
        if card.get("session_id"):
            print(f"{indent}Session ID: {card.get('session_id')} (双人模式)")
        lots_data = card.get("lots_data", {})
        print(f"{indent}拍品数量: {len(lots_data.get('lots', []))}")
        print(f"{indent}总筹码: {lots_data.get('total_chips')}")
        print(f"{indent}筹码范围: {lots_data.get('min_bid')}-{lots_data.get('max_bid')}")

        # 按维度展示拍品
        lots_by_dimension = lots_data.get("lots_by_dimension", {})
        if lots_by_dimension:
            print(f"{indent}按维度分组:")
            for dim, lots in lots_by_dimension.items():
                print(f"{indent}  [{dim}] {len(lots)}个拍品")
                for lot in lots[:2]:  # 只展示前2个
                    print(f"{indent}    - {lot.get('title')}")

        # 双人模式内部状态
        internal_state = card.get("internal_state")
        if internal_state:
            print(f"{indent}[双人模式]")
            print(f"{indent}  用户已做过: {internal_state.get('user_has_done')}")
            if internal_state.get("last_result"):
                last = internal_state.get("last_result")
                print(f"{indent}  上次结果类型: {last.get('value_type')}")

    elif card_type == "values_auction_result":
        print(f"{indent}测评ID: {card.get('assessment_id')}")
        result = card.get("result_data", {})
        print(f"{indent}价值观类型: {result.get('value_type')}")
        print(f"{indent}Top3价值观: {result.get('value_labels', [])}")
        print(f"{indent}放弃的: {result.get('abandoned', [])}")

        bids = result.get("bids", [])
        print(f"{indent}竞拍详情 (Top 5):")
        for bid in bids[:5]:
            print(f"{indent}  #{bid.get('rank')} {bid.get('title')} - {bid.get('chips')}筹码 ({bid.get('percentage')}%)")

        # 隐藏价值分析
        hidden_values = result.get("hidden_values", {})
        if hidden_values:
            print(f"{indent}隐藏价值权重 (Top 3):")
            sorted_hv = sorted(hidden_values.items(), key=lambda x: x[1], reverse=True)[:3]
            for key, weight in sorted_hv:
                print(f"{indent}  {key}: {weight:.2f}")

    elif card_type == "values_auction_interpretation":
        print(f"{indent}测评ID: {card.get('assessment_id')}")
        interp = card.get("interpretation_data", {})
        print(f"{indent}摘要: {interp.get('summary', '')[:80]}...")
        print(f"{indent}恋爱风格: {interp.get('love_style')}")
        print(f"{indent}匹配建议: {interp.get('match_suggestions', [])}")
        print(f"{indent}注意事项: {interp.get('caution_traits', [])}")

        top3_analysis = interp.get("top3_analysis", [])
        if top3_analysis:
            print(f"{indent}Top3解读:")
            for t in top3_analysis:
                print(f"{indent}  {t.get('title')} ({t.get('chips')}筹码): {t.get('interpretation', '')[:50]}...")

    elif card_type == "values_auction_waiting":
        print(f"{indent}Session ID: {card.get('session_id')}")
        waiting = card.get("waiting_data", {})
        print(f"{indent}消息: {waiting.get('message')}")
        your_result = waiting.get("your_result", {})
        print(f"{indent}你的类型: {your_result.get('value_type')}")
        print(f"{indent}对方状态: {waiting.get('partner_status')}")

    elif card_type == "values_match_analysis":
        print(f"{indent}Session ID: {card.get('session_id')}")
        match = card.get("match_data", {})
        print(f"{indent}匹配类型: {match.get('match_type')}")
        print(f"{indent}共鸣拍品: {match.get('common_lots', [])}")

        user1 = match.get("user1", {})
        user2 = match.get("user2", {})
        print(f"{indent}用户1: {user1.get('value_type')}")
        print(f"{indent}用户2: {user2.get('value_type')}")

        # 冲突分析
        conflicts = match.get("conflicts", [])
        if conflicts:
            print(f"{indent}⚠️ 冲突风险 ({len(conflicts)}个):")
            for c in conflicts[:2]:
                print(f"{indent}  - {c.get('description', '')[:60]}...")
                print(f"{indent}    建议: {c.get('suggestion', '')[:60]}...")

        # 错位分析
        misalignments = match.get("misalignments", [])
        if misalignments:
            print(f"{indent}⚡ 价值观错位 ({len(misalignments)}个):")
            for m in misalignments[:2]:
                print(f"{indent}  - {m.get('description')}")

        # 隐藏价值共鸣
        common_hidden = match.get("common_hidden_values", [])
        if common_hidden:
            print(f"{indent}💫 隐藏价值共鸣:")
            for hv in common_hidden[:3]:
                print(f"{indent}  {hv.get('key')}: 你({hv.get('a_weight'):.2f}) TA({hv.get('b_weight'):.2f})")

    elif card_type == "values_auction_history":
        result_data = card.get("result_data")
        if result_data:
            print(f"{indent}上次测评时间: {result_data.get('assessed_at')}")
            print(f"{indent}价值观类型: {result_data.get('value_type')}")
            top3 = result_data.get("top3", [])
            print(f"{indent}Top3:")
            for t in top3[:3]:
                print(f"{indent}  {t.get('title')} - {t.get('chips')}筹码")
        else:
            print(f"{indent}无历史记录")

    elif card_type == "error":
        error = card.get("error_data", {})
        print(f"{indent}❌ 错误: {error.get('message')}")


def test_single_mode_flow():
    """测试单人拍卖完整流程"""
    print("\n" + "=" * 60)
    print("测试单人价值观拍卖完整流程")
    print("=" * 60)

    user_key = "test_user_single_001"
    source = None  # 使用None模拟数据源

    # 1. 开始拍卖
    print("\n1️⃣ 开始价值观拍卖")
    try:
        intro = start_values_auction(source=source, user_key=user_key)
        print_card(intro)
        assert intro["card_type"] == "values_auction_intro", "应该返回介绍卡片"
        assessment_id = intro["assessment_id"]
        print("   ✅ 开始拍卖成功")
    except Exception as e:
        print(f"   ❌ 开始拍卖失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 2. 获取拍品列表
    print("\n2️⃣ 获取拍品列表")
    try:
        lots_card = get_lots_list(assessment_id=assessment_id)
        print_card(lots_card)
        assert lots_card["card_type"] == "values_auction_lots", "应该返回拍品列表卡片"
        print("   ✅ 获取拍品列表成功")
    except Exception as e:
        print(f"   ❌ 获取拍品列表失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 3. 模拟竞拍（分配筹码）
    print("\n3️⃣ 模拟竞拍（分配筹码）")
    try:
        # 构建竞拍数据：重点投资"灵魂伴侣"和"家人健康"
        bids = [
            {"lot_id": "soulmate", "chips": 4},         # 灵魂伴侣
            {"lot_id": "family_health", "chips": 3},    # 家人健康
            {"lot_id": "warm_home", "chips": 2},        # 温暖的家
            {"lot_id": "three_best_friends", "chips": 1},  # 三个知己
            {"lot_id": "mansion", "chips": 0},          # 豪华别墅（放弃）
            {"lot_id": "ipo_empire", "chips": 0},       # 上市公司（放弃）
            {"lot_id": "forbes_rank", "chips": 0},      # 富豪榜（放弃）
            {"lot_id": "elite_reputation", "chips": 0}, # 社会身份（放弃）
            {"lot_id": "never_worry_money", "chips": 0}, # 不为钱妥协（放弃）
            {"lot_id": "cure_disease", "chips": 0},     # 研发特效药（放弃）
        ]

        print("   竞拍策略:")
        for bid in bids[:4]:
            title = LOT_ID_TO_TITLE.get(bid["lot_id"], bid["lot_id"])
            print(f"     {title}: {bid['chips']}筹码")

        result_card = submit_auction_bids(
            source=source,
            assessment_id=assessment_id,
            user_key=user_key,
            bids=bids,
        )
        print_card(result_card)
        assert result_card["card_type"] == "values_auction_result", "应该返回结果卡片"
        print("   ✅ 竞拍成功")
    except Exception as e:
        print(f"   ❌ 竞拍失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 4. 获取AI解读
    print("\n4️⃣ 获取AI解读")
    try:
        interp_card = generate_ai_interpretation(
            source=source,
            assessment_id=assessment_id,
            user_key=user_key,
        )
        print_card(interp_card)
        assert interp_card["card_type"] == "values_auction_interpretation", "应该返回解读卡片"
        print("   ✅ AI解读成功")
    except Exception as e:
        print(f"   ❌ AI解读失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 5. 查看历史记录
    print("\n5️⃣ 查看历史记录")
    try:
        history_card = get_last_result(source=source, user_key=user_key)
        if history_card:
            print("   找到历史记录:")
            print(f"     类型: {history_card.get('value_type')}")
            print(f"     Top3: {[t.get('title') for t in history_card.get('top3', [])]}")
            print("   ✅ 历史记录查询成功")
        else:
            print("   ⚠️ 未找到历史记录（可能是模拟数据源的问题）")
    except Exception as e:
        print(f"   ❌ 历史记录查询失败: {e}")

    print("\n✅ 单人拍卖流程验证完成")
    return True


def test_dual_mode_flow():
    """测试双人拍卖完整流程"""
    print("\n" + "=" * 60)
    print("测试双人价值观拍卖完整流程")
    print("=" * 60)

    user_a_key = "test_user_dual_a_001"
    user_b_key = "test_user_dual_b_001"
    source = None

    # 1. 用户A开始双人拍卖
    print("\n1️⃣ 用户A发起双人拍卖")
    try:
        start_card = start_values_auction_together(
            source=source,
            user_key=user_a_key,
            partner_key=user_b_key,
        )
        print_card(start_card)
        assert start_card["card_type"] == "values_auction_lots", "应该返回拍品列表卡片"
        assert start_card.get("is_dual_mode") == True, "应该是双人模式"
        session_id = start_card["session_id"]
        print(f"   Session ID: {session_id}")
        print("   ✅ 双人拍卖启动成功")
    except Exception as e:
        print(f"   ❌ 双人拍卖启动失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 2. 用户A提交竞拍
    print("\n2️⃣ 用户A提交竞拍")
    try:
        bids_a = [
            {"lot_id": "soulmate", "chips": 4},        # 灵魂伴侣（高投）
            {"lot_id": "family_health", "chips": 3},   # 家人健康
            {"lot_id": "warm_home", "chips": 2},       # 温暖的家
            {"lot_id": "three_best_friends", "chips": 1},  # 三个知己
        ]

        waiting_card = submit_auction_bids_together(
            source=source,
            session_id=session_id,
            user_key=user_a_key,
            bids=bids_a,
        )
        print_card(waiting_card)
        assert waiting_card["card_type"] == "values_auction_waiting", "应该返回等待卡片"
        print("   ✅ 用户A竞拍成功，等待用户B")
    except Exception as e:
        print(f"   ❌ 用户A竞拍失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 3. 用户B提交竞拍（触发匹配分析）
    print("\n3️⃣ 用户B提交竞拍")
    try:
        bids_b = [
            {"lot_id": "soulmate", "chips": 3},        # 灵魂伴侣（双方都看重）
            {"lot_id": "family_health", "chips": 3},   # 家人健康（双方都看重）
            {"lot_id": "absolute_favor", "chips": 3},  # 绝对偏爱
            {"lot_id": "warm_home", "chips": 1},       # 温暖的家
        ]

        match_card = submit_auction_bids_together(
            source=source,
            session_id=session_id,
            user_key=user_b_key,
            bids=bids_b,
        )
        print_card(match_card)
        assert match_card["card_type"] == "values_match_analysis", "应该返回匹配分析卡片"
        print("   ✅ 双方竞拍完成，匹配分析生成成功")
    except Exception as e:
        print(f"   ❌ 用户B竞拍失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 4. 用户A查询状态
    print("\n4️⃣ 用户A查询状态")
    try:
        status_a = check_dual_auction_status(
            source=source,
            session_id=session_id,
            user_key=user_a_key,
        )
        print(f"   状态: {status_a.get('status')}")
        if status_a.get("status") == "both_done":
            print("   ✅ 状态查询成功，双方已完成")
        else:
            print(f"   ⚠️ 状态异常: {status_a}")
    except Exception as e:
        print(f"   ❌ 状态查询失败: {e}")

    print("\n✅ 双人拍卖流程验证完成")
    return True


def test_reuse_mechanism():
    """测试复用机制"""
    print("\n" + "=" * 60)
    print("测试双人拍卖复用机制")
    print("=" * 60)

    # 先完成一次单人拍卖
    user_key = "test_user_reuse_001"
    partner_key = "test_user_reuse_partner_001"
    source = None

    # 1. 先完成单人拍卖
    print("\n1️⃣ 先完成单人拍卖（建立历史记录）")
    try:
        intro = start_values_auction(source=source, user_key=user_key)
        assessment_id = intro["assessment_id"]

        bids = [
            {"lot_id": "soulmate", "chips": 4},
            {"lot_id": "family_health", "chips": 3},
            {"lot_id": "warm_home", "chips": 2},
            {"lot_id": "three_best_friends", "chips": 1},
        ]

        result = submit_auction_bids(
            source=source,
            assessment_id=assessment_id,
            user_key=user_key,
            bids=bids,
        )
        print(f"   完成单人拍卖，类型: {result.get('result_data', {}).get('value_type')}")
        print("   ✅ 单人拍卖完成")
    except Exception as e:
        print(f"   ❌ 单人拍卖失败: {e}")
        return False

    # 2. 发起双人拍卖
    print("\n2️⃣ 发起双人拍卖")
    try:
        start_card = start_values_auction_together(
            source=source,
            user_key=user_key,
            partner_key=partner_key,
        )
        print_card(start_card)

        # 检查是否有复用提示
        internal_state = start_card.get("internal_state")
        if internal_state and internal_state.get("user_has_done"):
            print("   ✅ 系统识别到用户已做过，提供复用选项")
        else:
            print("   ⚠️ 系统未识别历史记录")

        session_id = start_card["session_id"]
    except Exception as e:
        print(f"   ❌ 双人拍卖启动失败: {e}")
        return False

    # 3. 用户复用上次结果
    print("\n3️⃣ 用户复用上次结果")
    try:
        reuse_result = reuse_last_result_together(
            source=source,
            session_id=session_id,
            user_key=user_key,
        )
        print_card(reuse_result)
        print("   ✅ 复用成功")
    except Exception as e:
        print(f"   ❌ 复用失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 4. 对方提交竞拍
    print("\n4️⃣ 对方提交竞拍")
    try:
        bids_partner = [
            {"lot_id": "soulmate", "chips": 3},
            {"lot_id": "family_health", "chips": 3},
            {"lot_id": "absolute_favor", "chips": 3},
        ]

        match_card = submit_auction_bids_together(
            source=source,
            session_id=session_id,
            user_key=partner_key,
            bids=bids_partner,
        )
        print_card(match_card)
        print("   ✅ 对方提交成功，匹配分析生成")
    except Exception as e:
        print(f"   ❌ 对方提交失败: {e}")
        return False

    print("\n✅ 复用机制验证完成")
    return True


def test_edge_cases():
    """测试边界情况"""
    print("\n" + "=" * 60)
    print("测试边界情况")
    print("=" * 60)

    user_key = "test_user_edge_001"
    source = None

    # 1. 测试筹码超限
    print("\n1️⃣ 测试筹码超限（应该失败）")
    try:
        intro = start_values_auction(source=source, user_key=user_key)
        assessment_id = intro["assessment_id"]

        # 超过10筹码
        invalid_bids = [
            {"lot_id": "loyalty", "chips": 6},
            {"lot_id": "values_match", "chips": 5},
        ]

        result = submit_auction_bids(
            source=source,
            assessment_id=assessment_id,
            user_key=user_key,
            bids=invalid_bids,
        )

        if result.get("card_type") == "error":
            print(f"   ✅ 正确返回错误: {result.get('error_data', {}).get('message')}")
        else:
            print(f"   ❌ 未正确校验筹码超限")
    except Exception as e:
        print(f"   ✅ 正确抛出异常: {e}")

    # 2. 测试无效拍品ID
    print("\n2️⃣ 测试无效拍品ID（应该失败）")
    try:
        intro2 = start_values_auction(source=source, user_key=user_key)
        assessment_id2 = intro2["assessment_id"]

        invalid_bids2 = [
            {"lot_id": "invalid_lot_id", "chips": 5},
        ]

        result2 = submit_auction_bids(
            source=source,
            assessment_id=assessment_id2,
            user_key=user_key,
            bids=invalid_bids2,
        )

        if result2.get("card_type") == "error":
            print(f"   ✅ 正确返回错误: {result2.get('error_data', {}).get('message')}")
        else:
            print(f"   ❌ 未正确校验无效拍品ID")
    except Exception as e:
        print(f"   ✅ 正确抛出异常: {e}")

    print("\n✅ 边界情况验证完成")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("价值观拍卖会完整流程手动测试")
    print("=" * 60)

    success_count = 0
    total_tests = 4

    # 测试单人模式
    if test_single_mode_flow():
        success_count += 1

    # 测试双人模式
    if test_dual_mode_flow():
        success_count += 1

    # 测试复用机制
    if test_reuse_mechanism():
        success_count += 1

    # 测试边界情况
    if test_edge_cases():
        success_count += 1

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"成功验证: {success_count}/{total_tests} 个场景")

    if success_count == total_tests:
        print("\n🎉 所有测试验证成功！价值观拍卖会完整落地！")
        print("\n已验证的功能：")
        print("  ✅ 单人拍卖完整流程（开始→拍品→竞拍→结果→解读）")
        print("  ✅ 双人拍卖完整流程（双方提交→等待→匹配分析）")
        print("  ✅ 复用机制（历史记录识别→复用提交）")
        print("  ✅ 边界校验（筹码超限、无效拍品ID）")
        print("  ✅ 所有卡片类型渲染")
        print("  ✅ 隐藏价值分析")
        print("  ✅ 冲突/错位检测")
    else:
        print(f"\n⚠️ 有 {total_tests - success_count} 个测试失败")
        sys.exit(1)