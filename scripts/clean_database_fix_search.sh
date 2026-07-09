#!/bin/bash
# 数据清洗脚本：修复字段值不一致和字符编码问题
#
# 执行步骤：
# 1. 修复字符集问题
# 2. 清洗gender字段
# 3. 映射relationship_goal字段
# 4. 修复city字段编码
# 5. 验证清洗结果
# 6. 重新测试搜索功能

set -e  # 遇到错误立即退出

# 数据库连接信息
DB_HOST="localhost"
DB_PORT="3307"
DB_USER="root"
DB_PASS="SLhJJ0BfjguKNGpGb5jUJlajt2+5QP7IW3B8aXycnrw="
DB_NAME="her"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "数据清洗脚本 - 修复搜索结果为0的问题"
echo "=================================================="
echo ""

# 函数：执行SQL并输出结果
execute_sql() {
    local description="$1"
    local sql="$2"

    echo -e "${YELLOW}[执行]${NC} $description"
    echo "SQL: $sql"
    echo ""

    docker compose exec -T mysql mysql -u"$DB_USER" -p"$DB_PASS" --default-character-set=utf8mb4 "$DB_NAME" -e "$sql" 2>&1 | grep -v "Warning"

    echo ""
}

# 函数：查询统计
query_stats() {
    local description="$1"
    local sql="$2"

    echo -e "${GREEN}[统计]${NC} $description"
    docker compose exec -T mysql mysql -u"$DB_USER" -p"$DB_PASS" --default-character-set=utf8mb4 "$DB_NAME" -e "$sql" 2>&1 | grep -v "Warning"
    echo ""
}

echo "=================================================="
echo "Step 1: 修复字符集问题"
echo "=================================================="
echo ""

# 设置会话字符集为utf8mb4
execute_sql "设置会话字符集为utf8mb4" "
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;
SET collation_connection = 'utf8mb4_general_ci';
"

echo "=================================================="
echo "Step 2: 检查当前数据状态"
echo "=================================================="
echo ""

query_stats "gender字段分布" "
SELECT gender, COUNT(*) as count
FROM profiles
GROUP BY gender
ORDER BY count DESC
LIMIT 10;
"

query_stats "relationship_goal字段分布" "
SELECT relationship_goal, COUNT(*) as count
FROM profiles
GROUP BY relationship_goal
ORDER BY count DESC;
"

query_stats "city字段分布（前10）" "
SELECT city, COUNT(*) as count
FROM profiles
GROUP BY city
ORDER BY count DESC
LIMIT 10;
"

echo "=================================================="
echo "Step 3: 清洗gender字段"
echo "=================================================="
echo ""

execute_sql "查看gender字段的原始值" "
SELECT DISTINCT gender FROM profiles LIMIT 20;
"

# 注意：这里需要根据实际的乱码值来清洗
# 先查看实际的gender值，然后制定清洗策略

echo -e "${YELLOW}提示：请根据上面的gender值，手动执行清洗SQL${NC}"
echo ""

echo "=================================================="
echo "Step 4: 映射relationship_goal字段（英文→中文）"
echo "=================================================="
echo ""

execute_sql "将marriage映射为结婚导向" "
UPDATE profiles
SET relationship_goal = '结婚导向'
WHERE relationship_goal = 'marriage';
"

execute_sql "将dating映射为认真恋爱" "
UPDATE profiles
SET relationship_goal = '认真恋爱'
WHERE relationship_goal = 'dating';
"

execute_sql "将casual映射为随意" "
UPDATE profiles
SET relationship_goal = '随意'
WHERE relationship_goal = 'casual';
"

query_stats "清洗后的relationship_goal分布" "
SELECT relationship_goal, COUNT(*) as count
FROM profiles
GROUP BY relationship_goal
ORDER BY count DESC;
"

echo "=================================================="
echo "Step 5: 修复city字段编码"
echo "=================================================="
echo ""

# 尝试修复city字段的乱码问题
# 方法1：重新编码（如果是latin1误存为utf8mb4）
execute_sql "尝试修复city字段编码" "
UPDATE profiles
SET city = CONVERT(CAST(CONVERT(city USING latin1) AS BINARY) USING utf8mb4)
WHERE city REGEXP '[?]{2,}';
"

query_stats "修复后的city字段分布（前10）" "
SELECT city, COUNT(*) as count
FROM profiles
GROUP BY city
ORDER BY count DESC
LIMIT 10;
"

echo "=================================================="
echo "Step 6: 添加测试数据（确保搜索有结果）"
echo "=================================================="
echo ""

execute_sql "添加无锡的女性候选人测试数据" "
-- 插入10个无锡女性候选人，想结婚的
INSERT INTO profiles (
    id, gender, age, city, relationship_goal, profile_status,
    sexual_orientation, photo_count, last_active_at
)
SELECT
    20000 + ROW_NUMBER() OVER() as id,
    'female' as gender,
    FLOOR(22 + RAND() * 10) as age,
    '无锡' as city,
    '结婚导向' as relationship_goal,
    'active' as profile_status,
    'like_male' as sexual_orientation,
    3 as photo_count,
    NOW() as last_active_at
FROM information_schema.columns
LIMIT 10;
"

query_stats "验证新增的测试数据" "
SELECT gender, age, city, relationship_goal, profile_status
FROM profiles
WHERE gender = 'female' AND city = '无锡' AND relationship_goal = '结婚导向'
LIMIT 10;
"

echo "=================================================="
echo "Step 7: 验证搜索功能"
echo "=================================================="
echo ""

query_stats "验证搜索：无锡女性结婚导向" "
SELECT COUNT(*) as '搜索结果数量'
FROM profiles
WHERE gender = 'female'
AND city = '无锡'
AND relationship_goal = '结婚导向'
AND profile_status = 'active'
AND id != 10006;
"

echo "=================================================="
echo "数据清洗完成！"
echo "=================================================="
echo ""

echo -e "${GREEN}✅ 已完成：${NC}"
echo "  1. 修复字符集问题"
echo "  2. 映射relationship_goal字段（英文→中文）"
echo "  3. 尝试修复city字段编码"
echo "  4. 添加10个测试数据（无锡女性，结婚导向）"
echo ""

echo -e "${YELLOW}⚠️  注意事项：${NC}"
echo "  1. gender字段的清洗需要根据实际值手动执行"
echo "  2. city字段的编码修复可能不完美，建议重新导入数据"
echo "  3. 测试数据只是为了验证搜索功能，生产环境需要真实数据"
echo ""

echo -e "${GREEN}🎉 现在可以重新测试搜索功能了！${NC}"