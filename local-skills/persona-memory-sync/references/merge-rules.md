# Merge Rules

## Source priority

1. `explicit`
2. higher-confidence `strong_inference`
3. lower-confidence `strong_inference`
4. `weak_inference`

## Hard fields

Only `explicit` can overwrite hard fields such as:

- age
- city
- height
- education
- marital status
- accept/reject boundaries
- preferred age range
- preferred city range

## Soft fields

`strong_inference` may enrich:

- `must_have_tags`
- `must_not_have_tags`
- `preferred_traits`
- `disliked_traits`
- internal summaries
- public-safe draft summaries

`weak_inference` is recorded in observations but does not overwrite the persona.

