#!/usr/bin/env bash
# 前端组件测试脚本

set -e

echo "=================================================="
echo "前端组件测试"
echo "=================================================="

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试计数器
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# 测试函数
function test_component_exists() {
    local component_name=$1
    local component_path=$2

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if [ -f "$component_path" ]; then
        echo "${GREEN}✅${NC} $component_name 组件存在: $component_path"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo "${RED}❌${NC} $component_name 组件不存在: $component_path"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

function test_import_in_page() {
    local import_name=$1
    local page_path=$2

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if grep -q "import.*$import_name" "$page_path"; then
        echo "${GREEN}✅${NC} $import_name 已导入到页面"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo "${RED}❌${NC} $import_name 未导入到页面"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

function test_field_in_interface() {
    local field_name=$1
    local page_path=$2

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if grep -q "$field_name" "$page_path"; then
        echo "${GREEN}✅${NC} 字段 $field_name 在接口中定义"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo "${RED}❌${NC} 字段 $field_name 未在接口中定义"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

function test_card_in_page() {
    local card_name=$1
    local page_path=$2

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if grep -q "$card_name" "$page_path"; then
        echo "${GREEN}✅${NC} 卡片 $card_name 在页面中实现"
        PASSED_TESTS=$((PASSED_TESTS + 1))
    else
        echo "${RED}❌${NC} 卡片 $card_name 未在页面中实现"
        FAILED_TESTS=$((FAILED_TESTS + 1))
    fi
}

echo ""
echo "=== 测试1：组件文件存在性 ==="

FRONTEND_DIR="frontend/her-app/components/her/ui"
EDIT_PAGE="frontend/her-app/components/her/edit-profile-page.tsx"

test_component_exists "CollapsibleCard" "$FRONTEND_DIR/collapsible-card.tsx"
test_component_exists "NumberInputWithUnit" "$FRONTEND_DIR/number-input-with-unit.tsx"
test_component_exists "SelectDropdown" "$FRONTEND_DIR/select-dropdown.tsx"

echo ""
echo "=== 测试2：组件导入验证 ==="

test_import_in_page "CollapsibleCard" "$EDIT_PAGE"
test_import_in_page "NumberInputWithUnit" "$EDIT_PAGE"
test_import_in_page "SelectDropdown" "$EDIT_PAGE"
test_import_in_page "User" "$EDIT_PAGE"
test_import_in_page "Briefcase" "$EDIT_PAGE"
test_import_in_page "Home" "$EDIT_PAGE"
test_import_in_page "Target" "$EDIT_PAGE"

echo ""
echo "=== 测试3：字段接口定义验证 ==="

# 已有字段
test_field_in_interface "name:" "$EDIT_PAGE"
test_field_in_interface "gender:" "$EDIT_PAGE"
test_field_in_interface "sexualOrientation:" "$EDIT_PAGE"
test_field_in_interface "birthday:" "$EDIT_PAGE"
test_field_in_interface "currentCity:" "$EDIT_PAGE"
test_field_in_interface "photos:" "$EDIT_PAGE"
test_field_in_interface "relationshipGoal:" "$EDIT_PAGE"
test_field_in_interface "marriageStatus:" "$EDIT_PAGE"
test_field_in_interface "hasChildren:" "$EDIT_PAGE"

# 新增字段
test_field_in_interface "height:" "$EDIT_PAGE"
test_field_in_interface "weight:" "$EDIT_PAGE"
test_field_in_interface "education:" "$EDIT_PAGE"
test_field_in_interface "job:" "$EDIT_PAGE"
test_field_in_interface "incomeRange:" "$EDIT_PAGE"
test_field_in_interface "hometownCity:" "$EDIT_PAGE"
test_field_in_interface "childrenCount:" "$EDIT_PAGE"
test_field_in_interface "childrenLivingWithSelf:" "$EDIT_PAGE"
test_field_in_interface "smoking:" "$EDIT_PAGE"
test_field_in_interface "drinking:" "$EDIT_PAGE"
test_field_in_interface "hasHouse:" "$EDIT_PAGE"
test_field_in_interface "hasCar:" "$EDIT_PAGE"
test_field_in_interface "religion:" "$EDIT_PAGE"
test_field_in_interface "isOnlyChild:" "$EDIT_PAGE"
test_field_in_interface "district:" "$EDIT_PAGE"

echo ""
echo "=== 测试4：卡片分组验证 ==="

test_card_in_page "卡片1：照片展示" "$EDIT_PAGE"
test_card_in_page "卡片2：基本信息" "$EDIT_PAGE"
test_card_in_page "卡片3：职业与经济" "$EDIT_PAGE"
test_card_in_page "卡片4：家庭背景" "$EDIT_PAGE"
test_card_in_page "卡片5：生活方式" "$EDIT_PAGE"

echo ""
echo "=== 测试5：数据提交验证 ==="

TOTAL_TESTS=$((TOTAL_TESTS + 1))
if grep -q "height: profile.height" "$EDIT_PAGE"; then
    echo "${GREEN}✅${NC} height字段已添加到提交逻辑"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo "${RED}❌${NC} height字段未添加到提交逻辑"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

TOTAL_TESTS=$((TOTAL_TESTS + 1))
if grep -q "weight: profile.weight" "$EDIT_PAGE"; then
    echo "${GREEN}✅${NC} weight字段已添加到提交逻辑"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo "${RED}❌${NC} weight字段未添加到提交逻辑"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

TOTAL_TESTS=$((TOTAL_TESTS + 1))
if grep -q "education: profile.education" "$EDIT_PAGE"; then
    echo "${GREEN}✅${NC} education字段已添加到提交逻辑"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo "${RED}❌${NC} education字段未添加到提交逻辑"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

echo ""
echo "=== 测试6：验证逻辑验证 ==="

TOTAL_TESTS=$((TOTAL_TESTS + 1))
if grep -q "身高需在100-250cm之间" "$EDIT_PAGE"; then
    echo "${GREEN}✅${NC} 身高验证规则已实现"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo "${RED}❌${NC} 身高验证规则未实现"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

TOTAL_TESTS=$((TOTAL_TESTS + 1))
if grep -q "体重需在30-200kg之间" "$EDIT_PAGE"; then
    echo "${GREEN}✅${NC} 体重验证规则已实现"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo "${RED}❌${NC} 体重验证规则未实现"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

TOTAL_TESTS=$((TOTAL_TESTS + 1))
if grep -q "孩子数量需在0-10之间" "$EDIT_PAGE"; then
    echo "${GREEN}✅${NC} 孩子数量验证规则已实现"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo "${RED}❌${NC} 孩子数量验证规则未实现"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

TOTAL_TESTS=$((TOTAL_TESTS + 1))
if grep -q "有孩子时需填写孩子数量" "$EDIT_PAGE"; then
    echo "${GREEN}✅${NC} 条件验证规则已实现"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo "${RED}❌${NC} 条件验证规则未实现"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

echo ""
echo "=== 测试7：条件显示逻辑验证 ==="

TOTAL_TESTS=$((TOTAL_TESTS + 1))
if grep -q "profile.hasChildren === 'yes'" "$EDIT_PAGE"; then
    echo "${GREEN}✅${NC} 条件显示逻辑已实现"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    echo "${RED}❌${NC} 条件显示逻辑未实现"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi

echo ""
echo "=================================================="
echo "测试统计"
echo "=================================================="
echo "总测试数: $TOTAL_TESTS"
echo "${GREEN}通过: $PASSED_TESTS${NC}"
echo "${RED}失败: $FAILED_TESTS${NC}"

if [ $FAILED_TESTS -eq 0 ]; then
    echo ""
    echo "${GREEN}✅ 所有前端测试通过！${NC}"
    exit 0
else
    echo ""
    echo "${RED}❌ 存在测试失败！${NC}"
    exit 1
fi