from __future__ import annotations

import json
import pathlib
import sys
import unittest
from datetime import datetime
from unittest import mock

import os


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from match_domain import (  # noqa: E402
    AGGREGATE_CASE,
    AGGREGATE_RELATION,
    CASE_EVENT_PAYLOAD_SCHEMA,
    PHOTO_ANALYSIS_JOB_TYPE,
    PHOTO_EVENT_TYPE_DELETED,
    PHOTO_EVENT_TYPE_REPLACED,
    RULE_PROVENANCE_SCHEMA,
    build_subscription_refresh_provenance,
    CaseStatus,
    CaseType,
    InMemoryLedgerStore,
    MatchEvent,
    PairStatus,
    PhotoAnalysisEvent,
    ProfileRef,
    RelationStatus,
    SyncEventBus,
    build_photo_analysis_event,
    build_canonical_event,
    build_case_aggregate_event,
    bundle_matchmaking_case_entities,
    bundle_proxy_intro_case_entities,
    case_event_time_bucket,
    clear_photo_analysis_subscribers,
    correlation_case_event,
    correlation_relation_action,
    enqueue_photo_analysis_job_from_event,
    entity_id_case,
    entity_id_pair,
    entity_id_profile,
    entity_id_recommendation,
    entity_id_relation,
    ensure_photo_analysis_async_subscription,
    match_event_from_merged_action_payload,
    match_events_from_action_rows,
    match_events_from_case_event_rows,
    merge_payload_with_event,
    pair_key,
    publish_photo_analysis_event,
    reduce_case_ledger,
    reduce_relation_ledger,
    relation_key,
    reset_trace_id,
    run_photo_analysis_job_worker,
    set_trace_id,
    sort_ledger_events,
    subscribe_photo_analysis_events,
)


