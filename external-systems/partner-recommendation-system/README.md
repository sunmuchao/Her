# Partner Recommendation System

This directory is the Phase 3/4 outer system for `partner-search`.

It is intentionally separate from the skill itself.

- `partner-search` still only does `画像 / 条件 -> 候选结果`
- this outer system owns saved searches, recommendation history, user actions, refresh timing, frequency caps, cooldowns, and in-app recommendation cards
- proactive recommendation now defaults to `direct_greet_only`: candidates first pass a rule gate, then wait for a real user review; only after that can they be pushed

## Directory Map

- `recommendation_system/storage.py`
  - SQLite schema and low-level storage helpers
- `recommendation_system/service.py`
  - subscription refresh, persona-driven criteria compilation, recommendation dedupe, cooldown, frequency cap, quiet-hours, run snapshots, and card generation
- `recommendation_system/proxy_intro.py`
  - proxy-intro case creation, dispatch, reply handling, timeout handling, and audit sync
- `recommendation_system/criteria_compiler.py`
  - compile `persona + subscription overrides -> effective criteria`
- `recommendation_system/search_client.py`
  - bridge into `partner-search`'s Python API
- `recommendation_system/no_match_opt_in.py`
  - outer search-session wrapper for the "no result -> ask whether to keep looking" flow
- `scripts/create_saved_search_subscription.py`
  - create a saved-search subscription
- `scripts/refresh_saved_searches.py`
  - refresh due subscriptions and queue new candidates
- `scripts/deliver_in_app_recommendations.py`
  - convert queued recommendations into in-app cards
- `scripts/record_recommendation_action.py`
  - store `skip`, `save`, or `direct_greet`
- `scripts/record_user_review.py`
  - store the pre-delivery review decision before a recommendation is allowed to notify
- `scripts/request_proxy_intro.py`
  - create a proxy-intro case from a recommendation
- `scripts/dispatch_match_case_outreach.py`
  - move pending proxy-intro cases into awaiting-reply state
- `scripts/record_match_case_reply.py`
  - store accepted/declined proxy-intro replies
- `scripts/close_timed_out_match_cases.py`
  - close overdue proxy-intro cases
- `scripts/close_match_case.py`
  - close an active proxy-intro case after handoff or cancellation
- `tests/test_recommendation_system.py`
  - Phase 3 regression tests

## Database Tables

- `saved_search_subscriptions`
  - who enabled continuous search
  - the original request, persona snapshot fallback, and subscription-level overrides
  - refresh cadence, quiet hours, daily cap, score threshold, skip cooldown
  - recommendation mode and the extra bar for proactive `direct_greet` pushes
- `profile_recommendations`
  - recommendation history per `(subscription, candidate)`
  - latest score snapshot
  - delivery status
  - cooldown state
  - final proactive-review status such as `direct_greet_ready`, `save_only`, or `rejected`
  - user review status such as `pending_review`, `direct_greet`, or `save`
- `recommendation_actions`
  - user actions such as `skip`, `save`, `direct_greet`, and proxy-intro audit actions
- `in_app_recommendation_cards`
  - the actual station/in-app recommendation payload shown to the user
- `saved_search_runs`
  - one snapshot per refresh
  - the resolved persona snapshot, effective criteria, and top candidate ids used for that run
- `match_cases`
  - proxy-intro case state, safe summary, deadlines, and cooling
- `match_case_events`
  - audit trail for case creation, outreach, replies, timeout, and close
- `match_case_outreach_attempts`
  - outreach send attempts and provider payloads

## Source Of Truth

- `persona` is the long-term preference source.
- `saved_search_subscriptions` is the recurring task shell: still searching or not, cadence, caps, quiet hours, and optional subscription overrides.
- the original `criteria` is kept as the bootstrap request and fallback for fields the persona sync does not currently project into searchable filters.
- each refresh rebuilds `effective criteria` from `current persona + subscription overrides + bootstrap fallback`, then records a `saved_search_runs` snapshot for audit.
- when a subscription has `self_id`, refresh resolves the latest synced profile row live; when it has only `self_profile`, refresh falls back to that stored snapshot.

## End-to-End Flow

1. Create a saved-search subscription in the outer system.
2. Run the refresh job.
3. The refresh job resolves the latest persona profile, compiles effective criteria, then calls `partner-search`.
4. New high-score candidates first pass the proactive-review gate.
5. `direct_greet_ready` candidates become `review_pending`.
6. A real user review must then mark the candidate as `direct_greet`.
7. Only after that does the recommendation move to `pending_delivery`.
8. Run the delivery job.
9. The delivery job applies quiet hours and daily caps, then writes in-app cards.
10. Record user actions such as `skip`, `save`, `direct_greet`, or `request_proxy_intro`.
11. If the user chooses proxy intro, create a `match_case`.
12. Dispatch the outreach, record replies, and handle timeout or closure.
13. Future refreshes use recommendation history, case state, cooldown state, and the latest persona snapshot to avoid noisy repeat reminders.

## Recommendation Modes

- `direct_greet_only`
  - default mode
  - candidates that look like `save` stay in recommendation history but do not generate proactive cards
  - only candidates that pass the real-user review become `pending_delivery`
