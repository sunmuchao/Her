#!/usr/bin/env python3
"""测试 TTS 服务是否正常工作"""

import sys
import os

# 加载 .env 文件中的环境变量
from pathlib import Path
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    print(f"加载环境变量: {env_file}")
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# 添加 chat_system 到 Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'external-systems', 'partner-chat-system'))

print("Python path:")
for p in sys.path[:5]:
    print(f"  {p}")

print("\n测试导入 TTS 服务...")

try:
    # 尝试导入 tts_service
    from chat_system.tts_service import synthesize_tts
    print("✅ 成功导入 tts_service")

    # 测试生成语音
    print("\n测试生成语音...")
    result = synthesize_tts("你好，我是小雅", voice="xiaoxiao")

    if result:
        print("✅ 语音生成成功")
        print(f"  media_type: {result['media_type']}")
        print(f"  media_url: {result['media_url']}")
        print(f"  duration_ms: {result['media_metadata']['duration_ms']}")
        print(f"  format: {result['media_metadata']['format']}")
        print(f"  size: {result['media_metadata']['size']}")
    else:
        print("❌ 语音生成失败")

except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("  可能需要安装 edge-tts: pip install edge-tts")

except Exception as e:
    print(f"❌ 测试失败: {e}")