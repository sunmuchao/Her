# 学习闭环功能实施文档

## 一、已完成的工作

### Phase 1: 数据层准备 ✅

**创建的文件**：
1. `/Users/sunmuchao/Downloads/Her/outer_system_mysql_schema.py` - 新增两个表定义：
   - `discovery_rejection_feedbacks` - 拒绝反馈表
   - `discovery_working_criteria_adjustments` - working_criteria调整记录表

2. `/Users/sunmuchao/Downloads/Her/db_migrations/targets/discovery/m0007_add_rejection_feedback.py` - 数据库迁移脚本

### Phase 2: 工具层实现 ✅

**创建的文件**：
1. `/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system/discovery_system/feedback_service.py` - 反馈服务核心逻辑：
   - 反馈类型推断函数 `infer_feedback_type`
   - 反馈选项生成函数 `generate_feedback_options`
   - 反馈到调整策略映射 `FEEDBACK_TO_CRITERIA_ADJUSTMENT`
   - 二级追问选项映射 `SECONDARY_OPTIONS_MAP`

### Phase 3: Agent Prompt设计 ✅

**创建的文件**：
1. `/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md` - Agent角色定义：
   - 核心角色和原则
   - 追问时机判断（每次都追问）
   - 反馈选项设计原则（避免抽象选项）
   - 反馈类型到调整策略映射

### Phase 4: 前端实现 ✅

**创建的文件**：
1. `/Users/sunmuchao/Downloads/Her/frontend/her-app/components/discovery/FeedbackOptionsPanel.tsx` - 前端组件：
   - 一级反馈选项组件 `FeedbackOptionsPanel`
   - 二级追问组件 `SecondaryFeedbackPanel`

### Phase 5: 后端API实现 ✅

**创建的文件**：
1. `/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway/gateway/discovery_feedback_routes.py` - API路由：
   - POST `/v1/discovery/feedback` - 提交反馈
   - POST `/v1/discovery/feedback/skip` - 跳过反馈
   - GET `/v1/discovery/feedback/options` - 获取选项列表

### Phase 6: 验证与测试 ✅

**创建的文件**：
1. `/Users/sunmuchao/Downloads/Her/tests/test_rejection_feedback.py` - 测试用例：
   - 反馈类型推断测试
   - 反馈选项生成测试
   - 调整策略映射测试

---

## 二、后续需要完成的工作

### 2.1 数据层集成

**需要做的事情**：
1. 运行数据库迁移脚本，创建新表
2. 在storage.py中添加反馈记录的存储接口：
   - `insert_rejection_feedback()`
   - `insert_criteria_adjustment()`
   - `load_working_criteria_adjustments()`

### 2.2 工具层集成

**需要做的事情**：
1. 在service.py中添加工具函数的集成：
   - `record_rejection_feedback()`
   - `adjust_working_criteria()`
   - `trigger_secondary_follow_up()`
   - `record_feedback_skip()`

2. 在agent_runtime.py中注册新工具：
   - 将新工具添加到DiscoveryRunInput的工具列表
   - 更新Agent Prompt，引用DISCOVERY_AGENT_SOUL.md

### 2.3 前端集成

**需要做的事情**：
1. 在Discovery页面中集成FeedbackOptionsPanel组件：
   - 在用户说"换一批"时展示选项
   - 处理选项点击事件
   - 处理二级追问展示

2. 在map-discovery-view.ts中添加feedback_options视图类型：
   - 支持一级选项展示
   - 支持二级追问展示

### 2.4 API路由集成

**需要做的事情**：
1. 在discovery_routes.py中注册新的API路由：
   - 导入discovery_feedback_routes
   - 添加路由映射

2. 实现API路由的实际逻辑：
   - 完善handle_submit_feedback的完整流程
   - 完善handle_skip_feedback的记录逻辑
   - 完善handle_get_feedback_options的候选人获取逻辑

### 2.5 Criteria Compiler扩展

**需要做的事情**：
1. 在criteria_compiler.py中添加反馈调整支持：
   - 新增`compile_effective_criteria_with_feedback()`函数
   - 加载working_criteria调整记录
   - 合并反馈调整到搜索条件

---

## 三、部署步骤

### 3.1 本地测试

```bash
# 1. 运行数据库迁移
python -m db_migrations targets discovery

# 2. 运行单元测试
python -m pytest tests/test_rejection_feedback.py

# 3. 启动本地服务
docker-compose up -d mysql
python -m gateway.main
```

