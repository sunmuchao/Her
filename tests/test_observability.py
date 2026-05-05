from __future__ import annotations

import json
import logging

import pytest

from observability import CHAT_FUNNEL_MESSAGE_SEND, emit_pipeline_record, funnel_stage, metric_gauge


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
