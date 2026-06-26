#!/bin/bash
# 简单的短信发送stub脚本（用于开发环境）
# 将验证码写入临时文件，方便测试

echo "$HER_SMS_CODE" > /tmp/her_sms_code.txt
echo "SMS stub: sent code $HER_SMS_CODE to phone $HER_SMS_PHONE" >> /tmp/her_sms_debug.log