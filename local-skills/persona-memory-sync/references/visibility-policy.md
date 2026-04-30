# Visibility Policy

## public

Can be shown directly after rendering:

- anonymous display name from `public_profile_view` only, not raw real name
- age
- city
- masked education from `public_education` / `public_profile_view` only, not raw `education`
- masked public job text
- relationship goal
- `public_personality`
- `public_values`
- `public_notes`

## match_only

Visible to matching and matchmaking backend only:

- `matcher_traits_json`
- `matcher_preferences_json`
- `matcher_risks_json`
- `matcher_summary_internal`
- raw dealbreaker tags

## private_audit

Visible only for audit and debugging:

- field-scoped observation evidence summary
- confidence score
- source type
- conversation reference

Do not store or render full raw conversation transcripts in `evidence_text`.
