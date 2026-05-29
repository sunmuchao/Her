-- 检查是否有异常的main_group会话被自动创建
-- 查询accepted状态的case，检查是否有main_group会话

-- 1. 查询所有accepted状态的proxy_intro case
SELECT
    mc.case_id,
    mc.case_status,
    mc.created_at,
    mc.updated_at,
    mc.requester_id,
    mc.candidate_id
FROM match_cases mc
WHERE mc.case_status = 'accepted'
ORDER BY mc.updated_at DESC
LIMIT 10;

-- 2. 检查这些case是否有对应的main_group会话
SELECT
    cc.conversation_id,
    cc.case_id,
    cc.channel_key,
    cc.status,
    cc.created_at,
    mc.case_status
FROM chat_conversations cc
JOIN match_cases mc ON cc.case_id = mc.case_id
WHERE cc.channel_key = 'main_group'
  AND mc.case_status = 'accepted'
ORDER BY cc.created_at DESC
LIMIT 10;

-- 3. 检查是否有accepted状态的case但在聊天中（应该显示在"正在进行中"）
-- 这就是问题所在：这些case不应该有main_group会话
SELECT
    mc.case_id,
    mc.case_status,
    mc.close_reason,
    cc.conversation_id AS main_group_conversation_id,
    cc.created_at AS conversation_created_at,
    mc.updated_at AS case_updated_at
FROM match_cases mc
LEFT JOIN chat_conversations cc
    ON mc.case_id = cc.case_id
    AND cc.channel_key = 'main_group'
WHERE mc.case_status = 'accepted'
  AND cc.conversation_id IS NOT NULL
ORDER BY mc.updated_at DESC
LIMIT 10;

-- 4. 检查opening_probe任务是否在这些case上触发过
SELECT
    cas.session_id,
    cas.case_id,
    cas.status,
    cat.task_id,
    cat.reason,
    cat.created_at
FROM chat_agent_sessions cas
JOIN chat_agent_tasks cat ON cas.session_id = cat.session_id
WHERE cat.reason = 'opening_probe'
  AND cas.case_id IN (
      SELECT mc.case_id
      FROM match_cases mc
      WHERE mc.case_status = 'accepted'
  )
ORDER BY cat.created_at DESC
LIMIT 10;