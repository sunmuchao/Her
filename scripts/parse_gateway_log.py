#!/usr/bin/env python3
"""解析gateway日志，定位性别过滤失效的根因

目标：找到Agent调用search_partner_candidates工具时的criteria_json参数
"""

import json
import re
from pathlib import Path

LOG_FILE = Path("/Users/sunmuchao/Downloads/Her/.run/logs/gateway.log")

# 测试session ID
SESSION_ID = "discovery-session-0889b212e3a8"

print(f"【解析日志文件】{LOG_FILE}")
print(f"【目标Session】{SESSION_ID}")
print("=" * 80)

# 查找该session的所有日志
session_logs = []

with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if SESSION_ID in line:
            session_logs.append(line.strip())

print(f"\n找到 {len(session_logs)} 条相关日志")

# 查找关键日志
print("\n【关键日志1】搜索开始时的criteria参数")
print("=" * 80)
for log in session_logs:
    if "【搜索开始】" in log:
        print(log)
        # 提取criteria参数
        match = re.search(r"criteria=({[^}]*})", log)
        if match:
            criteria_str = match.group(1)
            print(f"\n提取的criteria参数: {criteria_str}")
            try:
                criteria = json.loads(criteria_str)
                print(f"解析后的criteria字典: {json.dumps(criteria, ensure_ascii=False, indent=2)}")
                if criteria == {}:
                    print("\n❌ **根本原因找到**：criteria是空字典！")
                    print("这说明Agent没有正确提取用户消息中的条件（性别、年龄、城市）")
            except Exception as e:
                print(f"解析失败: {e}")
        break

# 查找Agent调用工具的日志
print("\n【关键日志2】Agent调用工具的参数")
print("=" * 80)
for log in session_logs:
    if "tool_name" in log and "search_partner_candidates" in log:
        print(log)
        # 尝试解析JSON格式的日志
        try:
            log_data = json.loads(log)
            tool_name = log_data.get("tool_name", "")
            if tool_name == "search_partner_candidates":
                print(f"\n找到工具调用: {tool_name}")
                print(f"日志内容: {json.dumps(log_data, ensure_ascii=False, indent=2)[:500]}")
        except Exception as e:
            # 不是JSON格式，直接显示
            print(f"非JSON日志: {log[:200]}")

# 查找用户消息
print("\n【关键日志3】用户消息内容")
print("=" * 80)
for log in session_logs:
    if "找个苏州的25-30岁的温柔女生" in log:
        print(log[:300])
        break

print("\n" + "=" * 80)
print("分析完成")
print("=" * 80)

print("\n【结论】")
print("如果criteria={}（空字典），说明：")
print("1. Agent没有正确提取用户消息中的条件（性别=女、年龄=25-30、城市=苏州）")
print("2. 或者Agent传递的criteria_json参数是空字符串")
print("3. 导致搜索工具只能用默认条件（可能是用户profile中的默认条件）")
print("\n【下一步】")
print("需要查看Agent的意图识别逻辑，看为什么没有提取性别条件")
print("可能的问题：")
print("- SOUL.md中的提示词没有指导Agent正确提取性别")
print("- Agent模型能力不足，无法理解'女生'→性别=女")
print("- 工具schema描述不清晰，Agent不知道如何传递性别参数")