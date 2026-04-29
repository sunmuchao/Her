---
name: persona-memory-sync
description: Persist and evolve a dating user's long-term persona, partner preferences, and inferred matching signals into MySQL, then sync both internal match-only fields and public-safe profile fields for partner search workflows.
---

# Persona Memory Sync

Use this skill when a dating or matchmaking conversation reveals new information about a user's own profile, partner preferences, dealbreakers, or stable inferred tendencies, and that information should be persisted into MySQL.

This skill separates three concerns:

- `user_persona_observations`: every new signal, with source and confidence
- `user_personas`: the user's long-term persona memory
- `profiles`: the internal match-ready profile used by search and ranking

Do not treat `profiles` as a raw public profile. The public-facing version must come from `public_*` fields or an equivalent `public_profile_view`.

## Workflow

1. Ensure schema exists.
   Run `python3 scripts/ensure_persona_tables.py`.
2. Convert the new conversation signal into a structured patch.
   Use explicit fields whenever possible.
3. Upsert persona memory.
   Run `python3 scripts/upsert_persona_memory.py --user-key ... --source-type ... --patch-json ...`.
4. Sync to `profiles`.
   Run `python3 scripts/sync_persona_to_profile.py --user-key ...`.
5. Optionally preview or refresh public rendering.
   Run `python3 scripts/render_public_profile.py --user-key ... --write-profile`.

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
