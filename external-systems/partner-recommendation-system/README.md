# Partner Recommendation System

This directory is the Phase 3 outer system for `partner-search`.

It is intentionally separate from the skill itself.

- `partner-search` still only does `画像 / 条件 -> 候选结果`
- this outer system owns saved searches, recommendation history, user actions, refresh timing, frequency caps, cooldowns, and in-app recommendation cards

## Directory Map

- `recommendation_system/storage.py`
  - SQLite schema and low-level storage helpers
- `recommendation_system/service.py`
  - subscription refresh, recommendation dedupe, cooldown, frequency cap, quiet-hours, and card generation
- `recommendation_system/search_client.py`
  - bridge into `partner-search`'s Python API
- `scripts/create_saved_search_subscription.py`
  - create a saved-search subscription
- `scripts/refresh_saved_searches.py`
  - refresh due subscriptions and queue new candidates
- `scripts/deliver_in_app_recommendations.py`
  - convert queued recommendations into in-app cards
- `scripts/record_recommendation_action.py`
  - store `skip`, `save`, or `direct_greet`
- `tests/test_recommendation_system.py`
  - Phase 3 regression tests

## Database Tables

- `saved_search_subscriptions`
  - who enabled continuous search
  - the saved criteria and requester profile
  - refresh cadence, quiet hours, daily cap, score threshold, skip cooldown
- `profile_recommendations`
  - recommendation history per `(subscription, candidate)`
  - latest score snapshot
  - delivery status
  - cooldown state
- `recommendation_actions`
  - user actions such as `skip`, `save`, `direct_greet`
- `in_app_recommendation_cards`
  - the actual station/in-app recommendation payload shown to the user

## End-to-End Flow

1. Create a saved-search subscription in the outer system.
2. Run the refresh job.
3. The refresh job calls `partner-search` through its Python API.
4. New high-score candidates become `pending_delivery`.
5. Run the delivery job.
6. The delivery job applies quiet hours and daily caps, then writes in-app cards.
7. Record user actions such as `skip` or `save`.
8. Future refreshes use recommendation history and cooldown state to avoid noisy repeat reminders.

## Quick Start

Create one subscription:

```bash
python3 external-systems/partner-recommendation-system/scripts/create_saved_search_subscription.py \
  --db /tmp/partner-phase3.sqlite3 \
  --requester-id 70001 \
  --source 'mysql://user:pass@127.0.0.1:3306/her?table=profiles' \
  --title '无锡认真恋爱' \
  --criteria-json '{"gender":"女","cities":["无锡"],"relationship_goals":["认真恋爱","结婚导向"],"must_have":["情绪稳定"],"verified_level_min":"photo"}' \
  --self-profile-json '{"age":28,"city":"无锡","height":178}'
```

Refresh due subscriptions:

```bash
python3 external-systems/partner-recommendation-system/scripts/refresh_saved_searches.py \
  --db /tmp/partner-phase3.sqlite3
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

## Notes

- This system currently targets in-app recommendation cards only.
- It does not do proxy intro or automatic matchmaking.
- It depends on the Phase 2 Python API from `local-skills/partner-search`.
- Run `bash scripts/run_tests.sh` in this directory to verify Phase 3 behavior.
