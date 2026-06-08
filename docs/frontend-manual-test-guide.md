# 学习闭环功能 - 前端手动测试指南

## 一、测试环境准备

### 1.1 启动服务

```bash
# 1. 启动MySQL（已完成）
docker ps | grep mysql  # 确认MySQL运行在3307端口

# 2. 启动Gateway服务
cd /Users/sunmuchao/Downloads/Her
# 根据你的启动方式启动Gateway（可能需要docker-compose或python脚本）

# 3. 启动前端应用
cd frontend/her-app
pnpm dev  # 或 npm run dev
```

### 1.2 验证数据库表

```bash
# 确认新表已创建
mysql -h 127.0.0.1 -P 3307 -u root her_discovery -e "SHOW TABLES LIKE 'discovery_%';"

# 应该看到：
# discovery_rejection_feedbacks
# discovery_working_criteria_adjustments
```

---

## 二、前端手动测试流程

### 测试场景1：用户说"换一批" → 系统追问 → 用户选"太远了"

**测试步骤**：

1. **打开Discovery页面**
   - 打开浏览器：http://localhost:3000/discovery
   - 确认页面加载成功

2. **触发换一批**
   - 在对话框中输入："给我换一批"
   - 发送消息

3. **验证系统追问**
   - ✅ 系统应该回复："好的，我帮你换一批新的。顺便问一句，上一批主要哪里不太对？"
   - ✅ 应展示4-6个反馈选项
   - ✅ 选项应该包含：
     - 动态生成的选项（基于候选人特征）
     - 通用具体选项（性格气质不对、外在条件不合适等）
     - "跳过，直接换"

4. **用户选择反馈**
   - 点击"太远了（都是异地）"选项

5. **验证系统响应**
   - ✅ 系统应该回复："明白了，我帮你调整一下，同城优先"
   - ✅ 应触发新搜索，展示同城候选人

6. **验证数据库记录**
   ```bash
   mysql -h 127.0.0.1 -P 3307 -u root her_discovery -e "
   SELECT feedback_id, feedback_type, feedback_text
   FROM discovery_rejection_feedbacks
   ORDER BY created_at DESC LIMIT 1;"
   ```

   - ✅ 应有一条记录，feedback_type='location_distance'
   - ✅ feedback_text='太远了（都是异地）'

---

### 测试场景2：用户选"外在条件不合适" → 二级追问

**测试步骤**：

1. **再次触发换一批**
   - 输入："换一批"
   - 发送

2. **选择一级选项**
   - 点击"外在条件不合适（年龄/学历/收入）"

3. **验证二级追问**
   - ✅ 系统应该追问："具体是哪个条件不太对？"
   - ✅ 应展示二级选项：
     - 年龄差距有点大
     - 学历不太匹配
     - 收入差距有点大
     - 城市太远了
     - 都不太合适
     - 不想说，直接换

4. **选择二级选项**
   - 点击"年龄差距有点大"

5. **验证系统响应**
   - ✅ 系统应该调整年龄范围
   - ✅ 展示年龄更接近的候选人

6. **验证数据库记录**
   ```bash
   mysql -h 127.0.0.1 -P 3307 -u root her_discovery -e "
   SELECT feedback_id, feedback_type, is_secondary_feedback, primary_feedback_id
   FROM discovery_rejection_feedbacks
   WHERE feedback_type='criteria_age'
   ORDER BY created_at DESC LIMIT 1;"
   ```

   - ✅ 应有一条二级反馈记录
   - ✅ is_secondary_feedback=1
   - ✅ primary_feedback_id指向一级反馈

---

### 测试场景3：用户选"性格气质不对" → 建议做测评

**测试步骤**：

1. **触发换一批**
   - 输入："换一批"

2. **选择性格气质**
   - 点击"性格气质不对（相处感觉不搭）"

3. **验证测评建议**
   - ✅ 系统应该建议："性格匹配需要深度了解。要不要做个性格测评？"
   - ✅ 应展示测评选项：
     - 好的，做测评（MBTI/依恋）
     - 先不做了，继续换一批
     - 直接换

4. **选择做测评**
   - 点击"好的，做测评（MBTI/依恋）"

5. **验证测评触发**
   - ✅ 应跳转到MBTI测评页面
   - 或展示测评卡片

---

