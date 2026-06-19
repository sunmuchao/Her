#!/usr/bin/env python3
"""
为5位候选人的Discovery Session生成摘要信息

流程：
1. 将turns表中的对话内容写入memory_items表（摘要生成逻辑从memory_items读取）
2. 调用系统的process_session_end()生成摘要
3. 摘要自动写入her数据库的conversation_summaries表
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# 确保her repo在sys.path中
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# 导入核心模块
from match_domain.session_end_processor import process_session_end
from external_systems.partner_discovery_system.discovery_system.storage import connect_db

# ============================================================================
# 配置
# ============================================================================

DSN = os.environ.get("PARTNER_DISCOVERY_DB") or "mysql://root@127.0.0.1:3307/her_discovery"

# 5位候选人的session信息
SESSIONS = [
    {
        'session_id': 'discovery-session-c9c84cd45881',
        'requester_id': 573,
        'profile_id': 573,
        'name': '李欣琪',
        'attachment': '回避型'
    },
    {
        'session_id': 'discovery-session-3736c5cc27eb',
        'requester_id': 6609,
        'profile_id': 6609,
        'name': '陈佳悦',
        'attachment': '安全型'
    },
    {
        'session_id': 'discovery-session-03812e67508e',
        'requester_id': 3611,
        'profile_id': 3611,
        'name': '冯静雯',
        'attachment': '焦虑型'
    },
    {
        'session_id': 'discovery-session-ff37e68c0df5',
        'requester_id': 2701,
        'profile_id': 2701,
        'name': '张安萌',
        'attachment': '安全型'
    },
    {
        'session_id': 'discovery-session-0f33cf41a7bd',
        'requester_id': 6209,
        'profile_id': 6209,
        'name': '陈以心',
        'attachment': '安全型'
    }
]

# ============================================================================
# Step 1: 将turns写入memory_items
# ============================================================================

def convert_turns_to_memory_items(session_id: str):
    """将turns表中的对话转换为memory_items格式"""
    conn = connect_db(DSN)

    # 查询turns
    rows = conn.execute("""
        SELECT turn_id, request_kind, user_message_text, agent_decision_json, created_at
        FROM discovery_agent_turns
        WHERE session_id = ?
        ORDER BY turn_id ASC
    """, (session_id,)).fetchall()

    memory_items = []

    for row in rows:
        # row是字典格式
        agent_decision = json.loads(str(row.get('agent_decision_json') or '{}'))

        # 用户消息
        user_message = row.get('user_message_text')
        if user_message:
            memory_items.append({
                'role': 'user',
                'content': str(user_message),
                'created_at': str(row.get('created_at'))
            })

        # AI回复
        assistant_message = agent_decision.get('assistant_message')
        if assistant_message:
            memory_items.append({
                'role': 'assistant',
                'content': str(assistant_message),
                'created_at': str(row.get('created_at'))
            })

    conn.close()

    return memory_items

def write_memory_items(session_id: str, memory_items: list):
    """写入memory_items表"""
    if not memory_items:
        print(f"  ⚠️  {session_id} 没有聊天记录，跳过")
        return 0

    conn = connect_db(DSN)

    # 清空旧的memory_items（避免重复）
    conn.execute("""
        DELETE FROM discovery_agent_session_memory_items
        WHERE session_id = ?
    """, (session_id,))

    # 写入新的memory_items
    for item in memory_items:
        item_json = json.dumps(item, ensure_ascii=False)
        conn.execute("""
            INSERT INTO discovery_agent_session_memory_items
            (session_id, item_json, created_at)
            VALUES (?, ?, ?)
        """, (session_id, item_json, item['created_at']))

    conn.commit()
    conn.close()

    return len(memory_items)

# ============================================================================
# Step 2: 生成摘要
# ============================================================================

async def generate_summary_for_session(session: dict):
    """为单个session生成摘要"""
    session_id = session['session_id']
    requester_id = session['requester_id']
    profile_id = session['profile_id']
    name = session['name']

    print(f"\n{'='*60}")
    print(f"处理 {name} 的会话摘要")
    print(f"Session ID: {session_id}")
    print(f"{'='*60}")

    # Step 1: 将turns写入memory_items
    print("Step 1: 将turns转换为memory_items...")
    memory_items = convert_turns_to_memory_items(session_id)
    item_count = write_memory_items(session_id, memory_items)
    print(f"  ✓ 写入 {item_count} 条聊天记录")

    if item_count < 2:
        print("  ⚠️  聊天记录太少，跳过摘要生成")
        return {'status': 'skipped', 'reason': 'no_messages'}

    # Step 2: 调用系统的摘要生成逻辑
    print("Step 2: 调用系统摘要生成逻辑...")
    try:
        result = await process_session_end(
            session_id=session_id,
            requester_id=requester_id,
            profile_id=profile_id,
            conversation_type="discovery",
            dsn=DSN,  # 传递DSN参数，确保能读取memory_items
        )

        if result.get('success'):
            print(f"  ✓ 摘要生成成功")
            print(f"  ✓ 消息数: {result.get('message_count')}")
            print(f"  ✓ 可量化字段: {list(result.get('quantifiable_data', {}).keys())}")
            print(f"  ✓ 不可量化字段: {list(result.get('non_quantifiable_data', {}).keys())}")
            print(f"  ✓ 已保存字段: {result.get('saved_keys', [])}")

            return {
                'status': 'success',
                'summary_data': result.get('summary_data'),
                'message_count': result.get('message_count')
            }
        else:
            print(f"  ✗ 摘要生成失败: {result.get('error')}")
            return {
                'status': 'failed',
                'error': result.get('error'),
                'message': result.get('message')
            }

    except Exception as e:
        print(f"  ✗ 异常: {str(e)}")
        return {
            'status': 'failed',
            'error': 'exception',
            'message': str(e)
        }

# ============================================================================
# 主流程
# ============================================================================

async def main():
    print("\n" + "="*60)
    print("为5位候选人生成Discovery Session摘要")
    print("="*60)

    results = {
        'total': len(SESSIONS),
        'success': 0,
        'failed': 0,
        'skipped': 0,
        'details': []
    }

    for session in SESSIONS:
        result = await generate_summary_for_session(session)

        if result['status'] == 'success':
            results['success'] += 1
        elif result['status'] == 'skipped':
            results['skipped'] += 1
        else:
            results['failed'] += 1

        results['details'].append({
            'name': session['name'],
            'session_id': session['session_id'],
            'attachment': session['attachment'],
            **result
        })

    # 打印总结
    print("\n" + "="*60)
    print("处理完成")
    print("="*60)
    print(f"总数: {results['total']}")
    print(f"成功: {results['success']}")
    print(f"跳过: {results['skipped']}")
    print(f"失败: {results['failed']}")
    print("="*60)

    # 返回详细结果
    return results

if __name__ == '__main__':
    results = asyncio.run(main())

    # 打印详细结果
    print("\n详细结果:")
    for detail in results['details']:
        status_icon = '✓' if detail['status'] == 'success' else '✗' if detail['status'] == 'failed' else '-'
        print(f"{status_icon} {detail['name']} ({detail['attachment']}) | status={detail['status']}")

        if detail['status'] == 'success' and detail.get('summary_data'):
            print(f"  摘要内容:")
            for key, value in detail['summary_data'].items():
                print(f"    - {key}: {value}")

    sys.exit(0 if results['failed'] == 0 else 1)