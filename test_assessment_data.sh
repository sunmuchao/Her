#!/bin/bash

# 测试 assessment_result 数据完整性

echo "=== 测试 API 返回的数据结构 ==="
curl -s http://127.0.0.1:3000/api/gateway/v1/discovery/sessions/discovery-session-0cfc66c566ae | python3 -c "
import json
import sys

data = json.load(sys.stdin)
timeline = data.get('view', {}).get('timeline', [])

for item in timeline:
    if item.get('item_type') == 'assessment_result':
        card = item.get('card', {})
        result_data = card.get('result_data', {})

        print('✓ 找到 assessment_result')
        print(f'  - type_code: {result_data.get(\"type_code\")}')
        print(f'  - dimension_rows 数量: {len(result_data.get(\"dimension_rows\", []))}')
        print(f'  - labels 数量: {len(result_data.get(\"labels\", []))}')
        print(f'  - labels 内容: {result_data.get(\"labels\", [])}')

        if result_data.get('dimension_rows'):
            print('  - dimension_rows 第一项:', result_data['dimension_rows'][0])

        # 检查 interpretation_data
        interp = result_data.get('interpretation_data', {})
        if interp.get('extreme_tags'):
            print(f'  - extreme_tags 数量: {len(interp[\"extreme_tags\"])}')
            print('  - extreme_tags 第一项:', interp['extreme_tags'][0])

        break
"

echo ""
echo "=== 测试完成 ==="