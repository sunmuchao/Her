"""Profile JSON-RPC handlers for the gateway."""

from __future__ import annotations

from typing import Any, Protocol

from chat_system import (  # type: ignore[import-untyped]
    dispute_profile_field_verification,
    evaluate_profile_consistency,
    expire_due_profile_field_verifications,
    field_verification_policies,
    get_photo_risk_score_run,
    get_profile_field_verification_submission,
    get_profile_review_case,
    get_profile_review_case_appeal,
    list_photo_risk_review_queue,
    list_photo_risk_score_runs,
    list_profile_field_verification_submissions,
    list_profile_review_case_appeals,
    list_profile_review_cases,
    resubmit_profile_field_verification,
    review_profile_field_verification,
    review_profile_review_case,
    review_profile_review_case_appeal,
    submit_profile_field_verification,
    submit_profile_review_case_appeal,
)

from .profile_access import with_resolved_subject_user_id, with_visible_subject_user_id
from .role_sets import INTERNAL_WRITE_ROLES, PROFILE_REVIEW_ROLES, STAFF_OVERRIDE_ROLES

JSONRPC_NOT_HANDLED = object()


class ProfileJsonrpcGateway(Protocol):
    def _assert_actor_can_access_owner(
        self,
        environ: dict[str, Any],
        owner_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> str: ...

    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _require_roles(
        self,
        environ: dict[str, Any],
        roles: frozenset[str],
        *,
        message: str,
    ) -> Any: ...

    def _resolve_actor_bound_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> str: ...

    def _resolve_operator_actor_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        roles: frozenset[str],
        message: str,
    ) -> str: ...

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def handle_profile_jsonrpc(
    gateway: ProfileJsonrpcGateway,
    environ: dict[str, Any],
    method: str,
    params: dict[str, Any],
) -> Any:
    if method == "profile.get_field_verification_policies":
        return field_verification_policies()
    if method == "profile.submit_field_verification":
        return gateway._with_chat(
            submit_profile_field_verification,
            **with_resolved_subject_user_id(
                gateway,
                environ,
                dict(params),
                treat_empty_as_missing=False,
            ),
        )
    if method == "profile.list_field_verifications":
        return gateway._with_chat(
            list_profile_field_verification_submissions,
            **with_visible_subject_user_id(gateway, environ, dict(params)),
        )
    if method == "profile.get_field_verification":
        submission = gateway._with_verification(get_profile_field_verification_submission, params["submission_id"])
        gateway._assert_actor_can_access_owner(
            environ,
            (submission or {}).get("subject_user_id"),
            field_name="subject_user_id",
        )
        return submission
    if method == "profile.resubmit_field_verification":
        payload = with_resolved_subject_user_id(
            gateway,
            environ,
            dict(params),
            treat_empty_as_missing=False,
        )
        submission_id = payload.pop("submission_id")
        return gateway._with_verification(resubmit_profile_field_verification, submission_id, **payload)
    if method == "profile.dispute_field_verification":
        payload = with_resolved_subject_user_id(
            gateway,
            environ,
            dict(params),
            treat_empty_as_missing=False,
        )
        submission_id = payload.pop("submission_id")
        return gateway._with_verification(dispute_profile_field_verification, submission_id, **payload)
    if method == "profile.review_field_verification":
        payload = dict(params)
        submission_id = payload.pop("submission_id")
        reviewer_id = gateway._resolve_operator_actor_id(
            environ,
            payload.pop("reviewer_id", None),
            field_name="reviewer_id",
            roles=PROFILE_REVIEW_ROLES,
            message="current actor cannot review profile verifications",
        )
        return gateway._with_verification(review_profile_field_verification, submission_id, reviewer_id, **payload)
    if method == "profile.expire_due_field_verifications":
        gateway._require_roles(
            environ,
            PROFILE_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
            message="current actor cannot expire due profile verifications",
        )
        return gateway._with_verification(expire_due_profile_field_verifications, **params)
    if method == "profile.evaluate_risk_case":
        gateway._require_roles(
            environ,
            PROFILE_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
            message="current actor cannot evaluate profile review cases",
        )
        return gateway._with_verification(evaluate_profile_consistency, **params)
    if method == "profile.list_risk_cases":
        return gateway._with_chat(
            list_profile_review_cases,
            **with_visible_subject_user_id(gateway, environ, dict(params)),
        )
    if method == "profile.get_risk_case":
        risk_case = gateway._with_risk(get_profile_review_case, params["profile_review_case_id"])
        gateway._assert_actor_can_access_owner(
            environ,
            (risk_case or {}).get("subject_user_id"),
            field_name="subject_user_id",
        )
        return risk_case
    if method == "profile.list_photo_risk_runs":
        return gateway._with_chat(
            list_photo_risk_score_runs,
            **with_visible_subject_user_id(gateway, environ, dict(params)),
        )
    if method == "profile.get_photo_risk_run":
        row = gateway._with_risk(get_photo_risk_score_run, int(params["score_run_id"]))
        gateway._assert_actor_can_access_owner(
            environ,
            (row or {}).get("subject_user_id"),
            field_name="subject_user_id",
        )
        return row
    if method == "profile.list_photo_risk_review_queue":
        gateway._require_roles(
            environ,
            PROFILE_REVIEW_ROLES,
            message="current actor cannot view the photo risk review queue",
        )
        return gateway._with_risk(list_photo_risk_review_queue, **params)
    if method == "profile.review_risk_case":
        payload = dict(params)
        profile_review_case_id = payload.pop("profile_review_case_id")
        resolver_id = gateway._resolve_operator_actor_id(
            environ,
            payload.pop("resolver_id", None),
            field_name="resolver_id",
            roles=PROFILE_REVIEW_ROLES,
            message="current actor cannot review profile risk cases",
        )
        return gateway._with_risk(review_profile_review_case, profile_review_case_id, resolver_id, **payload)
    if method == "profile.submit_risk_case_appeal":
        payload = dict(params)
        profile_review_case_id = payload.pop("profile_review_case_id")
        appellant_id = gateway._resolve_actor_bound_id(
            environ,
            payload.pop("appellant_id", None),
            field_name="appellant_id",
        )
        return gateway._with_risk(submit_profile_review_case_appeal, profile_review_case_id, appellant_id, **payload)
    if method == "profile.list_risk_case_appeals":
        return gateway._with_chat(
            list_profile_review_case_appeals,
            **with_visible_subject_user_id(gateway, environ, dict(params)),
        )
    if method == "profile.get_risk_case_appeal":
        appeal = gateway._with_risk(get_profile_review_case_appeal, int(params["appeal_id"]))
        gateway._assert_actor_can_access_owner(
            environ,
            (appeal or {}).get("subject_user_id"),
            field_name="subject_user_id",
        )
        return appeal
    if method == "profile.review_risk_case_appeal":
        payload = dict(params)
        appeal_id = int(payload.pop("appeal_id"))
        resolver_id = gateway._resolve_operator_actor_id(
            environ,
            payload.pop("resolver_id", None),
            field_name="resolver_id",
            roles=PROFILE_REVIEW_ROLES,
            message="current actor cannot review profile appeals",
        )
        return gateway._with_risk(review_profile_review_case_appeal, appeal_id, resolver_id, **payload)
    return JSONRPC_NOT_HANDLED
