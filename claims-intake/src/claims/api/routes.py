"""HTTP surface for the claims intake service.

This layer does three things and no more: it parses the request, it calls the
service, and it maps the outcome to a status code. It holds no rule logic. A rule
that appears here is a rule the service layer cannot be tested for.

Day 4 lab. Implement against `docs/api-contract.md` sections 5 and 6.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from claims.models import NotificationRequest
from claims.policy_client import (
    LookupFailureReason,
    PolicyClient,
    PolicyLookupFailed,
    StubPolicyClient,
)
from claims.repository import NotificationRepository
from claims.service import submit_notification

app = FastAPI(title="Claims Intake Service")

# One in-memory store and one stub master for the running process. Tests replace
# these through FastAPI dependency overrides so a lookup can fail without a
# network and a duplicate can be seeded without sharing this process state.
_policy_client: PolicyClient = StubPolicyClient()
_repository = NotificationRepository()

STATUS_BY_CODE: dict[str, int] = {
    "MALFORMED_REQUEST": 400,
    "POLICY_NOT_FOUND": 422,
    "LOSS_BEFORE_INCEPTION": 422,
    "POLICY_CANCELLED": 422,
    "LOSS_AFTER_EXPIRY": 422,
    "AMOUNT_EXCEEDS_LIMIT": 422,
    "TYPE_NOT_COVERED": 422,
    "DUPLICATE_NOTIFICATION": 409,
    "POLICY_MASTER_TIMEOUT": 504,
    "POLICY_MASTER_UNREACHABLE": 503,
    "POLICY_MASTER_UNPARSABLE": 502,
}

MESSAGE_BY_CODE: dict[str, str] = {
    "MALFORMED_REQUEST": "The request cannot be interpreted.",
    "POLICY_NOT_FOUND": "No policy found with that number.",
    "LOSS_BEFORE_INCEPTION": "Loss date precedes policy inception.",
    "POLICY_CANCELLED": "The policy is cancelled on the loss date.",
    "LOSS_AFTER_EXPIRY": "Loss date falls after policy expiry.",
    "AMOUNT_EXCEEDS_LIMIT": "Estimated amount exceeds the policy limit.",
    "TYPE_NOT_COVERED": "Claim type is not covered on this policy.",
    "DUPLICATE_NOTIFICATION": "A notification for this loss has already been recorded.",
    "POLICY_MASTER_TIMEOUT": "The policy master did not answer in time.",
    "POLICY_MASTER_UNREACHABLE": "The policy master could not be reached.",
    "POLICY_MASTER_UNPARSABLE": "The policy master returned an unreadable response.",
}

LOOKUP_CODE_BY_REASON: dict[LookupFailureReason, str] = {
    "timeout": "POLICY_MASTER_TIMEOUT",
    "unreachable": "POLICY_MASTER_UNREACHABLE",
    "unparsable": "POLICY_MASTER_UNPARSABLE",
}


def get_policy_client() -> PolicyClient:
    return _policy_client


def get_repository() -> NotificationRepository:
    return _repository


def _jsonable(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _envelope(code: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "message": MESSAGE_BY_CODE[code],
        "detail": {key: _jsonable(item) for key, item in detail.items()},
    }


def _error(code: str, detail: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=STATUS_BY_CODE[code], content=_envelope(code, detail))


@app.exception_handler(RequestValidationError)
async def malformed_request(_request: object, _exc: RequestValidationError) -> JSONResponse:
    """A body this service cannot interpret. Contract sections 2.4 and 6."""
    return _error("MALFORMED_REQUEST", {})


@app.post("/notifications")
def create_notification(
    notification: NotificationRequest,
    policy_client: Annotated[PolicyClient, Depends(get_policy_client)],
    repository: Annotated[NotificationRepository, Depends(get_repository)],
) -> JSONResponse:
    """Accept a first notice of loss. Mapping is contract sections 5 and 6."""
    try:
        outcome = submit_notification(notification, policy_client, repository)
    except PolicyLookupFailed as exc:
        return _lookup_failed(exc)

    if outcome.passed:
        return JSONResponse(
            status_code=201,
            content={
                "claim_reference": outcome.claim_reference,
                "status": "recorded",
            },
        )
    return _error(str(outcome.code), dict(outcome.detail))


def _lookup_failed(exc: PolicyLookupFailed) -> JSONResponse:
    """The master did not answer. This is not POLICY_NOT_FOUND. Contract §5, §6."""
    code = LOOKUP_CODE_BY_REASON[exc.reason]
    return _error(code, {"policy_number": exc.policy_number, "reason": exc.reason})
