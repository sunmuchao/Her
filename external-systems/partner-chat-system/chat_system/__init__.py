"""Partner chat subsystem: threads, messages, risk controls, and summaries."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

_EXPORT_MODULES = {
    "CONV_KIND_DM": ".conversations",
    "CONV_KIND_GROUP": ".conversations",
    "LAYOUT_ROLE_ASSISTANT_DM_A": ".conversations",
    "LAYOUT_ROLE_ASSISTANT_DM_B": ".conversations",
    "LAYOUT_ROLE_MAIN_GROUP": ".conversations",
    "ROLE_AGENT": ".conversations",
    "ROLE_HUMAN": ".conversations",
    "ROLE_SYSTEM": ".conversations",
    "SRC_SYSTEM": ".service",
    "SRC_USER": ".service",
    "SOURCE_AGENT": ".conversations",
    "SOURCE_SYSTEM": ".conversations",
    "SOURCE_USER": ".conversations",
    "VIS_DYADIC": ".service",
    "VIS_OWNER_ONLY": ".service",
    "VIS_SYSTEM": ".service",
    "build_case_conversation_timeline": ".conversations",
    "build_thread_risk_overview": ".risk",
    "build_chat_timeline": ".timeline",
    "build_fraud_network_overview": ".fraud_graph",
    "build_risk_case_playback": ".moderation_ops",
    "build_risk_weekly_dashboard": ".moderation_ops",
    "build_user_trust_hub": ".self_service",
    "batch_review_risk_cases": ".moderation_ops",
    "classify_phone_scenario": ".auth_accounts",
    "close_idle_agent_sessions": ".assistant_sessions",
    "connect_db": ".storage",
    "current_time": ".service",
    "create_live_video_verification_challenge": ".verification",
    "create_assistant_case_layout": ".conversations",
    "dispute_profile_field_verification": ".profile_reviews",
    "evaluate_profile_consistency": ".profile_reviews",
    "expire_due_profile_field_verifications": ".profile_reviews",
    "evaluate_fraud_network": ".fraud_graph",
    "field_verification_policies": ".profile_reviews",
    "get_photo_risk_review_queue_item": ".profile_reviews",
    "get_photo_risk_score_run": ".profile_reviews",
    "get_agent_session": ".assistant_sessions",
    "get_agent_session_by_case": ".assistant_sessions",
    "get_agent_task": ".assistant_sessions",
    "get_conversation": ".conversations",
    "get_conversation_by_case_and_key": ".conversations",
    "get_conversation_member": ".conversations",
    "get_or_create_conversation": ".conversations",
    "get_profile_field_verification_submission": ".profile_reviews",
    "get_profile_review_case_appeal": ".profile_reviews",
    "get_profile_review_case": ".profile_reviews",
    "get_current_auth_payload": ".auth_accounts",
    "get_session_by_access_token": ".auth_accounts",
    "get_or_create_thread": ".service",
    "get_fraud_network_profile": ".fraud_graph",
    "get_risk_case": ".risk",
    "get_thread": ".service",
    "get_thread_summary": ".summaries",
    "get_thread_by_case": ".service",
    "initialize_database": ".storage",
    "list_case_conversations": ".conversations",
    "list_agent_tasks": ".assistant_sessions",
    "list_conversation_members": ".conversations",
    "list_conversation_messages": ".conversations",
    "list_fraud_network_links": ".fraud_graph",
    "list_fraud_network_profiles": ".fraud_graph",
    "list_member_reports": ".risk",
    "list_meeting_feedback": ".risk",
    "list_messages": ".service",
    "list_failed_outbox": ".outbox_admin",
    "list_pending_outbox": ".outbox_admin",
    "list_processing_outbox": ".outbox_admin",
    "list_retry_pending_outbox": ".outbox_admin",
    "list_photo_risk_review_queue": ".profile_reviews",
    "list_photo_risk_score_runs": ".profile_reviews",
    "list_photo_review_requests": ".verification",
    "list_profile_field_verification_submissions": ".profile_reviews",
    "list_profile_review_case_appeals": ".profile_reviews",
    "list_profile_review_cases": ".profile_reviews",
    "list_profile_review_events": ".profile_reviews",
    "list_risk_appeals": ".moderation_ops",
    "list_risk_cases": ".risk",
    "list_risk_signals": ".risk",
    "list_verification_assets": ".verification",
    "list_verification_notifications": ".verification",
    "list_verification_reviews": ".verification",
    "list_verification_submissions": ".verification",
    "post_conversation_message": ".conversations",
    "post_message": ".service",
    "process_pending_agent_tasks": ".assistant_orchestrator",
    "requeue_outbox_rows": ".outbox_admin",
    "reset_all_tables": ".storage",
    "request_live_video_verification": ".verification",
    "record_fraud_network_observation": ".fraud_graph",
    "refresh_session": ".auth_accounts",
    "resubmit_profile_field_verification": ".profile_reviews",
    "resubmit_live_video_verification": ".verification",
    "review_risk_appeal": ".moderation_ops",
    "review_profile_field_verification": ".profile_reviews",
    "review_profile_review_case_appeal": ".profile_reviews",
    "review_profile_review_case": ".profile_reviews",
    "review_risk_case": ".risk",
    "review_live_video_verification": ".verification",
    "run_chat_maintenance": ".maintenance",
    "run_chat_outbox_worker": ".outbox_worker",
    "serve_chat_outbox_worker": ".outbox_worker",
    "revoke_session_by_access_token": ".auth_accounts",
    "submit_risk_appeal": ".moderation_ops",
    "issue_sms_code": ".auth_accounts",
    "submit_profile_field_verification": ".profile_reviews",
    "submit_profile_review_case_appeal": ".profile_reviews",
    "submit_live_video_verification": ".verification",
    "submit_meeting_feedback": ".risk",
    "submit_member_report": ".risk",
    "verify_sms_code": ".auth_accounts",
    "summarize_outbox": ".outbox_admin",
    "get_risk_appeal": ".moderation_ops",
    "get_verification_submission": ".verification",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    try:
        module_name = _EXPORT_MODULES[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
