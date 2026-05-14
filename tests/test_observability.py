from __future__ import annotations

import json
import logging

import pytest

from match_domain import reset_actor_context, reset_trace_id, set_actor_context, set_trace_id
from observability import CHAT_FUNNEL_MESSAGE_SEND, emit_pipeline_record, funnel_stage, metric_gauge
from observability import audit_event


def test_emit_pipeline_record_json_parseable(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="her.pipeline")
    emit_pipeline_record(her_kind="test", foo="bar")
    assert caplog.records
    msg = caplog.records[-1].getMessage()
    data = json.loads(msg)
    assert data["her_kind"] == "test"
    assert data["foo"] == "bar"
    assert data["her_schema"] == "1"


def test_funnel_and_metric_helpers(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="her.pipeline")
    funnel_stage(system="recommendation", stage="refresh", subscription_id="s1")
    metric_gauge("x.y", 3, z="a")
    lines = [json.loads(r.getMessage()) for r in caplog.records[-2:]]
    assert lines[0]["funnel_system"] == "recommendation"
    assert lines[0]["funnel_stage"] == "refresh"
    assert lines[1]["metric"] == "x.y"
    assert lines[1]["value"] == 3


def test_chat_funnel_constant() -> None:
    assert CHAT_FUNNEL_MESSAGE_SEND == "message_send"


def test_emit_pipeline_record_includes_actor_and_trace_context(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="her.pipeline")
    trace_token = set_trace_id("trace-ctx-1")
    actor_token = set_actor_context(
        "operator-1",
        actor_roles=["platform_admin", "service_worker"],
        auth_source="cli",
        reason="manual_repair",
    )
    try:
        emit_pipeline_record(her_kind="test", foo="bar")
    finally:
        reset_actor_context(actor_token)
        reset_trace_id(trace_token)
    data = json.loads(caplog.records[-1].getMessage())
    assert data["trace_id"] == "trace-ctx-1"
    assert data["actor_id"] == "operator-1"
    assert data["actor_roles"] == ["platform_admin", "service_worker"]
    assert data["actor_auth_source"] == "cli"
    assert data["actor_reason"] == "manual_repair"


def test_audit_event_emits_structured_audit_log(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="her.pipeline")
    audit_event(
        action="gateway.staff_override",
        resource_type="recommendation_subscription",
        resource_id="sub-1",
        outcome="allowed",
        reason="support_assist",
        impersonated_owner_id="70001",
    )
    data = json.loads(caplog.records[-1].getMessage())
    assert data["her_kind"] == "audit"
    assert data["audit_action"] == "gateway.staff_override"
    assert data["resource_type"] == "recommendation_subscription"
    assert data["resource_id"] == "sub-1"
    assert data["outcome"] == "allowed"
    assert data["impersonated_owner_id"] == "70001"
