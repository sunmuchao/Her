-- 李欣琪（回避型依恋）完整session

INSERT INTO discovery_agent_sessions
(session_id, requester_id, profile_id, status, phase, state_json, latest_view_json, created_at, updated_at)
VALUES ('discovery-session-c9c84cd45881', 573, 573, 'active', 'results_shown', '{}', '{}', '2026-06-10 14:30:00', '2026-06-10 14:30:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-c9c84cd45881', 'session_opened', NULL, '{"assistant_message": "\\u6211\\u6839\\u636e\\u4f60\\u521a\\u586b\\u7684\\u8d44\\u6599\\u7b5b\\u4e86\\u51e0\\u4f4d\\uff0c\\u4f60\\u5148\\u770b\\u770b\\u6709\\u6ca1\\u6709\\u773c\\u7f18\\u3002\\u89c9\\u5f97\\u4e0d\\u5408\\u9002\\uff0c\\u968f\\u65f6\\u8ddf\\u6211\\u8bf4\\u3002", "criteria_labels": ["\\u65e0\\u9521", "\\u7537", "27-32\\u5c81", "\\u8ba4\\u771f\\u604b\\u7231"], "phase": "results_shown", "result_group_title": "\\u6839\\u636e\\u4f60\\u7684\\u8d44\\u6599\\uff0c\\u5148\\u7ed9\\u4f60\\u770b\\u8fd9\\u4e9b", "selected_candidates": [{"profile_id": 8931, "reason_summary": "30\\u5c81\\u4ea7\\u54c1\\u7ecf\\u7406\\uff0c\\u60c5\\u7eea\\u7a33\\u5b9a\\u7406\\u6027\\uff0c\\u793e\\u4ea4\\u5708\\u7b80\\u5355"}, {"profile_id": 7724, "reason_summary": "29\\u5c81\\u836f\\u5e08\\uff0c\\u6e29\\u548c\\u6709\\u8d23\\u4efb\\u611f\\uff0c\\u5de5\\u4f5c\\u7a33\\u5b9a"}, {"profile_id": 6726, "reason_summary": "32\\u5c81\\u6559\\u5e08\\uff0c\\u8fb9\\u754c\\u6e05\\u695a\\u6709\\u4e3b\\u89c1\\uff0c\\u5c0a\\u91cd\\u5f7c\\u6b64\\u7a7a\\u95f4"}], "suggested_actions": []}', '{"composer": {"disabled": false, "placeholder": "\\u7ee7\\u7eed\\u544a\\u8bc9\\u7ea2\\u5a18\\u4f60\\u7684\\u8981\\u6c42"}, "criteria_chips": [{"chip_id": "chip-1", "label": "\\u65e0\\u9521"}, {"chip_id": "chip-2", "label": "\\u7537"}, {"chip_id": "chip-3", "label": "27-32\\u5c81"}, {"chip_id": "chip-4", "label": "\\u8ba4\\u771f\\u604b\\u7231"}], "timeline": [{"item_type": "assistant_message", "body": "\\u6211\\u6839\\u636e\\u4f60\\u521a\\u586b\\u7684\\u8d44\\u6599\\u7b5b\\u4e86\\u51e0\\u4f4d...", "created_at": "2026-06-10T14:30:00"}, {"item_type": "result_group", "title": "\\u6839\\u636e\\u4f60\\u7684\\u8d44\\u6599\\uff0c\\u5148\\u7ed9\\u4f60\\u770b\\u8fd9\\u4e9b", "cards": [{"profile_id": 8931, "title": "\\u5f20\\u8fb0\\u745e 30"}, {"profile_id": 7724, "title": "\\u8d75\\u6d69\\u8861 29"}, {"profile_id": 6726, "title": "\\u8d75\\u601d\\u51ef 32"}]}]}', '2026-06-10 14:30:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-c9c84cd45881', 'user_message', '我比较看重边界感，不喜欢对方太黏人，希望能有自己的空间', '{"assistant_message": "\\u6536\\u5230\\u3002\\u6211\\u6ce8\\u610f\\u5230\\u4f60\\u63d0\\u5230\\u8fb9\\u754c\\u611f\\uff0c\\u8fd9\\u70b9\\u5f88\\u91cd\\u8981\\u3002\\u4f60\\u5e0c\\u671b\\u5bf9\\u65b9\\u80fd\\u7406\\u89e3\\u4f60\\u9700\\u8981\\u72ec\\u7acb\\u7a7a\\u95f4\\uff0c\\u4e0d\\u5f3a\\u5236\\u5206\\u4eab\\u6240\\u6709\\u4e8b\\u60c5\\uff0c\\u5bf9\\u5417\\uff1f\\u6211\\u5e2e\\u4f60\\u628a\\u8fd9\\u70b9\\u52a0\\u5230\\u7b5b\\u9009\\u6761\\u4ef6\\u91cc\\u3002", "phase": "collecting_preferences", "selected_candidates": []}', '{"timeline": [{"item_type": "user_message", "body": "\\u6211\\u6bd4\\u8f83\\u770b\\u91cd\\u8fb9\\u754c\\u611f\\uff0c\\u4e0d\\u559c\\u6b22\\u5bf9\\u65b9\\u592a\\u9ecf\\u4eba\\uff0c\\u5e0c\\u671b\\u80fd\\u6709\\u81ea\\u5df1\\u7684\\u7a7a\\u95f4"}, {"item_type": "assistant_message", "body": "\\u6536\\u5230\\u3002\\u6211\\u6ce8\\u610f\\u5230\\u4f60\\u63d0\\u5230\\u8fb9\\u754c\\u611f\\uff0c\\u8fd9\\u70b9\\u5f88\\u91cd\\u8981\\u3002\\u4f60\\u5e0c\\u671b\\u5bf9\\u65b9\\u80fd\\u7406\\u89e3\\u4f60\\u9700\\u8981\\u72ec\\u7acb\\u7a7a\\u95f4\\uff0c\\u4e0d\\u5f3a\\u5236\\u5206\\u4eab\\u6240\\u6709\\u4e8b\\u60c5\\uff0c\\u5bf9\\u5417\\uff1f\\u6211\\u5e2e\\u4f60\\u628a\\u8fd9\\u70b9\\u52a0\\u5230\\u7b5b\\u9009\\u6761\\u4ef6\\u91cc\\u3002"}]}', '2026-06-10 14:35:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-c9c84cd45881', 'user_message', '对，而且我希望对方有自己的爱好和朋友圈，不要每天都要在一起', '{"assistant_message": "\\u660e\\u767d\\u4e86\\uff0c\\u6b23\\u742a\\u3002\\u4f60\\u5e0c\\u671b\\u7684\\u662f\\u4e00\\u79cd\\u6210\\u719f\\u72ec\\u7acb\\u7684\\u5173\\u7cfb\\u6a21\\u5f0f\\uff0c\\u4e24\\u4e2a\\u4eba\\u90fd\\u6709\\u81ea\\u5df1\\u7684\\u751f\\u6d3b\\u548c\\u7a7a\\u95f4\\uff0c\\u4f46\\u5173\\u952e\\u65f6\\u523b\\u80fd\\u5f7c\\u6b64\\u652f\\u6301\\u3002\\u6211\\u91cd\\u65b0\\u8c03\\u6574\\u4e86\\u4e00\\u4e0b\\u7b5b\\u9009\\uff0c\\u8fd9\\u6b21\\u7ed9\\u4f60\\u63a8\\u8350\\u51e0\\u4f4d\\u66f4\\u7b26\\u5408\\u4f60\\u671f\\u5f85\\u7684\\uff1a", "phase": "results_shown", "selected_candidates": []}', '{"timeline": [{"item_type": "user_message", "body": "\\u5bf9\\uff0c\\u800c\\u4e14\\u6211\\u5e0c\\u671b\\u5bf9\\u65b9\\u6709\\u81ea\\u5df1\\u7684\\u7231\\u597d\\u548c\\u670b\\u53cb\\u5708\\uff0c\\u4e0d\\u8981\\u6bcf\\u5929\\u90fd\\u8981\\u5728\\u4e00\\u8d77"}, {"item_type": "assistant_message", "body": "\\u660e\\u767d\\u4e86\\uff0c\\u6b23\\u742a\\u3002\\u4f60\\u5e0c\\u671b\\u7684\\u662f\\u4e00\\u79cd\\u6210\\u719f\\u72ec\\u7acb\\u7684\\u5173\\u7cfb\\u6a21\\u5f0f\\uff0c\\u4e24\\u4e2a\\u4eba\\u90fd\\u6709\\u81ea\\u5df1\\u7684\\u751f\\u6d3b\\u548c\\u7a7a\\u95f4\\uff0c\\u4f46\\u5173\\u952e\\u65f6\\u523b\\u80fd\\u5f7c\\u6b64\\u652f\\u6301\\u3002\\u6211\\u91cd\\u65b0\\u8c03\\u6574\\u4e86\\u4e00\\u4e0b\\u7b5b\\u9009\\uff0c\\u8fd9\\u6b21\\u7ed9\\u4f60\\u63a8\\u8350\\u51e0\\u4f4d\\u66f4\\u7b26\\u5408\\u4f60\\u671f\\u5f85\\u7684\\uff1a"}]}', '2026-06-10 14:38:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-c9c84cd45881', 'user_message', '赵思凯看起来不错，他的边界感和独立性都比较符合', '{"assistant_message": "\\u597d\\u7684\\uff0c\\u6b23\\u742a\\uff01\\u8d75\\u601d\\u51ef32\\u5c81\\u6559\\u5e08\\uff0c\\u786e\\u5b9e\\u5f88\\u7b26\\u5408\\u4f60\\u7684\\u8981\\u6c42\\u3002\\u4ed6\\u7684\\u6027\\u683c\\u662f\\u8fb9\\u754c\\u6e05\\u695a\\u3001\\u6709\\u4e3b\\u89c1\\u3001\\u5c0a\\u91cd\\u5f7c\\u6b64\\u7a7a\\u95f4\\uff0c\\u800c\\u4e14\\u4ed6\\u4e5f\\u63d0\\u5230\\u5e0c\\u671b\\u4e24\\u4e2a\\u4eba\\u90fd\\u6709\\u72ec\\u7acb\\u7684\\u751f\\u6d3b\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 6726, "reason_summary": "32\\u5c81\\u6559\\u5e08\\uff0c\\u8fb9\\u754c\\u6e05\\u695a"}]}', '{"timeline": [{"item_type": "user_message", "body": "\\u8d75\\u601d\\u51ef\\u770b\\u8d77\\u6765\\u4e0d\\u9519\\uff0c\\u4ed6\\u7684\\u8fb9\\u754c\\u611f\\u548c\\u72ec\\u7acb\\u6027\\u90fd\\u6bd4\\u8f83\\u7b26\\u5408"}, {"item_type": "assistant_message", "body": "\\u597d\\u7684\\uff0c\\u6b23\\u742a\\uff01\\u8d75\\u601d\\u51ef32\\u5c81\\u6559\\u5e08\\uff0c\\u786e\\u5b9e\\u5f88\\u7b26\\u5408\\u4f60\\u7684\\u8981\\u6c42\\u3002\\u4ed6\\u7684\\u6027\\u683c\\u662f\\u8fb9\\u754c\\u6e05\\u695a\\u3001\\u6709\\u4e3b\\u89c1\\u3001\\u5c0a\\u91cd\\u5f7c\\u6b64\\u7a7a\\u95f4\\uff0c\\u800c\\u4e14\\u4ed6\\u4e5f\\u63d0\\u5230\\u5e0c\\u671b\\u4e24\\u4e2a\\u4eba\\u90fd\\u6709\\u72ec\\u7acb\\u7684\\u751f\\u6d3b\\u3002"}]}', '2026-06-10 14:46:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-c9c84cd45881', 'user_message', '张辰瑞有点太理性了，感觉相处起来会比较冷淡', '{"assistant_message": "\\u6536\\u5230\\uff0c\\u6b23\\u742a\\u3002\\u4f60\\u63d0\\u5230\\u5f20\\u8fb0\\u745e\\u592a\\u7406\\u6027\\u53ef\\u80fd\\u663e\\u5f97\\u51b7\\u6de1\\uff0c\\u8fd9\\u70b9\\u6211\\u7406\\u89e3\\u3002\\u867d\\u7136\\u7406\\u6027\\u662f\\u4f18\\u70b9\\uff0c\\u4f46\\u5982\\u679c\\u7f3a\\u4e4f\\u6e29\\u5ea6\\uff0c\\u786e\\u5b9e\\u53ef\\u80fd\\u5f71\\u54cd\\u76f8\\u5904\\u611f\\u53d7\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 6726, "reason_summary": "32\\u5c81\\u6559\\u5e08\\uff0c\\u8fb9\\u754c\\u6e05\\u695a"}]}', '{"timeline": [{"item_type": "user_message", "body": "\\u5f20\\u8fb0\\u745e\\u6709\\u70b9\\u592a\\u7406\\u6027\\u4e86\\uff0c\\u611f\\u89c9\\u76f8\\u5904\\u8d77\\u6765\\u4f1a\\u6bd4\\u8f83\\u51b7\\u6de1"}, {"item_type": "assistant_message", "body": "\\u6536\\u5230\\uff0c\\u6b23\\u742a\\u3002\\u4f60\\u63d0\\u5230\\u5f20\\u8fb0\\u745e\\u592a\\u7406\\u6027\\u53ef\\u80fd\\u663e\\u5f97\\u51b7\\u6de1\\uff0c\\u8fd9\\u70b9\\u6211\\u7406\\u89e3\\u3002\\u867d\\u7136\\u7406\\u6027\\u662f\\u4f18\\u70b9\\uff0c\\u4f46\\u5982\\u679c\\u7f3a\\u4e4f\\u6e29\\u5ea6\\uff0c\\u786e\\u5b9e\\u53ef\\u80fd\\u5f71\\u54cd\\u76f8\\u5904\\u611f\\u53d7\\u3002"}]}', '2026-06-10 14:58:00');


