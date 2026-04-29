---
name: partner-search
description: Search a MySQL dating profile database for partner candidates that match the user's preferences. Use when the user wants to search a dating profile library, including requests like 在相亲资料库里找对象、筛人、匹配候选人或推荐合适对象, and Codex needs to filter, rank, and explain matches from MySQL data.
---

# Partner Search

Use this skill when the user has a profile library and wants candidate matches, such as "在资料库里帮我筛合适对象" or "从相亲库里推荐几个人", rather than general dating advice.

## Quick Start

Ensure the Python dependency is present first. Run `python3 -m pip install pymysql` if the environment does not already have `PyMySQL`.

1. Find the profile source.
   Pass `--source` explicitly, or set `PARTNER_SEARCH_MYSQL_SOURCE` first if you want a reusable local default. The skill no longer assumes a built-in MySQL root DSN.
2. Convert the user's request into CLI flags.
   Start with direct filters such as `--gender`, `--city`, `--relationship-goal`, and `--verified-level-min`. Add `--must-have` / `--must-not-have` for text requirements and `--self-id` or `--self-*` only when reciprocal matching matters.
3. Run `scripts/search_candidates.py`.
4. Return the best matches with three things:
   - why they match
   - what information is missing
   - any obvious risks or mismatches
   - which questions to confirm next when the profile is promising but still fuzzy
   - how much is real fit versus just profile completeness

Companion write scripts such as `scripts/backfill_profile_enrichment.py` and `scripts/seed_gap_profiles.py` should use the same `--source` / `PARTNER_SEARCH_MYSQL_SOURCE` entrypoint instead of relying on an implicit local root connection.

## Criteria Flags

Use only the flags you need:

- Basic profile filters: `--gender`, `--age-min` / `--age-max`, `--height-min` / `--height-max`, `--city`, `--district`, `--settlement-city`, `--relationship-goal`
- Lifestyle and family filters: `--smoking`, `--drinking`, `--long-distance`, `--marital-status`, `--has-children`, `--want-children`, `--accept-partner-children`, `--marriage-timeline`
- Quality filters: `--profile-status`, `--active-within-days`, `--verified-level`, `--verified-level-min`, `--photo-count-min`
- Text matching: `--must-have`, `--must-not-have`, `--prefer`
- Known-field control: `--require-known` for fields that must be explicitly filled instead of blank or unknown
- Reciprocal matching: `--self-id`, the `--self-*` flags, and `--exclude-id`
- Optional media lookup: `--photo-preview-count`, `--photos-table`
- Debug output: `--show-source` when you explicitly need the redacted source DSN and table in the final text output

Repeat multi-value flags such as `--city`, `--relationship-goal`, `--must-have`, `--must-not-have`, and `--prefer` as needed, or pass comma-separated values.

Run `python3 scripts/search_candidates.py --help` for the full CLI.

## Source Rules

- For MySQL, pass a DSN like `mysql://user:pass@host:3306/db?table=profiles&photos_table=profile_photos`. Use `--table` or `--photos-table` when the table names are not in the DSN or when auto-detection is ambiguous.
- If the DSN omits `table=` and the database has multiple equally plausible candidate tables, the script now stops with an explicit error instead of guessing. Prefer setting `?table=profiles` in the DSN.
- If `PARTNER_SEARCH_MYSQL_SOURCE` is set, the script uses that value as its default DSN. Otherwise you must pass `--source`.
- When you use multiple `--source` values together with `--self-id`, that id must resolve to exactly one source. If the same id exists in multiple libraries, narrow the source list first.

## Run the Script

Use the local MySQL database directly:

```bash
python3 scripts/search_candidates.py \
  --gender 女 \
  --age-min 24 \
  --age-max 30 \
  --city 无锡 \
  --district 滨湖区 \
  --settlement-city 无锡 \
  --relationship-goal 认真恋爱 \
  --relationship-goal 结婚导向 \
  --must-have 情绪稳定 \
  --must-not-have 抽烟 \
  --prefer 消费观正常 \
  --prefer 生活规律 \
  --housing-status 已购房 \
  --car-status 有车 \
  --verified-level-min photo \
  --photo-count-min 4 \
  --photo-preview-count 3 \
  --limit 10
```

Use `--self-id` for reciprocal matching against another profile's partner preferences:

```bash
python3 scripts/search_candidates.py \
  --self-id 90001 \
  --gender 女 \
  --city 无锡 \
  --relationship-goal 认真恋爱 \
  --relationship-goal 结婚导向 \
  --want-children 想要 \
  --verified-level-min basic \
  --active-within-days 30 \
  --limit 10
```

Use `--self-*` when your own profile is not stored in the database:

```bash
python3 scripts/search_candidates.py \
  --gender 女 \
  --city 无锡 \
  --self-age 28 \
  --self-city 无锡 \
  --self-height 178 \
  --self-education 本科 \
  --self-income-wan 40 \
  --self-marital-status 未婚 \
  --self-has-children 0
```