### 3.2 灰度发布

1. **第1周**：10%用户上线
   - 监控反馈收集率
   - 监控跳过率
   - 监控系统性能

2. **第2周**：50%用户上线
   - 观察推荐满意度提升
   - 观察Persona信号增长
   - 优化追问策略

3. **第3周**：100%用户上线
   - 全量上线
   - 持续监控和迭代

---

## 四、监控指标

### 4.1 关键指标

| 指标 | 目标 | 监控方式 |
|------|------|----------|
| **反馈收集率** | ≥40% | SQL查询统计 |
| **跳过率** | <60% | SQL查询统计 |
| **推荐满意度提升** | ≥15% | 用户调研/转化率对比 |
| **Persona信号增长** | ≥3倍/月 | observation表统计 |

### 4.2 监控SQL

```sql
-- 反馈收集率
SELECT
    COUNT(*) AS total_refreshes,
    SUM(CASE WHEN 追问_skipped = FALSE THEN 1 ELSE 0 END) AS feedback_count,
    SUM(CASE WHEN 追问_skipped = FALSE THEN 1 ELSE 0 END) / COUNT(*) AS feedback_rate
FROM discovery_rejection_feedbacks
WHERE created_at >= '2026-01-01';

-- 反馈类型分布
SELECT
    feedback_type,
    COUNT(*) AS count
FROM discovery_rejection_feedbacks
WHERE created_at >= '2026-01-01'
GROUP BY feedback_type
ORDER BY count DESC;

-- Persona信号增长
SELECT COUNT(*) AS monthly_signals
FROM persona_observations
WHERE source_type = 'rejection_feedback'
AND created_at >= '2026-01-01'
AND created_at < '2026-02-01';
```

---

## 五、后续迭代方向

### 5.1 短期迭代（1-2个月）

1. **优化追问策略**：
   - 根据跳过率调整追问频率
   - 根据用户性格调整追问语气
   - 动态生成更精准的选项

2. **完善调整策略**：
   - 添加更多反馈类型的调整逻辑
   - 优化调整算法（避免过激调整）
   - 添加"撤销调整"功能

### 5.2 中期迭代（3-6个月）

1. **个性化追问**：
   - 根据用户性格调整追问方式
   - 根据历史反馈优化选项生成
   - 智能判断追问时机

2. **长期偏好学习**：
   - 多次反馈后沉淀到persona
   - 自动识别偏好变化趋势
   - 建议用户更新偏好设置

### 5.3 长期迭代（6个月以上）

1. **多模态反馈**：
   - 支持语音反馈
   - 支持图片反馈（候选人照片不满意）
   - 支持自由文本反馈

2. **智能推荐优化**：
   - 基于反馈历史优化推荐算法
   - 预测用户可能的偏好变化
   - 自动调整推荐策略

---

## 六、风险应对

### 6.1 用户反感追问

**应对措施**：
- 监控跳过率，如果超过60%，考虑减少追问频率
- 追问语气要自然，避免模板化
- 提供明确的"跳过"选项，不强制用户

### 6.2 反馈类型识别错误

**应对措施**：
- 提供具体选项，降低识别难度
- 二级追问确认具体原因
- 调整后告知用户，用户可以纠正

### 6.3 调整策略过激

**应对措施**：
- 调整应该是渐进式的，不要一次过激
- working_criteria只影响当前session
- 长期偏好需要多次确认后才沉淀到persona

---

## 七、总结

### 已完成的实施

| Phase | 完成度 | 关键产出 |
|-------|--------|----------|
| Phase 1 | 100% | 数据库表定义、迁移脚本 |
| Phase 2 | 100% | 反馈服务核心逻辑 |
| Phase 3 | 100% | Agent Prompt设计 |
| Phase 4 | 100% | 前端组件骨架 |
| Phase 5 | 100% | API路由骨架 |
| Phase 6 | 100% | 测试用例 |
| Phase 7 | 80% | 实施文档 |

### 后续工作清单

1. ✅ 数据层：表定义、迁移脚本已完成
2. ✅ 工具层：反馈服务逻辑已完成
3. ✅ Agent Prompt：角色定义已完成
4. ✅ 前端：组件骨架已完成
5. ✅ API：路由骨架已完成
6. ✅ 测试：单元测试已完成
7. ⏳ 集成：需要将各个模块集成到现有系统中
8. ⏳ 部署：需要按步骤进行灰度发布

**核心骨架已搭建完成，后续需要完善集成逻辑和部署上线。**