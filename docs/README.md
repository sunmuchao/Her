# Docs Guide

- Frontend improvement plan: [`frontend-improvement-plan.md`](./frontend-improvement-plan.md) — 现状问题、分阶段改造、验收与 PR 拆分。
- Section 13.1 mainline architecture improvement plan: [`section13-1-mainline-architecture-improvement-plan.md`](./section13-1-mainline-architecture-improvement-plan.md) — 围绕“找对象 -> 建立连接 -> 聊天”的完整收敛方案。
- Section 13.1 mainline architecture task breakdown: [`section13-1-mainline-architecture-task-breakdown.md`](./section13-1-mainline-architecture-task-breakdown.md) — 将收敛方案拆成阶段任务、文件落点、交付物与验收标准。
- Current implementation truth lives in executable code, package README files under `external-systems/`, and the test suite.
- Files under `docs/chat-*` and `docs/discovery-*` include historical design and planning material. They are useful for context, but they are not authoritative when they reference files or flows that no longer exist.
- When a planning document and the live code disagree, follow the live code and update the document instead of reviving the old proposal verbatim.
