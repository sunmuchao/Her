#!/bin/bash
# 生成生产级随机密钥并存储到 secrets 目录

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SECRETS_DIR="${REPO_ROOT}/secrets"

echo "=== 生成生产级密钥 ==="

mkdir -p "${SECRETS_DIR}"

# 生成 MySQL root 密码（32位强密钥）
echo "生成 MySQL root 密码..."
openssl rand -base64 32 > "${SECRETS_DIR}/mysql_root_password.txt"
chmod 600 "${SECRETS_DIR}/mysql_root_password.txt"

# 生成 MinIO 密钥（16位用户名 + 32位密码）
echo "生成 MinIO 密钥..."
openssl rand -base64 16 | tr -d '=' | tr '+/' '-_' > "${SECRETS_DIR}/minio_root_user.txt"
openssl rand -base64 32 > "${SECRETS_DIR}/minio_root_password.txt"
chmod 600 "${SECRETS_DIR}/minio_root_user.txt" "${SECRETS_DIR}/minio_root_password.txt"

# 生成 Redis 密码（可选，用于 Redis 认证）
echo "生成 Redis 密码..."
openssl rand -base64 24 > "${SECRETS_DIR}/redis_password.txt"
chmod 600 "${SECRETS_DIR}/redis_password.txt"

# 生成 Grafana admin 密码
echo "生成 Grafana admin 密码..."
openssl rand -base64 20 > "${SECRETS_DIR}/grafana_admin_password.txt"
chmod 600 "${SECRETS_DIR}/grafana_admin_password.txt"

# 生成示例 .env 文件（供参考）
echo "生成 .env.secrets 示例文件..."
cat > "${REPO_ROOT}/.env.secrets.example" <<EOF
# === 密钥配置示例 ===
# 将以下密钥替换为 secrets/ 目录中的实际值
# 生产环境请使用 Docker Secrets 或 Kubernetes Secrets

# MySQL 密钥
MYSQL_ROOT_PASSWORD_FILE=/run/secrets/mysql_root_password

# MinIO 密钥
MINIO_ROOT_USER_FILE=/run/secrets/minio_root_user
MINIO_ROOT_PASSWORD_FILE=/run/secrets/minio_root_password

# Redis 密钥（可选）
REDIS_PASSWORD_FILE=/run/secrets/redis_password

# Grafana 密钥
GF_SECURITY_ADMIN_PASSWORD_FILE=/run/secrets/grafana_admin_password
EOF

chmod 600 "${REPO_ROOT}/.env.secrets.example"

echo ""
echo "✅ 密钥生成完成！"
echo ""
echo "生成的密钥文件："
ls -la "${SECRETS_DIR}/"
echo ""
echo "⚠️  重要提醒："
echo "  1. secrets/ 目录已在 .gitignore 中添加，不会提交到仓库"
echo "  2. 生产环境请使用 Docker Secrets 或 Kubernetes Secrets"
echo "  3. 请妥善保管密钥文件，不要泄露"
echo "  4. 定期更新密钥（建议每90天）"
echo ""
echo "下一步："
echo "  1. 查看 .env.secrets.example 了解如何使用密钥"
echo "  2. 修改 docker-compose.yml 使用 Docker Secrets"
echo "  3. 运行 scripts/validate_config.py 校验密钥强度"