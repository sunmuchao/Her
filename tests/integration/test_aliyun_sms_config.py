#!/usr/bin/env python3
"""
阿里云短信配置验证脚本

使用方法：
1. 设置环境变量（推荐在生产环境中设置，而不是在脚本中）
2. 运行此脚本检查配置是否完整
3. 可选择发送测试短信

示例：
  export HER_SMS_PROVIDER=aliyun
  export HER_SMS_ALIYUN_ACCESS_KEY_ID=LTAI5t...
  export HER_SMS_ALIYUN_ACCESS_KEY_SECRET=abc123...
  export HER_SMS_ALIYUN_SIGN_NAME=你的签名
  export HER_SMS_ALIYUN_TEMPLATE_CODE=SMS_123456789

  python test_aliyun_sms_config.py
  python test_aliyun_sms_config.py --send-test 13800138000
"""

import argparse
import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from external_systems.partner_http_gateway.gateway.auth_providers import (
    AliyunPnvsProvider,
    AliyunSmsProvider,
    DisabledSmsProvider,
    build_sms_provider,
)


def check_env_variables():
    """检查环境变量配置是否完整"""
    print("=" * 60)
    print("阿里云短信环境变量检查")
    print("=" * 60)

    # 检查 AccessKey（普通短信和 PNVS 都需要）
    print("\n【必需配置 - AccessKey】")
    access_key_vars = {
        "HER_SMS_ALIYUN_ACCESS_KEY_ID": ["ALIBABA_CLOUD_ACCESS_KEY_ID", "ALICLOUD_ACCESS_KEY_ID"],
        "HER_SMS_ALIYUN_ACCESS_KEY_SECRET": ["ALIBABA_CLOUD_ACCESS_KEY_SECRET", "ALICLOUD_ACCESS_KEY_SECRET"],
    }

    access_key_configured = True
    for primary_name, aliases in access_key_vars.items():
        found_value = None
        found_name = None

        # 先检查主要变量
        primary_value = os.environ.get(primary_name, "").strip()
        if primary_value:
            found_value = primary_value
            found_name = primary_name
        else:
            # 检查别名
            for alias in aliases:
                alias_value = os.environ.get(alias, "").strip()
                if alias_value:
                    found_value = alias_value
                    found_name = alias
                    break

        if found_value:
            # 隐藏敏感信息
            if "SECRET" in found_name.upper() or "KEY" in found_name.upper():
                masked = found_value[:8] + "..." + found_value[-4:] if len(found_value) > 12 else found_value[:4] + "..."
                print(f"✅ {found_name}: {masked}")
            else:
                print(f"✅ {found_name}: {found_value}")
        else:
            print(f"❌ {primary_name}: 未设置")
            if aliases:
                print(f"   别名 {aliases} 也未设置")
            access_key_configured = False

    # 检查普通短信服务的额外配置（签名和模板）
    print("\n【普通短信服务配置 - 签名和模板】（可选）")
    print("   注意：如果使用 PNVS（短信认证服务），则不需要")
    sms_vars = {
        "HER_SMS_ALIYUN_SIGN_NAME": ["HER_SMS_SIGN_NAME"],
        "HER_SMS_ALIYUN_TEMPLATE_CODE": ["HER_SMS_TEMPLATE_CODE"],
    }

    sms_configured = True
    for primary_name, aliases in sms_vars.items():
        found_value = None
        found_name = None

        primary_value = os.environ.get(primary_name, "").strip()
        if primary_value:
            found_value = primary_value
            found_name = primary_name
        else:
            for alias in aliases:
                alias_value = os.environ.get(alias, "").strip()
                if alias_value:
                    found_value = alias_value
                    found_name = alias
                    break

        if found_value:
            print(f"✅ {found_name}: {found_value}")
        else:
            print(f"⚠️  {primary_name}: 未设置")
            sms_configured = False

    # 检查 PNVS 配置（系统赠送的签名和模板）
    print("\n【PNVS 短信认证服务配置】（可选）")
    print("   注意：如果使用普通短信服务，则不需要")
    pnvs_vars = {
        "HER_SMS_ALIYUN_PNVS_SIGN_NAME": [],
        "HER_SMS_ALIYUN_PNVS_TEMPLATE_CODE": [],
    }

    pnvs_configured = True
    for primary_name, aliases in pnvs_vars.items():
        found_value = None
        found_name = None

        primary_value = os.environ.get(primary_name, "").strip()
        if primary_value:
            found_value = primary_value
            found_name = primary_name
        else:
            for alias in aliases:
                alias_value = os.environ.get(alias, "").strip()
                if alias_value:
                    found_value = alias_value
                    found_name = alias
                    break

        if found_value:
            print(f"✅ {found_name}: {found_value}")
        else:
            print(f"⚠️  {primary_name}: 未设置")
            pnvs_configured = False

    # 检查可选环境变量
    print("\n【可选环境变量】")
    optional_vars = {
        "HER_SMS_PROVIDER": "自动检测",
        "HER_SMS_ALIYUN_REGION_ID": "cn-hangzhou",
        "HER_SMS_ALIYUN_ENDPOINT": "https://dysmsapi.aliyuncs.com/",
        "HER_SMS_ALIYUN_TEMPLATE_PARAM_KEY": "code",
    }

    for var_name, default_value in optional_vars.items():
        value = os.environ.get(var_name, "").strip()
        if value:
            print(f"  {var_name}: {value}")
        else:
            print(f"  {var_name}: 未设置（默认: {default_value})")

    # 总结配置状态
    if not access_key_configured:
        print("\n❌ AccessKey 未配置")
        return False
    elif sms_configured:
        print("\n✅ 普通短信服务配置完整")
        print("   需要自己申请签名和模板")
        return True
    elif pnvs_configured:
        print("\n✅ PNVS 短信认证服务配置完整")
        print("   使用系统赠送的签名和模板")
        return True
    else:
        print("\n⚠️  AccessKey 已配置，但缺少签名和模板")
        print("   请选择以下方式之一：")
        print("   1. 配置普通短信服务（需要自己申请签名和模板）")
        print("   2. 配置 PNVS 服务（使用系统赠送的签名和模板）")
        print("      - 设置 HER_SMS_ALIYUN_PNVS_SIGN_NAME")
        print("      - 设置 HER_SMS_ALIYUN_PNVS_TEMPLATE_CODE")
        print("      - 从控制台获取：https://dypns.console.aliyun.com/")
        return False


