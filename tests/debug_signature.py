#!/usr/bin/env python3
"""阿里云签名算法验证脚本"""

import hmac
import hashlib
import base64
import urllib.parse
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

def signature_for(params, access_key_secret):
    """计算签名"""
    canonical = canonical_query(params)
    string_to_sign = f"GET&%2F&{percent_encode(canonical)}"
    print(f"\n[String to Sign]:\n{string_to_sign}\n")

    digest = hmac.new(
        f"{access_key_secret}&".encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")

# 测试参数
params = {
    "AccessKeyId": "LTAI5t5mKE1YFnmHoL4Da4D9",
    "Action": "SendSmsVerifyCode",
    "Code": "123456",
    "Format": "JSON",
    "PhoneNumber": "18846811193",
    "RegionId": "cn-hangzhou",
    "SignName": "云渝科技验证平台",
    "SignatureMethod": "HMAC-SHA1",
    "SignatureNonce": "test123456789012",
    "SignatureVersion": "1.0",
    "TemplateCode": "100001",
    "Timestamp": "2026-06-24T02:26:50Z",
    "Version": "2017-05-25",
}

print("=" * 80)
print("阿里云 PNVS 签名算法验证")
print("=" * 80)

print("\n[原始参数]:")
for key, value in sorted(params.items()):
    print(f"  {key}: {value}")

print("\n[规范化查询字符串]:")
canonical = canonical_query(params)
print(canonical)

print("\n[计算签名]:")
sig = signature_for(params, "HYbj1056bzG6hqsIVYSRujcSf3N2GX")
print(f"Signature: {sig}")

print("\n[完整请求 URL]:")
signed_params = dict(params)
signed_params["Signature"] = sig
request_url = "https://dypnsapi.aliyuncs.com/?"
request_url += "&".join(
    f"{percent_encode(key)}={percent_encode(value)}"
    for key, value in sorted(signed_params.items())
)
print(request_url)