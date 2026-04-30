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

## Core Rules

- One persona equals one reviewer.
- The same roleplayed user agent who disclosed the persona should also review the stored data and the recommendation result.
- The main agent may run deterministic local scripts, SQL queries, and search commands.
- The main agent must not let a local script generate the final verdict.
- If the runtime cannot hold all sub-agents at once, batch them. Do not hand a persona's memory review to a different agent.
- Keep audit artifacts under `tmp/persona_agent_audits/<run_id>/` so the run is reproducible.

## Quick Start

Use this skill as a three-layer audit:

1. Persona disclosure audit
   Start roleplayed user agents and let them reveal profile, preference, and boundary information through conversation.
2. Memory and public exposure audit
   Sync persona memory into MySQL, fetch `user_personas`, `user_persona_observations`, `profiles`, and `public_profile_view`, then send that snapshot back to the same agent.
3. Recommendation audit
   Run partner search from the stored profile, then let the same agent judge whether the candidates are actually acceptable.

If the user asks for "多 agent 审计", the final report must separate:

- memory accuracy problems
- privacy exposure problems
- matching logic problems
- simulated-user satisfaction

## Required Artifacts

Write these files when the audit is substantial:

- `input_personas.json`
- `raw_agent_feedback.json` when you are saving the raw `wait_agent` or per-agent reply payload first
- `memory_snapshots.json`
- `search_outputs.json`
- `agent_feedback.json`
- `audit_summary.json`

Use a single run directory such as `tmp/persona_agent_audits/persona_eval_20260430_1/`.

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
   Record at least:
   - `persona_id`
   - `agent_id`
   - `user_key`
   - `private_boundaries`
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
   Use a structured JSON request. Recommended shape:

```json
{
  "memory_accuracy": {
    "accurate": ["..."],
    "drift": ["..."],
    "do_not_public": ["..."],
    "summary": "..."
  },
  "matching_feedback": {
    "overall_satisfaction": "高/中/低",
    "candidate_reviews": [
      {"rank": 1, "name": "", "verdict": "愿意聊/一般/不想聊", "reason": "..."}
    ],
    "no_match_reasonable": true,
    "systemic_issues": ["..."],
    "summary": "..."
  },
  "overall_score": 0,
  "final_summary": "..."
}
```

7. Run partner search for that persona.
   Use `python3 local-skills/partner-search/scripts/search_candidates.py` with reciprocal matching based on the stored profile.
   Important:
   - when audit personas were inserted into `profiles`, exclude all audit profile ids with repeated `--exclude-id`
   - otherwise the synthetic audit personas may match each other and pollute the result
8. Send the candidate result or no-match explanation back to the same roleplayed user agent.
   That agent should decide:
   - whether the recommended people are actually acceptable
   - whether it is only "能聊聊再看" or truly "满意"
   - whether a no-match result feels reasonable or feels like a system bug
9. Diagnose empty-result runs before blaming ranking.
   If a persona gets no matches and the pool summary is tiny or only shows `exclude_record_ref`, run a direct source check to distinguish:
   - data pool empty
   - reciprocal hard filters too strict
   - synthetic profile contamination
   - missing structured fields
10. Aggregate the audit across personas.
    Keep the roleplayed user's judgment separate from the main agent's diagnosis.
    If the raw reviewer replies were saved from tool output first, normalize them before aggregation.
    Use `python3 local-skills/persona-eval/scripts/summarize_agent_feedback.py` to summarize reviewer feedback after the JSON responses are collected.

## What To Look For

- `must_have_tags` holding soft traits such as `愿意沟通` or `稳定工作` and over-filtering the pool
- conditional acceptance collapsing into vague enums such as `可协商`
- city and distance preferences being narrowed too much, such as losing `稳定留沪` or `双城过渡`
- relationship-goal strength drifting too hard in either direction, such as flattening everything into `认真恋爱` or `结婚导向`
- child and remarriage semantics being inverted, especially "对方要接受我有孩子" versus "我接受对方有孩子"
- public rewrite drift such as awkward wording, duplicated phrases, or softened meaning that no longer matches the user
- private boundaries leaking into public text, especially exact income, employer, hospital, divorce reason, family burden, or medical history
- recommendation quality gaps where the profile is stored correctly but the search result still feels wrong to the simulated user
- no-match results caused by dataset coverage rather than bad ranking logic

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

Also include a run-level section with:

- how many personas were audited
- average `overall_score` when the agents provided one
- matching satisfaction distribution
- repeated memory drift patterns
- repeated privacy exposure patterns
- repeated matching failures

## Useful Scripts

- `python3 local-skills/persona-eval/scripts/run_persona_eval.py`
  Rerun a benchmark persona command file and write result JSON.
- `python3 local-skills/persona-eval/scripts/run_persona_eval_bundle.py`
  Generate results JSON, packet markdown, and reviewer metrics in one pass.
- `python3 local-skills/persona-eval/scripts/generate_persona_packets.py`
  Render result packets for review.
- `python3 local-skills/persona-eval/scripts/normalize_agent_feedback.py`
  Normalize raw `wait_agent` status payloads, `results` reports, or mixed feedback lists into standard `agent_feedback.json`.
- `python3 local-skills/persona-eval/scripts/summarize_agent_feedback.py`
  Summarize both legacy candidate-only feedback and the newer `memory_accuracy + matching_feedback` reviewer JSON.
- `python3 local-skills/persona-eval/scripts/build_audit_summary.py`
  Build a final `audit_summary.json` from reviewer feedback plus optional memory snapshots, search outputs, and dataset diagnostics.

## Legacy Note

Legacy deterministic benchmark scripts may still exist in this directory for plain search reruns or packet rendering, but they are not the path for user-judgment audit. Do not reintroduce a local script that calls OpenAI to play the role and write the verdict in one step.