def check_provider():
    """检查实际使用的 Provider 类型"""
    print("\n" + "=" * 60)
    print("短信 Provider 类型检查")
    print("=" * 60)

    provider = build_sms_provider()
    provider_type = type(provider).__name__

    print(f"当前 Provider: {provider_type}")

    if isinstance(provider, AliyunPnvsProvider):
        print("✅ 已启用阿里云短信认证服务（PNVS）")
        print("   特点：免签名审核、免模板审核（使用系统赠送资源）")
        print(f"   AccessKey ID: {provider._access_key_id[:8]}...")
        print(f"   系统赠送签名: {provider._sign_name}")
        print(f"   系统赠送模板: {provider._template_code}")
        print(f"   区域 ID: {provider._region_id}")
        return True
    elif isinstance(provider, AliyunSmsProvider):
        print("✅ 已启用阿里云普通短信服务")
        print("   特点：需要签名和模板审核")
        print(f"   AccessKey ID: {provider._access_key_id[:8]}...")
        print(f"   签名名称: {provider._sign_name}")
        print(f"   模板 CODE: {provider._template_code}")
        print(f"   区域 ID: {provider._region_id}")
        return True
    elif isinstance(provider, DisabledSmsProvider):
        print("❌ 短信服务未启用")
        print("   这将导致发送验证码时返回 503 错误")
        print("\n解决方案:")
        print("   1. 设置 HER_SMS_PROVIDER=aliyun")
        print("   2. 或确保阿里云相关环境变量已完整配置")
        return False
    else:
        print(f"⚠️  使用的是其他 Provider: {provider_type}")
        print("   如果想使用阿里云短信，请设置 HER_SMS_PROVIDER=aliyun")
        return False


