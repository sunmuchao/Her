#!/usr/bin/env python3
"""
完全复现用户实际场景的签名调试脚本

根据用户提供的错误信息，服务器期望的 string_to_sign：
GET&%2F&AccessKeyId%3DLTAI5t5mKE1YFnmHoL4Da4D9%26Action%3DSendSmsVerifyCode%26Code%3D123456%26Format%3DJSON%26PhoneNumber%3D18846811193%26RegionId%3Dcn-hangzhou%26SignName%3D%25E4%25BA%2591%25E6%25B8%259A%25E7%25A7%2591%25E6%258A%2580%25E9%25AA%258C%25E8%25AF%2581%25E5%25B9%25B3%25E5%258F%25B0%26SignatureMethod%3DHMAC-SHA1%26SignatureNonce%3Dc927ae42fd35f08c59becefbe41778fc%26SignatureVersion%3D1.0%26TemplateCode%3D100001%26Timestamp%3D2026-06-24T02%253A26%253A50Z%26Version%3D2017-05-25
"""

import hmac
import hashlib
import base64
import urllib.parse

def percent_encode(value):
    """阿里云签名专用编码"""
    return urllib.parse.quote(str(value), safe="~-_.")

def signature_for_test():
    """直接测试签名计算"""

    # 从服务器错误信息中提取的参数（解码后）
    params = {
        "AccessKeyId": "LTAI5t5mKE1YFnmHoL4Da4D9",
        "Action": "SendSmsVerifyCode",
        "Code": "123456",
        "Format": "JSON",
        "PhoneNumber": "18846811193",
        "RegionId": "cn-hangzhou",
        "SignName": "云渝科技验证平台",  # 从服务器信息解码得到
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": "c927ae42fd35f08c59becefbe41778fc",  # 从服务器信息提取
        "SignatureVersion": "1.0",
        "TemplateCode": "100001",
        "Timestamp": "2026-06-24T02:26:50Z",  # 从服务器信息解码得到
        "Version": "2017-05-25",
    }

    # 服务器期望的 string_to_sign（直接解码）
    server_string_to_sign_encoded = "GET&%2F&AccessKeyId%3DLTAI5t5mKE1YFnmHoL4Da4D9%26Action%3DSendSmsVerifyCode%26Code%3D123456%26Format%3DJSON%26PhoneNumber%3D18846811193%26RegionId%3Dcn-hangzhou%26SignName%3D%25E4%25BA%2591%25E6%25B8%259A%25E7%25A7%2591%25E6%258A%2580%25E9%25AA%258C%25E8%25AF%2581%25E5%25B9%25B3%25E5%258F%25B0%26SignatureMethod%3DHMAC-SHA1%26SignatureNonce%3Dc927ae42fd35f08c59becefbe41778fc%26SignatureVersion%3D1.0%26TemplateCode%3D100001%26Timestamp%3D2026-06-24T02%253A26%253A50Z%26Version%3D2017-05-25"

    print("=" * 80)
    print("签名算法对比分析")
    print("=" * 80)

    print("\n【服务器期望的 String to Sign】:")
    print(server_string_to_sign_encoded)
    print("\n解码后:")
    # 解码一次（从双重编码到单次编码）
    decoded_once = urllib.parse.unquote(server_string_to_sign_encoded)
    print(decoded_once)

    print("\n【我计算的 String to Sign】:")
    # 构造规范化查询字符串
    items = sorted((str(key), str(value)) for key, value in params.items())
    canonical = "&".join(
        f"{percent_encode(key)}={percent_encode(value)}"
        for key, value in items
    )
    print("规范化查询字符串:")
    print(canonical)

    # 构造 string_to_sign
    my_string_to_sign = f"GET&%2F&{percent_encode(canonical)}"
    print("\nString to Sign:")
    print(my_string_to_sign)

    print("\n【对比】:")
    print(f"服务器期望: {server_string_to_sign_encoded}")
    print(f"我计算出的: {my_string_to_sign}")
    print(f"是否匹配: {server_string_to_sign_encoded == my_string_to_sign}")

    # 找出差异位置
    if server_string_to_sign_encoded != my_string_to_sign:
        print("\n【差异分析】:")
        min_len = min(len(server_string_to_sign_encoded), len(my_string_to_sign))
        for i in range(min_len):
            if server_string_to_sign_encoded[i] != my_string_to_sign[i]:
                print(f"位置 {i}:")
                print(f"  服务器: {server_string_to_sign_encoded[i:i+50]}...")
                print(f"  我: {my_string_to_sign[i:i+50]}...")
                break

    print("\n【签名计算】:")
    access_key_secret = "HYbj1056bzG6hqsIVYSRujcSf3N2GX"  # 用户暴露的 Secret

    # 用服务器期望的 string_to_sign 计算签名
    server_digest = hmac.new(
        f"{access_key_secret}&".encode("utf-8"),
        server_string_to_sign_encoded.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    server_sig = base64.b64encode(server_digest).decode("utf-8")
    print(f"用服务器 string_to_sign 计算的签名: {server_sig}")

    # 用我计算的 string_to_sign 计算签名
    my_digest = hmac.new(
        f"{access_key_secret}&".encode("utf-8"),
        my_string_to_sign.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    my_sig = base64.b64encode(my_digest).decode("utf-8")
    print(f"用我计算的 string_to_sign 计算的签名: {my_sig}")

if __name__ == "__main__":
    signature_for_test()