class MatchDomainTests(unittest.TestCase):
    def test_profile_ref_requires_identity(self):
        with self.assertRaises(ValueError):
            ProfileRef(source="mysql://root@127.0.0.1:3307/her?table=profiles")

    def test_relation_key_is_directional(self):
        owner = ProfileRef(source="mysql://a", profile_id=1001)
        target = ProfileRef(source="mysql://a", profile_id=1002)

        self.assertNotEqual(relation_key(owner, target), relation_key(target, owner))
        self.assertEqual(
            relation_key(owner, target),
            "mysql://a#profile:1001->mysql://a#profile:1002",
        )

    def test_pair_key_is_order_insensitive(self):
        left = ProfileRef(source="mysql://a", profile_id=1001)
        right = ProfileRef(source="mysql://a", user_key="user-b")

        self.assertEqual(pair_key(left, right), pair_key(right, left))
        self.assertIn("<->", pair_key(left, right))

    def test_match_event_to_dict_includes_contract_fields(self):
        event = MatchEvent(
            event_id="evt-1",
            event_type="relation_skipped",
            aggregate_type="relation",
            aggregate_id="rel-1",
            actor_type="user",
            actor_id="70001",
            source_service="recommendation-system",
            correlation_id="corr-1",
            idempotency_key="idem-1",
            occurred_at=datetime(2026, 5, 3, 9, 0, 0),
            payload={"cooldown_until": "2026-06-02 09:00:00"},
        )

        payload = event.to_dict()
        self.assertEqual(payload["event_type"], "relation_skipped")
        self.assertEqual(payload["aggregate_type"], "relation")
        self.assertEqual(payload["occurred_at"], "2026-05-03 09:00:00")
        self.assertEqual(payload["payload"]["cooldown_until"], "2026-06-02 09:00:00")

    def test_canonical_status_vocab_matches_design_doc(self):
        self.assertEqual(RelationStatus.COOLING.value, "cooling")
        self.assertEqual(RelationStatus.PROXY_INTRO_ACTIVE.value, "proxy_intro_active")
        self.assertEqual(RelationStatus.DIRECT_GREET_STARTED.value, "direct_greet_started")
        self.assertEqual(PairStatus.NEEDS_REVALIDATION.value, "needs_revalidation")
        self.assertEqual(PairStatus.MUTUAL_ACCEPT.value, "mutual_accept")
        self.assertEqual(CaseType.MATCHMAKING.value, "matchmaking")
        self.assertEqual(CaseStatus.AWAITING_REPLY.value, "awaiting_reply")

    def test_reduce_relation_ledger_proxy_intro_lifecycle(self):
        rk = "mysql://a#profile:1->mysql://a#profile:2"
        t0 = datetime(2026, 1, 1, 10, 0, 0)
        t1 = datetime(2026, 1, 1, 10, 1, 0)
        t2 = datetime(2026, 1, 1, 10, 2, 0)

        def rel_evt(event_type: str, ts: datetime, payload: dict | None = None) -> MatchEvent:
            return MatchEvent(
                event_id=f"evt-{event_type}-{ts.isoformat()}",
                event_type=event_type,
                aggregate_type=AGGREGATE_RELATION,
                aggregate_id=rk,
                actor_type="user",
                actor_id="1",
                source_service="recommendation-system",
                correlation_id="c1",
                occurred_at=ts,
                payload=dict(payload or {}),
            )

        events = [
            rel_evt("save", t0),
            rel_evt("request_proxy_intro", t1, {"case_id": "case-abc"}),
            rel_evt("proxy_intro_reply_accepted", t2),
        ]
        mid = reduce_relation_ledger(events)
        self.assertEqual(mid.status, RelationStatus.PROXY_INTRO_ACTIVE)
        self.assertEqual(mid.active_match_case_id, "case-abc")

        closed = reduce_relation_ledger(
            events
            + [
                rel_evt("proxy_intro_closed_handoff_completed", datetime(2026, 1, 1, 11, 0, 0)),
            ]
        )
        self.assertEqual(closed.status, RelationStatus.CLOSED)
        self.assertIsNone(closed.active_match_case_id)

    def test_reduce_case_ledger_matchmaking_happy_path(self):
        cid = "case-mm-1"

        def case_evt(event_type: str, minute: int) -> MatchEvent:
            return MatchEvent(
                event_id=f"{event_type}-{minute}",
                event_type=event_type,
                aggregate_type=AGGREGATE_CASE,
                aggregate_id=cid,
                actor_type="system",
                actor_id="system",
                source_service="matchmaking-system",
                correlation_id="c2",
                occurred_at=datetime(2026, 2, 1, 9, minute, 0),
            )

        st = reduce_case_ledger(
            [
                case_evt("case_created", 0),
                case_evt("first_contact_sent", 1),
                case_evt("first_reply_accepted", 2),
                case_evt("second_contact_sent", 3),
                case_evt("second_reply_accepted", 4),
            ]
        )
        self.assertEqual(st.status, CaseStatus.ACCEPTED)

    def test_match_events_from_action_rows_parses_canonical_event(self):
        merged = merge_payload_with_event(
            {"note": "x"},
            build_canonical_event(
                event_type="skip",
                aggregate_type=AGGREGATE_RELATION,
                aggregate_id="k1",
                actor_type="user",
                actor_id="9",
                source_service="recommendation-system",
                correlation_id="r1",
                occurred_at=datetime(2026, 3, 1, 12, 0, 0),
            ),
        )
        evt = match_event_from_merged_action_payload(merged)
        self.assertIsNotNone(evt)
        assert evt is not None
        self.assertEqual(evt.event_type, "skip")

        rows = [{"action_payload_json": __import__("json").dumps(merged)}]
        parsed = match_events_from_action_rows(
            rows,
            payload_loader=lambda raw: __import__("json").loads(raw) if raw else {},
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(reduce_relation_ledger(parsed).status, RelationStatus.SKIPPED)

    def test_in_memory_ledger_store_orders_by_time(self):
        store = InMemoryLedgerStore()
        base = datetime(2026, 4, 1, 10, 0, 0)
        e2 = build_canonical_event(
            event_type="save",
            aggregate_type=AGGREGATE_RELATION,
            aggregate_id="agg",
            actor_type="user",
            actor_id="1",
            source_service="recommendation-system",
            correlation_id="x",
            occurred_at=base,
        )
        e1 = build_canonical_event(
            event_type="skip",
            aggregate_type=AGGREGATE_RELATION,
            aggregate_id="agg",
            actor_type="user",
            actor_id="1",
            source_service="recommendation-system",
            correlation_id="y",
            occurred_at=datetime(2026, 4, 1, 9, 0, 0),
        )
        store.append(e2)
        store.append(e1)
        stream = store.load_stream(aggregate_type=AGGREGATE_RELATION, aggregate_id="agg")
        self.assertEqual([e.event_type for e in stream], ["skip", "save"])

    def test_entity_ids_use_her_namespace(self):
        owner = ProfileRef(source="mysql://a", profile_id=1)
        self.assertTrue(entity_id_profile(owner).startswith("her:prf:"))
        self.assertEqual(entity_id_recommendation(42), "her:rec:42")
        rk = relation_key(owner, ProfileRef(source="mysql://a", profile_id=2))
        self.assertEqual(entity_id_relation(rk), f"her:rel:{rk}")

    def test_correlation_ids_pipe_separated_with_trace(self):
        self.assertEqual(
            correlation_relation_action(9, "skip", trace_id="a1b2c3"),
            "a1b2c3|her:rec:9|skip",
        )
        self.assertEqual(
            correlation_case_event("case-x", "proxy_intro", "opened", trace_id="t0"),
            "t0|her:case:case-x|proxy_intro|opened",
        )

    def test_build_case_aggregate_event_unifies_proxy_and_matchmaking_envelope(self):
        occurred = datetime(2026, 4, 1, 10, 30, 45)
        proxy_case = {
            "case_id": "case-p1",
            "subscription_id": "sub-1",
            "recommendation_id": 9,
            "requester_id": 100,
            "candidate_id": 200,
            "source": "mysql://a",
            "self_id": 100,
        }
        proxy_evt = build_case_aggregate_event(
            event_type="case_created",
            case_id="case-p1",
            case_type=CaseType.PROXY_INTRO,
            source_service="recommendation-system",
            actor_type="system",
            actor_id="system",
            occurred_at=occurred,
            payload={
                "subscription_id": proxy_case["subscription_id"],
                "recommendation_id": proxy_case["recommendation_id"],
                "candidate_id": proxy_case["candidate_id"],
            },
            entity_ids=bundle_proxy_intro_case_entities(proxy_case),
            trace_id="t" * 32,
        )
        self.assertEqual(proxy_evt.aggregate_type, AGGREGATE_CASE)
        self.assertEqual(proxy_evt.payload.get("schema"), CASE_EVENT_PAYLOAD_SCHEMA)
        self.assertEqual(proxy_evt.payload.get("case_type"), CaseType.PROXY_INTRO.value)
        self.assertEqual(
            proxy_evt.correlation_id,
            correlation_case_event("case-p1", CaseType.PROXY_INTRO.value, "case_created", trace_id="t" * 32),
        )
        bucket = case_event_time_bucket(occurred)
        self.assertTrue(proxy_evt.idempotency_key.endswith(f":case_created:{bucket}"))

        mm_evt = build_case_aggregate_event(
            event_type="case_created",
            case_id="case-m1",
            case_type=CaseType.MATCHMAKING,
            source_service="matchmaking-system",
            actor_type="system",
            actor_id="system",
            occurred_at=occurred,
            payload={"pair_key": "pk1", "initiator_type": "system"},
            entity_ids=bundle_matchmaking_case_entities(
                case_id="case-m1",
                pair_key="pk1",
                first_contact_member_id="m-low",
                second_contact_member_id="m-high",
            ),
            trace_id="t" * 32,
        )
        self.assertEqual(mm_evt.payload.get("schema"), CASE_EVENT_PAYLOAD_SCHEMA)
        self.assertEqual(mm_evt.payload.get("case_type"), CaseType.MATCHMAKING.value)
        eids = mm_evt.payload.get("entity_ids") or {}
        self.assertEqual(eids.get("case"), entity_id_case("case-m1"))
        self.assertEqual(eids.get("pair"), entity_id_pair("pk1"))
        self.assertIn("member_first_contact", eids)
        self.assertIn("member_second_contact", eids)

    def test_build_canonical_event_merges_entity_ids_and_trace_env(self):
        old = os.environ.pop("HER_TRACE_ID", None)
        os.environ["HER_TRACE_ID"] = "e" * 32
        try:
            evt = build_canonical_event(
                event_type="save",
                aggregate_type=AGGREGATE_RELATION,
                aggregate_id="k",
                actor_type="user",
                actor_id="1",
                source_service="recommendation-system",
                correlation_id="x",
                occurred_at=datetime(2026, 3, 1, 12, 0, 0),
                entity_ids={"recommendation": "her:rec:1"},
            )
            self.assertEqual(evt.trace_id, "e" * 32)
            self.assertEqual(evt.payload.get("entity_ids", {}).get("recommendation"), "her:rec:1")
            self.assertIn("trace_id", evt.to_dict())
        finally:
            if old is None:
                os.environ.pop("HER_TRACE_ID", None)
            else:
                os.environ["HER_TRACE_ID"] = old

    def test_trace_context_var_overrides_env(self):
        old_env = os.environ.pop("HER_TRACE_ID", None)
        os.environ["HER_TRACE_ID"] = "f" * 32
        tok = set_trace_id("c" * 32)
        try:
            evt = build_canonical_event(
                event_type="skip",
                aggregate_type=AGGREGATE_RELATION,
                aggregate_id="k",
                actor_type="user",
                actor_id="1",
                source_service="recommendation-system",
                correlation_id="y",
                occurred_at=datetime(2026, 3, 1, 12, 0, 0),
            )
            self.assertEqual(evt.trace_id, "c" * 32)
        finally:
            reset_trace_id(tok)
            if old_env is None:
                os.environ.pop("HER_TRACE_ID", None)
            else:
                os.environ["HER_TRACE_ID"] = old_env

    def test_sort_ledger_events_stable(self):
        t = datetime(2026, 5, 1, 1, 0, 0)
        a = MatchEvent(
            event_id="b",
            event_type="x",
            aggregate_type=AGGREGATE_RELATION,
            aggregate_id="z",
            actor_type="user",
            actor_id="1",
            source_service="s",
            correlation_id="c",
            occurred_at=t,
        )
        b = MatchEvent(
            event_id="a",
            event_type="y",
            aggregate_type=AGGREGATE_RELATION,
            aggregate_id="z",
            actor_type="user",
            actor_id="1",
            source_service="s",
            correlation_id="c",
            occurred_at=t,
        )
        ordered = sort_ledger_events([a, b])
        self.assertEqual([e.event_id for e in ordered], ["a", "b"])

    def test_match_events_from_case_event_rows_prefers_canonical_column(self):
        evt = build_canonical_event(
            event_type="case_created",
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="c1",
            actor_type="system",
            actor_id="system",
            source_service="matchmaking-system",
            correlation_id="x",
            occurred_at=datetime(2026, 3, 1, 12, 0, 0),
            payload={"pair_key": "p1"},
        )
        row = {
            "canonical_event_json": json.dumps(evt.to_dict()),
            "payload": {"note": "domain-only"},
        }
        parsed = match_events_from_case_event_rows([row])
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].event_type, "case_created")
        self.assertEqual(parsed[0].payload.get("pair_key"), "p1")

    def test_sync_event_bus_invokes_subscribers(self):
        bus = SyncEventBus()
        seen: list[str] = []
        bus.subscribe(lambda e: seen.append(e.event_type))
        evt = build_canonical_event(
            event_type="case_created",
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="c1",
            actor_type="system",
            actor_id="system",
            source_service="matchmaking-system",
            correlation_id="x",
            occurred_at=datetime(2026, 3, 2, 8, 0, 0),
        )
        bus.publish(evt)
        self.assertEqual(seen, ["case_created"])

    def test_photo_event_bus_publish_and_enqueue_flow(self):
        clear_photo_analysis_subscribers()
        seen: list[PhotoAnalysisEvent] = []
        subscribe_photo_analysis_events(lambda event: seen.append(event))
        event = build_photo_analysis_event(
            event_type=PHOTO_EVENT_TYPE_REPLACED,
            profile_id=12,
            persona_source_dsn="mysql://persona",
            profile_source_dsn="mysql://profiles",
            source_table_name="profiles",
            trigger_fields=["avatar_url"],
        )
        with mock.patch("match_domain.photo_event_bus.ensure_photo_analysis_async_subscription"):
            publish_photo_analysis_event(event)

        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].event_type, PHOTO_EVENT_TYPE_REPLACED)
        clear_photo_analysis_subscribers()

    def test_enqueue_photo_analysis_job_from_event_uses_async_jobs(self):
        event = build_photo_analysis_event(
            event_type=PHOTO_EVENT_TYPE_DELETED,
            profile_id=18,
            persona_source_dsn="mysql://persona",
            profile_source_dsn="mysql://profiles",
            source_table_name="profiles",
        )
        fake_conn = mock.Mock()
        fake_conn.close = mock.Mock()

        with (
            mock.patch("match_domain.photo_event_bus._connect_job_db", return_value=fake_conn),
            mock.patch("match_domain.photo_event_bus.enqueue_async_job", return_value={"job_type": PHOTO_ANALYSIS_JOB_TYPE}) as mocked_enqueue,
        ):
            result = enqueue_photo_analysis_job_from_event(event)

        mocked_enqueue.assert_called_once()
        self.assertEqual(result["job_type"], PHOTO_ANALYSIS_JOB_TYPE)

    def test_run_photo_analysis_job_worker_delegates_to_async_worker(self):
        fake_conn = mock.Mock()
        fake_conn.close = mock.Mock()

        with (
            mock.patch("match_domain.photo_event_bus._connect_job_db", return_value=fake_conn),
            mock.patch(
                "match_domain.photo_event_bus.run_async_job_worker",
                return_value={"processed": [{"job_type": PHOTO_ANALYSIS_JOB_TYPE}]},
            ) as mocked_worker,
        ):
            result = run_photo_analysis_job_worker(source_dsn="mysql://persona", limit=2)

        mocked_worker.assert_called_once()
        self.assertEqual(result["processed"][0]["job_type"], PHOTO_ANALYSIS_JOB_TYPE)

    def test_ensure_photo_analysis_async_subscription_is_idempotent(self):
        clear_photo_analysis_subscribers()
        with mock.patch("match_domain.photo_event_bus.subscribe_photo_analysis_events") as mocked_subscribe:
            ensure_photo_analysis_async_subscription()
            ensure_photo_analysis_async_subscription()
        mocked_subscribe.assert_called_once()
        clear_photo_analysis_subscribers()

    def test_subscription_refresh_provenance_pins_rule_sets_and_fingerprints(self):
        prov = build_subscription_refresh_provenance(
            subscription_id="saved-search-abc",
            persona_profile={"target_gender": "女", "target_age_min": 27},
            search_request={"criteria": {"cities": ["无锡"]}, "limit": 5},
        )
        self.assertEqual(prov["schema"], RULE_PROVENANCE_SCHEMA)
        self.assertEqual(prov["fingerprints"]["subscription_id"], "saved-search-abc")
        self.assertEqual(len(prov["fingerprints"]["persona_profile"]), 64)
        self.assertEqual(len(prov["fingerprints"]["search_request"]), 64)
        self.assertIn("partner_search.scoring", prov["rule_sets"])
        subscription = {
            "subscription_id": "saved-search-abc",
            "min_direct_greet_score": 60,
            "max_review_candidates_per_refresh": 3,
            "recommendation_mode": "direct_greet_only",
            "auto_reject_on_follow_up_questions": True,
            "auto_reject_on_risk_flags": True,
            "direct_greet_profile_json": "{}",
            "subscription_overrides_json": "{}",
            "quiet_hours_start": 22,
            "quiet_hours_end": 9,
            "daily_notification_cap": 2,
            "skip_cooldown_days": 30,
            "min_notify_score": 40,
        }
        prov_with_params = build_subscription_refresh_provenance(
            subscription_id="saved-search-abc",
            persona_profile={"target_gender": "女", "target_age_min": 27},
            search_request={"criteria": {"cities": ["无锡"]}, "limit": 5},
            subscription=subscription,
        )
        self.assertIn("effective_params", prov_with_params)


if __name__ == "__main__":
    unittest.main()
