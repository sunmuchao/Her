#!/usr/bin/env python3
"""对比服务器期望的签名和我计算的签名"""

import hmac
import hashlib
import base64
import urllib.parse
import json
import secrets
from datetime import datetime

def percent_encode(value):
    """阿里云签名专用编码"""
    return urllib.parse.quote(str(value), safe="~-_.")

def canonical_query(params):
    """构造规范化查询字符串"""
    items = sorted((str(key), str(value)) for key, value in params.items())
    return "&".join(
        f"{percent_encode(key)}={percent_encode(value)}"
        for key, value in items
    )

def signature_for(params, secret):
    """计算签名"""
    canonical = canonical_query(params)
    string_to_sign = f"GET&%2F&{percent_encode(canonical)}"

    print("=" * 80)
    print("【签名计算过程】")
    print("=" * 80)
    print(f"\n1. 参数列表（排序后）:")
    for key, value in sorted(params.items()):
        print(f"   {key}: {value}")

    print(f"\n2. 规范化查询字符串（单次编码）:")
    print(f"   {canonical[:200]}...")

    print(f"\n3. String to Sign（双重编码）:")
    print(f"   {string_to_sign[:200]}...")

    digest = hmac.new(
        f"{secret}&".encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    sig = base64.b64encode(digest).decode("utf-8")

    print(f"\n4. 计算的签名: {sig}")
    return sig, string_to_sign

# 用户当前的参数
params = {
    "AccessKeyId": "LTAI5t5mKE1YFnmHoL4Da4D9",
    "Action": "SendSmsVerifyCode",
    "Format": "JSON",
    "PhoneNumber": "18846811193",
    "RegionId": "cn-hangzhou",
    "SignName": "云渚科技验证平台",
    "TemplateCode": "100001",
    "TemplateParam": json.dumps({"code": "123456", "min": "5"}, ensure_ascii=False, separators=(",", ":")),
    "SignatureMethod": "HMAC-SHA1",
    "SignatureNonce": secrets.token_hex(16),
    "SignatureVersion": "1.0",
    "Timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "Version": "2017-05-25",
}

secret = "HYbj1056bzG6hqsIVYSRujcSf3N2GX"

sig, my_string_to_sign = signature_for(params, secret)

# 服务器期望的（从错误信息提取，但被截断了）
server_string_to_sign = "GET&%2F&AccessKeyId%3DLTAI5t5mKE1YFnmHoL4Da4D9%26Action%3DSendSmsVerifyCode%26Format%3DJSON%26PhoneNumber%3D18846811193%26RegionId%3Dcn-hangzhou%26SignName%3D%25E4%25BA%2591%25E6%25B8%259A%25E7%25A7%2591%25"

print(f"\n\n【对比】")
print(f"服务器期望（截断）: {server_string_to_sign}")
print(f"我计算的（完整）: {my_string_to_sign[:len(server_string_to_sign)]}")
print(f"是否匹配（截断部分）: {server_string_to_sign == my_string_to_sign[:len(server_string_to_sign)]}")

# 检查参数是否有缺失
print(f"\n【参数检查】")
print(f"服务器期望中出现的参数: AccessKeyId, Action, Format, PhoneNumber, RegionId, SignName")
print(f"我包含的所有参数: {', '.join(sorted(params.keys()))}")
print(f"\n可能问题: TemplateCode 和 TemplateParam 是否应该包含在签名计算中？")