- `match_based`
  - legacy fallback mode
  - any candidate above the score threshold can still be pushed even if the direct-greet review would have said `save`

## Proxy-Intro Flow

- `request_proxy_intro`
  - creates a `match_case`
  - stores only a safe summary before outreach
  - moves the recommendation into `proxy_intro_in_progress`
- `accepted`
  - keeps the case active until handoff is explicitly closed
- `declined` / `timed_out`
  - applies a longer cooldown before the same candidate can be reconsidered
- `closed`
  - marks the handoff or cancellation as finished

## Empty-Result Opt-In Flow

This is the new conversation-layer entry for:

- run `partner-search` once
- if `result_count == 0`, ask the user `是否需要如果有合适的我主动通知你？`
- if the user agrees, create a saved-search subscription in this outer system

The key boundary stays the same:

- `partner-search` only answers `这次搜到了谁`
- this outer system answers `这次没搜到，要不要以后继续帮你盯着`

Programmatic example:

```python
from recommendation_system import (
    connect_db,
    handle_opt_in_decision,
    initialize_database,
    run_search_session,
)

conn = connect_db("/tmp/partner-phase3.sqlite3")
initialize_database(conn)

session = run_search_session(
    source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
    criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
    self_profile={"age": 28, "city": "无锡", "height": 178},
    limit=10,
)

if session["needs_opt_in_prompt"]:
    print(session["opt_in_prompt"])
    decision = handle_opt_in_decision(
        conn,
        requester_id=70001,
        search_session=session,
        user_opted_in=True,
        title="无锡认真恋爱持续留意",
    )
```

`handle_opt_in_decision(...)` stores the original search request, including:

- `source`
- `criteria`
- `self_profile` or `self_id`
- `table_name`
- `photos_table_name`
- `limit`

After that, the normal Phase 3 refresh and delivery jobs take over.
At refresh time, the system re-resolves the latest persona profile and rebuilds the effective criteria, instead of replaying the old query literally.
When `self_id` points at a profile row synced by `persona-memory-sync`, refresh rehydrates the latest `profile fields + matcher_preferences_json + matcher_risks_json` back into persona-style preference keys before compiling criteria.

## Quick Start

Create one subscription:

```bash
python3 external-systems/partner-recommendation-system/scripts/create_saved_search_subscription.py \
  --db /tmp/partner-phase3.sqlite3 \
  --requester-id 70001 \
  --source 'mysql://user:pass@127.0.0.1:3306/her?table=profiles' \
  --title '无锡认真恋爱' \
  --criteria-json '{"gender":"女","cities":["无锡"],"relationship_goals":["认真恋爱","结婚导向"],"must_have":["情绪稳定"],"verified_level_min":"photo"}' \
  --subscription-overrides-json '{"verified_level_min":"id"}' \
  --self-profile-json '{"age":28,"city":"无锡","height":178}' \
  --recommendation-mode direct_greet_only \
  --min-direct-greet-score 60
```

If the requester profile already lives in the partner-search source, use `--self-id` so refreshes can resolve the latest persona snapshot directly.

Refresh due subscriptions:

```bash
python3 external-systems/partner-recommendation-system/scripts/refresh_saved_searches.py \
  --db /tmp/partner-phase3.sqlite3
```

Record the real-user review before delivery:

```bash
python3 external-systems/partner-recommendation-system/scripts/record_user_review.py \
  --db /tmp/partner-phase3.sqlite3 \
  --subscription-id saved-search-xxxx \
  --candidate-id 90001 \
  --review direct_greet
```

Deliver pending in-app recommendation cards:

```bash
python3 external-systems/partner-recommendation-system/scripts/deliver_in_app_recommendations.py \
  --db /tmp/partner-phase3.sqlite3
```

Record a user action:

```bash
python3 external-systems/partner-recommendation-system/scripts/record_recommendation_action.py \
  --db /tmp/partner-phase3.sqlite3 \
  --subscription-id saved-search-xxxx \
  --candidate-id 90001 \
  --action skip
```

Create a proxy-intro case:

```bash
python3 external-systems/partner-recommendation-system/scripts/request_proxy_intro.py \
  --db /tmp/partner-phase3.sqlite3 \
  --subscription-id saved-search-xxxx \
  --candidate-id 90001
```

Dispatch pending proxy-intro outreach:

```bash
python3 external-systems/partner-recommendation-system/scripts/dispatch_match_case_outreach.py \
  --db /tmp/partner-phase3.sqlite3
```

Record a proxy-intro reply:

```bash
python3 external-systems/partner-recommendation-system/scripts/record_match_case_reply.py \
  --db /tmp/partner-phase3.sqlite3 \
  --case-id match-case-xxxx \
  --reply accepted
```

## Notes

- This system currently targets in-app recommendation cards only.
- Proxy intro now lives in this outer system; automatic matchmaking still does not.
- It depends on the Phase 2 Python API from `local-skills/partner-search`.
- Run `bash scripts/run_tests.sh` in this directory to verify Phase 3/4 behavior.