-- 陈佳悦（安全型依恋）完整session

INSERT INTO discovery_agent_sessions
(session_id, requester_id, profile_id, status, phase, state_json, latest_view_json, created_at, updated_at)
VALUES ('discovery-session-3736c5cc27eb', 6609, 6609, 'active', 'results_shown', '{}', '{}', '2026-06-11 15:20:00', '2026-06-11 15:20:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-3736c5cc27eb', 'session_opened', NULL, '{"assistant_message": "\\u6211\\u6839\\u636e\\u4f60\\u521a\\u586b\\u7684\\u8d44\\u6599\\u7b5b\\u4e86\\u51e0\\u4f4d\\uff0c\\u4f60\\u5148\\u770b\\u770b\\u6709\\u6ca1\\u6709\\u773c\\u7f18\\u3002\\u89c9\\u5f97\\u4e0d\\u5408\\u9002\\uff0c\\u968f\\u65f6\\u8ddf\\u6211\\u8bf4\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 8931, "reason_summary": ""}, {"profile_id": 7724, "reason_summary": ""}, {"profile_id": 6726, "reason_summary": ""}]}', '{"timeline": []}', '2026-06-11 15:20:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-3736c5cc27eb', 'user_message', '我希望能找个性格温和、有责任感的人，最好是工作稳定的', '{"assistant_message": "\\u6536\\u5230\\uff0c\\u4f73\\u60a6\\u3002\\u4f60\\u63d0\\u5230\\u5e0c\\u671b\\u5bf9\\u65b9\\u6027\\u683c\\u6e29\\u548c\\u3001\\u6709\\u8d23\\u4efb\\u611f\\u4e14\\u5de5\\u4f5c\\u7a33\\u5b9a\\uff0c\\u8fd9\\u4e9b\\u90fd\\u662f\\u5efa\\u7acb\\u957f\\u671f\\u5173\\u7cfb\\u7684\\u57fa\\u7840\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 7724, "reason_summary": ""}, {"profile_id": 6726, "reason_summary": ""}, {"profile_id": 5701, "reason_summary": ""}]}', '{"timeline": []}', '2026-06-11 15:26:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-3736c5cc27eb', 'user_message', '我长期在无锡定居，希望对方也有定居意向，不要经常变动', '{"assistant_message": "\\u660e\\u767d\\u4e86\\uff0c\\u4f73\\u60a6\\u3002\\u4f60\\u5728\\u65e0\\u9521\\u957f\\u671f\\u5b9a\\u5c45\\uff0c\\u5e0c\\u671b\\u5bf9\\u65b9\\u4e5f\\u6709\\u660e\\u786e\\u7684\\u5b9a\\u5c45\\u8ba1\\u5212\\uff0c\\u8fd9\\u6837\\u4e24\\u4eba\\u624d\\u80fd\\u4e00\\u8d77\\u89c4\\u5212\\u672a\\u6765\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 7724, "reason_summary": ""}, {"profile_id": 6726, "reason_summary": ""}, {"profile_id": 5701, "reason_summary": ""}]}', '{"timeline": []}', '2026-06-11 15:30:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-3736c5cc27eb', 'user_message', '赵浩衡看起来不错，温和有责任感，而且也是药师工作稳定', '{"assistant_message": "\\u597d\\u7684\\uff0c\\u4f73\\u60a6\\uff01\\u8d75\\u6d69\\u886129\\u5c81\\u836f\\u5e08\\uff0c\\u786e\\u5b9e\\u5f88\\u7b26\\u5408\\u4f60\\u7684\\u8981\\u6c42\\u3002\\u4ed6\\u7684\\u6027\\u683c\\u6e29\\u548c\\u6709\\u8d23\\u4efb\\u611f\\uff0c\\u800c\\u4e14\\u5728\\u65e0\\u9521\\u5b9a\\u5c45\\u591a\\u5e74\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 7724, "reason_summary": ""}]}', '{"timeline": []}', '2026-06-11 15:40:00');


