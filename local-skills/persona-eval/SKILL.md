---
name: persona-eval
description: Audit the full matchmaking journey with roleplayed user agents who disclose persona details, inspect stored and public memory, review partner recommendations, and judge satisfaction themselves.
---

# Persona Eval

Use this skill when the user wants to audit the full journey from the simulated user's own point of view, such as:

- "启动多个模拟用户 agent 跑完整撮合流程"
- "让每个模拟用户自己检查画像落库对不对"
- "让模拟用户看公开展示有没有泄露不想公开的信息"
- "让模拟用户自己判断推荐对象满不满意"

This skill is for audit, not live matchmaking. If the user only wants to search the database for candidates, use `partner-search`. If the user only wants to persist or merge persona memory into MySQL, use `persona-memory-sync`.

Do not use a local script that calls OpenAI and produces the review for you. The judgment must come from the roleplayed user agent itself.

## Core Rule

- One persona equals one reviewer.
- The same roleplayed user agent who disclosed the persona should also review the stored data and the recommendation result.
- The main agent may run deterministic local scripts, SQL queries, and search commands.
- The main agent must not let a local script generate the final verdict.

## Inputs

- Default persona set: `local-skills/persona-memory-sync/references/audit_personas.json`
- Persona memory tables and sync scripts from `local-skills/persona-memory-sync`
- Search script from `local-skills/partner-search/scripts/search_candidates.py`
- MySQL DSN such as `mysql://root@127.0.0.1:3307/her?table=profiles&photos_table=profile_photos`

## Workflow

1. Pick the personas to audit.
   Use the built-in `audit_personas.json` or a user-provided set.
2. Start one roleplayed user agent per persona when the runtime supports sub-agents.
   Pass the persona's `role_brief` and `private_boundaries`. Tell the agent to do two jobs:
   - answer as that user during persona collection
   - later judge whether the stored data, public rendering, and match result feel right
3. Let the roleplayed user expose profile and preference information through conversation.
   Separate:
   - what the user explicitly said
   - what the system is only strongly inferring
4. Persist the memory with deterministic local tools.
   Use:
   - `python3 local-skills/persona-memory-sync/scripts/ensure_persona_tables.py`
   - `python3 local-skills/persona-memory-sync/scripts/upsert_persona_memory.py`
   - `python3 local-skills/persona-memory-sync/scripts/sync_persona_to_profile.py`
   - `python3 local-skills/persona-memory-sync/scripts/render_public_profile.py --write-profile`
5. Fetch the audit snapshot.
   At minimum inspect:
   - `user_persona_observations`
   - `user_personas`
   - `profiles`
   - `public_profile_view`
6. Send the stored snapshot back to the same roleplayed user agent.
   Ask that agent to judge:
   - which fields are accurate
   - which fields drifted or became too hard a constraint
   - which public fields expose information the user would not want shown
7. Run partner search for that persona.
   Use `python3 local-skills/partner-search/scripts/search_candidates.py` with reciprocal matching based on the stored profile.
8. Send the candidate result or no-match explanation back to the same roleplayed user agent.
   That agent should decide:
   - whether the recommended people are actually acceptable
   - whether it is only "能聊聊再看" or truly "满意"
   - whether a no-match result feels reasonable or feels like a system bug
9. Aggregate the audit across personas.
   Separate:
   - memory accuracy problems
   - privacy exposure problems
   - matching logic problems
   - whether the simulated users themselves felt satisfied

## What To Look For

- `must_have_tags` holding soft traits such as `愿意沟通` or `稳定工作` and over-filtering the pool
- public rewrite drift such as awkward wording, duplicated phrases, or softened meaning that no longer matches the user
- private boundaries leaking into public text, especially exact income, employer, hospital, divorce reason, family burden, or medical history
- recommendation quality gaps where the profile is stored correctly but the search result still feels wrong to the simulated user

## Output Shape

Report each persona in plain language with:

- `persona`
- `what the user actually meant`
- `stored correctly`
- `stored with drift`
- `publicly exposed but should not be`
- `candidate result`
- `simulated user verdict`
- `systemic issue behind the result`

Keep the simulated user's own judgment separate from the main agent's system diagnosis.

## Legacy Note

Legacy deterministic benchmark scripts may still exist in this directory for plain search reruns or packet rendering, but they are not the path for user-judgment audit. Do not reintroduce a local script that calls OpenAI to play the role and write the verdict in one step.
