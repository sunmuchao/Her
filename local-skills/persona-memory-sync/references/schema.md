# Schema

## Boundary Note

This schema exists only to support the current `persona-memory-sync` capability:
writing persona memory, recording observations, syncing existing profile fields, and exposing current public-safe fields.

Do not treat this schema document as permission to grow `persona-memory-sync` into a broader product domain
or to add unrelated workflow tables, subscription tables, notification tables, recommendation history tables,
or other new business responsibilities.

This skill maintains three storage layers:

- `user_persona_observations`: append-only signal log
- `user_personas`: the user's stable long-term memory
- `profiles`: the internal match-ready profile used by search

The script `ensure_persona_tables.py` creates:

- `user_personas`
- `user_persona_observations`
- extra `profiles` columns:
  - `public_education`
  - `public_job`
  - `matcher_traits_json`
  - `matcher_preferences_json`
  - `matcher_risks_json`
  - `matcher_summary_internal`
  - `public_personality`
  - `public_values`
  - `public_notes`
- `public_profile_view`

`profiles` is intentionally not treated as a raw public table. Public UI should read `public_*` or the view, including masked education from `public_education` and masked job text from `public_job` instead of assuming raw fields are safe.
