---
name: persona-memory-sync
description: Persist and evolve a dating user's long-term persona, partner preferences, and inferred matching signals into MySQL, then sync both internal match-only fields and public-safe profile fields for partner search workflows.
---

# Persona Memory Sync

Use this skill when a dating or matchmaking conversation reveals new information about a user's own profile, partner preferences, dealbreakers, or stable inferred tendencies, and that information should be persisted into MySQL.

## Scope

- 只处理当前已有的人设记忆落库能力：写入 `user_persona_observations`、合并 `user_personas`、同步到 `profiles`、渲染公开安全字段。
- Phase 1 只做结构整理：把核心读写逻辑收口到公共库，CLI 脚本保留为薄包装层，补齐测试和交付说明。
- 默认继续沿用现有表结构、字段语义、source type 规则、公开字段渲染规则，不改变已有输入输出契约。

## Current Runtime Layout

- 当前真实实现位于仓库根目录 `persona_memory_sync/`。
- `local-skills/persona-memory-sync/scripts/` 里的脚本主要保留为兼容包装层和 skill 内部示例。
- 已安装环境优先使用控制台命令 `persona-memory-sync`；在仓库 checkout 里也可以继续运行 `local-skills/persona-memory-sync/scripts/*.py`。

## Non-Goals

- 不新增产品功能，不扩展新的记忆类型、工作流、后台任务、提醒机制、业务 API 或事件系统。
- 不改变现有 merge 规则、public rendering 规则、profiles 同步策略、source type 权限边界。
- 不把 `persona-memory-sync` 变成新的业务编排层；它仍然只负责当前这套记忆写入与同步能力。

## Functional Boundary

This boundary is hard, not aspirational.

- `persona-memory-sync` 的产品功能边界，只能是当前已有的“写入 / 更新用户画像并同步公开安全字段”的能力。
- 可以调整代码结构、调用方式、CLI、Python API、engine 分层、测试和文档。
- 这些结构调整不代表可以顺带增加新的产品职责。

Allowed:

- 写入 `user_persona_observations`
- 合并并更新 `user_personas`
- 同步现有 `profiles` 字段
- 生成和回写现有 `public_*` 字段或等价公开视图字段
- 为以上现有能力补 CLI、Python API、engine 包装层

Not allowed:

- 新增新的画像产品能力、记忆类型、事件语义或新的长期状态机
- 新增提醒、订阅、持续监听、消息分发、通知、审核流、任务编排
- 新增推荐、匹配、候选召回、排序、代理撮合、自动媒合
- 把 `persona-memory-sync` 扩成通用画像中心、工作流中心或业务编排层
- 因为补了 CLI / Python API / engine，就顺带新增新的输入语义、输出语义或新的业务流程

Rule of thumb:

- 可以改“怎么调用、怎么组织代码、怎么暴露接口”
- 不可以改“这个 skill 负责什么产品能力”

## Delivery Order

1. Phase 1：结构收口
   让脚本只负责参数解析和 JSON 输出，核心逻辑集中到共享库，补单测。
2. Phase 2：引擎边界明确
   在不加新功能的前提下，把共享库当成稳定引擎层，梳理调用边界和复用方式。
3. Phase 3：对外接入整理
   只在确认有真实复用方时，再决定是否补独立 API/CLI 适配层；没有复用方就不额外扩展。

## Engine Boundary

- `persona_memory_sync/persona_memory_engine.py` 是当前正式运行时入口层。
- CLI 入口 `persona-memory-sync upsert`、`persona-memory-sync sync-profile`、`persona-memory-sync render-public` 以及兼容脚本 `local-skills/persona-memory-sync/scripts/*.py` 都应通过 engine 层调用，不再直接拼装底层读写流程。
- `persona_memory_sync/persona_memory_lib.py` 继续保留为内部实现细节，负责规则、字段映射、SQL 读写和公开文案生成；新调用方默认不要直接依赖它的运行时函数。
- `persona-memory-sync ensure-schema` 或兼容脚本 `local-skills/persona-memory-sync/scripts/ensure_persona_tables.py` 仍然属于建表和 schema 补齐入口，不属于运行时 engine。
- `engine` 和 `Python API` 只是现有能力的调用壳，不是新增功能的授权入口。

Engine responsibilities:

- 把外部调用统一收口成稳定的运行时入口
- 定义现有 3 个动作的标准 request 形态：
  `UpsertPersonaMemoryRequest`、`SyncPersonaProfileRequest`、`RenderPublicProfileRequest`
- 负责少量入口级整理，例如默认表名解析、patch 标准化触发、是否附带 `normalized_patch`
- 把请求转交给 `persona_memory_lib.py` 执行
- 保持 CLI、Python API、审计脚本走同一套运行路径