-- 冯静雯（焦虑型依恋）完整session

INSERT INTO discovery_agent_sessions
(session_id, requester_id, profile_id, status, phase, state_json, latest_view_json, created_at, updated_at)
VALUES ('discovery-session-03812e67508e', 3611, 3611, 'active', 'results_shown', '{}', '{}', '2026-06-12 16:45:00', '2026-06-12 16:45:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-03812e67508e', 'session_opened', NULL, '{"assistant_message": "\\u6211\\u6839\\u636e\\u4f60\\u521a\\u586b\\u7684\\u8d44\\u6599\\u7b5b\\u4e86\\u51e0\\u4f4d\\uff0c\\u4f60\\u5148\\u770b\\u770b\\u6709\\u6ca1\\u6709\\u773c\\u7f18\\u3002\\u89c9\\u5f97\\u4e0d\\u5408\\u9002\\uff0c\\u968f\\u65f6\\u8ddf\\u6211\\u8bf4\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 7724, "reason_summary": ""}, {"profile_id": 6726, "reason_summary": ""}, {"profile_id": 8931, "reason_summary": ""}]}', '{"timeline": []}', '2026-06-12 16:45:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-03812e67508e', 'user_message', '我比较慢热，需要对方主动一点，不然我会很焦虑，担心他是不是不喜欢我', '{"assistant_message": "\\u6536\\u5230\\uff0c\\u9759\\u96ef\\u3002\\u4f60\\u63d0\\u5230\\u81ea\\u5df1\\u6162\\u70ed\\u9700\\u8981\\u5bf9\\u65b9\\u4e3b\\u52a8\\uff0c\\u8fd9\\u79cd\\u611f\\u53d7\\u5f88\\u771f\\u5b9e\\u3002\\u7126\\u8651\\u611f\\u5f80\\u5f80\\u6e90\\u4e8e\\u4e0d\\u786e\\u5b9a\\uff0c\\u6240\\u4ee5\\u4f60\\u5e0c\\u671b\\u5bf9\\u65b9\\u80fd\\u7ed9\\u4f60\\u6e05\\u6670\\u7684\\u5b89\\u5168\\u611f\\u786e\\u8ba4\\u3002", "phase": "collecting_preferences", "selected_candidates": []}', '{"timeline": []}', '2026-06-12 16:53:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-03812e67508e', 'user_message', '对，我希望他能主动分享日常，不要让我总是猜测他的想法', '{"assistant_message": "\\u660e\\u767d\\u4e86\\uff0c\\u9759\\u96ef\\u3002\\u4f60\\u5e0c\\u671b\\u7684\\u662f\\u4e00\\u79cd\\u900f\\u660e\\u5ea6\\u9ad8\\u7684\\u5173\\u7cfb\\uff0c\\u5bf9\\u65b9\\u613f\\u610f\\u4e3b\\u52a8\\u5206\\u4eab\\u65e5\\u5e38\\u548c\\u60f3\\u6cd5\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 7724, "reason_summary": ""}, {"profile_id": 5701, "reason_summary": ""}, {"profile_id": 1318, "reason_summary": ""}]}', '{"timeline": []}', '2026-06-12 16:56:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-03812e67508e', 'user_message', '而且我有长期在无锡定居的打算，希望对方也有', '{"assistant_message": "\\u6536\\u5230\\uff0c\\u9759\\u96ef\\u3002\\u957f\\u671f\\u5b9a\\u5c45\\u65e0\\u9521\\u4e5f\\u662f\\u4e2a\\u91cd\\u8981\\u7684\\u5b89\\u5168\\u611f\\u6765\\u6e90\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 7724, "reason_summary": ""}, {"profile_id": 5701, "reason_summary": ""}, {"profile_id": 6726, "reason_summary": ""}]}', '{"timeline": []}', '2026-06-12 17:01:00');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-03812e67508e', 'user_message', '赵浩衡看起来不错，温和细腻，而且他也是药师，工作稳定', '{"assistant_message": "\\u597d\\u7684\\uff0c\\u9759\\u96ef\\uff01\\u8d75\\u6d69\\u886129\\u5c81\\u836f\\u5e08\\uff0c\\u6e29\\u548c\\u7ec6\\u817b\\uff0c\\u5584\\u4e8e\\u503e\\u542c\\u548c\\u6c9f\\u901a\\uff0c\\u800c\\u4e14\\u4ed6\\u63d0\\u5230\\u613f\\u610f\\u4e3b\\u52a8\\u5206\\u4eab\\u65e5\\u5e38\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 7724, "reason_summary": ""}]}', '{"timeline": []}', '2026-06-12 17:13:00');


-- 张安萌（安全型依恋）补充现有session

INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-ff37e68c0df5', 'user_message', '这几位看起来都还不错，不过我希望能找个性格温和善沟通的', '{"assistant_message": "\\u6536\\u5230\\uff0c\\u5b89\\u840c\\u3002\\u4f60\\u63d0\\u5230\\u5e0c\\u671b\\u5bf9\\u65b9\\u6027\\u683c\\u6e29\\u548c\\u5584\\u6c9f\\u901a\\uff0c\\u8fd9\\u548c\\u4f60\\u7684\\u6027\\u683c\\u5f88\\u5339\\u914d\\u3002\\u6211\\u5e2e\\u4f60\\u8c03\\u6574\\u7b5b\\u9009\\uff0c\\u91cd\\u70b9\\u770b\\u51e0\\u4f4d\\u6c9f\\u901a\\u80fd\\u529b\\u5f3a\\u7684\\uff1a", "phase": "results_shown", "selected_candidates": [{"profile_id": 1318, "reason_summary": ""}, {"profile_id": 7724, "reason_summary": ""}, {"profile_id": 2288, "reason_summary": ""}]}', '{"timeline": []}', '2026-05-28 18:08:08');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-ff37e68c0df5', 'user_message', '胡嘉衡看起来不错，29岁会计，而且性格温和善沟通', '{"assistant_message": "\\u597d\\u7684\\uff0c\\u5b89\\u840c\\uff01\\u80e1\\u5609\\u886129\\u5c81\\u4f1a\\u8ba1\\uff0c\\u786e\\u5b9e\\u6027\\u683c\\u6e29\\u548c\\u5584\\u6c9f\\u901a\\uff0c\\u548c\\u4f60\\u5f88\\u5339\\u914d\\u3002\\u800c\\u4e14\\u4ed6\\u5728\\u65e0\\u9521\\u5b9a\\u5c45\\u591a\\u5e74\\uff0c\\u5de5\\u4f5c\\u7a33\\u5b9a\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 1318, "reason_summary": ""}]}', '{"timeline": []}', '2026-05-28 18:13:08');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-ff37e68c0df5', 'user_message', '不过孙承骁也是采购，跟我职业一样，会不会更有共同话题', '{"assistant_message": "\\u4f60\\u8bf4\\u5f97\\u5bf9\\uff0c\\u5b89\\u840c\\uff01\\u5b59\\u627f\\u9a8128\\u5c81\\u91c7\\u8d2d\\uff0c\\u548c\\u4f60\\u804c\\u4e1a\\u76f8\\u540c\\uff0c\\u786e\\u5b9e\\u53ef\\u80fd\\u6709\\u66f4\\u591a\\u5171\\u540c\\u8bdd\\u9898\\u548c\\u884c\\u4e1a\\u7406\\u89e3\\u3002\\u6211\\u5e2e\\u4f60\\u770b\\u770b\\u4ed6\\u7684\\u8be6\\u7ec6\\u8d44\\u6599\\uff1a", "phase": "results_shown", "selected_candidates": [{"profile_id": 2288, "reason_summary": ""}]}', '{"timeline": []}', '2026-05-28 18:18:08');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-ff37e68c0df5', 'user_message', '嗯，那我先看看孙承骁的资料吧，采购同行应该挺有意思', '{"assistant_message": "\\u597d\\u7684\\uff0c\\u5b89\\u840c\\uff01\\u6211\\u5e2e\\u4f60\\u6253\\u5f00\\u5b59\\u627f\\u9a81\\u7684\\u8d44\\u6599\\u9875\\u3002\\u4ed6\\u662f28\\u5c81\\u91c7\\u8d2d\\uff0c\\u672c\\u79d1\\u5b66\\u5386\\uff0c\\u5728\\u65e0\\u9521\\u5de5\\u4f5c\\u7a33\\u5b9a\\u3002\\u4f60\\u4eec\\u804c\\u4e1a\\u76f8\\u540c\\uff0c\\u786e\\u5b9e\\u6709\\u5f88\\u591a\\u53ef\\u4ee5\\u804a\\u7684\\u8bdd\\u9898\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 2288, "reason_summary": ""}]}', '{"timeline": []}', '2026-05-28 18:23:08');


