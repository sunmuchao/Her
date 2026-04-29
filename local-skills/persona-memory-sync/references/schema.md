# Schema

This skill maintains three storage layers:

- `user_persona_observations`: append-only signal log
- `user_personas`: the user's stable long-term memory
- `profiles`: the internal match-ready profile used by search

The script `ensure_persona_tables.py` creates:

- `user_personas`
- `user_persona_observations`
- extra `profiles` columns:
  - `matcher_traits_json`
  - `matcher_preferences_json`
  - `matcher_risks_json`
  - `matcher_summary_internal`
  - `public_personality`
  - `public_values`
  - `public_notes`
- `public_profile_view`

`profiles` is intentionally not treated as a raw public table. Public UI should read `public_*` or the view.