### 测试场景4：用户点击"跳过，直接换"

**测试步骤**：

1. **触发换一批**
   - 输入："换一批"

2. **跳过反馈**
   - 点击"跳过，直接换"

3. **验证系统响应**
   - ✅ 系统应该回复："好的，帮你换一批新的"
   - ✅ 应直接展示新候选人（不追问）

4. **验证数据库记录**
   ```bash
   mysql -h 127.0.0.1 -P 3307 -u root her_discovery -e "
   SELECT feedback_id, 追问_skipped
   FROM discovery_rejection_feedbacks
   WHERE 追问_skipped=1
   ORDER BY created_at DESC LIMIT 1;"
   ```

   - ✅ 应有一条跳过记录
   - ✅ 追问_skipped=1

---

### 测试场景5：连续多次"换一批"

**测试步骤**：

1. **第1次换一批**
   - 输入："换一批"
   - 选择"太远了（都是异地）"

2. **第2次换一批**
   - 输入："换一批"
   - 选择"太忙太卷（工作压力大的感觉）"

3. **第3次换一批**
   - 输入："换一批"
   - 选择"性格气质不对（相处感觉不搭）"

4. **验证累积调整**
   ```bash
   mysql -h 127.0.0.1 -P 3307 -u root her_discovery -e "
   SELECT COUNT(*) as total_feedbacks
   FROM discovery_rejection_feedbacks
   WHERE session_id='当前session_id';"
   ```

   - ✅ 应有3条反馈记录
   - ✅ 应有累积的criteria调整记录

5. **验证推荐质量提升**
   - ✅ 第3次推荐的候选人应更符合：
     - 同城
     - 生活感强
     - 性格匹配度高

---

### 测试场景6：用户主动表达不满

**测试步骤**：

1. **用户主动表达**
   - 输入："这批都太忙太卷了，工作压力太大"
   - 发送

2. **验证系统响应**
   - ✅ 系统应该回复："明白了，你希望找工作生活平衡一些的对象。我帮你调整一下"
   - ✅ 应直接调整（不追问）

3. **验证数据库记录**
   ```bash
   mysql -h 127.0.0.1 -P 3307 -u root her_discovery -e "
   SELECT feedback_id, feedback_type, source_type
   FROM discovery_rejection_feedbacks
   WHERE feedback_text LIKE '%太忙太卷%'
   ORDER BY created_at DESC LIMIT 1;"
   ```

   - ✅ feedback_type='work_life_balance'
   - ✅ source_type='explicit'

---

### 测试场景7：用户选"都不太合适" → 触发整体澄清

**测试步骤**：

1. **触发换一批**
   - 输入："换一批"

2. **选择外在条件不合适**
   - 点击"外在条件不合适（年龄/学历/收入）"

3. **二级追问选择**
   - 点击"都不太合适"

4. **验证整体澄清触发**
   - ✅ 系统应该建议："看来你的择偶条件可能需要调整一下。要不要重新聊聊你的偏好？"
   - ✅ 应展示重新设置偏好的选项

---

## 三、边界场景测试

### 3.1 验证反馈类型推断

**测试各种反馈文案**：

| 反馈文案 | 期望推断类型 | 验证方法 |
|---------|-------------|---------|
| "太远了（都是异地）" | location_distance | 查看数据库 |
| "年龄差距有点大（候选人 28-35，你 26）" | age_gap | 查看数据库 |
| "年龄差距有点大"（二级追问） | criteria_age | 查看数据库 |
| "职业不太匹配（程序员偏多）" | occupation_mismatch | 查看数据库 |
| "太忙太卷（工作压力大的感觉）" | work_life_balance | 查看数据库 |
| "性格气质不对（相处感觉不搭）" | personality_mismatch | 查看数据库 |
| "外在条件不合适（年龄/学历/收入）" | criteria_generic | 查看数据库 |
| "学历不太匹配"（二级追问） | criteria_education | 查看数据库 |
| "收入差距有点大"（二级追问） | criteria_income | 查看数据库 |
| "城市太远了"（二级追问） | location_distance | 查看数据库 |
| "都不太合适"（二级追问） | criteria_multiple | 查看数据库 |

---

### 3.2 验证Persona更新

**测试Persona写入**：