-- 陈以心（安全型依恋）补充现有session

INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-0f33cf41a7bd', 'user_message', '你好，我想看看这几位的详细信息', '{"assistant_message": "\\u4f60\\u597d\\uff0c\\u4ee5\\u5fc3\\uff01\\u521a\\u624d\\u6839\\u636e\\u4f60\\u7684\\u8d44\\u6599\\u7b5b\\u4e865\\u4f4d\\u65e0\\u9521\\u7684\\u7537\\u751f\\uff0c\\u4f60\\u53ef\\u4ee5\\u5148\\u770b\\u770b\\u6709\\u6ca1\\u6709\\u773c\\u7f18\\u3002\\u5982\\u679c\\u6709\\u89c9\\u5f97\\u4e0d\\u9519\\u7684\\uff0c\\u6216\\u8005\\u60f3\\u8c03\\u6574\\u7b5b\\u9009\\u65b9\\u5411\\uff0c\\u968f\\u65f6\\u8ddf\\u6211\\u8bf4\\uff5e", "phase": "results_shown", "selected_candidates": [{"profile_id": 8931, "reason_summary": ""}, {"profile_id": 7724, "reason_summary": ""}, {"profile_id": 7132, "reason_summary": ""}, {"profile_id": 8481, "reason_summary": ""}, {"profile_id": 6726, "reason_summary": ""}]}', '{"timeline": []}', '2026-05-29 11:35:06');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-0f33cf41a7bd', 'user_message', '我希望能找个开朗有责任感的人，最好是硕士学历', '{"assistant_message": "\\u6536\\u5230\\uff0c\\u4ee5\\u5fc3\\u3002\\u4f60\\u63d0\\u5230\\u5e0c\\u671b\\u5bf9\\u65b9\\u5f00\\u6717\\u6709\\u8d23\\u4efb\\u611f\\uff0c\\u800c\\u4e14\\u662f\\u7855\\u58eb\\u5b66\\u5386\\uff0c\\u8fd9\\u4e9b\\u6761\\u4ef6\\u548c\\u4f60\\u90fd\\u5f88\\u5339\\u914d\\u3002\\u6211\\u5e2e\\u4f60\\u91cd\\u65b0\\u7b5b\\u9009\\uff0c\\u91cd\\u70b9\\u770b\\u51e0\\u4f4d\\u7855\\u58eb\\u5b66\\u5386\\u7684\\uff1a", "phase": "results_shown", "selected_candidates": [{"profile_id": 8931, "reason_summary": ""}, {"profile_id": 7132, "reason_summary": ""}, {"profile_id": 6726, "reason_summary": ""}]}', '{"timeline": []}', '2026-05-29 11:38:06');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-0f33cf41a7bd', 'user_message', '张辰瑞看起来不错，30岁产品经理，硕士学历', '{"assistant_message": "\\u597d\\u7684\\uff0c\\u4ee5\\u5fc3\\uff01\\u5f20\\u8fb0\\u745e30\\u5c81\\u4ea7\\u54c1\\u7ecf\\u7406\\uff0c\\u7855\\u58eb\\u5b66\\u5386\\uff0c\\u786e\\u5b9e\\u7b26\\u5408\\u4f60\\u7684\\u8981\\u6c42\\u3002\\u800c\\u4e14\\u4ed6\\u6027\\u683c\\u5f00\\u6717\\u7406\\u6027\\uff0c\\u793e\\u4ea4\\u5708\\u7b80\\u5355\\u3002", "phase": "results_shown", "selected_candidates": [{"profile_id": 8931, "reason_summary": ""}]}', '{"timeline": []}', '2026-05-29 11:42:06');


INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('discovery-session-0f33cf41a7bd', 'user_message', '嗯，而且我也是产品运营，和他职业相近，应该有共同话题', '{"assistant_message": "\\u4f60\\u8bf4\\u5f97\\u5bf9\\uff0c\\u4ee5\\u5fc3\\uff01\\u4f60\\u505a\\u4ea7\\u54c1\\u8fd0\\u8425\\uff0c\\u4ed6\\u505a\\u4ea7\\u54c1\\u7ecf\\u7406\\uff0c\\u804c\\u4e1a\\u786e\\u5b9e\\u76f8\\u8fd1\\uff0c\\u6709\\u5f88\\u591a\\u53ef\\u4ee5\\u804a\\u7684\\u8bdd\\u9898\\u3002\\u6211\\u5e2e\\u4f60\\u6253\\u5f00\\u4ed6\\u7684\\u8d44\\u6599\\u9875\\u770b\\u770b\\uff1f", "phase": "results_shown", "selected_candidates": [{"profile_id": 8931, "reason_summary": ""}]}', '{"timeline": []}', '2026-05-29 11:48:06');
