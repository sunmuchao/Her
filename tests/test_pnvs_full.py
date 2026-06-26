#!/usr/bin/env python3
"""完整的 PNVS 测试脚本（包含详细调试信息）"""

import sys
sys.path.insert(0, '/Users/sunmuchao/Downloads/Her')

import os

# 设置环境变量
os.environ['HER_SMS_ALIYUN_PNVS_SIGN_NAME'] = '云渚科技验证平台'
os.environ['HER_SMS_ALIYUN_PNVS_TEMPLATE_CODE'] = '100001'
os.environ['HER_SMS_ALIYUN_ACCESS_KEY_ID'] = 'LTAI5t5mKE1YFnmHoL4Da4D9'
# ⚠️ 请使用重新生成的 Secret
os.environ['HER_SMS_ALIYUN_ACCESS_KEY_SECRET'] = '请替换为新的Secret'

from external_systems.partner_http_gateway.gateway.auth_providers import AliyunPnvsProvider

print("=" * 80)
print("阿里云 PNVS 短信认证服务测试")
print("=" * 80)

try:
    provider = AliyunPnvsProvider.from_env()

    print(f"\n配置信息:")
    print(f"  AccessKey ID: {provider._access_key_id}")
    print(f"  AccessKey Secret: {provider._access_key_secret[:8]}...")
    print(f"  签名名称: {provider._sign_name}")
    print(f"  模板 CODE: {provider._template_code}")
    print(f"  Endpoint: {provider._endpoint}")
    print(f"  Region ID: {provider._region_id}")

    print(f"\n正在发送短信到 18846811193...")

    result = provider.send_code('18846811193', '123456')

    print(f"\n✅ 发送成功!")
    print(f"  Provider: {result.get('provider')}")
    print(f"  Request ID: {result.get('request_id')}")
    print(f"  Biz ID: {result.get('biz_id')}")

except Exception as exc:
    print(f"\n❌ 发送失败: {exc}")
    print(f"  错误类型: {type(exc).__name__}")

    import traceback
    print(f"\n详细错误信息:")
    traceback.print_exc()

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)