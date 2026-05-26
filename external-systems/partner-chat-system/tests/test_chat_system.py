import base64
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from unittest import mock

import pytest

pytest.importorskip("cv2")
import cv2  # noqa: E402
from huggingface_hub.errors import LocalEntryNotFoundError  # noqa: E402
import numpy as np  # noqa: E402


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system import (  # noqa: E402
    build_fraud_network_overview,
    build_thread_risk_overview,
    create_live_video_verification_challenge,
    evaluate_profile_consistency,
    evaluate_fraud_network,
    get_photo_risk_score_run,
    get_or_create_thread,
    get_fraud_network_profile,
    get_verification_submission,
    get_risk_case,
    get_thread,
    get_thread_summary,
    list_fraud_network_profiles,
    list_photo_review_requests,
    list_photo_risk_review_queue,
    list_photo_risk_score_runs,
    list_member_reports,
    list_meeting_feedback,
    list_messages,
    list_risk_cases,
    list_risk_signals,
    list_verification_notifications,
    list_verification_submissions,
    post_message,
    resubmit_live_video_verification,
    review_profile_review_case,
    review_risk_case,
    review_live_video_verification,
    run_chat_maintenance,
    submit_live_video_verification,
    submit_meeting_feedback,
    submit_member_report,
)
import chat_system.verification as verification_module  # noqa: E402
import chat_system.live_video_local as live_video_local_module  # noqa: E402
import chat_system.persona_jobs as persona_jobs_module  # noqa: E402
import chat_system.profile_reviews as profile_reviews_module  # noqa: E402
from chat_system.outbox import (  # noqa: E402
    claim_pending_outbox_batch,
    get_outbox_row,
    list_failed_outbox,
    list_pending_outbox,
    list_processing_outbox,
    recover_stale_outbox_claims,
    requeue_outbox_rows,
    summarize_outbox,
)
from chat_system.outbox_consumer import consume_chat_outbox_batch  # noqa: E402
from chat_system.outbox import (  # noqa: E402
    resolve_outbox_consume_config,
    run_chat_outbox_worker,
    serve_chat_outbox_worker,
)
from chat_system.persona_jobs import enqueue_persona_sync_job, list_pending_persona_jobs, process_pending_persona_jobs  # noqa: E402
from chat_system.service import VIS_DYADIC, VIS_OWNER_ONLY  # noqa: E402
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN, connect_db, initialize_database, reset_all_tables  # noqa: E402


