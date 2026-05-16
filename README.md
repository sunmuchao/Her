# Her

Relationship-operations prototype covering search, persona memory, recommendation, matchmaking, chat, discovery, migrations, and gateway orchestration.

## Current Layout

- Core skill/runtime packages live at the repository root:
  - `partner_search/`
  - `persona_memory_sync/`
  - `profile_service/`
  - `match_domain/`
  - `async_jobs/`
  - `db_migrations/`
  - `observability/`
  - `task_scheduler/`
- External systems live under `external-systems/`:
  - `partner-recommendation-system/`
  - `partner-matchmaking-system/`
  - `partner-chat-system/`
  - `partner-discovery-system/`
  - `partner-http-gateway/`
- `local-skills/partner-search/` and `local-skills/persona-memory-sync/` now mainly provide skill metadata, examples, tests, and compatibility scripts.
  - The actual Python implementations are the root packages `partner_search` and `persona_memory_sync`.

## Docs Notes

- `external-systems/*/README.md`, root package code, and automated tests are the current implementation source of truth.
- `docs/chat-*` and `docs/discovery-*` contain a mix of current notes and historical planning material. Treat any references to missing files in those documents as proposal/archive context, not as live implementation requirements.

## Verification

```bash
ruff check .
pytest
python scripts/check_skill_packaging.py
scripts/release_check.sh --python .venv/bin/python
```

## Packaging Notes

- `pyproject.toml` is the primary packaging config.
- `setup.py` is retained as a compatibility layer for older editable-install paths.
- Console entrypoints:
  - `partner-search`
  - `persona-memory-sync`
