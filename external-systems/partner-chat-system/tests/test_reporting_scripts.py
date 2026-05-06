import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system.reporting import (  # noqa: E402
    build_roleplay_report_summary,
    build_thread_export_markdown,
    render_roleplay_report_markdown,
)
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN, connect_db, initialize_database, reset_all_tables  # noqa: E402


def _load_script_module(name: str, relative_path: str):
    path = SYSTEM_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReportingHelperTests(unittest.TestCase):
    def test_build_roleplay_report_summary_exposes_required_metrics(self):
        result = {
            "case_id": "case-report",
            "thread_id": "thread-report",
            "rounds": 2,
            "turn_evaluations": [
                {
                    "turn": 0,
                    "speaker": "pa",
                    "assistant_invoked": False,
                    "interaction_mode_gold": "none",
                    "interaction_mode_pred": "none",
                    "mutual_intent_assessment_gold": "normal",
                    "mutual_intent_assessment_pred": "normal",
                    "need_rescue_gold": False,
                    "need_rescue_pred": False,
                },
                {
                    "turn": 1,
                    "speaker": "pb",
                    "assistant_invoked": True,
                    "interaction_mode": "repair",
                    "assistant_mode_compliance": "compliant",
                    "assistant_guidance": {
                        "advice": ["你就说：我周末也会出去走走，你一般怎么放松？"],
                        "reply_suggestions": ["你就说：我周末也会出去走走，你一般怎么放松？"],
                    },
                    "interaction_mode_gold": "repair",
                    "interaction_mode_pred": "repair",
                    "mutual_intent_assessment_gold": "communication_problem",
                    "mutual_intent_assessment_pred": "communication_problem",
                    "need_rescue_gold": True,
                    "need_rescue_pred": True,
                },
            ],
            "assistant_metrics": {
                "precision_proxy": 1.0,
                "recall_proxy": 1.0,
                "follow_rate": 1.0,
                "partial_follow_rate": 0.0,
                "strong_follow_rate": 1.0,
                "followed_intervention_turns": 1,
                "recoverable_intervention_turns": 1,
                "improved_recovery_turns": 1,
                "improved_recovery_rate": 1.0,
                "slightly_improved_recovery_turns": 0,
                "clarified_low_interest_rate": None,
                "graceful_exit_rate": None,
                "overpush_risk_turns": 0,
                "avoid_violation_turns": 0,
                "assistant_invoke_avg_ms": 42.0,
                "assistant_invoke_max_ms": 42,
            },
            "naturalness_metrics": {"average_score": 4.0},
            "evaluation": {
                "pa": {"conversation_score": 4, "assistant_score": 5, "used_assistant": True},
                "pb": {"conversation_score": 3, "assistant_score": 4, "used_assistant": False},
            },
            "llm_stats": {
                "persona_next_message": {"calls": 2, "avg_ms": 120, "max_ms": 180},
            },
        }

        summary = build_roleplay_report_summary(result)

        self.assertEqual(summary["schema_version"], 1)
        self.assertEqual(summary["recognition_accuracy"]["interaction_mode_accuracy"]["rate"], 1.0)
        self.assertEqual(summary["advice_quality"]["assistant_score_avg_1to5"], 4.5)
        self.assertEqual(summary["advice_quality"]["direct_send_violation_rate"], 1.0)
        self.assertEqual(summary["user_adoption"]["follow_rate"], 1.0)
        self.assertEqual(summary["local_recovery"]["local_recovery_rate"], 1.0)
        self.assertEqual(summary["latency"]["assistant_invoke_avg_ms"], 42.0)
        self.assertEqual(summary["mode_distribution"]["counts"]["repair"], 1)

        markdown = render_roleplay_report_markdown(summary)
        self.assertIn("## 识别准确率", markdown)
        self.assertIn("## 建议质量", markdown)
        self.assertIn("## 延迟统计", markdown)
        self.assertIn("direct-send violation rate: 100.0%", markdown)

    def test_build_thread_export_markdown_splits_dialogue_assistant_and_summary(self):
        rows = [
            {
                "message_id": 1,
                "author_id": "pa",
                "message_recipient_id": None,
                "visibility": "dyadic",
                "source": "user",
                "body": "你好呀",
                "metadata_json": "{}",
                "created_at": "2026-05-06 09:00:01",
            },
            {
                "message_id": 2,
                "author_id": "assistant",
                "message_recipient_id": "pa",
                "visibility": "owner_only",
                "source": "agent_draft",
                "body": "先接住，再轻一点换题。",
                "metadata_json": json.dumps(
                    {
                        "assistant_trace": {
                            "guidance": {"interaction_mode": "repair"},
                            "hint_event": {"trigger_type": "mode_change"},
                        }
                    },
                    ensure_ascii=False,
                ),
                "created_at": "2026-05-06 09:00:02",
            },
            {
                "message_id": 3,
                "author_id": "pa",
                "message_recipient_id": "pa",
                "visibility": "owner_only",
                "source": "user",
                "body": "我想问问怎么回",
                "metadata_json": "{}",
                "created_at": "2026-05-06 09:00:03",
            },
        ]
        roleplay_result = {
            "case_id": "case-export",
            "thread_id": "thread-export",
            "rounds": 1,
            "turn_evaluations": [],
            "assistant_metrics": {},
            "evaluation": {"pa": {"conversation_score": 4, "assistant_score": 4, "used_assistant": True}},
        }

        markdown = build_thread_export_markdown(
            rows,
            thread_id="thread-export",
            roleplay_result=roleplay_result,
        )

        self.assertIn("## 主对话正文", markdown)
        self.assertIn("## 助手建议", markdown)
        self.assertIn("## 用户私有记录", markdown)
        self.assertIn("## 评测摘要", markdown)
        self.assertIn("mode=repair", markdown)
        self.assertIn("trigger=mode_change", markdown)
        self.assertIn("## 评测自评", markdown)


class ScriptSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_roleplay_script = _load_script_module(
            "run_dyadic_agent_roleplay_script",
            "scripts/run_dyadic_agent_roleplay.py",
        )
        cls.export_thread_script = _load_script_module(
            "export_chat_thread_script",
            "scripts/export_chat_thread.py",
        )

    def setUp(self):
        self.conn = connect_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_database(self.conn)
        reset_all_tables(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_run_roleplay_script_local_demo_writes_report_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = pathlib.Path(tmpdir) / "roleplay.json"
            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = [
                "run_dyadic_agent_roleplay.py",
                "--db",
                DEFAULT_CHAT_TEST_MYSQL_DSN,
                "--case-id",
                "script-local-demo-report",
                "--rounds",
                "4",
                "--assistant-mode",
                "fixed_turns",
                "--assistant-on-turns",
                "0",
                "--local-demo",
                "--output",
                str(out_path),
            ]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = self.run_roleplay_script.main()

            self.assertEqual(rc, 0)
            result = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertIn("report_summary", result)
            self.assertIn("recognition_accuracy", result["report_summary"])
            self.assertIn("advice_quality", result["report_summary"])
            self.assertIn("latency", result["report_summary"])
            self.assertIn("mode_distribution", result["report_summary"])
            self.assertEqual(result["report_summary"]["advice_quality"]["direct_send_violation_rate"], 0.0)
            self.assertIsNotNone(result["report_summary"]["latency"]["assistant_invoke_avg_ms"])
            self.assertIn('"report_summary"', stdout.getvalue())
            self.assertIn("# Roleplay Report", stderr.getvalue())

    def test_export_chat_thread_script_renders_partitioned_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            roleplay_json = pathlib.Path(tmpdir) / "roleplay.json"
            markdown_path = pathlib.Path(tmpdir) / "thread.md"

            run_argv = [
                "run_dyadic_agent_roleplay.py",
                "--db",
                DEFAULT_CHAT_TEST_MYSQL_DSN,
                "--case-id",
                "script-export-demo",
                "--rounds",
                "4",
                "--assistant-mode",
                "fixed_turns",
                "--assistant-on-turns",
                "0",
                "--local-demo",
                "--output",
                str(roleplay_json),
            ]
            with patch.object(sys, "argv", run_argv), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                run_rc = self.run_roleplay_script.main()
            self.assertEqual(run_rc, 0)

            export_argv = [
                "export_chat_thread.py",
                "--db",
                DEFAULT_CHAT_TEST_MYSQL_DSN,
                "--roleplay-json",
                str(roleplay_json),
                "--format",
                "markdown",
                "--output",
                str(markdown_path),
            ]
            with patch.object(sys, "argv", export_argv), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                export_rc = self.export_thread_script.main()
            self.assertEqual(export_rc, 0)

            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("## 主对话正文", markdown)
            self.assertIn("## 助手建议", markdown)
            self.assertIn("## 评测摘要", markdown)
            self.assertIn("## 评测自评", markdown)
            self.assertIn("assistant score avg", markdown)


if __name__ == "__main__":
    unittest.main()
