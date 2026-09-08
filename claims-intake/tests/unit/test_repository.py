"""Unit tests for recorded-claim storage.

Recording, reference generation, and duplicate lookup are tested separately.
The repository never writes a refusal: `record` accepts `ClaimRecord` only.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

import pytest

from claims.models import ClaimRecord, NotificationRequest, RuleFailure
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


def claim_from_request(
    repository: NotificationRepository, request: NotificationRequest
) -> ClaimRecord:
    return ClaimRecord(
        policy_number=request.policy_number,
        loss_date=request.loss_date,
        claim_type=request.claim_type,
        estimated_amount=request.estimated_amount,
        description=request.description,
        claim_reference=repository.issue_claim_reference(),
    )


@pytest.mark.parametrize(
    "unused_index",
    [
        pytest.param(0, id="first-reference"),
        pytest.param(1, id="second-reference"),
        pytest.param(2, id="third-reference"),
    ],
)
def test_issue_claim_reference_matches_contract_format(
    repository: NotificationRepository, unused_index: int
) -> None:
    for _ in range(unused_index):
        repository.issue_claim_reference()
    reference = repository.issue_claim_reference()
    assert CLAIM_REFERENCE_PATTERN.fullmatch(reference)
    year = datetime.now(tz=UTC).date().year
    assert reference.startswith(f"CLM-{year}-")


def test_issue_claim_reference_is_unique_and_never_reissued(
    repository: NotificationRepository,
) -> None:
    issued = [repository.issue_claim_reference() for _ in range(3)]
    assert len(issued) == len(set(issued))


@pytest.mark.parametrize(
    "request_",
    [
        pytest.param(make_request(), id="collision-with-description"),
        pytest.param(make_request(claim_type="theft"), id="theft"),
        pytest.param(make_request(description=None), id="no-description"),
    ],
)
def test_record_stores_the_claim_record(
    repository: NotificationRepository, request_: NotificationRequest
) -> None:
    claim = claim_from_request(repository, request_)
    stored = repository.record(claim)
    assert stored is claim
    assert stored.policy_number == request_.policy_number
    assert stored.loss_date == request_.loss_date
    assert type(stored.loss_date) is date
    assert type(stored.estimated_amount) is Decimal


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
def test_recorded_claim_records_keep_distinct_references(
    repository: NotificationRepository,
    first: NotificationRequest,
    second: NotificationRequest,
) -> None:
    recorded_first = repository.record(claim_from_request(repository, first))
    recorded_second = repository.record(claim_from_request(repository, second))
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
    recorded = repository.record(claim_from_request(repository, request_))
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
    repository.record(claim_from_request(repository, make_request()))
    assert (
        repository.find_matching(lookup_policy, lookup_date, lookup_type) is None
    )


@pytest.mark.parametrize(
    "not_a_claim",
    [
        pytest.param(make_request(policy_number="MOT-9999"), id="unknown-policy-request"),
        pytest.param(make_request(policy_number="mot-4471"), id="EDGE-07-lowercase-request"),
        pytest.param(
            RuleFailure(rule="V-1", code="POLICY_NOT_FOUND"),
            id="rule-failure",
        ),
    ],
)
def test_record_stores_only_claim_records(
    repository: NotificationRepository,
    not_a_claim: NotificationRequest | RuleFailure,
) -> None:
    """WI-0151 AC-3: a refusal is not a ClaimRecord, so it cannot be stored."""
    payload: Any = not_a_claim
    with pytest.raises(TypeError, match="ClaimRecord only"):
        repository.record(payload)


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
def test_find_matching_cannot_see_a_request_that_was_never_a_claim_record(
    repository: NotificationRepository, rejected: NotificationRequest
) -> None:
    """WI-0151 AC-3: find_matching reads ClaimRecords only."""
    repository.record(
        claim_from_request(
            repository,
            make_request(policy_number="MOT-4472", claim_type="theft"),
        )
    )
    failure = RuleFailure(rule="V-1", code="POLICY_NOT_FOUND")
    assert not isinstance(failure, ClaimRecord)
    assert (
        repository.find_matching(
            rejected.policy_number,
            rejected.loss_date,
            rejected.claim_type,
        )
        is None
    )