```bash
# 查看Persona记录
mysql -h 127.0.0.1 -P 3307 -u root her -e "
SELECT observation_id, user_key, patch_json, source_type
FROM persona_observations
WHERE source_type='rejection_feedback'
ORDER BY created_at DESC LIMIT 5;"
```

- ✅ 应有Persona记录
- ✅ patch_json应包含preferred_traits/disliked_traits
- ✅ source_type='rejection_feedback'

---

### 3.3 验证Criteria调整

**测试Criteria调整记录**：

```bash
# 查看Criteria调整
mysql -h 127.0.0.1 -P 3307 -u root her_discovery -e "
SELECT adjustment_id, affected_field, adjustment_type, before_value, after_value
FROM discovery_working_criteria_adjustments
ORDER BY created_at DESC LIMIT 5;"
```

- ✅ 应有调整记录
- ✅ affected_field应与反馈类型对应
- ✅ before_value和after_value应有变化

---

## 四、性能测试

### 4.1 连续操作测试

**测试步骤**：
1. 连续执行10次"换一批"操作
2. 每次选择不同反馈
3. 验证系统响应时间是否稳定
4. 验证数据库记录是否完整

**期望结果**：
- ✅ 每次响应时间<3秒
- ✅ 数据库有10条反馈记录
- ✅ 没有重复或错误记录

---

### 4.2 并发测试（可选）

**测试步骤**：
1. 打开2个浏览器窗口
2. 同时在不同session中操作
3. 验证数据是否隔离

---

## 五、问题排查

### 5.1 常见问题及解决方案

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| 系统不追问 | Agent Prompt未加载 | 检查DISCOVERY_AGENT_SOUL.md是否被引用 |
| 反馈类型推断错误 | infer_feedback_type逻辑有bug | 查看feedback_service.py |
| 数据库无记录 | 存储接口未调用 | 检查service.py的submit_rejection_feedback |
| Persona未更新 | sync接口未调用 | 检查persona memory API |
| Criteria未调整 | compiler未合并反馈 | 检查criteria_compiler |

---

### 5.2 日志查看

```bash
# 查看Gateway日志
tail -f /tmp/gateway.log

# 查看Discovery日志
tail -f /tmp/discovery.log

# 查看数据库操作日志
mysql -h 127.0.0.1 -P 3307 -u root her_discovery -e "
SELECT * FROM discovery_rejection_feedbacks
ORDER BY created_at DESC LIMIT 10;"
```

---

## 六、验证完成标准

### 6.1 必须通过的验证点

✅ **功能验证**：
- 追问机制正确（每次都追问）
- 反馈选项生成正确（动态+通用）
- 二级追问触发正确
- 反馈类型推断正确（14种）
- 系统响应符合预期

✅ **数据验证**：
- 数据库记录完整（feedbacks + adjustments）
- Persona更新正确
- Criteria调整正确

✅ **边界验证**：
- 跳过反馈处理正确
- 连续多次操作正确
- 主动表达不满处理正确
- 整体澄清触发正确

✅ **性能验证**：
- 响应时间稳定
- 数据一致性良好

---

## 七、测试报告模板

### 测试完成后的报告

```
测试人员：[你的名字]
测试时间：[日期]
测试环境：[环境描述]

一、测试场景执行情况
- 场景1：✅/❌ [详细说明]
- 场景2：✅/❌ [详细说明]
- 场景3：✅/❌ [详细说明]
- 场景4：✅/❌ [详细说明]
- 场景5：✅/❌ [详细说明]
- 场景6：✅/❌ [详细说明]
- 场景7：✅/❌ [详细说明]

二、边界场景验证情况
- 反馈类型推断：✅ 全部正确 / ❌ [错误说明]
- Persona更新：✅ 正常 / ❌ [异常说明]
- Criteria调整：✅ 正常 / ❌ [异常说明]

三、数据库验证情况
- 表结构：✅ 正确
- 数据记录：✅ 完整 / ❌ [缺失说明]
- 数据一致性：✅ 良好 / ❌ [问题说明]

四、性能测试情况
- 平均响应时间：[数值]秒
- 并发测试结果：[结果]

五、发现的问题
- [问题1]
- [问题2]

六、总体结论
✅ 所有测试通过，功能正常
❌ 存在问题，需要修复
```

---

**测试指南完成！请按照以上步骤逐一验证，确保每个功能点都正常工作。**