def send_test_sms(phone: str):
    """发送测试短信"""
    print("\n" + "=" * 60)
    print("发送测试短信")
    print("=" * 60)

    provider = build_sms_provider()

    if isinstance(provider, DisabledSmsProvider):
        print("❌ 短信服务未配置，无法发送测试短信")
        return False

    # 生成测试验证码
    test_code = "123456"

    print(f"目标手机号: {phone}")
    print(f"测试验证码: {test_code}")
    print("\n正在发送...")

    try:
        result = provider.send_code(phone, test_code)
        print("\n✅ 发送成功！")
        print(f"   Provider: {result.get('provider', 'unknown')}")
        print(f"   Request ID: {result.get('request_id', 'N/A')}")
        print(f"   Biz ID: {result.get('biz_id', 'N/A')}")

        # 提示用户检查短信
        print("\n请检查手机是否收到验证码短信")
        print(f"短信内容应包含验证码: {test_code}")

        return True
    except Exception as exc:
        print(f"\n❌ 发送失败: {exc}")
        print(f"   错误类型: {type(exc).__name__}")

        # 解析常见错误
        error_msg = str(exc)
        if "isv.SIGN_NAME_ILLEGAL" in error_msg:
            print("\n可能原因: 签名名称不合法或未审核通过")
        elif "isv.TEMPLATE_CODE_ILLEGAL" in error_msg:
            print("\n可能原因: 模板 CODE 不合法或未审核通过")
        elif "InvalidAccessKeyId" in error_msg:
            print("\n可能原因: AccessKey ID 无效")
        elif "SignatureDoesNotMatch" in error_msg:
            print("\n可能原因: AccessKey Secret 不匹配")
        elif "BUSINESS_LIMIT_CONTROL" in error_msg:
            print("\n可能原因: 短信发送频率超限，请稍后重试")
        elif "NO_PERMISSION" in error_msg:
            print("\n可能原因: AccessKey 无短信发送权限")

        return False


def main():
    parser = argparse.ArgumentParser(
        description="验证阿里云短信配置",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 仅检查配置
  python test_aliyun_sms_config.py

  # 发送测试短信（需要先配置环境变量）
  python test_aliyun_sms_config.py --send-test 13800138000

环境变量设置示例:
  export HER_SMS_PROVIDER=aliyun
  export HER_SMS_ALIYUN_ACCESS_KEY_ID=LTAI5t...
  export HER_SMS_ALIYUN_ACCESS_KEY_SECRET=abc123...
  export HER_SMS_ALIYUN_SIGN_NAME=你的签名
  export HER_SMS_ALIYUN_TEMPLATE_CODE=SMS_123456789
""",
    )
    parser.add_argument(
        "--send-test",
        metavar="PHONE",
        help="发送测试短信到指定手机号（中国大陆手机号）",
    )

    args = parser.parse_args()

    # 检查环境变量
    env_ok = check_env_variables()

    # 检查 Provider
    provider_ok = check_provider()

    # 如果要求发送测试短信
    if args.send_test:
        # 验证手机号格式
        phone = args.send_test.strip()
        if not phone or not phone.startswith("1") or len(phone) != 11:
            print("\n❌ 手机号格式错误，请提供11位中国大陆手机号")
            sys.exit(1)

        send_test_sms(phone)

    # 总结
    print("\n" + "=" * 60)
    print("配置检查总结")
    print("=" * 60)

    if env_ok and provider_ok:
        print("✅ 阿里云短信服务配置完整且已启用")
        print("   可以正常发送短信验证码")
        sys.exit(0)
    else:
        print("❌ 阿里云短信服务配置不完整或未启用")
        print("\n配置步骤:")
        print("   1. 登录阿里云控制台获取 AccessKey")
        print("      https://ram.console.aliyun.com/manage/ak")
        print("   2. 申请短信签名和模板")
        print("      https://dysms.console.aliyun.com/domestic/text/sign")
        print("      https://dysms.console.aliyun.com/domestic/text/template")
        print("   3. 设置环境变量（参考上方示例）")
        print("   4. 重新运行此脚本验证")
        print("\n详细文档:")
        print("   docs/operation-guides/aliyun-sms-configuration.md")
        sys.exit(1)


if __name__ == "__main__":
    main()