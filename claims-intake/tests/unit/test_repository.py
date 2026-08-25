"""Unit tests for recorded-notification storage.

The repository saves accepted requests and answers WI-0151's duplicate query.
It does not decide whether a request should be saved; tests that need a
rejection simply never call record.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

import pytest

from claims.models import NotificationRequest
from claims.repository import NotificationRepository

CLAIM_REFERENCE_PATTERN = re.compile(r"^CLM-\d{4}-\d{6}$")
ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository()


def make_request(
    *,
    policy_number: str = "MOT-4471",
    loss_date: date = date(2026, 4, 2),
    claim_type: ClaimType = "collision",
    estimated_amount: Decimal = Decimal("4200.00"),
    description: str | None = "Rear ended at a junction.",
) -> NotificationRequest:
    return NotificationRequest(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type=claim_type,
        estimated_amount=estimated_amount,
        description=description,
    )


@pytest.mark.parametrize(
    "request_",
    [
        pytest.param(make_request(), id="collision-with-description"),
        pytest.param(make_request(claim_type="theft"), id="theft"),
        pytest.param(make_request(description=None), id="no-description"),
    ],
)
def test_record_issues_claim_reference_matching_contract(
    repository: NotificationRepository, request_: NotificationRequest
) -> None:
    recorded = repository.record(request_)
    assert CLAIM_REFERENCE_PATTERN.fullmatch(recorded.claim_reference)
    year = datetime.now(tz=UTC).date().year
    assert recorded.claim_reference.startswith(f"CLM-{year}-")
    assert recorded.policy_number == request_.policy_number
    assert recorded.loss_date == request_.loss_date
    assert type(recorded.loss_date) is date
    assert recorded.estimated_amount == request_.estimated_amount
    assert type(recorded.estimated_amount) is Decimal


@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param(
            make_request(),
            make_request(claim_type="theft"),
            id="two-types-same-policy-and-date",
        ),
        pytest.param(
            make_request(),
            make_request(loss_date=date(2026, 4, 3)),
            id="two-dates-same-policy-and-type",
        ),
        pytest.param(
            make_request(),
            make_request(policy_number="MOT-4472"),
            id="two-policies-same-date-and-type",
        ),
    ],
)
def test_each_recorded_notification_gets_a_unique_claim_reference(
    repository: NotificationRepository,
    first: NotificationRequest,
    second: NotificationRequest,
) -> None:
    recorded_first = repository.record(first)
    recorded_second = repository.record(second)
    assert recorded_first.claim_reference != recorded_second.claim_reference


@pytest.mark.parametrize(
    "request_",
    [
        pytest.param(make_request(), id="default-trio"),
        pytest.param(
            make_request(policy_number="MOT-4481", claim_type="weather"),
            id="weather-on-named-perils-policy",
        ),
    ],
)
def test_find_matching_returns_the_record_when_all_three_fields_agree(
    repository: NotificationRepository, request_: NotificationRequest
) -> None:
    recorded = repository.record(request_)
    found = repository.find_matching(
        request_.policy_number,
        request_.loss_date,
        request_.claim_type,
    )
    assert found is recorded
    assert found.claim_reference == recorded.claim_reference


@pytest.mark.parametrize(
    ("lookup_policy", "lookup_date", "lookup_type"),
    [
        pytest.param("MOT-4472", date(2026, 4, 2), "collision", id="policy-number-differs"),
        pytest.param("MOT-4471", date(2026, 4, 3), "collision", id="loss-date-differs"),
        pytest.param("MOT-4471", date(2026, 4, 2), "theft", id="claim-type-differs"),
    ],
)
def test_find_matching_is_not_a_duplicate_when_only_two_fields_agree(
    repository: NotificationRepository,
    lookup_policy: str,
    lookup_date: date,
    lookup_type: ClaimType,
) -> None:
    repository.record(make_request())
    assert (
        repository.find_matching(lookup_policy, lookup_date, lookup_type) is None
    )


@pytest.mark.parametrize(
    "rejected",
    [
        pytest.param(make_request(policy_number="MOT-9999"), id="unknown-policy"),
        pytest.param(make_request(policy_number="mot-4471"), id="EDGE-07-lowercase"),
        pytest.param(
            make_request(policy_number="MOT-4497", loss_date=date(2026, 1, 15)),
            id="cancelled-policy-loss",
        ),
    ],
)
def test_rejected_notification_is_never_recorded_so_resubmit_is_not_duplicate(
    repository: NotificationRepository, rejected: NotificationRequest
) -> None:
    """WI-0151 AC-3: a refusal is not written, so it cannot be duplicated."""
    repository.record(make_request(policy_number="MOT-4472", claim_type="theft"))
    first_lookup = repository.find_matching(
        rejected.policy_number,
        rejected.loss_date,
        rejected.claim_type,
    )
    resubmit_lookup = repository.find_matching(
        rejected.policy_number,
        rejected.loss_date,
        rejected.claim_type,
    )
    assert first_lookup is None
    assert resubmit_lookup is None
