"""Adapters that connect the team-owned security controls to the app.

The original teammate modules remain at repository root as their source of
truth. This module provides package-friendly wrappers for the deployable
`email_assistant` application without copying their rule logic.
"""

from __future__ import annotations

from action_authorizer import authorize_action
from db_manager import (
    get_action_requests,
    get_database_summary,
    get_test_results,
    get_verdicts,
    initialize_db,
    log_action_request,
    log_test_result,
    log_verdict,
)
from output_validator import validate_output
from verdict_handler import handle_verdict


def verdict_policy(verdict: str) -> dict:
    """Apply the team's PASS/REVIEW/BLOCK behavior mapping."""
    return handle_verdict(verdict)


def validate_private_output(draft: str) -> dict:
    """Run Amarachi's private-data disclosure check unchanged."""
    return validate_output(draft)


def record_verdict(
    email_id: str,
    verdict: str,
    evidence: str = "",
    reason: str = "",
) -> bool:
    """Best-effort audit logging for one screening result.

    Logging must never weaken the security decision. A database failure returns
    False so callers may surface a warning, but it never turns REVIEW/BLOCK into
    PASS.
    """
    try:
        initialize_db()
        log_verdict(email_id, verdict, evidence=evidence, reason=reason)
        return True
    except Exception:
        return False


def authorize_mock_action(action_request: dict, *, audit: bool = True) -> dict:
    """Authorize a mock action and optionally persist the decision."""
    decision = authorize_action(action_request)

    audit_logged = False
    audit_error = ""
    if audit:
        try:
            initialize_db()
            log_action_request(
                decision.get("action_type", "unknown"),
                action_request.get("target") if isinstance(action_request, dict) else None,
                bool(decision.get("allowed")),
                decision.get("reason"),
            )
            audit_logged = True
        except Exception as exc:
            audit_error = type(exc).__name__

    return {
        **decision,
        "audit_logged": audit_logged,
        "audit_error": audit_error,
    }


def record_test_result(test_name: str, status: str, details=None) -> bool:
    """Persist a test result without letting audit failures break the app."""
    try:
        initialize_db()
        log_test_result(test_name, status, details=details)
        return True
    except Exception:
        return False


def audit_summary() -> dict:
    """Return current audit counts."""
    initialize_db()
    return get_database_summary()


def recent_verdicts() -> list[dict]:
    initialize_db()
    return get_verdicts()


def recent_actions() -> list[dict]:
    initialize_db()
    return get_action_requests()


def recent_test_results() -> list[dict]:
    initialize_db()
    return get_test_results()