class ChatSystemTests(unittest.TestCase):
    def setUp(self):
        self._old_verification_provider = os.environ.get("HER_VERIFICATION_PROVIDER")
        self._old_verification_auto_triage = os.environ.get("HER_VERIFICATION_AUTO_TRIAGE")
        os.environ["HER_VERIFICATION_PROVIDER"] = "local_oss"
        os.environ["HER_VERIFICATION_AUTO_TRIAGE"] = "1"
        self.conn = connect_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_database(self.conn)
        reset_all_tables(self.conn)
        self._reset_profile_sync_table()

    def tearDown(self):
        self._reset_profile_sync_table()
        self.conn.close()
        if self._old_verification_provider is None:
            os.environ.pop("HER_VERIFICATION_PROVIDER", None)
        else:
            os.environ["HER_VERIFICATION_PROVIDER"] = self._old_verification_provider
        if self._old_verification_auto_triage is None:
            os.environ.pop("HER_VERIFICATION_AUTO_TRIAGE", None)
        else:
            os.environ["HER_VERIFICATION_AUTO_TRIAGE"] = self._old_verification_auto_triage

    def _reset_profile_sync_table(self) -> None:
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS `profiles`")
        self.conn.commit()

    def _deepfake_face_mask(self) -> np.ndarray:
        mask = np.zeros((192, 192), dtype=np.uint8)
        cv2.ellipse(mask, (96, 106), (58, 68), 0, 0, 360, 255, -1)
        return mask.astype(bool)

    def _build_photo_edit_face_crops(self, *, edited: bool, count: int = 4) -> list[np.ndarray]:
        rng = np.random.default_rng(20260521 if edited else 20260520)
        crops: list[np.ndarray] = []
        for index in range(count):
            crop = np.full((192, 192, 3), (32, 40, 54), dtype=np.uint8)
            face_axes = (58, 82) if edited else (68, 82)
            face_mask = np.zeros((192, 192), dtype=np.uint8)
            cv2.ellipse(face_mask, (96, 104), face_axes, 0, 0, 360, 255, -1)
            face_mask_bool = face_mask.astype(bool)
            face_tone = np.array([176, 198, 220], dtype=np.int16)
            face_shift = np.array([index - 2, index - 1, index], dtype=np.int16)
            face_color = tuple(np.clip(face_tone + face_shift, 0, 255).astype(np.uint8).tolist())
            cv2.ellipse(crop, (96, 104), face_axes, 0, 0, 360, face_color, -1)
            cv2.ellipse(crop, (74, 86), (11, 6), 0, 0, 360, (48, 48, 48), -1)
            cv2.ellipse(crop, (118, 86), (11, 6), 0, 0, 360, (48, 48, 48), -1)
            cv2.line(crop, (96, 92), (96, 122), (90, 108, 136), 2)
            cv2.ellipse(crop, (96, 136), (20, 5 + (index % 2)), 0, 0, 360, (74, 88, 150), -1)
            natural_noise = rng.integers(-10, 11, size=crop.shape, dtype=np.int16)
            textured = np.clip(crop.astype(np.int16) + natural_noise, 0, 255).astype(np.uint8)
            crop[face_mask_bool] = textured[face_mask_bool]

            if edited:
                blurred = cv2.GaussianBlur(crop, (11, 11), 0)
                crop[face_mask_bool] = blurred[face_mask_bool]
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).astype(np.int16)
                hsv[:, :, 1][face_mask_bool] = np.clip(hsv[:, :, 1][face_mask_bool] + 32, 0, 255)
                hsv[:, :, 2][face_mask_bool] = np.clip(hsv[:, :, 2][face_mask_bool] + 28, 0, 255)
                crop = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
                highlight = np.zeros_like(crop)
                cv2.ellipse(highlight, (96, 98), (42, 48), 0, 0, 360, (16, 18, 18), -1)
                boosted = np.clip(crop.astype(np.int16) + highlight.astype(np.int16), 0, 255).astype(np.uint8)
                crop[face_mask_bool] = boosted[face_mask_bool]

            crops.append(crop)
        return crops

    def _build_synthetic_face_sequence(self, *, manipulated: bool) -> list[np.ndarray]:
        rng = np.random.default_rng(20260513 if manipulated else 20260512)
        inner_mask = self._deepfake_face_mask()
        frames: list[np.ndarray] = []
        for index in range(8):
            frame = np.full((192, 192, 3), (34, 42, 54), dtype=np.uint8)
            face_tone = np.array([174, 198, 220], dtype=np.int16)
            face_shift = np.array([index - 3, index - 2, index - 1], dtype=np.int16)
            face_color = tuple(np.clip(face_tone + face_shift, 0, 255).astype(np.uint8).tolist())
            cv2.ellipse(frame, (96, 106), (70, 82), 0, 0, 360, face_color, -1)
            cv2.ellipse(frame, (74, 88), (11, 6), 0, 0, 360, (42, 42, 42), -1)
            cv2.ellipse(frame, (118, 88), (11, 6), 0, 0, 360, (42, 42, 42), -1)
            mouth_open = 3 + (index % 3)
            cv2.ellipse(frame, (96, 132), (22, mouth_open), 0, 0, 360, (64, 68, 128), -1)
            natural_noise = rng.integers(-4, 5, size=frame.shape, dtype=np.int16)
            frame = np.clip(frame.astype(np.int16) + natural_noise, 0, 255).astype(np.uint8)

            if manipulated:
                altered = frame.astype(np.int16)
                inner_noise = rng.integers(-22, 23, size=frame.shape, dtype=np.int16)
                inner_shift = np.array(
                    [14 - index, ((index % 2) * 18) - 9, 10 + (index * 2)],
                    dtype=np.int16,
                )
                altered[inner_mask] = np.clip(
                    altered[inner_mask] + inner_noise[inner_mask] + inner_shift,
                    0,
                    255,
                )
                frame = altered.astype(np.uint8)
                if index % 2 == 0:
                    blurred = cv2.GaussianBlur(frame, (7, 7), 0)
                    frame[inner_mask] = blurred[inner_mask]
                seam_color = (
                    235 if index % 2 == 0 else 60,
                    52 + (index * 6),
                    200 - (index * 8),
                )
                cv2.ellipse(frame, (96, 106), (58, 68), 0, 0, 360, seam_color, 3)
            frames.append(frame)
        return frames

    def test_thread_create_idempotent_and_messages(self):
        t1 = get_or_create_thread(
            self.conn,
            case_id="case-1",
            relation_key="rel-a|b",
            participant_a_id="user-a",
            participant_b_id="user-b",
            metadata={"source": "test"},
            now=datetime(2026, 5, 4, 10, 0, 0),
        )
        t2 = get_or_create_thread(
            self.conn,
            case_id="case-1",
            relation_key="rel-a|b",
            participant_a_id="user-a",
            participant_b_id="user-b",
            now=datetime(2026, 5, 4, 10, 1, 0),
        )
        self.assertEqual(t1["thread_id"], t2["thread_id"])

        post_message(
            self.conn,
            t1["thread_id"],
            "user-a",
            "hello b",
            visibility=VIS_DYADIC,
            now=datetime(2026, 5, 4, 10, 2, 0),
        )
        a_msgs = list_messages(self.conn, t1["thread_id"], "user-a")
        b_msgs = list_messages(self.conn, t1["thread_id"], "user-b")
        self.assertEqual(len(a_msgs), 1)
        self.assertEqual(len(b_msgs), 1)
        self.assertEqual(a_msgs[0]["body"], "hello b")

        post_message(
            self.conn,
            t1["thread_id"],
            "user-a",
            "note to self",
            visibility=VIS_OWNER_ONLY,
            message_recipient_id="user-a",
            now=datetime(2026, 5, 4, 10, 3, 0),
        )
        a_all = list_messages(self.conn, t1["thread_id"], "user-a")
        b_only = list_messages(self.conn, t1["thread_id"], "user-b")
        self.assertEqual(len(a_all), 2)
        self.assertEqual(len(b_only), 1)

    def test_client_msg_idempotent(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-idem",
            relation_key="r1",
            participant_a_id="u1",
            participant_b_id="u2",
        )
        m1 = post_message(
            self.conn,
            th["thread_id"],
            "u1",
            "x",
            client_msg_id="idem-1",
        )
        m2 = post_message(
            self.conn,
            th["thread_id"],
            "u1",
            "x",
            client_msg_id="idem-1",
        )
        self.assertEqual(m1["message_id"], m2["message_id"])

    def test_owner_only_messages_from_non_participants_are_hidden(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-private-visibility",
            relation_key="private-visibility",
            participant_a_id="alice",
            participant_b_id="bob",
        )
        with self.assertRaisesRegex(ValueError, "author is not a participant"):
            post_message(
                self.conn,
                th["thread_id"],
                "legacy-bot",
                "legacy private message",
                visibility=VIS_OWNER_ONLY,
                source="user",
                message_recipient_id="alice",
            )

        self.conn.execute(
            """
            INSERT INTO chat_messages (
              thread_id, author_id, message_recipient_id, visibility, source, body,
              client_msg_id, reply_to_message_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                th["thread_id"],
                "legacy-bot",
                "alice",
                "owner_only",
                "legacy",
                "legacy hidden private message",
                json.dumps({}),
                datetime(2026, 5, 4, 10, 4, 0),
            ),
        )
        self.conn.execute(
            """
            INSERT INTO chat_messages (
              thread_id, author_id, message_recipient_id, visibility, source, body,
              client_msg_id, reply_to_message_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (
                th["thread_id"],
                "alice",
                "alice",
                "owner_only",
                "user",
                "real private note",
                json.dumps({}),
                datetime(2026, 5, 4, 10, 5, 0),
            ),
        )
        self.conn.commit()

        alice_view = list_messages(self.conn, th["thread_id"], "alice")
        self.assertEqual([item["body"] for item in alice_view], ["real private note"])

    def test_get_thread(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-gt",
            relation_key="r3",
            participant_a_id="a",
            participant_b_id="b",
        )
        row = get_thread(self.conn, th["thread_id"])
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["case_id"], "case-gt")
        self.assertEqual(row["metadata"], {})

    def test_outbox_rows_on_thread_and_message(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-ob",
            relation_key="rob",
            participant_a_id="oa",
            participant_b_id="ob",
        )
        c1 = self.conn.execute("SELECT COUNT(*) AS c FROM outbox_events", ()).fetchone()
        self.assertGreaterEqual(int(c1["c"]), 1)
        post_message(self.conn, th["thread_id"], "oa", "ping", visibility=VIS_DYADIC)
        c2 = self.conn.execute("SELECT COUNT(*) AS c FROM outbox_events", ()).fetchone()
        self.assertGreaterEqual(int(c2["c"]), 2)
        pending = list_pending_outbox(self.conn, limit=50)
        self.assertGreaterEqual(len(pending), 2)

    def test_live_chat_does_not_enqueue_persona_job_mid_conversation(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-pj",
            relation_key="rpj",
            participant_a_id="pa",
            participant_b_id="pb",
        )
        post_message(
            self.conn,
            th["thread_id"],
            "pa",
            "我在杭州工作，岗位是产品经理",
            visibility=VIS_DYADIC,
        )
        jobs = list_pending_persona_jobs(self.conn)
        self.assertEqual(jobs, [])
        out = process_pending_persona_jobs(self.conn, limit=10)
        self.assertEqual(out["examined"], 0)
        self.assertEqual(out["applied"], 0)
        self.assertEqual(out["needs_review"], 0)

    def test_process_pending_persona_jobs_routes_writes_through_profile_service(self):
        self.conn.execute(
            """
            INSERT INTO persona_sync_jobs (
              thread_id, message_id, subject_user_id, update_key, status, patch_json, evidence_json, created_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                "thread-profile-service",
                100000001,
                "user-profile-service",
                "job-key-1",
                json.dumps({"self_job": "产品经理"}),
                json.dumps(
                    {
                        "source_type": "explicit",
                        "apply_scope": "persona_and_profile",
                        "conversation_ref": "thread-profile-service/100000001",
                        "evidence_text": "用户明确说自己做产品。",
                        "confidence_score": 88,
                    }
                ),
                datetime(2026, 5, 5, 8, 0, 0),
            ),
        )
        self.conn.commit()

        with (
            mock.patch.dict(os.environ, {"HER_CHAT_PERSONA_MYSQL_SOURCE": "mysql://persona-source?table=profiles"}, clear=False),
            mock.patch.object(
                persona_jobs_module,
                "apply_persona_patch",
                return_value={"status": "synced", "profile_id": 88},
            ) as mocked,
        ):
            out = process_pending_persona_jobs(
                self.conn,
                limit=10,
                now=datetime(2026, 5, 5, 8, 5, 0),
            )

        self.assertEqual(out["examined"], 1)
        self.assertEqual(out["applied"], 1)
        self.assertEqual(out["needs_review"], 0)
        mocked.assert_called_once_with(
            {
                "source": "mysql://persona-source?table=profiles",
                "user_key": "user-profile-service",
                "source_type": "explicit",
                "patch": {"self_job": "产品经理"},
                "confidence_score": 88,
                "evidence_text": "用户明确说自己做产品。",
                "conversation_ref": "thread-profile-service/100000001",
                "sync_profile": True,
                "apply_scope": "persona_and_profile",
            }
        )
        row = self.conn.execute(
            "SELECT status, sync_result_json FROM persona_sync_jobs WHERE update_key = ? LIMIT 1",
            ("job-key-1",),
        ).fetchone()
        self.assertEqual(row["status"], "applied")
        self.assertIn('"ok": true', row["sync_result_json"])

    def test_persona_sync_jobs_allow_n_updates_for_same_subject_and_message(self):
        evidence_base = {
            "conversation_ref": "thread-1/100",
            "reason": "assistant_post_chat_review",
            "source_type": "explicit",
            "basis": "self_statement",
            "apply_scope": "persona_only",
        }
        ok1 = enqueue_persona_sync_job(
            self.conn,
            thread_id="thread-1",
            message_id=100,
            subject_user_id="user-b",
            patch={"self_job": "财务相关工作"},
            evidence={**evidence_base, "evidence_text": "用户明确说自己做财务相关工作。"},
        )
        ok2 = enqueue_persona_sync_job(
            self.conn,
            thread_id="thread-1",
            message_id=100,
            subject_user_id="user-b",
            patch={"persona_summary_internal": "生活节奏偏规律。"},
            evidence={**evidence_base, "evidence_text": "用户明确说自己生活比较规律。"},
        )
        ok3 = enqueue_persona_sync_job(
            self.conn,
            thread_id="thread-1",
            message_id=100,
            subject_user_id="user-b",
            patch={"target_accept_long_distance": "不接受"},
            evidence={**evidence_base, "evidence_text": "用户明确说自己不接受长期异地。"},
        )

        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertTrue(ok3)
        jobs = list_pending_persona_jobs(self.conn)
        self.assertEqual(len(jobs), 3)

    def test_outbox_consume_clears_pending(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-oc",
            relation_key="roc",
            participant_a_id="x",
            participant_b_id="y",
        )
        post_message(self.conn, th["thread_id"], "x", "one", visibility=VIS_DYADIC)
        self.assertGreaterEqual(len(list_pending_outbox(self.conn)), 1)
        out = consume_chat_outbox_batch(self.conn, limit=50)
        self.assertGreaterEqual(out["marked_published"], 1)
        self.assertEqual(len(list_pending_outbox(self.conn)), 0)

    def test_outbox_consume_schedules_retry_and_then_marks_failed(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-oc-retry",
            relation_key="roc-retry",
            participant_a_id="x",
            participant_b_id="y",
        )
        consume_chat_outbox_batch(
            self.conn,
            limit=10,
            now=datetime(2026, 5, 8, 21, 59, 50),
        )
        msg = post_message(
            self.conn,
            th["thread_id"],
            "x",
            "retry me",
            visibility=VIS_DYADIC,
            now=datetime(2026, 5, 8, 22, 0, 0),
        )
        cur = self.conn.execute(
            """
            SELECT outbox_id
            FROM outbox_events
            WHERE source_row_table = ? AND source_row_id = ?
            LIMIT 1
            """,
            ("chat_messages", int(msg["message_id"])),
        )
        row = cur.fetchone()
        assert row is not None
        outbox_id = int(row["outbox_id"])

        with mock.patch("chat_system.outbox_consumer._maybe_enqueue_agent_task_from_event", side_effect=RuntimeError("boom")):
            first = consume_chat_outbox_batch(
                self.conn,
                limit=10,
                now=datetime(2026, 5, 8, 22, 0, 5),
                retry_delay_seconds=60,
                max_attempts=2,
            )

        row = get_outbox_row(self.conn, outbox_id)
        assert row is not None
        self.assertEqual(first["retry_scheduled"], 1)
        self.assertEqual(first["failed"], 0)
        self.assertEqual(row["publish_status"], "retry_pending")
        self.assertEqual(int(row["publish_attempts"]), 1)
        self.assertEqual(len(list_pending_outbox(self.conn, limit=10, now=datetime(2026, 5, 8, 22, 0, 30))), 0)
        self.assertEqual(len(list_pending_outbox(self.conn, limit=10, now=datetime(2026, 5, 8, 22, 1, 6))), 1)

        with mock.patch("chat_system.outbox_consumer._maybe_enqueue_agent_task_from_event", side_effect=RuntimeError("boom")):
            second = consume_chat_outbox_batch(
                self.conn,
                limit=10,
                now=datetime(2026, 5, 8, 22, 1, 6),
                retry_delay_seconds=60,
                max_attempts=2,
            )

        row = get_outbox_row(self.conn, outbox_id)
        assert row is not None
        self.assertEqual(second["retry_scheduled"], 0)
        self.assertEqual(second["failed"], 1)
        self.assertEqual(row["publish_status"], "failed")
        self.assertEqual(int(row["publish_attempts"]), 2)
        self.assertIsNone(row["next_retry_at"])
        self.assertEqual(len(list_pending_outbox(self.conn, limit=10, now=datetime(2026, 5, 8, 22, 2, 10))), 0)

    def test_outbox_admin_can_summarize_and_requeue_failed_rows(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-oc-requeue",
            relation_key="roc-requeue",
            participant_a_id="x",
            participant_b_id="y",
        )
        consume_chat_outbox_batch(
            self.conn,
            limit=10,
            now=datetime(2026, 5, 8, 22, 9, 50),
        )
        msg = post_message(
            self.conn,
            th["thread_id"],
            "x",
            "requeue me",
            visibility=VIS_DYADIC,
            now=datetime(2026, 5, 8, 22, 10, 0),
        )
        cur = self.conn.execute(
            """
            SELECT outbox_id
            FROM outbox_events
            WHERE source_row_table = ? AND source_row_id = ?
            LIMIT 1
            """,
            ("chat_messages", int(msg["message_id"])),
        )
        row = cur.fetchone()
        assert row is not None
        outbox_id = int(row["outbox_id"])

        with mock.patch("chat_system.outbox_consumer._maybe_enqueue_agent_task_from_event", side_effect=RuntimeError("boom")):
            consume_chat_outbox_batch(
                self.conn,
                limit=10,
                now=datetime(2026, 5, 8, 22, 10, 5),
                retry_delay_seconds=60,
                max_attempts=1,
            )

        self.assertEqual(len(list_failed_outbox(self.conn, limit=10)), 1)
        summary = summarize_outbox(self.conn, now=datetime(2026, 5, 8, 22, 10, 6))
        self.assertEqual(summary["failed_rows"], 1)
        self.assertEqual(summary["pending_rows"], 0)
        self.assertEqual(summary["retry_pending_rows"], 0)

        changed = requeue_outbox_rows(self.conn, [outbox_id], reset_attempts=True)
        self.conn.commit()
        self.assertEqual(changed, 1)
        row = get_outbox_row(self.conn, outbox_id)
        assert row is not None
        self.assertEqual(row["publish_status"], "pending")
        self.assertEqual(int(row["publish_attempts"]), 0)
        self.assertEqual(len(list_failed_outbox(self.conn, limit=10)), 0)
        self.assertEqual(len(list_pending_outbox(self.conn, limit=10, now=datetime(2026, 5, 8, 22, 10, 7))), 1)

    def test_outbox_claim_recovery_requeues_stale_processing_rows(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-oc-processing",
            relation_key="roc-processing",
            participant_a_id="x",
            participant_b_id="y",
        )
        msg = post_message(
            self.conn,
            th["thread_id"],
            "x",
            "stale claim",
            visibility=VIS_DYADIC,
            now=datetime(2026, 5, 8, 22, 10, 30),
        )
        cur = self.conn.execute(
            """
            SELECT outbox_id
            FROM outbox_events
            WHERE source_row_table = ? AND source_row_id = ?
            LIMIT 1
            """,
            ("chat_messages", int(msg["message_id"])),
        )
        row = cur.fetchone()
        assert row is not None
        outbox_id = int(row["outbox_id"])

        claimed = claim_pending_outbox_batch(
            self.conn,
            limit=10,
            claim_token="token-stale",
            worker_name="worker-a",
            now=datetime(2026, 5, 8, 22, 10, 31),
            claim_timeout_seconds=30,
            stale_retry_delay_seconds=60,
            max_attempts=3,
        )
        self.assertEqual(claimed["stale_recovered"], 0)
        claimed_ids = {int(item["outbox_id"]) for item in claimed["rows"]}
        self.assertIn(outbox_id, claimed_ids)
        self.assertGreaterEqual(len(claimed["rows"]), 1)
        self.assertGreaterEqual(len(list_processing_outbox(self.conn, limit=10)), 1)
        row = get_outbox_row(self.conn, outbox_id)
        assert row is not None
        self.assertEqual(row["publish_status"], "processing")
        self.assertEqual(row["processing_token"], "token-stale")
        self.assertEqual(len(list_pending_outbox(self.conn, limit=10, now=datetime(2026, 5, 8, 22, 10, 31))), 0)

        recovered = recover_stale_outbox_claims(
            self.conn,
            now=datetime(2026, 5, 8, 22, 11, 5),
            claim_timeout_seconds=30,
            retry_delay_seconds=60,
            max_attempts=3,
        )
        self.conn.commit()
        self.assertGreaterEqual(recovered, 1)
        row = get_outbox_row(self.conn, outbox_id)
        assert row is not None
        self.assertEqual(row["publish_status"], "retry_pending")
        self.assertEqual(int(row["publish_attempts"]), 1)
        self.assertIsNone(row["processing_token"])
        self.assertEqual(len(list_processing_outbox(self.conn, limit=10)), 0)
        pending_ids = {
            int(item["outbox_id"])
            for item in list_pending_outbox(
                self.conn,
                limit=10,
                now=datetime(2026, 5, 8, 22, 12, 6),
            )
        }
        self.assertIn(outbox_id, pending_ids)

    def test_outbox_worker_uses_env_config_and_reports_summary(self):
        with mock.patch.dict(
            os.environ,
            {
                "HER_CHAT_OUTBOX_BATCH_LIMIT": "25",
                "HER_CHAT_OUTBOX_MAX_BATCHES": "2",
                "HER_CHAT_OUTBOX_RETRY_DELAY_SECONDS": "90",
                "HER_CHAT_OUTBOX_RETRY_BACKOFF_MULTIPLIER": "3",
                "HER_CHAT_OUTBOX_RETRY_MAX_DELAY_SECONDS": "900",
                "HER_CHAT_OUTBOX_MAX_ATTEMPTS": "4",
                "HER_CHAT_OUTBOX_CLAIM_TIMEOUT_SECONDS": "180",
                "HER_CHAT_OUTBOX_POLL_INTERVAL_SECONDS": "7",
                "HER_CHAT_OUTBOX_MAX_IDLE_POLLS": "5",
                "HER_CHAT_OUTBOX_WORKER_NAME": "env-worker",
            },
            clear=False,
        ):
            config = resolve_outbox_consume_config()

        self.assertEqual(
            config,
            {
                "limit": 25,
                "max_batches": 2,
                "retry_delay_seconds": 90,
                "retry_backoff_multiplier": 3,
                "retry_max_delay_seconds": 900,
                "max_attempts": 4,
                "claim_timeout_seconds": 180,
                "poll_interval_seconds": 7,
                "max_idle_polls": 5,
                "worker_name": "env-worker",
            },
        )
        result = run_chat_outbox_worker(
            self.conn,
            limit=5,
            max_batches=2,
            retry_delay_seconds=30,
            retry_backoff_multiplier=2,
            retry_max_delay_seconds=120,
            max_attempts=2,
            claim_timeout_seconds=45,
            worker_name="manual-worker",
            now=datetime(2026, 5, 8, 22, 11, 0),
        )
        self.assertEqual(result["config"]["limit"], 5)
        self.assertEqual(result["config"]["retry_delay_seconds"], 30)
        self.assertEqual(result["config"]["retry_backoff_multiplier"], 2)
        self.assertEqual(result["config"]["retry_max_delay_seconds"], 120)
        self.assertEqual(result["config"]["max_attempts"], 2)
        self.assertEqual(result["config"]["claim_timeout_seconds"], 45)
        self.assertEqual(result["config"]["max_batches"], 2)
        self.assertEqual(result["config"]["worker_name"], "manual-worker")
        self.assertIn("summary_before", result)
        self.assertIn("summary_after", result)
        self.assertIn("totals", result)

    def test_outbox_worker_serve_polls_until_idle(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-oc-serve",
            relation_key="roc-serve",
            participant_a_id="x",
            participant_b_id="y",
        )
        post_message(
            self.conn,
            th["thread_id"],
            "x",
            "serve worker",
            visibility=VIS_DYADIC,
            now=datetime(2026, 5, 8, 22, 12, 0),
        )
        state = {"now": datetime(2026, 5, 8, 22, 12, 1)}

        def clock_fn():
            return state["now"]

        def sleep_fn(seconds: int) -> None:
            state["now"] = state["now"] + timedelta(seconds=seconds)

        result = serve_chat_outbox_worker(
            self.conn,
            limit=10,
            max_batches_per_cycle=1,
            retry_delay_seconds=30,
            retry_backoff_multiplier=2,
            retry_max_delay_seconds=120,
            max_attempts=3,
            claim_timeout_seconds=60,
            poll_interval_seconds=5,
            max_idle_polls=2,
            worker_name="loop-worker",
            clock_fn=clock_fn,
            sleep_fn=sleep_fn,
        )

        self.assertEqual(result["worker_name"], "loop-worker")
        self.assertEqual(result["stopped_reason"], "idle")
        self.assertEqual(result["poll_interval_seconds"], 5)
        self.assertEqual(result["max_idle_polls"], 2)
        self.assertGreaterEqual(result["cycles_run"], 2)
        self.assertGreaterEqual(result["totals"]["marked_published"], 1)
        self.assertEqual(len(list_pending_outbox(self.conn, limit=10, now=state["now"])), 0)

    def test_live_video_verification_provider_defaults_to_local_oss_when_env_missing(self):
        previous = os.environ.pop("HER_VERIFICATION_PROVIDER", None)
        try:
            self.assertEqual(verification_module._machine_review_provider_name(), "local_oss")
        finally:
            if previous is not None:
                os.environ["HER_VERIFICATION_PROVIDER"] = previous

    def test_maintenance_refreshes_summary(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-sum",
            relation_key="rsum",
            participant_a_id="sa",
            participant_b_id="sb",
        )
        post_message(self.conn, th["thread_id"], "sa", "hello summary line", visibility=VIS_DYADIC)
        run_chat_maintenance(self.conn, persona_limit=0, flush_outbox=False)
        s = get_thread_summary(self.conn, th["thread_id"])
        self.assertIsNotNone(s)
        assert s is not None
        self.assertIn("hello summary line", s["summary_text"])

    def test_submit_member_report_creates_risk_case_and_links_reports(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-risk-report",
            relation_key="risk-report",
            participant_a_id="user-a",
            participant_b_id="user-b",
        )
        msg = post_message(self.conn, th["thread_id"], "user-b", "我们可以先聊聊", visibility=VIS_DYADIC)
        out = submit_member_report(
            self.conn,
            th["thread_id"],
            "user-a",
            "profile_mismatch",
            reason_text="资料和聊天里说法对不上",
            message_id=int(msg["message_id"]),
            now=datetime(2026, 5, 5, 9, 0, 0),
        )

        self.assertEqual(out["report"]["report_type"], "profile_mismatch")
        self.assertEqual(out["report"]["reported_user_id"], "user-b")
        self.assertEqual(out["risk_case"]["thread_id"], th["thread_id"])
        self.assertEqual(out["risk_case"]["report_count"], 1)
        self.assertEqual(out["risk_case"]["recommended_action"], "warn")

        reports = list_member_reports(self.conn, risk_case_id=out["risk_case"]["risk_case_id"])
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["risk_case_id"], out["risk_case"]["risk_case_id"])

    def test_auto_keyword_signal_can_be_reviewed_into_chat_restriction(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-risk-auto",
            relation_key="risk-auto",
            participant_a_id="user-a",
            participant_b_id="user-b",
        )
        risky = post_message(
            self.conn,
            th["thread_id"],
            "user-b",
            "先加微信，我带你投资，收益稳，转账后马上进群",
            visibility=VIS_DYADIC,
            now=datetime(2026, 5, 5, 10, 0, 0),
        )

        reports = list_member_reports(self.conn, thread_id=th["thread_id"])
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["report_source"], "system_rule")
        self.assertEqual(reports[0]["message_id"], risky["message_id"])
        self.assertIn("investment", reports[0]["signal_codes"])
        self.assertIn("money_transfer", reports[0]["signal_codes"])

        risk_cases = list_risk_cases(self.conn, thread_id=th["thread_id"])
        self.assertEqual(len(risk_cases), 1)
        self.assertEqual(risk_cases[0]["recommended_action"], "limit_chat")
        reviewed = review_risk_case(
            self.conn,
            risk_cases[0]["risk_case_id"],
            "moderator-1",
            status="action_applied",
            applied_action="limit_chat",
            resolution_note="命中投资+转账，先限制继续发言",
            now=datetime(2026, 5, 5, 10, 5, 0),
        )
        self.assertEqual(reviewed["status"], "action_applied")
        self.assertEqual(reviewed["applied_action"], "limit_chat")
        fetched = get_risk_case(self.conn, reviewed["risk_case_id"])
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["resolver_id"], "moderator-1")

        with self.assertRaisesRegex(ValueError, "restricted by risk action"):
            post_message(
                self.conn,
                th["thread_id"],
                "user-b",
                "继续聊一下投资细节",
                visibility=VIS_DYADIC,
                now=datetime(2026, 5, 5, 10, 6, 0),
            )

    def test_behavior_signal_records_repeated_opening_and_high_frequency_outreach(self):
        thread_ids = []
        for idx in range(3):
            th = get_or_create_thread(
                self.conn,
                case_id=f"case-behavior-{idx}",
                relation_key=f"risk-behavior-{idx}",
                participant_a_id=f"user-{idx}",
                participant_b_id="spammer",
            )
            thread_ids.append(th["thread_id"])
            post_message(
                self.conn,
                th["thread_id"],
                "spammer",
                "你好呀，我们加微信聊更方便",
                visibility=VIS_DYADIC,
                now=datetime(2026, 5, 5, 11, idx * 5, 0),
            )

        reports = list_member_reports(self.conn, thread_id=thread_ids[-1])
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["report_source"], "system_rule")
        self.assertIn("off_platform", reports[0]["signal_codes"])
        self.assertIn("repeated_opening", reports[0]["signal_codes"])
        self.assertIn("high_frequency_outreach", reports[0]["signal_codes"])

        signals = list_risk_signals(self.conn, subject_user_id="spammer")
        signal_codes = [item["signal_code"] for item in signals]
        self.assertIn("repeated_opening", signal_codes)
        self.assertIn("high_frequency_outreach", signal_codes)

    def test_fraud_network_can_link_shared_entities_and_apply_global_freeze(self):
        source_dsn = "mysql://root@127.0.0.1:3307/her_graph?table=profiles"
        suspects = [
            ("suspect-a", 9101, "203.0.113.11"),
            ("suspect-b", 9102, "203.0.113.12"),
            ("suspect-c", 9103, "203.0.113.13"),
        ]
        shared_metadata = {
            "risk_observation": {
                "device_fingerprint": "device-cluster-001",
                "contact_handles": ["wechat:ringcenter01"],
                "avatar_fingerprint": "avatar-same-001",
                "registration_path": "ios_invite",
                "user_agent": "Her/1.0 (iPhone; iOS 18.1)",
            }
        }

        for idx, (suspect_user_id, profile_id, client_ip) in enumerate(suspects):
            metadata = {
                "participant_profiles": {
                    suspect_user_id: {
                        "profile_id": profile_id,
                        "source_dsn": source_dsn,
                        "source_table_name": "profiles",
                    }
                }
            }
            thread = get_or_create_thread(
                self.conn,
                case_id=f"case-fraud-graph-{idx}",
                relation_key=f"fraud-graph-{idx}",
                participant_a_id=f"victim-{idx}",
                participant_b_id=suspect_user_id,
                metadata=metadata,
                now=datetime(2026, 5, 5, 14, idx, 0),
            )
            message_metadata = {
                **shared_metadata,
                "risk_observation": {
                    **shared_metadata["risk_observation"],
                    "client_ip": client_ip,
                },
            }
            post_message(
                self.conn,
                thread["thread_id"],
                suspect_user_id,
                "加微信 ringcenter01，我带你做投资，收益稳，先转一笔就能进群",
                visibility=VIS_DYADIC,
                metadata=message_metadata,
                now=datetime(2026, 5, 5, 14, idx * 3 + 1, 0),
            )

        overview = evaluate_fraud_network(
            self.conn,
            "suspect-a",
            source_dsn=source_dsn,
            source_table_name="profiles",
            profile_id=9101,
            now=datetime(2026, 5, 5, 14, 20, 0),
        )
        profile = overview["network_profile"]
        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertEqual(profile["review_status"], "action_applied")
        self.assertEqual(profile["applied_action"], "freeze")
        self.assertEqual(profile["connected_subject_count"], 2)
        self.assertIn("shared_device_fingerprint", profile["signal_codes"])
        self.assertIn("shared_external_contact", profile["signal_codes"])
        self.assertGreaterEqual(int(profile["graph_risk_score"]), 160)

        linked_users = [item["linked_user_id"] for item in overview["account_links"]]
        self.assertEqual(linked_users, ["suspect-b", "suspect-c"])

        fetched_profile = get_fraud_network_profile(self.conn, "suspect-a")
        self.assertIsNotNone(fetched_profile)
        assert fetched_profile is not None
        self.assertEqual(fetched_profile["applied_action"], "freeze")

        high_risk_profiles = list_fraud_network_profiles(self.conn, minimum_score=100, limit=10)
        self.assertGreaterEqual(len(high_risk_profiles), 3)

        playback = build_fraud_network_overview(self.conn, "suspect-a")
        self.assertEqual(playback["moderation_state"]["applied_action"], "freeze")

        restricted_thread = get_or_create_thread(
            self.conn,
            case_id="case-fraud-graph-retry",
            relation_key="fraud-graph-retry",
            participant_a_id="victim-retry",
            participant_b_id="suspect-a",
            metadata={
                "participant_profiles": {
                    "suspect-a": {
                        "profile_id": 9101,
                        "source_dsn": source_dsn,
                        "source_table_name": "profiles",
                    }
                }
            },
            now=datetime(2026, 5, 5, 14, 25, 0),
        )
        with self.assertRaisesRegex(ValueError, "restricted by risk action: freeze"):
            post_message(
                self.conn,
                restricted_thread["thread_id"],
                "suspect-a",
                "继续平台内聊聊吧",
                visibility=VIS_DYADIC,
                now=datetime(2026, 5, 5, 14, 26, 0),
            )

    def test_income_mismatch_can_recommend_require_verification(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-income-review",
            relation_key="risk-income-review",
            participant_a_id="user-a",
            participant_b_id="user-b",
        )
        out = submit_member_report(
            self.conn,
            th["thread_id"],
            "user-a",
            "income_mismatch",
            reason_text="收入说法和实际情况明显对不上",
            now=datetime(2026, 5, 5, 12, 0, 0),
        )
        self.assertEqual(out["risk_case"]["recommended_action"], "require_verification")
        reviewed = review_risk_case(
            self.conn,
            out["risk_case"]["risk_case_id"],
            "moderator-2",
            status="action_applied",
            applied_action="require_verification",
            resolution_note="要求补充收入和职业证明",
            now=datetime(2026, 5, 5, 12, 5, 0),
        )
        self.assertEqual(reviewed["applied_action"], "require_verification")

    def test_suspected_fake_photo_report_has_photo_specific_signal(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-photo-risk",
            relation_key="risk-photo-review",
            participant_a_id="user-a",
            participant_b_id="user-b",
        )
        out = submit_member_report(
            self.conn,
            th["thread_id"],
            "user-a",
            "suspected_fake_photo",
            reason_text="怀疑照片不是本人，线下见面差异很大",
            evidence={"photo_gap": "looks_like_different_person"},
            now=datetime(2026, 5, 5, 12, 30, 0),
        )
        self.assertIn("suspected_fake_photo", out["report"]["signal_codes"])
        self.assertEqual(out["risk_case"]["recommended_action"], "require_verification")

    def test_meeting_feedback_can_generate_reports_and_thread_risk_overview(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-meeting-feedback",
            relation_key="risk-meeting-feedback",
            participant_a_id="reviewer",
            participant_b_id="candidate",
        )
        out = submit_meeting_feedback(
            self.conn,
            th["thread_id"],
            "reviewer",
            photo_match_status="mismatch",
            profile_consistency_status="mismatch",
            notes="真人和照片差异比较大，职业描述也有明显出入",
            now=datetime(2026, 5, 5, 13, 0, 0),
        )
        self.assertEqual(out["feedback"]["counterpart_user_id"], "candidate")
        self.assertEqual(len(out["generated_reports"]), 2)
        report_types = {item["report_type"] for item in out["generated_reports"]}
        self.assertEqual(report_types, {"photo_mismatch", "profile_mismatch"})

        feedback_rows = list_meeting_feedback(self.conn, thread_id=th["thread_id"])
        self.assertEqual(len(feedback_rows), 1)
        overview = build_thread_risk_overview(self.conn, th["thread_id"], "reviewer")
        self.assertEqual(overview["counterpart_user_id"], "candidate")
        self.assertIn("资料一致性风险", "".join(overview["caution_messages"]))

    def test_photo_review_request_can_be_created_from_risk_case_and_completed(self):
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `photo_verification_level` VARCHAR(32),
                  `live_video_verified` TINYINT(1),
                  `updated_at` DATETIME
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                INSERT INTO `profiles` (`id`, `photo_verification_level`, `live_video_verified`, `updated_at`)
                VALUES (1101, 'uploaded', 0, '2026-05-05 13:50:00')
                """
            )
        self.conn.commit()

        th = get_or_create_thread(
            self.conn,
            case_id="case-photo-request",
            relation_key="risk-photo-request",
            participant_a_id="reviewer-a",
            participant_b_id="candidate-a",
            metadata={
                "participant_profiles": {
                    "candidate-a": {
                        "profile_id": 1101,
                        "source_dsn": DEFAULT_CHAT_TEST_MYSQL_DSN,
                        "source_table_name": "profiles",
                    }
                }
            },
        )
        report = submit_member_report(
            self.conn,
            th["thread_id"],
            "reviewer-a",
            "suspected_fake_photo",
            reason_text="感觉照片不像同一个人",
            now=datetime(2026, 5, 5, 14, 0, 0),
        )
        risk_case_id = report["risk_case"]["risk_case_id"]
        review_risk_case(
            self.conn,
            risk_case_id,
            "moderator-photo",
            status="action_applied",
            applied_action="require_verification",
            resolution_note="请先补录真人活体视频",
            now=datetime(2026, 5, 5, 14, 5, 0),
        )

        requests = list_photo_review_requests(self.conn, user_id="candidate-a")
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request["status"], "awaiting_submission")
        self.assertEqual(request["photo_review_task"]["linked_risk_case_ids"], [risk_case_id])
        self.assertEqual(request["notifications"][0]["notification_type"], "photo_review_requested")

        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                first = submit_live_video_verification(
                    self.conn,
                    user_id="candidate-a",
                    submission_id=request["submission_id"],
                    profile_id=1101,
                    source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles",
                    video_base64=base64.b64encode(b"photo-request-first").decode("ascii"),
                    file_name="first-photo-request.mp4",
                    content_type="video/mp4",
                    metadata={
                        "machine_review_inputs": {
                            "liveness_score": 45,
                            "face_match_score": 86,
                            "challenge_score": 35,
                        }
                    },
                    now=datetime(2026, 5, 5, 14, 10, 0),
                )
                approved = resubmit_live_video_verification(
                    self.conn,
                    request["submission_id"],
                    user_id="candidate-a",
                    video_base64=base64.b64encode(b"photo-request-second").decode("ascii"),
                    file_name="second-photo-request.mp4",
                    content_type="video/mp4",
                    challenge_phrase="请重新补录一次",
                    metadata={
                        "machine_review_inputs": {
                            "liveness_score": 96,
                            "face_match_score": 93,
                            "challenge_score": 91,
                        }
                    },
                    now=datetime(2026, 5, 5, 14, 20, 0),
                )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(first["submission_id"], request["submission_id"])
        self.assertEqual(first["status"], "resubmission_required")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["profile_sync"]["status"], "synced")
        notification_types = [item["notification_type"] for item in approved["notifications"]]
        self.assertIn("photo_review_requested", notification_types)
        self.assertIn("photo_review_resubmission_required", notification_types)
        self.assertIn("photo_review_approved", notification_types)

        notification_rows = list_verification_notifications(self.conn, submission_id=request["submission_id"])
        self.assertEqual(
            {item["notification_type"] for item in notification_rows},
            {
                "photo_review_requested",
                "photo_review_resubmission_required",
                "photo_review_approved",
            },
        )

    def test_photo_review_request_can_be_frozen_after_risk_escalation(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-photo-freeze",
            relation_key="risk-photo-freeze",
            participant_a_id="reviewer-b",
            participant_b_id="candidate-b",
        )
        report = submit_member_report(
            self.conn,
            th["thread_id"],
            "reviewer-b",
            "photo_heavily_edited",
            reason_text="怀疑修图太重",
            now=datetime(2026, 5, 5, 15, 0, 0),
        )
        risk_case_id = report["risk_case"]["risk_case_id"]
        review_risk_case(
            self.conn,
            risk_case_id,
            "moderator-b",
            status="action_applied",
            applied_action="require_verification",
            resolution_note="先补录真人视频",
            now=datetime(2026, 5, 5, 15, 10, 0),
        )
        request = list_photo_review_requests(self.conn, user_id="candidate-b")[0]
        self.assertEqual(request["status"], "awaiting_submission")

        review_risk_case(
            self.conn,
            risk_case_id,
            "moderator-c",
            status="action_applied",
            applied_action="freeze",
            resolution_note="风险升级，先冻结处理",
            now=datetime(2026, 5, 5, 15, 20, 0),
        )

        frozen = get_verification_submission(self.conn, request["submission_id"])
        assert frozen is not None
        self.assertEqual(frozen["status"], "frozen")
        notification_types = {item["notification_type"] for item in frozen["notifications"]}
        self.assertIn("photo_review_requested", notification_types)
        self.assertIn("photo_review_frozen", notification_types)

    def test_live_video_verification_can_submit_review_and_sync_profile(self):
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `photo_verification_level` VARCHAR(32),
                  `live_video_verified` TINYINT(1),
                  `updated_at` DATETIME
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                INSERT INTO `profiles` (`id`, `photo_verification_level`, `live_video_verified`, `updated_at`)
                VALUES (1001, 'uploaded', 0, '2026-05-05 09:00:00')
                """
            )
        self.conn.commit()

        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                submission = submit_live_video_verification(
                    self.conn,
                    user_id="user-v1",
                    profile_id=1001,
                    source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles",
                    video_base64=base64.b64encode(b"fake-mp4-binary").decode("ascii"),
                    file_name="selfie.mp4",
                    content_type="video/mp4",
                    challenge_phrase="今天是周一",
                    metadata={"device": "ios"},
                    now=datetime(2026, 5, 5, 9, 30, 0),
                )
                self.assertEqual(submission["status"], "under_review")
                self.assertEqual(submission["recommended_decision"], "manual_review")
                self.assertEqual(submission["recommended_next_step"], "manual_review")
                self.assertEqual(submission["verification_provider"], "local_oss")
                self.assertFalse(submission["auto_review_applied"])
                self.assertEqual(len(submission["assets"]), 1)
                stored_file = pathlib.Path(temp_dir) / submission["assets"][0]["storage_key"]
                self.assertTrue(stored_file.exists())

                reviewed = review_live_video_verification(
                    self.conn,
                    submission["submission_id"],
                    "moderator-1",
                    decision="approve",
                    review_note="视频人物和资料一致，允许通过",
                    liveness_result="pass",
                    face_match_result="pass",
                    profile_consistency_result="pass",
                    now=datetime(2026, 5, 5, 9, 40, 0),
                )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(reviewed["status"], "approved")
        self.assertEqual(reviewed["latest_sync_status"], "synced")
        self.assertEqual(reviewed["profile_sync"]["status"], "synced")
        self.assertEqual(len(reviewed["reviews"]), 1)

        fetched = get_verification_submission(self.conn, submission["submission_id"])
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["status"], "approved")

        listed = list_verification_submissions(self.conn, user_id="user-v1")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["submission_id"], submission["submission_id"])

        row = self.conn.execute(
            "SELECT * FROM profiles WHERE id = ? LIMIT 1",
            (1001,),
        ).fetchone()
        self.assertEqual(row["photo_verification_level"], "live_video_verified")
        self.assertEqual(int(row["live_video_verified"]), 1)

    def test_live_video_verification_can_auto_approve_with_strong_machine_review(self):
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `photo_verification_level` VARCHAR(32),
                  `live_video_verified` TINYINT(1),
                  `updated_at` DATETIME
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                INSERT INTO `profiles` (`id`, `photo_verification_level`, `live_video_verified`, `updated_at`)
                VALUES (1002, 'uploaded', 0, '2026-05-05 10:50:00')
                """
            )
        self.conn.commit()

        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                submission = submit_live_video_verification(
                    self.conn,
                    user_id="user-v2",
                    profile_id=1002,
                    source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles",
                    video_base64=base64.b64encode(b"auto-approve-video").decode("ascii"),
                    file_name="auto-approve.mp4",
                    content_type="video/mp4",
                    challenge_phrase="请眨眼并读出今天日期",
                    metadata={
                        "device": "ios",
                        "machine_review_inputs": {
                            "liveness_score": 96,
                            "face_match_score": 94,
                            "challenge_score": 92,
                            "risk_flags": [],
                        },
                    },
                    now=datetime(2026, 5, 5, 11, 0, 0),
                )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(submission["status"], "approved")
        self.assertTrue(submission["auto_review_applied"])
        self.assertEqual(submission["review_decision"], "approve")
        self.assertEqual(submission["reviewer_id"], "system:auto_verification")
        self.assertEqual(submission["recommended_next_step"], "complete")
        self.assertEqual(submission["profile_sync"]["status"], "synced")
        self.assertEqual(len(submission["reviews"]), 1)
        self.assertEqual(submission["reviews"][0]["decision"], "approve")

        row = self.conn.execute(
            "SELECT * FROM profiles WHERE id = ? LIMIT 1",
            (1002,),
        ).fetchone()
        self.assertEqual(row["photo_verification_level"], "live_video_verified")
        self.assertEqual(int(row["live_video_verified"]), 1)

    def test_live_video_verification_can_request_resubmission_and_upload_again(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                submission = submit_live_video_verification(
                    self.conn,
                    user_id="user-v3",
                    video_base64=base64.b64encode(b"first-video").decode("ascii"),
                    file_name="first.mov",
                    content_type="video/quicktime",
                    metadata={
                        "machine_review_inputs": {
                            "liveness_score": 42,
                            "face_match_score": 88,
                            "challenge_score": 35,
                        }
                    },
                    now=datetime(2026, 5, 5, 10, 0, 0),
                )
                updated = resubmit_live_video_verification(
                    self.conn,
                    submission["submission_id"],
                    user_id="user-v3",
                    video_base64=base64.b64encode(b"second-video").decode("ascii"),
                    file_name="second.mov",
                    content_type="video/quicktime",
                    challenge_phrase="补录第二次",
                    metadata={
                        "retry": 1,
                        "machine_review_inputs": {
                            "liveness_score": 95,
                            "face_match_score": 91,
                            "challenge_score": 90,
                        },
                    },
                    now=datetime(2026, 5, 5, 10, 10, 0),
                )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(submission["status"], "resubmission_required")
        self.assertEqual(submission["review_decision"], "request_resubmission")
        self.assertEqual(submission["reviews"][0]["decision"], "request_resubmission")
        self.assertEqual(updated["status"], "approved")
        self.assertEqual(updated["resubmission_count"], 1)
        self.assertEqual(len(updated["assets"]), 2)
        self.assertEqual(len(updated["reviews"]), 2)
        self.assertEqual(updated["reviews"][-1]["decision"], "approve")
        self.assertEqual(updated["challenge_phrase"], "补录第二次")
        self.assertEqual(updated["machine_review"]["attempt"], 2)

    def test_live_video_verification_realtime_challenge_can_auto_approve(self):
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `photo_verification_level` VARCHAR(32),
                  `live_video_verified` TINYINT(1),
                  `updated_at` DATETIME
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                INSERT INTO `profiles` (`id`, `photo_verification_level`, `live_video_verified`, `updated_at`)
                VALUES (1003, 'uploaded', 0, '2026-05-05 11:50:00')
                """
            )
        self.conn.commit()

        challenge = create_live_video_verification_challenge(
            user_id="user-v5",
            profile_id=1003,
            challenge_actions=["blink", "open_mouth", "turn_left"],
            now=datetime(2026, 5, 5, 12, 0, 0),
        )
        self.assertEqual(challenge["required_actions"], ["blink", "open_mouth", "turn_left"])
        self.assertRegex(
            challenge["challenge_phrase"],
            r"^请依次完成：眨眼、张嘴、向左转头；并大声读出数字 \d{2}$",
        )
        self.assertRegex(challenge["spoken_code"], r"^\d{2}$")
        self.assertEqual(len(challenge["prompt_steps"]), 4)
        self.assertEqual(challenge["prompt_steps"][-1]["kind"], "spoken_code")

        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                submission = submit_live_video_verification(
                    self.conn,
                    user_id="user-v5",
                    profile_id=1003,
                    source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles",
                    video_base64=base64.b64encode(b"realtime-proof-video").decode("ascii"),
                    file_name="realtime-proof.mp4",
                    content_type="video/mp4",
                    challenge_token=challenge["challenge_token"],
                    metadata={
                        "action_result": {
                            "capture_mode": "realtime_challenge",
                            "completed_actions": ["blink", "open_mouth", "turn_left"],
                            "action_events": [
                                {"action": "blink", "step_index": 1, "detected_at_ms": 720, "score": 95},
                                {"action": "open_mouth", "step_index": 2, "detected_at_ms": 1510, "score": 93},
                                {"action": "turn_left", "step_index": 3, "detected_at_ms": 2290, "score": 90},
                            ],
                            "action_scores": {
                                "blink": 95,
                                "open_mouth": 93,
                                "turn_left": 90,
                            },
                            "face_count_max": 1,
                            "challenge_phrase_rendered": True,
                            "spoken_prompt_rendered": True,
                            "spoken_prompt_display_ms": 1900,
                            "audio_recorded": True,
                            "recording_duration_ms": 4200,
                            "video_recorded": True,
                        },
                        "machine_review_inputs": {
                            "face_match_score": 94,
                        },
                        "speech_challenge_result": {
                            "provider": "unit_test_asr",
                            "transcript_text": challenge["spoken_code"],
                            "transcript_confidence": 96,
                            "speech_started_at_ms": 2500,
                            "speech_ended_at_ms": 3280,
                            "audio_video_sync_score": 84,
                        },
                    },
                    now=datetime(2026, 5, 5, 12, 1, 0),
                )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(submission["status"], "approved")
        self.assertRegex(
            submission["challenge_phrase"],
            r"^请依次完成：眨眼、张嘴、向左转头；并大声读出数字 \d{2}$",
        )
        self.assertEqual(submission["review_decision"], "approve")
        self.assertEqual(submission["recommended_next_step"], "complete")
        self.assertEqual(submission["machine_review"]["capture_mode"], "realtime_challenge")
        self.assertEqual(submission["machine_review"]["required_actions"], ["blink", "open_mouth", "turn_left"])
        self.assertEqual(submission["machine_review"]["speech_result"], "pass")
        self.assertTrue(submission["machine_review"]["spoken_code_match"])
        self.assertEqual(
            submission["metadata"]["action_challenge"]["spoken_code"],
            challenge["spoken_code"],
        )
        self.assertEqual(submission["profile_sync"]["status"], "synced")

    def test_live_video_verification_realtime_challenge_rejects_expired_token(self):
        challenge = create_live_video_verification_challenge(
            user_id="user-v6",
            challenge_actions=["blink", "turn_right"],
            now=datetime(2026, 5, 5, 12, 0, 0),
        )
        with self.assertRaisesRegex(ValueError, "expired"):
            submit_live_video_verification(
                self.conn,
                user_id="user-v6",
                video_base64=base64.b64encode(b"expired-realtime-video").decode("ascii"),
                file_name="expired.mp4",
                content_type="video/mp4",
                challenge_token=challenge["challenge_token"],
                metadata={
                    "action_result": {
                        "capture_mode": "realtime_challenge",
                        "completed_actions": ["blink", "turn_right"],
                    }
                },
                now=datetime(2026, 5, 5, 12, 20, 0),
            )

    def test_live_video_verification_realtime_challenge_rejects_wrong_order(self):
        challenge = create_live_video_verification_challenge(
            user_id="user-v7",
            challenge_actions=["open_mouth", "blink", "turn_left"],
            now=datetime(2026, 5, 5, 12, 0, 0),
        )
        with self.assertRaisesRegex(ValueError, "does not follow challenge order"):
            submit_live_video_verification(
                self.conn,
                user_id="user-v7",
                video_base64=base64.b64encode(b"wrong-order-video").decode("ascii"),
                file_name="wrong-order.mp4",
                content_type="video/mp4",
                challenge_token=challenge["challenge_token"],
                metadata={
                    "action_result": {
                        "capture_mode": "realtime_challenge",
                        "completed_actions": ["blink", "open_mouth", "turn_left"],
                        "action_events": [
                            {"action": "blink", "step_index": 1, "detected_at_ms": 600, "score": 96},
                            {"action": "open_mouth", "step_index": 2, "detected_at_ms": 1340, "score": 95},
                            {"action": "turn_left", "step_index": 3, "detected_at_ms": 2100, "score": 92},
                        ],
                        "action_scores": {
                            "blink": 96,
                            "open_mouth": 95,
                            "turn_left": 92,
                        },
                        "challenge_phrase_rendered": True,
                        "spoken_prompt_rendered": True,
                        "audio_recorded": True,
                        "video_recorded": True,
                    }
                },
                now=datetime(2026, 5, 5, 12, 1, 0),
            )

    def test_live_video_verification_realtime_challenge_requests_resubmission_when_spoken_code_mismatches(self):
        challenge = create_live_video_verification_challenge(
            user_id="user-v8",
            challenge_actions=["blink", "open_mouth", "turn_left"],
            now=datetime(2026, 5, 5, 12, 0, 0),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                submission = submit_live_video_verification(
                    self.conn,
                    user_id="user-v8",
                    video_base64=base64.b64encode(b"spoken-code-mismatch-video").decode("ascii"),
                    file_name="spoken-mismatch.mp4",
                    content_type="video/mp4",
                    challenge_token=challenge["challenge_token"],
                    metadata={
                        "action_result": {
                            "capture_mode": "realtime_challenge",
                            "completed_actions": ["blink", "open_mouth", "turn_left"],
                            "action_events": [
                                {"action": "blink", "step_index": 1, "detected_at_ms": 700, "score": 95},
                                {"action": "open_mouth", "step_index": 2, "detected_at_ms": 1500, "score": 94},
                                {"action": "turn_left", "step_index": 3, "detected_at_ms": 2250, "score": 92},
                            ],
                            "action_scores": {
                                "blink": 95,
                                "open_mouth": 94,
                                "turn_left": 92,
                            },
                            "face_count_max": 1,
                            "challenge_phrase_rendered": True,
                            "spoken_prompt_rendered": True,
                            "spoken_prompt_display_ms": 2100,
                            "audio_recorded": True,
                            "recording_duration_ms": 4500,
                            "video_recorded": True,
                        },
                        "speech_challenge_result": {
                            "provider": "unit_test_asr",
                            "transcript_text": "12",
                            "transcript_confidence": 97,
                            "speech_started_at_ms": 2520,
                            "speech_ended_at_ms": 3270,
                            "audio_video_sync_score": 83,
                        },
                        "machine_review_inputs": {
                            "face_match_score": 92,
                            "liveness_score": 90,
                        },
                    },
                    now=datetime(2026, 5, 5, 12, 1, 0),
                )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(submission["status"], "resubmission_required")
        self.assertEqual(submission["recommended_decision"], "request_resubmission")
        self.assertEqual(submission["recommended_next_step"], "retry_live_video")
        self.assertEqual(submission["machine_review"]["speech_result"], "fail")
        self.assertFalse(submission["machine_review"]["spoken_code_match"])
        self.assertIn("spoken_code_mismatch", submission["machine_review"]["risk_flags"])

    def test_live_video_verification_rejects_non_local_provider_env_values(self):
        previous = os.environ.get("HER_VERIFICATION_PROVIDER")
        try:
            os.environ["HER_VERIFICATION_PROVIDER"] = "mock"
            with self.assertRaisesRegex(ValueError, "only supports local_oss"):
                verification_module._machine_review_provider_name()
            os.environ["HER_VERIFICATION_PROVIDER"] = "reported"
            with self.assertRaisesRegex(ValueError, "only supports local_oss"):
                verification_module._machine_review_provider_name()
        finally:
            if previous is None:
                os.environ["HER_VERIFICATION_PROVIDER"] = "local_oss"
            else:
                os.environ["HER_VERIFICATION_PROVIDER"] = previous

    def test_decode_video_bytes_accepts_data_url_with_codec_list(self):
        payload = "data:video/webm;codecs=vp9,opus;base64,QUJD"
        video_bytes, inferred_content_type = verification_module._decode_video_bytes(payload)
        self.assertEqual(video_bytes, b"ABC")
        self.assertEqual(inferred_content_type, "video/webm")

    def test_local_live_video_keeps_anti_spoof_result_when_whisper_bootstrap_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = pathlib.Path(temp_dir) / "demo.mp4"
            video_path.write_bytes(b"demo-video")
            anti_spoof_result = {
                "liveness_score": 96,
                "spoofing_risk_score": 4,
                "replay_attack_score": 9,
                "screen_risk_score": 7,
                "motion_score": 64,
                "face_presence_score": 100,
                "sampled_frame_count": 7,
                "valid_face_frame_count": 7,
                "detected_face_count_max": 1,
                "average_detection_confidence": 97,
                "risk_flags": [],
            }
            with mock.patch.object(
                live_video_local_module,
                "_inspect_media_file",
                return_value={"has_audio_track": True, "duration_ms": 4200},
            ), mock.patch.object(
                live_video_local_module,
                "_analyze_silent_face_video",
                return_value=anti_spoof_result,
            ), mock.patch.object(
                live_video_local_module,
                "_transcribe_video_audio",
                side_effect=LocalEntryNotFoundError("whisper download timeout"),
            ):
                out = live_video_local_module.analyze_local_live_video(video_path, spoken_code="37")

        self.assertEqual(out["provider"], "local_oss")
        self.assertEqual(out["provider_version"], "silent-face+faster-whisper-v1")
        self.assertEqual(out["liveness_score"], 96)
        self.assertEqual(out["face_presence_score"], 100)
        self.assertEqual(out["speech_challenge_result"]["provider"], "faster_whisper")
        self.assertEqual(out["speech_challenge_result"]["analysis_status"], "unavailable")
        self.assertEqual(out["speech_challenge_result"]["error_type"], "LocalEntryNotFoundError")
        self.assertIn("speech_analysis_unavailable", out["risk_flags"])

    def test_analyze_local_live_video_uses_same_person_result_for_face_match_score(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = pathlib.Path(temp_dir) / "demo.mp4"
            video_path.write_bytes(b"demo-video")
            anti_spoof_result = {
                "liveness_score": 96,
                "spoofing_risk_score": 4,
                "replay_attack_score": 9,
                "screen_risk_score": 7,
                "motion_score": 64,
                "face_presence_score": 100,
                "sampled_frame_count": 7,
                "valid_face_frame_count": 7,
                "detected_face_count_max": 1,
                "average_detection_confidence": 97,
                "risk_flags": [],
            }
            same_person_result = {
                "analysis_status": "ok",
                "face_match_score": 91,
                "same_person_score": 91,
                "reference_face_source_count": 2,
                "reference_face_count": 2,
                "matched_frame_count": 3,
                "best_similarity": 0.62,
                "risk_flags": [],
            }
            speech_result = {
                "provider": "faster_whisper",
                "transcript_text": "37",
                "transcript_segments": [],
                "transcript_confidence": 95,
                "speech_started_at_ms": 2480,
                "speech_ended_at_ms": 3290,
                "audio_duration_ms": 3290,
            }
            with mock.patch.object(
                live_video_local_module,
                "_inspect_media_file",
                return_value={"has_audio_track": True, "duration_ms": 4200},
            ), mock.patch.object(
                live_video_local_module,
                "_analyze_silent_face_video",
                return_value=anti_spoof_result,
            ), mock.patch.object(
                live_video_local_module,
                "_safe_analyze_same_person_faces",
                return_value=same_person_result,
            ) as same_person_mock, mock.patch.object(
                live_video_local_module,
                "_safe_transcribe_video_audio",
                return_value=speech_result,
            ):
                out = live_video_local_module.analyze_local_live_video(
                    video_path,
                    spoken_code="37",
                    reference_image_sources=["https://img.her.local/a.jpg", "https://img.her.local/b.jpg"],
                )

        self.assertEqual(out["face_match_score"], 91)
        self.assertEqual(out["same_person_score"], 91)
        self.assertEqual(out["reference_face_source_count"], 2)
        self.assertEqual(out["matched_face_frame_count"], 3)
        self.assertEqual(out["best_face_similarity"], 0.62)
        self.assertEqual(same_person_mock.call_args.kwargs["reference_image_sources"], ["https://img.her.local/a.jpg", "https://img.her.local/b.jpg"])

    def test_analyze_local_live_video_merges_deepfake_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = pathlib.Path(temp_dir) / "demo.mp4"
            video_path.write_bytes(b"demo-video")
            anti_spoof_result = {
                "liveness_score": 95,
                "spoofing_risk_score": 5,
                "replay_attack_score": 8,
                "screen_risk_score": 7,
                "motion_score": 68,
                "face_presence_score": 100,
                "sampled_frame_count": 7,
                "valid_face_frame_count": 7,
                "detected_face_count_max": 1,
                "average_detection_confidence": 96,
                "risk_flags": [],
            }
            same_person_result = {
                "analysis_status": "ok",
                "face_match_score": 90,
                "same_person_score": 90,
                "reference_face_source_count": 1,
                "reference_face_count": 1,
                "matched_frame_count": 3,
                "best_similarity": 0.61,
                "risk_flags": [],
            }
            deepfake_result = {
                "analysis_status": "ok",
                "deepfake_risk_score": 88,
                "deepfake_temporal_score": 92,
                "deepfake_artifact_score": 79,
                "deepfake_sampled_frame_count": 10,
                "deepfake_face_frame_count": 8,
                "risk_flags": ["deepfake_risk"],
            }
            with mock.patch.object(
                live_video_local_module,
                "_inspect_media_file",
                return_value={"has_audio_track": False, "duration_ms": 4200},
            ), mock.patch.object(
                live_video_local_module,
                "_analyze_silent_face_video",
                return_value=anti_spoof_result,
            ), mock.patch.object(
                live_video_local_module,
                "_safe_analyze_same_person_faces",
                return_value=same_person_result,
            ), mock.patch.object(
                live_video_local_module,
                "_safe_analyze_deepfake_video",
                return_value=deepfake_result,
            ):
                out = live_video_local_module.analyze_local_live_video(video_path)

        self.assertEqual(out["deepfake_risk_score"], 88)
        self.assertEqual(out["deepfake_analysis_status"], "ok")
        self.assertEqual(out["deepfake_temporal_score"], 92)
        self.assertEqual(out["deepfake_artifact_score"], 79)
        self.assertIn("deepfake_risk", out["risk_flags"])

    def test_analyze_deepfake_face_crops_scores_manipulated_sequence_higher(self):
        natural = live_video_local_module._analyze_deepfake_face_crops(
            self._build_synthetic_face_sequence(manipulated=False)
        )
        manipulated = live_video_local_module._analyze_deepfake_face_crops(
            self._build_synthetic_face_sequence(manipulated=True)
        )

        self.assertEqual(natural["analysis_status"], "ok")
        self.assertEqual(manipulated["analysis_status"], "ok")
        self.assertLess(natural["deepfake_risk_score"], 55)
        self.assertGreaterEqual(manipulated["deepfake_risk_score"], 60)
        self.assertGreater(manipulated["deepfake_temporal_score"], natural["deepfake_temporal_score"])
        self.assertGreater(manipulated["deepfake_artifact_score"], natural["deepfake_artifact_score"])
        self.assertTrue(manipulated["risk_flags"])

    def test_analyze_photo_edit_face_sets_scores_edited_reference_higher(self):
        live_metrics = [
            live_video_local_module._photo_edit_crop_metrics(
                crop,
                face_aspect_ratio=68.0 / 82.0,
            )
            for crop in self._build_photo_edit_face_crops(edited=False, count=5)
        ]
        natural_reference_metrics = [
            live_video_local_module._photo_edit_crop_metrics(
                crop,
                face_aspect_ratio=68.0 / 82.0,
            )
            for crop in self._build_photo_edit_face_crops(edited=False, count=3)
        ]
        edited_reference_metrics = [
            live_video_local_module._photo_edit_crop_metrics(
                crop,
                face_aspect_ratio=58.0 / 82.0,
            )
            for crop in self._build_photo_edit_face_crops(edited=True, count=3)
        ]

        natural = live_video_local_module._analyze_photo_edit_face_sets(
            natural_reference_metrics,
            live_metrics,
            reference_face_source_count=3,
        )
        edited = live_video_local_module._analyze_photo_edit_face_sets(
            edited_reference_metrics,
            live_metrics,
            reference_face_source_count=3,
        )

        self.assertEqual(natural["analysis_status"], "ok")
        self.assertEqual(edited["analysis_status"], "ok")
        self.assertLess(natural["photo_edit_risk_score"], 55)
        self.assertGreaterEqual(edited["photo_edit_risk_score"], 60)
        self.assertGreater(edited["skin_smoothing_risk_score"], natural["skin_smoothing_risk_score"])
        self.assertGreater(edited["beauty_filter_risk_score"], natural["beauty_filter_risk_score"])
        self.assertTrue(edited["risk_flags"])

    def test_analyze_local_live_video_merges_photo_edit_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = pathlib.Path(temp_dir) / "demo.mp4"
            video_path.write_bytes(b"demo-video")
            anti_spoof_result = {
                "liveness_score": 94,
                "spoofing_risk_score": 6,
                "replay_attack_score": 8,
                "screen_risk_score": 7,
                "motion_score": 70,
                "face_presence_score": 100,
                "sampled_frame_count": 7,
                "valid_face_frame_count": 7,
                "detected_face_count_max": 1,
                "average_detection_confidence": 96,
                "risk_flags": [],
            }
            same_person_result = {
                "analysis_status": "ok",
                "face_match_score": 90,
                "same_person_score": 90,
                "reference_face_source_count": 2,
                "reference_face_count": 2,
                "matched_frame_count": 3,
                "best_similarity": 0.62,
                "risk_flags": [],
            }
            photo_edit_result = {
                "analysis_status": "ok",
                "photo_edit_risk_score": 87,
                "skin_smoothing_risk_score": 92,
                "beauty_filter_risk_score": 81,
                "face_shape_delta_score": 48,
                "photo_edit_reference_face_count": 2,
                "photo_edit_live_face_frame_count": 5,
                "photo_edit_reference_source_count": 2,
                "photo_edit_edited_reference_count": 2,
                "risk_flags": ["photo_heavily_edited"],
            }
            with mock.patch.object(
                live_video_local_module,
                "_inspect_media_file",
                return_value={"has_audio_track": False, "duration_ms": 4200},
            ), mock.patch.object(
                live_video_local_module,
                "_analyze_silent_face_video",
                return_value=anti_spoof_result,
            ), mock.patch.object(
                live_video_local_module,
                "_safe_analyze_same_person_faces",
                return_value=same_person_result,
            ), mock.patch.object(
                live_video_local_module,
                "_safe_analyze_deepfake_video",
                return_value=live_video_local_module._deepfake_unavailable_result(
                    "not_needed",
                    sampled_frame_count=0,
                    face_frame_count=0,
                ),
            ), mock.patch.object(
                live_video_local_module,
                "_safe_analyze_photo_edit_risk",
                return_value=photo_edit_result,
            ):
                out = live_video_local_module.analyze_local_live_video(
                    video_path,
                    reference_image_sources=["https://img.her.local/a.jpg", "https://img.her.local/b.jpg"],
                )

        self.assertEqual(out["photo_edit_risk_score"], 87)
        self.assertEqual(out["photo_edit_analysis_status"], "ok")
        self.assertEqual(out["skin_smoothing_risk_score"], 92)
        self.assertEqual(out["beauty_filter_risk_score"], 81)
        self.assertEqual(out["photo_edit_edited_reference_count"], 2)
        self.assertIn("photo_heavily_edited", out["risk_flags"])

    def test_analyze_same_person_photo_entries_flags_mixed_identity(self):
        photo_entries = [
            {"face_count": 1, "embedding": np.asarray([1.0, 0.0, 0.0], dtype=np.float32)},
            {"face_count": 1, "embedding": np.asarray([0.98, 0.02, 0.0], dtype=np.float32)},
            {"face_count": 1, "embedding": np.asarray([0.0, 1.0, 0.0], dtype=np.float32)},
        ]

        class _DummyFaceEngine:
            @staticmethod
            def match(feature_a: np.ndarray, feature_b: np.ndarray) -> float:
                norm_a = float(np.linalg.norm(feature_a))
                norm_b = float(np.linalg.norm(feature_b))
                if norm_a <= 0 or norm_b <= 0:
                    return 0.0
                return float(np.dot(feature_a, feature_b) / (norm_a * norm_b))

        with mock.patch.object(
            live_video_local_module,
            "_face_match_engine",
            return_value=_DummyFaceEngine(),
        ):
            out = live_video_local_module._analyze_same_person_photo_entries(photo_entries)

        self.assertEqual(out["analysis_status"], "ok")
        self.assertLess(out["same_person_score"], 45)
        self.assertIn("mixed_identity_photos", out["risk_flags"])

    def test_analyze_profile_photo_duplicates_flags_cross_profile_duplicate(self):
        out = live_video_local_module._analyze_profile_photo_duplicates(
            [
                {"source": "a.jpg", "image_hash": int("10101010", 2)},
                {"source": "b.jpg", "image_hash": int("11110000", 2)},
            ],
            comparison_entries=[
                {"source": "other-1.jpg", "image_hash": int("10101010", 2)},
                {"source": "other-2.jpg", "image_hash": int("00001111", 2)},
            ],
        )

        self.assertEqual(out["analysis_status"], "ok")
        self.assertGreaterEqual(out["stolen_media_risk_score"], 85)
        self.assertGreaterEqual(out["cross_profile_duplicate_count"], 1)
        self.assertIn("stolen_media_risk", out["risk_flags"])

    def test_transcribe_video_audio_extracts_wav_before_whisper(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = pathlib.Path(temp_dir) / "demo.webm"
            audio_path = pathlib.Path(temp_dir) / "demo.wav"
            video_path.write_bytes(b"demo-video")
            audio_path.write_bytes(b"demo-audio")
            with mock.patch.object(
                live_video_local_module,
                "_extract_audio_track_to_wav",
                return_value=audio_path,
            ) as extract_mock, mock.patch.object(
                live_video_local_module,
                "_transcribe_audio_with_whisper_worker",
                return_value={
                    "provider": "faster_whisper",
                    "model_name": "tiny",
                    "transcript_text": "37",
                    "transcript_segments": [
                        {
                            "text": "37",
                            "start_ms": 2480,
                            "end_ms": 3290,
                            "confidence": 95,
                        }
                    ],
                    "transcript_confidence": 95,
                    "speech_started_at_ms": 2480,
                    "speech_ended_at_ms": 3290,
                    "audio_duration_ms": 3290,
                },
            ) as worker_mock, mock.patch.object(
                live_video_local_module,
                "_safe_compute_audio_video_sync_result",
                return_value={
                    "audio_video_sync_score": 84,
                    "audio_video_sync_status": "ok",
                    "audio_video_sync_offset_ms": 40,
                    "audio_video_sync_correlation": 0.74,
                    "audio_video_sync_overlap_ratio": 0.81,
                },
            ) as sync_mock:
                out = live_video_local_module._transcribe_video_audio(
                    video_path,
                    media_info={"has_audio_track": True, "duration_ms": 4200},
                )

        self.assertEqual(extract_mock.call_args.args[0], video_path)
        self.assertEqual(worker_mock.call_args.args[0], audio_path)
        self.assertEqual(worker_mock.call_args.kwargs["language"], None)
        self.assertEqual(sync_mock.call_args.args[0], video_path)
        self.assertEqual(sync_mock.call_args.kwargs["audio_path"], audio_path)
        self.assertEqual(out["provider"], "faster_whisper")
        self.assertEqual(out["transcript_text"], "37")
        self.assertEqual(out["audio_video_sync_score"], 84)
        self.assertEqual(out["audio_video_sync_status"], "ok")
        self.assertFalse(audio_path.exists())

    def test_score_audio_video_sync_curves_rewards_aligned_motion(self):
        audio_points = [
            {"timestamp_ms": 2000, "value": 0.05},
            {"timestamp_ms": 2040, "value": 0.16},
            {"timestamp_ms": 2080, "value": 0.35},
            {"timestamp_ms": 2120, "value": 0.72},
            {"timestamp_ms": 2160, "value": 0.96},
            {"timestamp_ms": 2200, "value": 0.84},
            {"timestamp_ms": 2240, "value": 0.48},
            {"timestamp_ms": 2280, "value": 0.19},
            {"timestamp_ms": 2320, "value": 0.07},
        ]
        aligned_visual_points = [
            {"timestamp_ms": 2010, "value": 0.02},
            {"timestamp_ms": 2090, "value": 0.22},
            {"timestamp_ms": 2140, "value": 0.61},
            {"timestamp_ms": 2190, "value": 0.88},
            {"timestamp_ms": 2240, "value": 0.43},
            {"timestamp_ms": 2290, "value": 0.12},
        ]
        shifted_visual_points = [
            {"timestamp_ms": 2450, "value": 0.02},
            {"timestamp_ms": 2530, "value": 0.22},
            {"timestamp_ms": 2580, "value": 0.61},
            {"timestamp_ms": 2630, "value": 0.88},
            {"timestamp_ms": 2680, "value": 0.43},
            {"timestamp_ms": 2730, "value": 0.12},
        ]

        aligned = live_video_local_module._score_audio_video_sync_curves(
            audio_points,
            aligned_visual_points,
            speech_start_ms=2040,
            speech_end_ms=2280,
        )
        shifted = live_video_local_module._score_audio_video_sync_curves(
            audio_points,
            shifted_visual_points,
            speech_start_ms=2040,
            speech_end_ms=2280,
        )

        self.assertGreaterEqual(aligned["audio_video_sync_score"], 75)
        self.assertLessEqual(shifted["audio_video_sync_score"], 55)

    def test_evaluate_speech_challenge_requires_audio_video_sync_for_pass(self):
        metadata = {
            "action_challenge": {
                "spoken_code": "37",
            },
            "action_result": {
                "audio_recorded": True,
                "spoken_prompt_rendered": True,
                "spoken_prompt_display_ms": 2200,
                "action_events": [
                    {"action": "blink", "detected_at_ms": 700},
                    {"action": "open_mouth", "detected_at_ms": 1450},
                    {"action": "turn_left", "detected_at_ms": 2200},
                ],
            },
            "speech_challenge_result": {
                "provider": "faster_whisper",
                "transcript_text": "37",
                "transcript_confidence": 95,
                "speech_started_at_ms": 2480,
                "speech_ended_at_ms": 3290,
            },
        }

        out = verification_module._evaluate_speech_challenge(metadata)

        self.assertEqual(out["speech_result"], "unclear")
        self.assertIn("audio_video_sync_unverified", out["risk_flags"])

    def test_transcribe_audio_with_whisper_worker_invokes_module_process(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = pathlib.Path(temp_dir) / "demo.wav"
            audio_path.write_bytes(b"demo-audio")
            completed = types.SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "provider": "faster_whisper",
                        "model_name": "tiny",
                        "transcript_text": "37",
                        "transcript_segments": [],
                        "transcript_confidence": 95,
                        "speech_started_at_ms": 2480,
                        "speech_ended_at_ms": 3290,
                        "audio_duration_ms": 3290,
                    }
                ),
                stderr="",
            )
            with mock.patch.object(live_video_local_module.subprocess, "run", return_value=completed) as run_mock:
                out = live_video_local_module._transcribe_audio_with_whisper_worker(audio_path, language="zh")

        self.assertEqual(out["transcript_text"], "37")
        command = run_mock.call_args.args[0]
        self.assertEqual(command[1:3], ["-m", "chat_system.live_video_whisper_worker"])
        self.assertEqual(command[3], str(audio_path))
        self.assertEqual(run_mock.call_args.kwargs["env"]["HER_VERIFICATION_WHISPER_LANGUAGE"], "zh")

    def test_transcribe_audio_with_whisper_worker_raises_on_worker_failure(self):
        completed = types.SimpleNamespace(returncode=139, stdout="", stderr="Segmentation fault")
        with mock.patch.object(live_video_local_module.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "Segmentation fault"):
                live_video_local_module._transcribe_audio_with_whisper_worker(pathlib.Path("/tmp/demo.wav"), language=None)

    def test_load_profile_reference_face_sources_prefers_primary_photo_rows(self):
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS `profile_photos`")
            cursor.execute("DROP TABLE IF EXISTS `profiles`")
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `avatar_url` VARCHAR(255)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE `profile_photos` (
                  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `photo_url` VARCHAR(255) NOT NULL,
                  `is_primary` TINYINT(1) DEFAULT 0,
                  `sort_order` INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                "INSERT INTO `profiles` (`id`, `avatar_url`) VALUES (1001, 'https://img.her.local/avatar-fallback.jpg')"
            )
            cursor.executemany(
                "INSERT INTO `profile_photos` (`profile_id`, `photo_url`, `is_primary`, `sort_order`) VALUES (%s, %s, %s, %s)",
                [
                    (1001, "https://img.her.local/gallery-2.jpg", 0, 2),
                    (1001, "https://img.her.local/primary.jpg", 1, 9),
                    (1001, "https://img.her.local/gallery-1.jpg", 0, 1),
                ],
            )
        self.conn.commit()

        out = verification_module._load_profile_reference_face_sources(
            profile_id=1001,
            source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles&photos_table=profile_photos",
            source_table_name=None,
        )

        self.assertEqual(
            out,
            [
                "https://img.her.local/primary.jpg",
                "https://img.her.local/gallery-1.jpg",
                "https://img.her.local/gallery-2.jpg",
            ],
        )

    def test_load_profile_reference_face_sources_falls_back_to_avatar(self):
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS `profile_photos`")
            cursor.execute("DROP TABLE IF EXISTS `profiles`")
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `avatar_url` VARCHAR(255)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                "INSERT INTO `profiles` (`id`, `avatar_url`) VALUES (1002, 'https://img.her.local/avatar-only.jpg')"
            )
        self.conn.commit()

        out = verification_module._load_profile_reference_face_sources(
            profile_id=1002,
            source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles&photos_table=profile_photos",
            source_table_name=None,
        )

        self.assertEqual(out, ["https://img.her.local/avatar-only.jpg"])

    def test_evaluate_profile_consistency_creates_photo_review_request_from_photo_authenticity_risk(self):
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS `profile_photos`")
            cursor.execute("DROP TABLE IF EXISTS `profiles`")
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `avatar_url` VARCHAR(255),
                  `education` VARCHAR(64),
                  `job` VARCHAR(255),
                  `income_range` VARCHAR(64),
                  `city` VARCHAR(64),
                  `job_change_count_30d` INT,
                  `income_change_count_30d` INT,
                  `city_change_count_30d` INT,
                  `profile_review_status` VARCHAR(32),
                  `job_verification_status` VARCHAR(32),
                  `income_verification_status` VARCHAR(32),
                  `education_verification_status` VARCHAR(32)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE `profile_photos` (
                  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `photo_url` VARCHAR(255) NOT NULL,
                  `is_primary` TINYINT(1) DEFAULT 0,
                  `sort_order` INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.executemany(
                (
                    "INSERT INTO `profiles` "
                    "(`id`, `avatar_url`, `education`, `job`, `income_range`, `city`, "
                    "`job_change_count_30d`, `income_change_count_30d`, `city_change_count_30d`, "
                    "`profile_review_status`, `job_verification_status`, `income_verification_status`, `education_verification_status`) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                ),
                [
                    (3001, None, "本科", "产品经理", "30-50万/年", "上海", 0, 0, 0, "approved", "verified", "verified", "verified"),
                    (3002, None, "本科", "产品经理", "30-50万/年", "上海", 0, 0, 0, "approved", "verified", "verified", "verified"),
                ],
            )
            cursor.executemany(
                "INSERT INTO `profile_photos` (`profile_id`, `photo_url`, `is_primary`, `sort_order`) VALUES (%s, %s, %s, %s)",
                [
                    (3001, "/tmp/photo-a.jpg", 1, 0),
                    (3001, "/tmp/photo-b.jpg", 0, 1),
                    (3002, "/tmp/photo-c.jpg", 1, 0),
                ],
            )
        self.conn.commit()

        mocked_review = {
            "analysis_status": "ok",
            "photo_authenticity_score": 36,
            "same_person_score": 32,
            "same_person_pair_count": 1,
            "same_person_matched_pair_count": 0,
            "same_person_average_similarity": 0.24,
            "same_person_min_similarity": 0.24,
            "photo_edit_risk_score": 88,
            "photo_edit_analysis_status": "ok",
            "skin_smoothing_risk_score": 91,
            "beauty_filter_risk_score": 80,
            "face_shape_delta_score": 45,
            "edited_photo_count": 2,
            "deepfake_risk_score": 0,
            "deepfake_analysis_status": "ok",
            "deepfake_artifact_score": 0,
            "deepfake_consistency_score": 0,
            "stolen_media_risk_score": 86,
            "stolen_media_analysis_status": "ok",
            "duplicate_photo_count": 0,
            "cross_profile_duplicate_count": 1,
            "exact_cross_profile_duplicate_count": 1,
            "source_count": 2,
            "loaded_source_count": 2,
            "valid_face_photo_count": 2,
            "multiple_face_photo_count": 0,
            "comparison_source_count": 1,
            "risk_flags": ["mixed_identity_photos", "photo_heavily_edited", "stolen_media_risk"],
        }
        with mock.patch.object(
            live_video_local_module,
            "analyze_profile_photo_authenticity_detailed",
            return_value={
                "review": mocked_review,
                "photo_entries": [
                    {
                        "source": "/tmp/photo-a.jpg",
                        "face_count": 1,
                        "face_detection_score": 97,
                        "image_hash_hex": "aaaaaaaaaaaaaaaa",
                        "embedding_available": True,
                        "embedding_dim": 512,
                        "embedding_preview": [0.11, 0.22],
                        "photo_edit_metrics": {"skin_detail": 0.14, "feature_skin_gap": 1.28},
                        "deepfake_metrics": {"seam_strength": 0.81, "detail_ratio": 1.02},
                    },
                    {
                        "source": "/tmp/photo-b.jpg",
                        "face_count": 1,
                        "face_detection_score": 96,
                        "image_hash_hex": "bbbbbbbbbbbbbbbb",
                        "embedding_available": True,
                        "embedding_dim": 512,
                        "embedding_preview": [0.33, 0.44],
                        "photo_edit_metrics": {"skin_detail": 0.12, "feature_skin_gap": 1.35},
                        "deepfake_metrics": {"seam_strength": 0.77, "detail_ratio": 1.01},
                    },
                ],
                "comparison_entries": [
                    {
                        "source": "/tmp/photo-c.jpg",
                        "face_count": 1,
                        "face_detection_score": 95,
                        "image_hash_hex": "cccccccccccccccc",
                        "embedding_available": True,
                        "embedding_dim": 512,
                        "embedding_preview": [0.55, 0.66],
                        "photo_edit_metrics": {"skin_detail": 0.15, "feature_skin_gap": 1.21},
                        "deepfake_metrics": {"seam_strength": 0.73, "detail_ratio": 1.03},
                    }
                ],
            },
        ):
            out = evaluate_profile_consistency(
                self.conn,
                profile_id=3001,
                source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles&photos_table=profile_photos",
                subject_user_id="user-photo-3001",
                now=datetime(2026, 5, 13, 16, 0, 0),
            )

        self.assertIsNotNone(out["risk_case"])
        self.assertIsNotNone(out["photo_review_request"])
        rule_codes = {item["rule_code"] for item in out["rule_hits"]}
        self.assertIn("profile_photo_identity_mismatch", rule_codes)
        self.assertIn("profile_photo_stolen_media_risk", rule_codes)
        self.assertIn("profile_photo_heavily_edited", rule_codes)
        self.assertEqual(out["photo_authenticity_review"]["photo_authenticity_score"], 36)
        self.assertEqual(
            (out["risk_case"]["evidence_summary"] or {}).get("photo_authenticity_review", {}).get("photo_authenticity_score"),
            36,
        )
        self.assertEqual(
            (out["risk_case"]["evidence_summary"] or {}).get("photo_review_signal_codes"),
            ["photo_mismatch", "identity_mismatch", "suspected_fake_photo", "photo_heavily_edited"],
        )
        self.assertEqual(out["photo_review_request"]["status"], "awaiting_submission")
        self.assertEqual(len(list_photo_review_requests(self.conn, user_id="user-photo-3001")), 1)

    def test_evaluate_profile_consistency_persists_photo_risk_service_records(self):
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS `profile_photos`")
            cursor.execute("DROP TABLE IF EXISTS `profiles`")
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `avatar_url` VARCHAR(255),
                  `education` VARCHAR(64),
                  `job` VARCHAR(255),
                  `income_range` VARCHAR(64),
                  `city` VARCHAR(64),
                  `job_change_count_30d` INT,
                  `income_change_count_30d` INT,
                  `city_change_count_30d` INT,
                  `profile_review_status` VARCHAR(32),
                  `job_verification_status` VARCHAR(32),
                  `income_verification_status` VARCHAR(32),
                  `education_verification_status` VARCHAR(32)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE `profile_photos` (
                  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `photo_url` VARCHAR(255) NOT NULL,
                  `is_primary` TINYINT(1) DEFAULT 0,
                  `sort_order` INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.executemany(
                (
                    "INSERT INTO `profiles` "
                    "(`id`, `avatar_url`, `education`, `job`, `income_range`, `city`, "
                    "`job_change_count_30d`, `income_change_count_30d`, `city_change_count_30d`, "
                    "`profile_review_status`, `job_verification_status`, `income_verification_status`, `education_verification_status`) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                ),
                [
                    (3101, None, "本科", "产品经理", "30-50万/年", "上海", 0, 0, 0, "approved", "verified", "verified", "verified"),
                    (3102, None, "本科", "产品经理", "30-50万/年", "上海", 0, 0, 0, "approved", "verified", "verified", "verified"),
                ],
            )
            cursor.executemany(
                "INSERT INTO `profile_photos` (`profile_id`, `photo_url`, `is_primary`, `sort_order`) VALUES (%s, %s, %s, %s)",
                [
                    (3101, "/tmp/persist-a.jpg", 1, 0),
                    (3101, "/tmp/persist-b.jpg", 0, 1),
                    (3102, "/tmp/persist-c.jpg", 1, 0),
                ],
            )
        self.conn.commit()

        mocked_review = {
            "analysis_status": "ok",
            "photo_authenticity_score": 36,
            "same_person_score": 32,
            "same_person_pair_count": 1,
            "same_person_matched_pair_count": 0,
            "same_person_average_similarity": 0.24,
            "same_person_min_similarity": 0.24,
            "photo_edit_risk_score": 88,
            "photo_edit_analysis_status": "ok",
            "skin_smoothing_risk_score": 91,
            "beauty_filter_risk_score": 80,
            "face_shape_delta_score": 45,
            "edited_photo_count": 2,
            "deepfake_risk_score": 0,
            "deepfake_analysis_status": "ok",
            "deepfake_artifact_score": 0,
            "deepfake_consistency_score": 0,
            "stolen_media_risk_score": 86,
            "stolen_media_analysis_status": "ok",
            "duplicate_photo_count": 0,
            "cross_profile_duplicate_count": 1,
            "exact_cross_profile_duplicate_count": 1,
            "source_count": 2,
            "loaded_source_count": 2,
            "valid_face_photo_count": 2,
            "multiple_face_photo_count": 0,
            "comparison_source_count": 1,
            "risk_flags": ["mixed_identity_photos", "photo_heavily_edited", "stolen_media_risk"],
        }
        mocked_bundle = {
            "review": mocked_review,
            "photo_entries": [
                {
                    "source": "/tmp/persist-a.jpg",
                    "face_count": 1,
                    "face_detection_score": 97,
                    "image_hash_hex": "aaaaaaaaaaaaaaaa",
                    "embedding_available": True,
                    "embedding_dim": 512,
                    "embedding_preview": [0.11, 0.22],
                    "photo_edit_metrics": {"skin_detail": 0.14, "feature_skin_gap": 1.28},
                    "deepfake_metrics": {"seam_strength": 0.81, "detail_ratio": 1.02},
                },
                {
                    "source": "/tmp/persist-b.jpg",
                    "face_count": 1,
                    "face_detection_score": 96,
                    "image_hash_hex": "bbbbbbbbbbbbbbbb",
                    "embedding_available": True,
                    "embedding_dim": 512,
                    "embedding_preview": [0.33, 0.44],
                    "photo_edit_metrics": {"skin_detail": 0.12, "feature_skin_gap": 1.35},
                    "deepfake_metrics": {"seam_strength": 0.77, "detail_ratio": 1.01},
                },
            ],
            "comparison_entries": [
                {
                    "source": "/tmp/persist-c.jpg",
                    "face_count": 1,
                    "face_detection_score": 95,
                    "image_hash_hex": "cccccccccccccccc",
                    "embedding_available": True,
                    "embedding_dim": 512,
                    "embedding_preview": [0.55, 0.66],
                    "photo_edit_metrics": {"skin_detail": 0.15, "feature_skin_gap": 1.21},
                    "deepfake_metrics": {"seam_strength": 0.73, "detail_ratio": 1.03},
                }
            ],
        }
        with mock.patch.object(
            live_video_local_module,
            "analyze_profile_photo_authenticity_detailed",
            return_value=mocked_bundle,
        ):
            out = evaluate_profile_consistency(
                self.conn,
                profile_id=3101,
                source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles&photos_table=profile_photos",
                subject_user_id="user-photo-3101",
                now=datetime(2026, 5, 13, 16, 30, 0),
            )

        service = out["photo_risk_service"]
        self.assertIsNotNone(service)
        self.assertEqual(service["score_run"]["photo_authenticity_score"], 36)
        self.assertIsNotNone(service["review_queue_item"])
        self.assertEqual(service["review_queue_item"]["queue_status"], "open")

        stored_run = get_photo_risk_score_run(self.conn, service["score_run_id"])
        self.assertIsNotNone(stored_run)
        assert stored_run is not None
        self.assertEqual(stored_run["decision"]["recommended_action"], "limited_exposure")
        self.assertEqual(len(stored_run["assets"]), 3)
        asset_roles = {item["feature_snapshot"]["asset_role"] for item in stored_run["assets"]}
        self.assertEqual(asset_roles, {"subject_profile_photo", "comparison_profile_photo"})
        self.assertEqual(
            (out["risk_case"]["evidence_summary"] or {}).get("photo_risk_service", {}).get("score_run_id"),
            service["score_run_id"],
        )

        listed_runs = list_photo_risk_score_runs(self.conn, profile_id=3101)
        self.assertEqual(len(listed_runs), 1)
        self.assertEqual(listed_runs[0]["score_run_id"], service["score_run_id"])

        queue_items = list_photo_risk_review_queue(self.conn, statuses=["open"], profile_id=3101)
        self.assertEqual(len(queue_items), 1)
        self.assertEqual(queue_items[0]["profile_review_case_id"], out["risk_case"]["profile_review_case_id"])

    def test_evaluate_profile_consistency_persists_clear_photo_risk_run_without_case(self):
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS `profile_photos`")
            cursor.execute("DROP TABLE IF EXISTS `profiles`")
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `avatar_url` VARCHAR(255),
                  `education` VARCHAR(64),
                  `job` VARCHAR(255),
                  `income_range` VARCHAR(64),
                  `city` VARCHAR(64),
                  `job_change_count_30d` INT,
                  `income_change_count_30d` INT,
                  `city_change_count_30d` INT,
                  `profile_review_status` VARCHAR(32),
                  `job_verification_status` VARCHAR(32),
                  `income_verification_status` VARCHAR(32),
                  `education_verification_status` VARCHAR(32)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE `profile_photos` (
                  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `photo_url` VARCHAR(255) NOT NULL,
                  `is_primary` TINYINT(1) DEFAULT 0,
                  `sort_order` INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                (
                    "INSERT INTO `profiles` "
                    "(`id`, `avatar_url`, `education`, `job`, `income_range`, `city`, "
                    "`job_change_count_30d`, `income_change_count_30d`, `city_change_count_30d`, "
                    "`profile_review_status`, `job_verification_status`, `income_verification_status`, `education_verification_status`) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                ),
                (3201, None, "本科", "产品经理", "30-50万/年", "上海", 0, 0, 0, "approved", "verified", "verified", "verified"),
            )
            cursor.executemany(
                "INSERT INTO `profile_photos` (`profile_id`, `photo_url`, `is_primary`, `sort_order`) VALUES (%s, %s, %s, %s)",
                [
                    (3201, "/tmp/clear-a.jpg", 1, 0),
                    (3201, "/tmp/clear-b.jpg", 0, 1),
                ],
            )
        self.conn.commit()

        mocked_bundle = {
            "review": {
                "analysis_status": "ok",
                "photo_authenticity_score": 93,
                "same_person_score": 95,
                "same_person_pair_count": 1,
                "same_person_matched_pair_count": 1,
                "same_person_average_similarity": 0.71,
                "same_person_min_similarity": 0.71,
                "photo_edit_risk_score": 12,
                "photo_edit_analysis_status": "ok",
                "skin_smoothing_risk_score": 8,
                "beauty_filter_risk_score": 9,
                "face_shape_delta_score": 6,
                "edited_photo_count": 0,
                "deepfake_risk_score": 0,
                "deepfake_analysis_status": "ok",
                "deepfake_artifact_score": 0,
                "deepfake_consistency_score": 0,
                "stolen_media_risk_score": 0,
                "stolen_media_analysis_status": "ok",
                "duplicate_photo_count": 0,
                "cross_profile_duplicate_count": 0,
                "exact_cross_profile_duplicate_count": 0,
                "source_count": 2,
                "loaded_source_count": 2,
                "valid_face_photo_count": 2,
                "multiple_face_photo_count": 0,
                "comparison_source_count": 0,
                "risk_flags": [],
            },
            "photo_entries": [
                {
                    "source": "/tmp/clear-a.jpg",
                    "face_count": 1,
                    "face_detection_score": 98,
                    "image_hash_hex": "1111111111111111",
                    "embedding_available": True,
                    "embedding_dim": 512,
                    "embedding_preview": [0.01, 0.02],
                    "photo_edit_metrics": {"skin_detail": 0.33},
                    "deepfake_metrics": {"seam_strength": 0.14},
                },
                {
                    "source": "/tmp/clear-b.jpg",
                    "face_count": 1,
                    "face_detection_score": 97,
                    "image_hash_hex": "2222222222222222",
                    "embedding_available": True,
                    "embedding_dim": 512,
                    "embedding_preview": [0.03, 0.04],
                    "photo_edit_metrics": {"skin_detail": 0.32},
                    "deepfake_metrics": {"seam_strength": 0.13},
                },
            ],
            "comparison_entries": [],
        }
        with mock.patch.object(
            live_video_local_module,
            "analyze_profile_photo_authenticity_detailed",
            return_value=mocked_bundle,
        ):
            out = evaluate_profile_consistency(
                self.conn,
                profile_id=3201,
                source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles&photos_table=profile_photos",
                subject_user_id="user-photo-3201",
                now=datetime(2026, 5, 13, 16, 40, 0),
            )

        self.assertIsNone(out["risk_case"])
        self.assertIsNone(out["photo_review_request"])
        self.assertEqual(out["photo_risk_service"]["decision"]["recommended_action"], "none")
        self.assertEqual(len(list_photo_risk_score_runs(self.conn, profile_id=3201)), 1)
        self.assertEqual(list_photo_risk_review_queue(self.conn, profile_id=3201), [])

    def test_evaluate_profile_consistency_gracefully_degrades_without_local_photo_runtime(self):
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS `profile_photos`")
            cursor.execute("DROP TABLE IF EXISTS `profiles`")
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `avatar_url` VARCHAR(255),
                  `education` VARCHAR(64),
                  `job` VARCHAR(255),
                  `income_range` VARCHAR(64),
                  `city` VARCHAR(64),
                  `job_change_count_30d` INT,
                  `income_change_count_30d` INT,
                  `city_change_count_30d` INT,
                  `profile_review_status` VARCHAR(32),
                  `job_verification_status` VARCHAR(32),
                  `income_verification_status` VARCHAR(32),
                  `education_verification_status` VARCHAR(32)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE `profile_photos` (
                  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `photo_url` VARCHAR(255) NOT NULL,
                  `is_primary` TINYINT(1) DEFAULT 0,
                  `sort_order` INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                (
                    "INSERT INTO `profiles` "
                    "(`id`, `avatar_url`, `education`, `job`, `income_range`, `city`, "
                    "`job_change_count_30d`, `income_change_count_30d`, `city_change_count_30d`, "
                    "`profile_review_status`, `job_verification_status`, `income_verification_status`, `education_verification_status`) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                ),
                (3301, None, "本科", "行政助理", "120万+/年", "无锡", 2, 0, 0, "approved", "self_reported", "self_reported", "self_reported"),
            )
        self.conn.commit()

        with mock.patch.object(
            profile_reviews_module.importlib,
            "import_module",
            side_effect=ModuleNotFoundError("No module named 'av'"),
        ):
            out = evaluate_profile_consistency(
                self.conn,
                profile_id=3301,
                source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles&photos_table=profile_photos",
                subject_user_id="user-missing-runtime-3301",
                now=datetime(2026, 5, 13, 16, 45, 0),
            )

        self.assertIsNotNone(out["risk_case"])
        self.assertEqual(out["risk_case"]["recommended_action"], "limited_exposure")
        self.assertEqual(out["photo_authenticity_review"]["analysis_status"], "unavailable")
        self.assertEqual(out["photo_authenticity_review"]["analysis_reason"], "runtime_dependency_unavailable")
        self.assertEqual(out["photo_authenticity_review"]["error_type"], "ModuleNotFoundError")
        self.assertEqual(out["photo_authenticity_review"]["source_count"], 0)
        self.assertIsNone(out["photo_review_request"])
        rule_codes = {item["rule_code"] for item in out["rule_hits"]}
        self.assertIn("income_job_mismatch", rule_codes)
        self.assertIn("frequent_profile_changes", rule_codes)

    def test_review_profile_review_case_syncs_photo_risk_queue_status(self):
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS `profile_photos`")
            cursor.execute("DROP TABLE IF EXISTS `profiles`")
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `avatar_url` VARCHAR(255),
                  `education` VARCHAR(64),
                  `job` VARCHAR(255),
                  `income_range` VARCHAR(64),
                  `city` VARCHAR(64),
                  `job_change_count_30d` INT,
                  `income_change_count_30d` INT,
                  `city_change_count_30d` INT,
                  `profile_review_status` VARCHAR(32),
                  `job_verification_status` VARCHAR(32),
                  `income_verification_status` VARCHAR(32),
                  `education_verification_status` VARCHAR(32)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                CREATE TABLE `profile_photos` (
                  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
                  `profile_id` BIGINT NOT NULL,
                  `photo_url` VARCHAR(255) NOT NULL,
                  `is_primary` TINYINT(1) DEFAULT 0,
                  `sort_order` INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.executemany(
                (
                    "INSERT INTO `profiles` "
                    "(`id`, `avatar_url`, `education`, `job`, `income_range`, `city`, "
                    "`job_change_count_30d`, `income_change_count_30d`, `city_change_count_30d`, "
                    "`profile_review_status`, `job_verification_status`, `income_verification_status`, `education_verification_status`) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                ),
                [
                    (3301, None, "本科", "产品经理", "30-50万/年", "上海", 0, 0, 0, "approved", "verified", "verified", "verified"),
                    (3302, None, "本科", "产品经理", "30-50万/年", "上海", 0, 0, 0, "approved", "verified", "verified", "verified"),
                ],
            )
            cursor.executemany(
                "INSERT INTO `profile_photos` (`profile_id`, `photo_url`, `is_primary`, `sort_order`) VALUES (%s, %s, %s, %s)",
                [
                    (3301, "/tmp/queue-a.jpg", 1, 0),
                    (3301, "/tmp/queue-b.jpg", 0, 1),
                    (3302, "/tmp/queue-c.jpg", 1, 0),
                ],
            )
        self.conn.commit()

        mocked_bundle = {
            "review": {
                "analysis_status": "ok",
                "photo_authenticity_score": 38,
                "same_person_score": 35,
                "same_person_pair_count": 1,
                "same_person_matched_pair_count": 0,
                "same_person_average_similarity": 0.26,
                "same_person_min_similarity": 0.26,
                "photo_edit_risk_score": 72,
                "photo_edit_analysis_status": "ok",
                "skin_smoothing_risk_score": 70,
                "beauty_filter_risk_score": 68,
                "face_shape_delta_score": 42,
                "edited_photo_count": 1,
                "deepfake_risk_score": 0,
                "deepfake_analysis_status": "ok",
                "deepfake_artifact_score": 0,
                "deepfake_consistency_score": 0,
                "stolen_media_risk_score": 91,
                "stolen_media_analysis_status": "ok",
                "duplicate_photo_count": 0,
                "cross_profile_duplicate_count": 1,
                "exact_cross_profile_duplicate_count": 1,
                "source_count": 2,
                "loaded_source_count": 2,
                "valid_face_photo_count": 2,
                "multiple_face_photo_count": 0,
                "comparison_source_count": 1,
                "risk_flags": ["mixed_identity_photos", "stolen_media_risk"],
            },
            "photo_entries": [
                {"source": "/tmp/queue-a.jpg", "face_count": 1, "face_detection_score": 97, "image_hash_hex": "abcd", "embedding_available": True, "embedding_dim": 512, "embedding_preview": [0.1], "photo_edit_metrics": None, "deepfake_metrics": None},
                {"source": "/tmp/queue-b.jpg", "face_count": 1, "face_detection_score": 96, "image_hash_hex": "bcde", "embedding_available": True, "embedding_dim": 512, "embedding_preview": [0.2], "photo_edit_metrics": None, "deepfake_metrics": None},
            ],
            "comparison_entries": [
                {"source": "/tmp/queue-c.jpg", "face_count": 1, "face_detection_score": 95, "image_hash_hex": "cdef", "embedding_available": True, "embedding_dim": 512, "embedding_preview": [0.3], "photo_edit_metrics": None, "deepfake_metrics": None},
            ],
        }
        with mock.patch.object(
            live_video_local_module,
            "analyze_profile_photo_authenticity_detailed",
            return_value=mocked_bundle,
        ):
            out = evaluate_profile_consistency(
                self.conn,
                profile_id=3301,
                source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles&photos_table=profile_photos",
                subject_user_id="user-photo-3301",
                now=datetime(2026, 5, 13, 16, 50, 0),
            )

        resolved = review_profile_review_case(
            self.conn,
            out["risk_case"]["profile_review_case_id"],
            "moderator-photo-1",
            status="resolved",
            resolution_note="已人工确认并结案",
            now=datetime(2026, 5, 13, 16, 55, 0),
        )
        self.assertEqual(resolved["photo_risk_queue_sync"]["queue_status"], "resolved")
        queue_items = list_photo_risk_review_queue(self.conn, statuses=["resolved"], profile_id=3301)
        self.assertEqual(len(queue_items), 1)
        self.assertEqual(queue_items[0]["profile_review_case_id"], out["risk_case"]["profile_review_case_id"])

    def test_live_video_verification_keeps_browser_speech_result_when_backend_whisper_is_unavailable(self):
        challenge = create_live_video_verification_challenge(
            user_id="user-v-browser-fallback",
            challenge_actions=["blink", "open_mouth", "turn_left"],
            now=datetime(2026, 5, 5, 13, 0, 0),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                submission = submit_live_video_verification(
                    self.conn,
                    user_id="user-v-browser-fallback",
                    video_base64=base64.b64encode(b"browser-speech-fallback-video" * 128).decode("ascii"),
                    file_name="browser-fallback.mp4",
                    content_type="video/mp4",
                    challenge_token=challenge["challenge_token"],
                    metadata={
                        "local_provider_result": {
                            "provider": "local_oss",
                            "provider_version": "silent-face+faster-whisper-v1",
                            "liveness_score": 94,
                            "face_match_score": 88,
                            "same_person_score": 88,
                            "replay_attack_score": 8,
                            "screen_risk_score": 10,
                            "spoofing_risk_score": 6,
                            "deepfake_risk_score": 0,
                            "motion_score": 71,
                            "face_presence_score": 97,
                            "sampled_frame_count": 7,
                            "valid_face_frame_count": 7,
                            "detected_face_count_max": 1,
                            "has_audio_track": True,
                            "risk_flags": [],
                            "speech_challenge_result": {
                                "provider": "faster_whisper",
                                "analysis_status": "unavailable",
                                "error_type": "LocalEntryNotFoundError",
                                "error_message": "whisper bootstrap timeout",
                            },
                        },
                        "action_result": {
                            "capture_mode": "realtime_challenge",
                            "completed_actions": ["blink", "open_mouth", "turn_left"],
                            "action_events": [
                                {"action": "blink", "step_index": 1, "detected_at_ms": 720, "score": 95},
                                {"action": "open_mouth", "step_index": 2, "detected_at_ms": 1490, "score": 94},
                                {"action": "turn_left", "step_index": 3, "detected_at_ms": 2260, "score": 92},
                            ],
                            "action_scores": {
                                "blink": 95,
                                "open_mouth": 94,
                                "turn_left": 92,
                            },
                            "face_count_max": 1,
                            "challenge_phrase_rendered": True,
                            "spoken_prompt_rendered": True,
                            "spoken_prompt_display_ms": 2300,
                            "audio_recorded": True,
                            "recording_duration_ms": 4700,
                            "video_recorded": True,
                        },
                        "speech_challenge_result": {
                            "provider": "browser_speech_recognition",
                            "transcript_text": challenge["spoken_code"],
                            "transcript_confidence": 95,
                            "speech_started_at_ms": 2480,
                            "speech_ended_at_ms": 3290,
                            "audio_video_sync_score": 83,
                        },
                    },
                    now=datetime(2026, 5, 5, 13, 1, 0),
                )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(submission["status"], "approved")
        self.assertEqual(submission["machine_review"]["speech_provider"], "browser_speech_recognition")
        self.assertEqual(submission["machine_review"]["speech_result"], "pass")
        self.assertTrue(submission["machine_review"]["spoken_code_match"])
        self.assertEqual(submission["metadata"]["speech_challenge_result"]["provider"], "browser_speech_recognition")

    def test_live_video_verification_local_oss_provider_can_auto_approve_with_backend_asr(self):
        os.environ["HER_VERIFICATION_PROVIDER"] = "local_oss"
        with self.conn.driver_connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE `profiles` (
                  `id` BIGINT PRIMARY KEY,
                  `photo_verification_level` VARCHAR(32),
                  `live_video_verified` TINYINT(1),
                  `updated_at` DATETIME
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cursor.execute(
                """
                INSERT INTO `profiles` (`id`, `photo_verification_level`, `live_video_verified`, `updated_at`)
                VALUES (1004, 'uploaded', 0, '2026-05-05 12:50:00')
                """
            )
        self.conn.commit()

        challenge = create_live_video_verification_challenge(
            user_id="user-v10",
            profile_id=1004,
            challenge_actions=["blink", "open_mouth", "turn_left"],
            now=datetime(2026, 5, 5, 13, 0, 0),
        )
        local_provider_result = {
            "provider": "local_oss",
            "provider_version": "silent-face+faster-whisper-v1",
            "liveness_score": 93,
            "face_match_score": 89,
            "same_person_score": 89,
            "replay_attack_score": 8,
            "screen_risk_score": 12,
            "spoofing_risk_score": 6,
            "deepfake_risk_score": 0,
            "motion_score": 76,
            "face_presence_score": 98,
            "sampled_frame_count": 7,
            "valid_face_frame_count": 7,
            "detected_face_count_max": 1,
            "has_audio_track": True,
            "risk_flags": [],
            "speech_challenge_result": {
                "provider": "faster_whisper",
                "transcript_text": challenge["spoken_code"],
                "transcript_confidence": 95,
                "speech_started_at_ms": 2480,
                "speech_ended_at_ms": 3290,
                "audio_duration_ms": 3290,
                "audio_video_sync_score": 84,
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                local_provider_module = types.SimpleNamespace(
                    LOCAL_OSS_PROVIDER_VERSION="silent-face+faster-whisper-v1",
                    analyze_local_live_video=mock.Mock(return_value=local_provider_result),
                )
                with mock.patch.object(
                    verification_module,
                    "_live_video_local_module",
                    return_value=local_provider_module,
                ):
                    submission = submit_live_video_verification(
                        self.conn,
                        user_id="user-v10",
                        profile_id=1004,
                        source_dsn=f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles",
                        video_base64=base64.b64encode(b"local-oss-provider-video" * 128).decode("ascii"),
                        file_name="local-oss.mp4",
                        content_type="video/mp4",
                        challenge_token=challenge["challenge_token"],
                        metadata={
                            "action_result": {
                                "capture_mode": "realtime_challenge",
                                "completed_actions": ["blink", "open_mouth", "turn_left"],
                                "action_events": [
                                    {"action": "blink", "step_index": 1, "detected_at_ms": 720, "score": 95},
                                    {"action": "open_mouth", "step_index": 2, "detected_at_ms": 1490, "score": 94},
                                    {"action": "turn_left", "step_index": 3, "detected_at_ms": 2260, "score": 92},
                                ],
                                "action_scores": {
                                    "blink": 95,
                                    "open_mouth": 94,
                                    "turn_left": 92,
                                },
                                "face_count_max": 1,
                                "challenge_phrase_rendered": True,
                                "spoken_prompt_rendered": True,
                                "spoken_prompt_display_ms": 2300,
                                "audio_recorded": True,
                                "recording_duration_ms": 4700,
                                "video_recorded": True,
                            }
                        },
                        now=datetime(2026, 5, 5, 13, 1, 0),
                    )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(submission["status"], "approved")
        self.assertEqual(submission["verification_provider"], "local_oss")
        self.assertEqual(submission["machine_review"]["speech_provider"], "faster_whisper")
        self.assertEqual(submission["machine_review"]["speech_result"], "pass")
        self.assertTrue(submission["machine_review"]["spoken_code_match"])
        self.assertEqual(submission["metadata"]["speech_challenge_result"]["provider"], "faster_whisper")
        self.assertEqual(submission["profile_sync"]["status"], "synced")

    def test_live_video_verification_local_oss_provider_escalates_high_spoof_risk(self):
        os.environ["HER_VERIFICATION_PROVIDER"] = "local_oss"
        challenge = create_live_video_verification_challenge(
            user_id="user-v11",
            challenge_actions=["blink", "open_mouth", "turn_left"],
            now=datetime(2026, 5, 5, 13, 0, 0),
        )
        local_provider_result = {
            "provider": "local_oss",
            "provider_version": "silent-face+faster-whisper-v1",
            "liveness_score": 52,
            "face_match_score": 87,
            "same_person_score": 87,
            "replay_attack_score": 91,
            "screen_risk_score": 88,
            "spoofing_risk_score": 92,
            "deepfake_risk_score": 0,
            "motion_score": 72,
            "face_presence_score": 95,
            "sampled_frame_count": 7,
            "valid_face_frame_count": 6,
            "detected_face_count_max": 1,
            "has_audio_track": True,
            "risk_flags": [],
            "speech_challenge_result": {
                "provider": "faster_whisper",
                "transcript_text": challenge["spoken_code"],
                "transcript_confidence": 94,
                "speech_started_at_ms": 2520,
                "speech_ended_at_ms": 3340,
                "audio_duration_ms": 3340,
                "audio_video_sync_score": 82,
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                local_provider_module = types.SimpleNamespace(
                    LOCAL_OSS_PROVIDER_VERSION="silent-face+faster-whisper-v1",
                    analyze_local_live_video=mock.Mock(return_value=local_provider_result),
                )
                with mock.patch.object(
                    verification_module,
                    "_live_video_local_module",
                    return_value=local_provider_module,
                ):
                    submission = submit_live_video_verification(
                        self.conn,
                        user_id="user-v11",
                        video_base64=base64.b64encode(b"spoof-risk-video" * 128).decode("ascii"),
                        file_name="spoof-risk.mp4",
                        content_type="video/mp4",
                        challenge_token=challenge["challenge_token"],
                        metadata={
                            "action_result": {
                                "capture_mode": "realtime_challenge",
                                "completed_actions": ["blink", "open_mouth", "turn_left"],
                                "action_events": [
                                    {"action": "blink", "step_index": 1, "detected_at_ms": 710, "score": 95},
                                    {"action": "open_mouth", "step_index": 2, "detected_at_ms": 1480, "score": 94},
                                    {"action": "turn_left", "step_index": 3, "detected_at_ms": 2280, "score": 91},
                                ],
                                "action_scores": {
                                    "blink": 95,
                                    "open_mouth": 94,
                                    "turn_left": 91,
                                },
                                "face_count_max": 1,
                                "challenge_phrase_rendered": True,
                                "spoken_prompt_rendered": True,
                                "spoken_prompt_display_ms": 2200,
                                "audio_recorded": True,
                                "recording_duration_ms": 4600,
                                "video_recorded": True,
                            }
                        },
                        now=datetime(2026, 5, 5, 13, 1, 0),
                    )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(submission["status"], "under_review")
        self.assertIsNone(submission["review_decision"])
        self.assertEqual(submission["recommended_next_step"], "strong_identity")
        self.assertIn("replay_attack", submission["machine_review"]["risk_flags"])
        self.assertIn("spoofing_risk", submission["machine_review"]["risk_flags"])

    def test_live_video_verification_local_oss_provider_escalates_high_deepfake_risk(self):
        os.environ["HER_VERIFICATION_PROVIDER"] = "local_oss"
        challenge = create_live_video_verification_challenge(
            user_id="user-v12",
            challenge_actions=["blink", "open_mouth", "turn_left"],
            now=datetime(2026, 5, 5, 13, 0, 0),
        )
        local_provider_result = {
            "provider": "local_oss",
            "provider_version": "silent-face+faster-whisper-v1",
            "liveness_score": 91,
            "face_match_score": 88,
            "same_person_score": 88,
            "replay_attack_score": 9,
            "screen_risk_score": 11,
            "spoofing_risk_score": 8,
            "deepfake_risk_score": 91,
            "deepfake_analysis_status": "ok",
            "deepfake_temporal_score": 94,
            "deepfake_artifact_score": 86,
            "deepfake_sampled_frame_count": 10,
            "deepfake_face_frame_count": 8,
            "motion_score": 75,
            "face_presence_score": 96,
            "sampled_frame_count": 7,
            "valid_face_frame_count": 7,
            "detected_face_count_max": 1,
            "has_audio_track": True,
            "risk_flags": [],
            "speech_challenge_result": {
                "provider": "faster_whisper",
                "transcript_text": challenge["spoken_code"],
                "transcript_confidence": 95,
                "speech_started_at_ms": 2490,
                "speech_ended_at_ms": 3300,
                "audio_duration_ms": 3300,
                "audio_video_sync_score": 84,
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                local_provider_module = types.SimpleNamespace(
                    LOCAL_OSS_PROVIDER_VERSION="silent-face+faster-whisper-v1",
                    analyze_local_live_video=mock.Mock(return_value=local_provider_result),
                )
                with mock.patch.object(
                    verification_module,
                    "_live_video_local_module",
                    return_value=local_provider_module,
                ):
                    submission = submit_live_video_verification(
                        self.conn,
                        user_id="user-v12",
                        video_base64=base64.b64encode(b"deepfake-risk-video" * 128).decode("ascii"),
                        file_name="deepfake-risk.mp4",
                        content_type="video/mp4",
                        challenge_token=challenge["challenge_token"],
                        metadata={
                            "action_result": {
                                "capture_mode": "realtime_challenge",
                                "completed_actions": ["blink", "open_mouth", "turn_left"],
                                "action_events": [
                                    {"action": "blink", "step_index": 1, "detected_at_ms": 710, "score": 95},
                                    {"action": "open_mouth", "step_index": 2, "detected_at_ms": 1480, "score": 94},
                                    {"action": "turn_left", "step_index": 3, "detected_at_ms": 2270, "score": 92},
                                ],
                                "action_scores": {
                                    "blink": 95,
                                    "open_mouth": 94,
                                    "turn_left": 92,
                                },
                                "face_count_max": 1,
                                "challenge_phrase_rendered": True,
                                "spoken_prompt_rendered": True,
                                "spoken_prompt_display_ms": 2200,
                                "audio_recorded": True,
                                "recording_duration_ms": 4650,
                                "video_recorded": True,
                            }
                        },
                        now=datetime(2026, 5, 5, 13, 1, 0),
                    )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(submission["status"], "under_review")
        self.assertEqual(submission["recommended_next_step"], "strong_identity")
        self.assertEqual(submission["machine_review"]["deepfake_risk_score"], 91)
        self.assertEqual(submission["machine_review"]["deepfake_analysis_status"], "ok")
        self.assertIn("deepfake_risk", submission["machine_review"]["risk_flags"])

    def test_live_video_verification_local_oss_provider_holds_high_photo_edit_risk_for_manual_review(self):
        os.environ["HER_VERIFICATION_PROVIDER"] = "local_oss"
        challenge = create_live_video_verification_challenge(
            user_id="user-v13",
            challenge_actions=["blink", "open_mouth", "turn_left"],
            now=datetime(2026, 5, 5, 13, 0, 0),
        )
        local_provider_result = {
            "provider": "local_oss",
            "provider_version": "silent-face+faster-whisper-v1",
            "liveness_score": 92,
            "face_match_score": 89,
            "same_person_score": 89,
            "replay_attack_score": 8,
            "screen_risk_score": 9,
            "spoofing_risk_score": 7,
            "deepfake_risk_score": 0,
            "photo_edit_risk_score": 88,
            "photo_edit_analysis_status": "ok",
            "skin_smoothing_risk_score": 94,
            "beauty_filter_risk_score": 82,
            "face_shape_delta_score": 46,
            "photo_edit_reference_face_count": 2,
            "photo_edit_live_face_frame_count": 5,
            "photo_edit_reference_source_count": 2,
            "photo_edit_edited_reference_count": 2,
            "motion_score": 74,
            "face_presence_score": 97,
            "sampled_frame_count": 7,
            "valid_face_frame_count": 7,
            "detected_face_count_max": 1,
            "has_audio_track": True,
            "risk_flags": [],
            "speech_challenge_result": {
                "provider": "faster_whisper",
                "transcript_text": challenge["spoken_code"],
                "transcript_confidence": 95,
                "speech_started_at_ms": 2490,
                "speech_ended_at_ms": 3300,
                "audio_duration_ms": 3300,
                "audio_video_sync_score": 84,
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                local_provider_module = types.SimpleNamespace(
                    LOCAL_OSS_PROVIDER_VERSION="silent-face+faster-whisper-v1",
                    analyze_local_live_video=mock.Mock(return_value=local_provider_result),
                )
                with mock.patch.object(
                    verification_module,
                    "_live_video_local_module",
                    return_value=local_provider_module,
                ):
                    submission = submit_live_video_verification(
                        self.conn,
                        user_id="user-v13",
                        video_base64=base64.b64encode(b"photo-edit-risk-video" * 128).decode("ascii"),
                        file_name="photo-edit-risk.mp4",
                        content_type="video/mp4",
                        challenge_token=challenge["challenge_token"],
                        metadata={
                            "action_result": {
                                "capture_mode": "realtime_challenge",
                                "completed_actions": ["blink", "open_mouth", "turn_left"],
                                "action_events": [
                                    {"action": "blink", "step_index": 1, "detected_at_ms": 710, "score": 95},
                                    {"action": "open_mouth", "step_index": 2, "detected_at_ms": 1490, "score": 94},
                                    {"action": "turn_left", "step_index": 3, "detected_at_ms": 2280, "score": 92},
                                ],
                                "action_scores": {
                                    "blink": 95,
                                    "open_mouth": 94,
                                    "turn_left": 92,
                                },
                                "face_count_max": 1,
                                "challenge_phrase_rendered": True,
                                "spoken_prompt_rendered": True,
                                "spoken_prompt_display_ms": 2200,
                                "audio_recorded": True,
                                "recording_duration_ms": 4620,
                                "video_recorded": True,
                            }
                        },
                        now=datetime(2026, 5, 5, 13, 1, 0),
                    )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(submission["status"], "under_review")
        self.assertEqual(submission["recommended_next_step"], "manual_review")
        self.assertEqual(submission["machine_review"]["photo_edit_risk_score"], 88)
        self.assertEqual(submission["machine_review"]["photo_edit_analysis_status"], "ok")
        self.assertIn("photo_heavily_edited", submission["machine_review"]["risk_flags"])

    def test_live_video_verification_can_escalate_to_strong_identity_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_storage_dir = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
            os.environ["HER_VERIFICATION_STORAGE_DIR"] = temp_dir
            try:
                submission = submit_live_video_verification(
                    self.conn,
                    user_id="user-v4",
                    video_base64=base64.b64encode(b"identity-risk-video").decode("ascii"),
                    file_name="risk.mp4",
                    content_type="video/mp4",
                    challenge_phrase="请抬头并张嘴",
                    metadata={
                        "machine_review_inputs": {
                            "liveness_score": 93,
                            "face_match_score": 18,
                            "challenge_score": 90,
                            "risk_flags": ["deepfake_risk"],
                        }
                    },
                    now=datetime(2026, 5, 5, 11, 30, 0),
                )
            finally:
                if old_storage_dir is None:
                    os.environ.pop("HER_VERIFICATION_STORAGE_DIR", None)
                else:
                    os.environ["HER_VERIFICATION_STORAGE_DIR"] = old_storage_dir

        self.assertEqual(submission["status"], "under_review")
        self.assertEqual(submission["recommended_decision"], "manual_review")
        self.assertEqual(submission["recommended_next_step"], "strong_identity")
        self.assertTrue(submission["machine_review"]["risk_flags"])
        self.assertFalse(submission["auto_review_applied"])
        self.assertEqual(len(submission["reviews"]), 0)


if __name__ == "__main__":
    unittest.main()
