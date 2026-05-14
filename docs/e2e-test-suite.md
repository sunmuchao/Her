# E2E Test Suite

## 1. 目标

这套测试不是单模块单元测试，而是拿真实数据库、真实网关入口、真实跨系统 case id 去跑关键业务链路。

重点解决两个问题：

1. 防止“单个模块都通过，但系统拼起来坏了”。
2. 把团队日常回归从“手工记命令”变成固定脚本。

---

## 2. 运行入口

统一入口：

```bash
bash scripts/run_e2e_tests.sh
```

可选参数：

```bash
bash scripts/run_e2e_tests.sh --python .venv/bin/python
bash scripts/run_e2e_tests.sh --skip-smoke
```

---

## 3. 当前覆盖

### 3.1 新增跨系统回归

文件：

- `external-systems/partner-http-gateway/gateway_tests/test_end_to_end_regression.py`

覆盖两条真链路：

1. 撮合 member -> 刷池 -> build pair -> open case -> dispatch -> 建聊天 thread -> timeline 汇总
2. 推荐订阅 -> refresh -> proxy-intro case -> 建聊天 thread -> timeline 汇总

这两条用例的价值是：

- 不只是测单个系统
- 明确验证 `case_id` 在不同系统之间能串起来
- 明确验证 `/v1/timeline` 这种聚合接口没有断

### 3.2 既有真实流回归

文件：

- `external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py`
- `external-systems/partner-http-gateway/gateway_tests/test_chat_conversations_v2.py`

它们继续负责：

- 推荐/信任/风控/资料核验的真实用户流
- v2 聊天会话可见性与消息流

### 3.3 Smoke

脚本：

- `external-systems/partner-chat-system/scripts/run_matchmaker_c_smoke.py --reset`

用途：

- 快速确认聊天侧触发式助理流程没有直接炸掉

---

## 4. 为什么必须串行跑

当前这些 E2E/真实流测试共享 MySQL 测试库。

所以不能并行跑，原因很简单：

- 会互相清库
- 会抢同一批固定测试表
- 容易出现“其实代码没坏，但测试互相踩库导致假失败”

因此 `scripts/run_e2e_tests.sh` 明确按固定顺序串行执行。

---

## 5. 运行前提

需要本地可用：

- Python 3.10+
- MySQL 测试实例
- 默认测试 DSN 或对应环境变量

常用环境变量：

- `PARTNER_RECOMMENDATION_TEST_DB`
- `PARTNER_MATCHMAKING_TEST_DB`
- `PARTNER_CHAT_TEST_DB`
- `PARTNER_SEARCH_E2E_TEST_DB`

如果没有单独配置 `PARTNER_SEARCH_E2E_TEST_DB`，会回退到 `PARTNER_SEARCH_REALISTIC_TEST_DB`。

---

## 6. 当前边界

这套 E2E 已经解决的是：

- 关键跨系统链路有固定回归
- timeline 聚合接口有真实数据验证
- 团队有统一脚本，不用手工拼命令

还没解决的是：

- 浏览器级前端 E2E
- 多 worker 并发下的长时间 soak test
- CI 分布式数据库隔离

那部分属于下一阶段测试基础设施建设，不是这次落地的范围。