Use `--source` when you want to point at a specific MySQL target:

```bash
python3 scripts/search_candidates.py \
  --source 'mysql://user:pass@127.0.0.1:3306/other_db?table=profiles' \
  --gender 女 \
  --city 无锡
```

## Interpretation Rules

- Treat age, city, gender, relationship goal, smoking, drinking, long-distance preference, marital status, and child plan as the strongest filters when present.
- Use `--district`, `--settlement-city`, `--housing-status`, `--car-status`, `--verified-level`, and `--photo-count-min` when the user wants a tighter local or profile-quality filter.
- Use `--photo-preview-count` when you want the result to include the top `N` image URLs from `profile_photos`.
- Match free-text requirements against `personality`, `values`, `notes`, `hobbies`, `lifestyle`, and the combined record text.
- When `--self-id` or any `--self-*` flag is provided, enforce reciprocal matching against the candidate's `preferred_*` and `accept_*` fields where available.
- Treat `接受` as a strong reciprocal match, `可协商` as a risk or follow-up question, and `未知` as unknown rather than positive evidence.
- When the user clearly cares about a field being explicit, use `--require-known` for fields such as `smoking`, `long_distance`, `want_children`, `accept_partner_children`, `accept_marital_status`, or `marriage_timeline`.
- Treat a blank `profile_status` as unknown rather than `active`; keep the record only when no explicit mismatch is found and call out the gap in `missing_fields`.
- Rank stronger candidates higher when they are more recently active, have a higher `verified_level`, share the same city as the requester, and carry fewer unresolved risks such as `可协商` or missing hard-decision fields.
- Read `score` as a combined rank only. Use `fit_score` to judge "像不像你要找的人", `confidence_score` to judge "这份资料靠不靠谱、够不够完整", and `risk_score` to judge "还有多少坑没排完". The current total score is `fit_score + confidence_score - risk_score`.
- Keep candidates with missing structured fields such as age, city, or height when no explicit mismatch is found, but call out those gaps in `missing_fields`.
- Treat keyword rules (`--must-have`, `--must-not-have`), verification minimums, recent-activity requirements, and reciprocal hard conflicts as elimination rules.
- Do not invent profile facts. If the profile never states "情绪稳定", report it as unknown rather than true.
- Never expose raw MySQL DSNs or passwords in the final response. If you mention the source, redact credentials first.
- Treat free-text `notes` as potentially sensitive. Summarize them only when useful, and avoid exposing raw addresses, schools, employers, contact details, or other unique identifiers.
- Use `match_evidence` and `follow_up_questions` to explain why a fuzzy personality keyword matched and what should be confirmed before recommending a serious next step, but hide the evidence text when the matched segment contains sensitive details.

## Performance Notes

- The script pushes simple structured filters such as gender, city, district, settlement city, age, profile status, verification level, and recent activity into MySQL first when the source table exposes matching columns.
- The MySQL prefilter now uses direct column comparisons instead of wrapping indexed columns in `LOWER(TRIM(...))`. Keep those structured fields normalized and on a case-insensitive collation such as `utf8mb4_unicode_ci` for the best chance of using indexes.
- The SQL prefilter keeps rows whose structured fields are blank so the Python scorer can still surface them with `missing_fields`.
- Recent activity uses the first available value from `last_active_at`, `updated_at`, and `created_at`, both in SQL prefiltering and in final scoring.
- Keep text preferences such as `--must-have`, `--must-not-have`, and `--prefer` in Python-side scoring; do not expect them to be fully SQL-backed.
- Photo previews are fetched after ranking so the script only queries `profile_photos` for the final result ids. If the photos table is unavailable or incomplete, continue without `photo_preview`.

## Output Format

Summarize the top matches in plain language. For each candidate, include:

- `score`
- `fit_score`, `confidence_score`, `risk_score`
- `scoring` in the text output so the caller can quickly separate "合适" from "资料靠谱"
- `meta` for compact status / verification / photo count / time context
- `photo_preview` when requested and available
- `matched_on`
- `reciprocal_on`
- `missing_fields`
- `risk_flags`
- `match_evidence` for `must-have` / `prefer` keywords when the script can trace them back to profile text
- `follow_up_questions` for the key unknowns or `可协商` risks
- `notes` as a short, masked summary rather than raw free text
- `source` only when you intentionally pass `--show-source` for debugging multi-source results

If nothing matches, say so plainly and include:

- `pool_summary` to show how many records were still in the pool after source loading
- `why_no_match` with the top elimination reasons
- `relax_suggestions` with the first 1-3 conditions worth loosening

## Resources

- Read `references/profile-schema.md` for supported fields and aliases, especially reciprocal preference columns such as `preferred_*`, `accept_*`, and child-plan fields.
- When validating changes to this skill itself, run `bash scripts/run_tests.sh` so the test pass does not leave `__pycache__` or `.pyc` artifacts inside the package.
