# Partner Matchmaking System

This directory is the Phase 5 outer system for `partner-search`.

It is intentionally separate from both `partner-search` and `persona-memory-sync`.

- `partner-search` still only does `画像 / 条件 -> 候选结果`
- `persona-memory-sync` still only does persona memory upsert and profile sync
- this outer system owns the dynamic matchmaking pool, mutual pair construction, match cases, feedback persistence, revalidation, cooldowns, and persona-sync integration

## Core Model

This system is not a requester-centric recommendation layer.

It works like a pool:

1. Users opt into the matchmaking pool.
2. Only users who are currently `active_single` stay in the active pool.
3. The system runs `partner-search` for active members.
4. It upgrades only reciprocal `A -> B` and `B -> A` edges into a mutual pair.
5. Eligible mutual pairs can open a system-created `match_case`.
6. Feedback with long-term preference changes automatically calls `persona-memory-sync`.
7. After persona sync, the outer system revalidates open pairs and cases.

## Directory Map

- `matchmaking_system/storage.py`
  - SQLite schema and low-level helpers
- `matchmaking_system/service.py`
  - pool membership, edge refresh, direct `partner-search` and `persona-memory-sync` API calls, reciprocal pairing, case workflow, feedback handling, and revalidation
- `tests/test_matchmaking_system.py`
  - Phase 5 regression tests

## Quick Start

Run tests:

```bash
bash external-systems/partner-matchmaking-system/scripts/run_tests.sh
```

## Notes

- This system currently targets a single-source pool membership model per member.
- It assumes pool members have a stable `user_key`, and preferably a `self_id` that resolves inside the same profile source used by `partner-search`.
- It does not implement final user-facing messaging channels. It only manages cases and state transitions.
