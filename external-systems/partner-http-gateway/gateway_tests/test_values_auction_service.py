from __future__ import annotations

import json

from assessment import values_auction_service as service


class _FakeCursor:
    def __init__(self, rows: dict[tuple[str, str, str], str]) -> None:
        self._rows = rows
        self._selected: str | None = None

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        normalized = " ".join(query.split()).upper()
        if normalized.startswith("DELETE FROM"):
            user_key, conversation_ref, field_name = (str(params[0]), str(params[1]), str(params[2]))
            self._rows.pop((user_key, conversation_ref, field_name), None)
            self._selected = None
            return

        if normalized.startswith("INSERT INTO"):
            user_key = str(params[0])
            field_name = str(params[1])
            field_value = str(params[2])
            conversation_ref = str(params[6])
            self._rows[(user_key, conversation_ref, field_name)] = field_value
            self._selected = None
            return

        if normalized.startswith("SELECT FIELD_VALUE FROM"):
            user_key, field_name, conversation_ref = (str(params[0]), str(params[1]), str(params[2]))
            self._selected = self._rows.get((user_key, conversation_ref, field_name))
            return

        raise AssertionError(f"Unexpected query: {query}")

    def fetchone(self):
        if self._selected is None:
            return None
        return (self._selected,)


class _FakeConn:
    def __init__(self, rows: dict[tuple[str, str, str], str]) -> None:
        self._rows = rows

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)

    def commit(self) -> None:
        return None


def _install_fakes(monkeypatch, *, last_result: dict | None = None):
    rows: dict[tuple[str, str, str], str] = {}
    conn = _FakeConn(rows)

    monkeypatch.setattr(service, "mysql_connect", lambda source: conn)
    monkeypatch.setattr(service, "release_persona_connection", lambda source, conn: None)
    monkeypatch.setattr(service, "apply_persona_patch", lambda **kwargs: None)
    monkeypatch.setattr(service, "fetch_persona", lambda cursor, persona_table, user_key=None: {})
    monkeypatch.setattr(service, "get_last_result", lambda **kwargs: last_result)
    return rows


def test_submit_together_updates_both_participants(monkeypatch):
    rows = _install_fakes(monkeypatch)
    source = "mysql://fake/her?table=user_personas"

    started = service.start_values_auction_together(
        user_key="u1",
        partner_key="u2",
        source=source,
    )
    session_id = started["session_id"]

    bids_a = [
        {"trait_id": "loyalty", "chips": 4},
        {"trait_id": "values_match", "chips": 3},
        {"trait_id": "companionship", "chips": 2},
        {"trait_id": "humor", "chips": 1},
    ]
    bids_b = [
        {"trait_id": "loyalty", "chips": 3},
        {"trait_id": "values_match", "chips": 3},
        {"trait_id": "companionship", "chips": 3},
        {"trait_id": "gentle", "chips": 1},
    ]

    waiting = service.submit_auction_bids_together(
        session_id=session_id,
        user_key="u1",
        bids=bids_a,
        source=source,
    )
    assert waiting["card_type"] == "values_auction_waiting"

    match = service.submit_auction_bids_together(
        session_id=session_id,
        user_key="u2",
        bids=bids_b,
        source=source,
    )
    assert match["card_type"] == "values_match_analysis"

    status_for_u1 = service.check_dual_auction_status(
        session_id=session_id,
        user_key="u1",
        source=source,
    )
    status_for_u2 = service.check_dual_auction_status(
        session_id=session_id,
        user_key="u2",
        source=source,
    )
    assert status_for_u1["status"] == "both_done"
    assert status_for_u2["status"] == "both_done"

    stored_u1 = json.loads(rows[("u1", session_id, service.VALUES_AUCTION_DUAL_SESSION_FIELD)])
    stored_u2 = json.loads(rows[("u2", session_id, service.VALUES_AUCTION_DUAL_SESSION_FIELD)])
    assert stored_u1["user_a_status"] == "done"
    assert stored_u1["user_b_status"] == "done"
    assert stored_u2["user_a_status"] == "done"
    assert stored_u2["user_b_status"] == "done"


def test_reuse_together_updates_both_participants(monkeypatch):
    last_result = {
        "value_type": "忠诚至上型",
        "bids": [
            {"trait_id": "loyalty", "trait_name": "专一忠诚", "chips": 4},
            {"trait_id": "values_match", "trait_name": "三观一致", "chips": 3},
            {"trait_id": "companionship", "trait_name": "陪伴时间", "chips": 3},
        ],
        "top3": [
            {"trait_id": "loyalty", "trait_name": "专一忠诚", "chips": 4},
            {"trait_id": "values_match", "trait_name": "三观一致", "chips": 3},
            {"trait_id": "companionship", "trait_name": "陪伴时间", "chips": 3},
        ],
    }
    rows = _install_fakes(monkeypatch, last_result=last_result)
    source = "mysql://fake/her?table=user_personas"

    started = service.start_values_auction_together(
        user_key="u1",
        partner_key="u2",
        source=source,
    )
    session_id = started["session_id"]

    waiting = service.reuse_last_result_together(
        session_id=session_id,
        user_key="u1",
        source=source,
    )
    assert waiting["card_type"] == "values_auction_waiting"

    match = service.reuse_last_result_together(
        session_id=session_id,
        user_key="u2",
        source=source,
    )
    assert match["card_type"] == "values_match_analysis"

    status_for_u1 = service.check_dual_auction_status(
        session_id=session_id,
        user_key="u1",
        source=source,
    )
    status_for_u2 = service.check_dual_auction_status(
        session_id=session_id,
        user_key="u2",
        source=source,
    )
    assert status_for_u1["status"] == "both_done"
    assert status_for_u2["status"] == "both_done"
