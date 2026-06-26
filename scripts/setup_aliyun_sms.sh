#!/bin/bash
# 阿里云短信服务快速配置脚本

echo "================================================"
echo "阿里云短信服务配置助手"
echo "================================================"
echo ""

# 安全提醒
echo "⚠️  重要安全提醒："
echo "   你刚才在聊天中暴露了 AccessKey Secret！"
echo "   建议立即重新生成 AccessKey Secret"
echo ""
echo "操作步骤："
echo "   1. 登录 https://ram.console.aliyun.com/manage/ak"
echo "   2. 删除当前的 AccessKey（LTAI5t5mKE1YFnmHoL4Da4D9）"
echo "   3. 创建新的 AccessKey"
echo "   4. 使用新的 AccessKey ID 和 Secret 配置"
echo ""
read -p "是否已经重新生成 AccessKey？(y/n): " regenerated

if [[ "$regenerated" != "y" ]]; then
    echo ""
    echo "请先重新生成 AccessKey 后再继续配置"
    echo "操作完成后重新运行此脚本"
    exit 1
fi

echo ""
echo "================================================"
echo "步骤 1：配置 AccessKey"
echo "================================================"
echo ""

read -p "请输入新的 AccessKey ID: " access_key_id
read -p "请输入新的 AccessKey Secret: " access_key_secret

if [[ -z "$access_key_id" || -z "$access_key_secret" ]]; then
    echo "❌ AccessKey ID 和 Secret 都是必需的"
    exit 1
fi

echo ""
echo "================================================"
echo "步骤 2：申请短信签名"
echo "================================================"
echo ""
echo "短信签名申请地址："
echo "   https://dysms.console.aliyun.com/domestic/text/sign"
echo ""
echo "签名申请要求："
echo "   - 签名必须是真实的企业/品牌名称"
echo "   - 需要提供相关证明材料"
echo "   - 审核时间：通常 1-2 小时"
echo ""
read -p "是否已经申请并通过审核？(y/n): " sign_approved

if [[ "$sign_approved" != "y" ]]; then
    echo ""
    echo "请先申请短信签名并等待审核通过"
    echo "审核完成后重新运行此脚本"
    exit 1
fi

read -p "请输入审核通过的签名名称: " sign_name

if [[ -z "$sign_name" ]]; then
    echo "❌ 签名名称是必需的"
    exit 1
fi

echo ""
echo "================================================"
echo "步骤 3：申请短信模板"
echo "================================================"
echo ""
echo "短信模板申请地址："
echo "   https://dysms.console.aliyun.com/domestic/text/template"
echo ""
echo "模板申请要求："
echo "   - 模板内容必须包含验证码变量 ${code}"
echo "   - 模板示例：您的验证码为：${code}，该验证码5分钟内有效"
echo "   - 审核时间：通常 1-2 小时"
echo ""
read -p "是否已经申请并通过审核？(y/n): " template_approved

if [[ "$template_approved" != "y" ]]; then
    echo ""
    echo "请先申请短信模板并等待审核通过"
    echo "审核完成后重新运行此脚本"
    exit 1
fi

read -p "请输入审核通过的模板 CODE: " template_code

if [[ -z "$template_code" ]]; then
    echo "❌ 模板 CODE 是必需的"
    exit 1
fi

echo ""
echo "================================================"
echo "步骤 4：生成配置文件"
echo "================================================"
echo ""

# 生成配置文件
config_file=".env.aliyun_sms.local"

cat > "$config_file" <<EOF
# 阿里云短信服务配置（自动生成）

HER_SMS_PROVIDER=aliyun

# 阿里云 AccessKey
HER_SMS_ALIYUN_ACCESS_KEY_ID=${access_key_id}
HER_SMS_ALIYUN_ACCESS_KEY_SECRET=${access_key_secret}

# 短信签名
HER_SMS_ALIYUN_SIGN_NAME=${sign_name}

# 短信模板
HER_SMS_ALIYUN_TEMPLATE_CODE=${template_code}

# 区域 ID（可选）
HER_SMS_ALIYUN_REGION_ID=cn-hangzhou

# 模板参数键名（可选）
HER_SMS_ALIYUN_TEMPLATE_PARAM_KEY=code
EOF

echo "✅ 配置文件已生成：$config_file"
echo ""
echo "⚠️  此文件已在 .gitignore 中，不会被提交到 git"

echo ""
echo "================================================"
echo "步骤 5：验证配置"
echo "================================================"
echo ""

# 加载环境变量
export HER_SMS_PROVIDER=aliyun
export HER_SMS_ALIYUN_ACCESS_KEY_ID="$access_key_id"
export HER_SMS_ALIYUN_ACCESS_KEY_SECRET="$access_key_secret"
export HER_SMS_ALIYUN_SIGN_NAME="$sign_name"
export HER_SMS_ALIYUN_TEMPLATE_CODE="$template_code"

echo "运行配置验证脚本..."
python tests/integration/test_aliyun_sms_config.py

echo ""
echo "================================================"
echo "配置完成"
echo "================================================"
echo ""
echo "下一步操作："
echo "   1. 运行测试验证：python tests/integration/test_aliyun_sms_config.py"
echo "   2. 发送测试短信：python tests/integration/test_aliyun_sms_config.py --send-test 13800138000"
echo "   3. 重启应用使配置生效"
echo ""
echo "详细文档："
echo "   docs/operation-guides/aliyun-sms-configuration.md"
echo ""