Engine is not responsible for:

- 定义新的产品能力
- 修改 merge 规则、public rendering 规则、source type 权限边界
- 直接承载业务编排、通知逻辑、审核流、任务流
- 绕过 `lib` 另写一套 SQL 或另写一套画像处理规则

Call chain:

- CLI -> engine -> lib -> MySQL
- Python API -> engine -> lib -> MySQL
- audit script -> engine -> lib -> MySQL

Rule of thumb:

- 想改“调用入口长什么样”，看 engine
- 想改“画像怎么合并、怎么同步、怎么渲染”，看 lib
- 想加新的产品职责，不应该放进 engine，也不应该放进这个 skill

This skill separates three concerns:

- `user_persona_observations`: every new signal, with source and confidence
- `user_personas`: the user's long-term persona memory
- `profiles`: the internal match-ready profile used by search and ranking

Do not treat `profiles` as a raw public profile. The public-facing version must come from `public_*` fields or an equivalent `public_profile_view`.

## Workflow

1. Ensure schema exists.
   Run `persona-memory-sync ensure-schema` or `python3 local-skills/persona-memory-sync/scripts/ensure_persona_tables.py`.
2. Convert the new conversation signal into a structured patch.
   Use explicit fields whenever possible.
3. Upsert persona memory.
   Run `persona-memory-sync upsert --user-key ... --source-type ... --patch-json ...`.
4. Sync to `profiles`.
   Run `persona-memory-sync sync-profile --user-key ...`.
5. Optionally preview or refresh public rendering.
   Run `persona-memory-sync render-public --user-key ... --write-profile`.

## Python API

Use the importable API when another Python caller wants structured results directly instead of shelling out to the CLI:

```python
from persona_memory_sync import (
    render_public_profile,
    sync_persona_profile,
    upsert_persona_memory,
)

upsert_result = upsert_persona_memory(
    {
        "source": "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
        "user_key": "demo-user",
        "source_type": "explicit",
        "patch": {
            "self_city": "上海",
            "self_relationship_goal": "认真恋爱",
        },
        "sync_profile": True,
    }
)

sync_result = sync_persona_profile(
    {
        "source": "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
        "user_key": "demo-user",
    }
)

public_result = render_public_profile(
    {
        "source": "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
        "user_key": "demo-user",
        "write_profile": True,
    }
)
```

The public package exports:

- `persona_memory_sync.upsert_persona_memory(...)`
- `persona_memory_sync.sync_persona_profile(...)`
- `persona_memory_sync.render_public_profile(...)`
- `UpsertPersonaMemoryRequest`, `SyncPersonaProfileRequest`, `RenderPublicProfileRequest` when you want explicit request objects
- `examples/python_api_integration.py` for a minimal outer-system call example that wraps the sync result into its own payload

Pass `--source` explicitly, or set `PERSONA_MEMORY_MYSQL_SOURCE` first if you want a reusable default. The skill no longer assumes a built-in local root DSN.

## Source Types

- `explicit`: the user clearly said it; may update hard fields
- `strong_inference`: repeated, high-confidence inference; may update soft tags and internal summaries
- `weak_inference`: keep as observation only; do not overwrite the persona

## Rules

- Hard fields such as age, city, height, education, marital status, and accept/reject boundaries should only be overwritten by `explicit`.
- Soft preference tags and internal summaries may be enriched by `strong_inference`.
- Raw negative labels such as `绿茶`, `拜金`, `冷暴力`, and `暧昧不清` should not be shown publicly. They should be normalized into neutral internal matcher features first.
- `partner-search` should read the enriched `profiles` row, including `matcher_*` fields.
- User-facing UI should read `public_*` fields or a `public_profile_view`, not raw internal matcher data.

## Patch Shape

The patch JSON should use `user_personas` field names. Common fields:

- `self_gender`, `self_age`, `self_city`, `self_height`, `self_education`, `self_income_wan`
- `self_marital_status`, `self_has_children`, `self_smoking`, `self_drinking`, `self_relationship_goal`
- `target_gender`, `target_age_min`, `target_age_max`, `target_cities`
- `target_height_min`, `target_education_min`, `target_marital_statuses`
- `target_accept_partner_children`, `target_accept_long_distance`
- `must_have_tags`, `must_not_have_tags`, `preferred_traits`, `disliked_traits`

Multi-value fields can be passed as arrays or comma-separated strings.

## Resources

- Schema details: `references/schema.md`
- Merge behavior: `references/merge-rules.md`
- Public rendering rules: `references/public-rendering.md`
- Visibility policy: `references/visibility-policy.md`
