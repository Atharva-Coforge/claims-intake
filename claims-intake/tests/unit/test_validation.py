"""Rule evaluation against `docs/api-contract.md` section 4 and the work items.

Each rule has one parametrized test covering both sides of its comparison, the
boundary, and the acceptance criteria that belong to that rule, including absence.
Order and recording criteria that cannot be observed on a single rule are tested
on `evaluate_notification` and `submit_notification`.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal, cast

import pytest

from claims.models import ClaimRecord, NotificationRequest, Policy
from claims.policy_client import LookupFailureReason, PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import (
    ValidationOutcome,
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
    evaluate_loss_after_inception,
    evaluate_loss_before_expiry,
    evaluate_not_duplicate,
    evaluate_notification,
    evaluate_policy_exists,
    evaluate_policy_not_cancelled,
    submit_notification,
)

CLAIM_REFERENCE_PATTERN = re.compile(r"^CLM-\d{4}-\d{6}$")
ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]
ALL_CLAIM_TYPES: list[ClaimType] = ["collision", "theft", "glass", "liability", "weather"]


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


def make_policy(
    *,
    policy_number: str = "MOT-4471",
    product: str = "personal_auto_standard",
    effective_date: date = date(2026, 3, 1),
    expiry_date: date = date(2027, 2, 28),
    cancellation_date: date | None = None,
    limit: Decimal = Decimal("50000.00"),
    permitted_claim_types: list[ClaimType] | None = None,
) -> Policy:
    return Policy(
        policy_number=policy_number,
        product=product,
        effective_date=effective_date,
        expiry_date=expiry_date,
        cancellation_date=cancellation_date,
        limit=limit,
        permitted_claim_types=(
            ALL_CLAIM_TYPES if permitted_claim_types is None else permitted_claim_types
        ),
    )


def policy_from_client(policy_number: str, client: StubPolicyClient | None = None) -> Policy:
    record = (client or StubPolicyClient()).get_policy(policy_number)
    return Policy(
        policy_number=record.policy_number,
        product=record.product,
        effective_date=record.effective_date,
        expiry_date=record.expiry_date,
        cancellation_date=record.cancellation_date,
        limit=record.limit,
        permitted_claim_types=cast(list[ClaimType], list(record.permitted_claim_types)),
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


def assert_passed(outcome: ValidationOutcome) -> None:
    assert outcome == ValidationOutcome.ok()


def assert_failed(
    outcome: ValidationOutcome,
    *,
    rule: str,
    code: str,
    **detail: object,
) -> None:
    assert outcome.passed is False
    assert outcome.rule == rule
    assert outcome.code == code
    for key, expected in detail.items():
        assert outcome.detail[key] == expected


# --- V-1 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy_number", "should_pass"),
    [
        pytest.param("MOT-4471", True, id="exists-in-master"),
        pytest.param("MOT-9999", False, id="absent-from-master"),
        pytest.param("mot-4471", False, id="EDGE-07-case-differs"),
    ],
)
def test_v1_policy_number_exists_in_the_policy_master(
    policy_client: StubPolicyClient, policy_number: str, should_pass: bool
) -> None:
    """Contract 4.2 V-1, 4.3 exact match including case; WI-0142 AC-4."""
    notification = make_request(policy_number=policy_number)
    outcome = evaluate_policy_exists(notification, policy_client)
    if should_pass:
        assert_passed(outcome)
    else:
        assert_failed(
            outcome,
            rule="V-1",
            code="POLICY_NOT_FOUND",
            policy_number=policy_number,
        )


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param("timeout", id="timeout"),
        pytest.param("unreachable", id="unreachable"),
        pytest.param("unparsable", id="unparsable"),
    ],
)
def test_v1_policy_lookup_failed_is_not_a_rule_outcome(
    reason: LookupFailureReason,
) -> None:
    """A master that did not answer is not POLICY_NOT_FOUND. Contract 1 and 6."""
    notification = make_request()
    client = StubPolicyClient(fail_with=reason)
    with pytest.raises(PolicyLookupFailed) as exc_info:
        evaluate_policy_exists(notification, client)
    assert exc_info.value.policy_number == notification.policy_number
    assert exc_info.value.reason == reason


# --- V-2 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "should_pass"),
    [
        pytest.param("MOT-4471", date(2026, 2, 28), False, id="day-before-inception"),
        pytest.param("MOT-4471", date(2026, 3, 1), True, id="on-inception-wi0142-ac3"),
        pytest.param("MOT-4471", date(2026, 3, 2), True, id="day-after-inception"),
        pytest.param("MOT-4479", date(2026, 3, 15), True, id="EDGE-01-on-inception"),
        pytest.param("MOT-4493", date(2026, 3, 2), False, id="EDGE-05-before-inception"),
    ],
)
def test_v2_loss_date_against_policy_effective_date(
    policy_number: str, loss_date: date, should_pass: bool
) -> None:
    """Contract 4.2 V-2; WI-0142 AC-1 and AC-3. Cover attaches on the inception day."""
    notification = make_request(policy_number=policy_number, loss_date=loss_date)
    policy = policy_from_client(policy_number)
    outcome = evaluate_loss_after_inception(notification, policy)
    if should_pass:
        assert_passed(outcome)
    else:
        assert_failed(
            outcome,
            rule="V-2",
            code="LOSS_BEFORE_INCEPTION",
            loss_date=loss_date,
            effective_date=policy.effective_date,
        )


# --- V-7 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "should_pass"),
    [
        pytest.param("MOT-4471", date(2026, 4, 2), True, id="cancellation-absent-wi0158-ac3"),
        pytest.param("MOT-4496", date(2026, 1, 31), True, id="day-before-cancellation"),
        pytest.param("MOT-4496", date(2026, 2, 1), False, id="on-cancellation-wi0158-ac2"),
        pytest.param("MOT-4496", date(2026, 2, 2), False, id="day-after-cancellation"),
        pytest.param("MOT-4497", date(2026, 1, 15), False, id="EDGE-04-on-cancellation"),
        pytest.param("MOT-4500", date(2026, 1, 8), False, id="EDGE-10-after-cancellation"),
    ],
)
def test_v7_loss_date_against_policy_cancellation_date(
    policy_number: str, loss_date: date, should_pass: bool
) -> None:
    """Contract 4.2 V-7; WI-0158 AC-1, AC-2, AC-3. Null cancellation does not apply."""
    notification = make_request(policy_number=policy_number, loss_date=loss_date)
    policy = policy_from_client(policy_number)
    outcome = evaluate_policy_not_cancelled(notification, policy)
    if should_pass:
        assert_passed(outcome)
        return
    assert policy.cancellation_date is not None
    assert_failed(
        outcome,
        rule="V-7",
        code="POLICY_CANCELLED",
        loss_date=loss_date,
        cancellation_date=policy.cancellation_date,
    )


# --- V-3 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "should_pass"),
    [
        pytest.param("MOT-4471", date(2027, 2, 27), True, id="day-before-expiry"),
        pytest.param("MOT-4471", date(2027, 2, 28), True, id="on-expiry"),
        pytest.param("MOT-4471", date(2027, 3, 1), False, id="day-after-expiry"),
        pytest.param("MOT-4489", date(2026, 2, 28), True, id="EDGE-03-on-expiry"),
        pytest.param("MOT-4500", date(2026, 1, 8), False, id="EDGE-10-after-expiry"),
    ],
)
def test_v3_loss_date_against_policy_expiry_date(
    policy_number: str, loss_date: date, should_pass: bool
) -> None:
    """Contract 4.2 V-3. A loss on the expiry date is covered."""
    notification = make_request(policy_number=policy_number, loss_date=loss_date)
    policy = policy_from_client(policy_number)
    outcome = evaluate_loss_before_expiry(notification, policy)
    if should_pass:
        assert_passed(outcome)
    else:
        assert_failed(
            outcome,
            rule="V-3",
            code="LOSS_AFTER_EXPIRY",
            loss_date=loss_date,
            expiry_date=policy.expiry_date,
        )


# --- V-6 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("seed_original", "candidate", "expect_duplicate"),
    [
        pytest.param(
            False,
            make_request(),
            False,
            id="no-recorded-notification-absence",
        ),
        pytest.param(True, make_request(), True, id="same-trio-wi0151-ac1"),
        pytest.param(
            True,
            make_request(policy_number="MOT-4472"),
            False,
            id="policy-number-differs",
        ),
        pytest.param(
            True,
            make_request(loss_date=date(2026, 4, 3)),
            False,
            id="loss-date-differs",
        ),
        pytest.param(
            True,
            make_request(claim_type="theft"),
            False,
            id="claim-type-differs",
        ),
    ],
)
def test_v6_duplicate_is_the_recorded_policy_date_and_type_trio(
    repository: NotificationRepository,
    seed_original: bool,
    candidate: NotificationRequest,
    expect_duplicate: bool,
) -> None:
    """Contract 4.2 V-6; WI-0151 AC-1 and AC-2. A missing record is not a duplicate."""
    recorded: ClaimRecord | None = None
    if seed_original:
        recorded = repository.record(claim_from_request(repository, make_request()))
    outcome = evaluate_not_duplicate(candidate, repository)
    if expect_duplicate:
        assert recorded is not None
        assert_failed(
            outcome,
            rule="V-6",
            code="DUPLICATE_NOTIFICATION",
            claim_reference=recorded.claim_reference,
        )
    else:
        assert_passed(outcome)


# --- V-5 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy_number", "claim_type", "should_pass"),
    [
        pytest.param("MOT-4471", "collision", True, id="standard-permits-collision"),
        pytest.param("MOT-4481", "collision", False, id="EDGE-09-named-perils-collision"),
        pytest.param("MOT-4481", "theft", True, id="named-perils-permits-theft"),
        pytest.param("MOT-4486", "liability", True, id="liability-only-permits-liability"),
        pytest.param("MOT-4486", "collision", False, id="liability-only-rejects-collision"),
        pytest.param("MOT-4486", "theft", False, id="liability-only-rejects-theft"),
    ],
)
def test_v5_claim_type_permitted_on_the_policy_product(
    policy_number: str, claim_type: ClaimType, should_pass: bool
) -> None:
    """Contract 4.2 V-5 and 2.3. In the product list vs absent from the product list."""
    notification = make_request(policy_number=policy_number, claim_type=claim_type)
    policy = policy_from_client(policy_number)
    outcome = evaluate_claim_type_covered(notification, policy)
    if should_pass:
        assert_passed(outcome)
    else:
        assert_failed(
            outcome,
            rule="V-5",
            code="TYPE_NOT_COVERED",
            claim_type=claim_type,
        )


# --- V-4 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy_number", "estimated_amount", "should_pass"),
    [
        pytest.param("MOT-4471", Decimal("49999.99"), True, id="amount-below-limit"),
        pytest.param("MOT-4471", Decimal("50000.00"), True, id="amount-equal-to-limit"),
        pytest.param("MOT-4471", Decimal("50000.01"), False, id="amount-above-limit"),
        pytest.param("MOT-4501", Decimal("50000.00"), True, id="EDGE-02-equal-to-limit"),
        pytest.param("MOT-4502", Decimal("26000.00"), False, id="EDGE-06-above-limit"),
    ],
)
def test_v4_estimated_amount_against_policy_limit(
    policy_number: str, estimated_amount: Decimal, should_pass: bool
) -> None:
    """Contract 4.2 V-4. An amount equal to the limit is within cover."""
    notification = make_request(policy_number=policy_number, estimated_amount=estimated_amount)
    policy = policy_from_client(policy_number)
    outcome = evaluate_amount_within_limit(notification, policy)
    if should_pass:
        assert_passed(outcome)
    else:
        assert_failed(
            outcome,
            rule="V-4",
            code="AMOUNT_EXCEEDS_LIMIT",
            estimated_amount=estimated_amount,
        )


# --- evaluate_notification (policy rules, first failure) -----------------


def test_evaluate_notification_passes_when_every_policy_rule_passes() -> None:
    """Contract 4.2: a notification inside term, type, and limit is admissible."""
    notification = make_request()
    outcome = evaluate_notification(notification, policy_from_client("MOT-4471"))
    assert_passed(outcome)


@pytest.mark.parametrize(
    ("notification", "policy", "rule", "code"),
    [
        pytest.param(
            make_request(loss_date=date(2026, 4, 1)),
            make_policy(
                effective_date=date(2026, 6, 1),
                cancellation_date=date(2026, 3, 1),
                expiry_date=date(2026, 3, 15),
                permitted_claim_types=["liability"],
                limit=Decimal("1.00"),
            ),
            "V-2",
            "LOSS_BEFORE_INCEPTION",
            id="v2-before-v7-when-both-fail",
        ),
        pytest.param(
            make_request(
                policy_number="MOT-4500",
                loss_date=date(2026, 1, 8),
            ),
            policy_from_client("MOT-4500"),
            "V-7",
            "POLICY_CANCELLED",
            id="EDGE-10-wi0158-ac4-v7-before-v3",
        ),
        pytest.param(
            make_request(loss_date=date(2027, 4, 1), claim_type="collision"),
            make_policy(
                expiry_date=date(2027, 2, 28),
                permitted_claim_types=["liability"],
                limit=Decimal("1.00"),
            ),
            "V-3",
            "LOSS_AFTER_EXPIRY",
            id="v3-before-v5-and-v4",
        ),
        pytest.param(
            make_request(
                policy_number="MOT-4481",
                loss_date=date(2026, 3, 27),
                claim_type="collision",
                estimated_amount=Decimal("30000.01"),
            ),
            policy_from_client("MOT-4481"),
            "V-5",
            "TYPE_NOT_COVERED",
            id="v5-before-v4-named-perils-collision",
        ),
        pytest.param(
            make_request(
                policy_number="MOT-4493",
                loss_date=date(2026, 3, 2),
                estimated_amount=Decimal("72000.00"),
            ),
            policy_from_client("MOT-4493"),
            "V-2",
            "LOSS_BEFORE_INCEPTION",
            id="EDGE-05-v2-before-v4",
        ),
    ],
)
def test_evaluate_notification_stops_at_the_first_policy_rule_failure(
    notification: NotificationRequest,
    policy: Policy,
    rule: str,
    code: str,
) -> None:
    """Contract 4.1: V-2, V-7, V-3, V-5, V-4. First failure only. WI-0158 AC-4."""
    outcome = evaluate_notification(notification, policy)
    assert outcome.passed is False
    assert outcome.rule == rule
    assert outcome.code == code


# --- submit_notification (orchestration, V-1, V-6, recording) ------------


def test_submit_notification_records_only_when_every_rule_passes(
    policy_client: StubPolicyClient, repository: NotificationRepository
) -> None:
    notification = make_request()
    result = submit_notification(notification, policy_client, repository)
    assert isinstance(result, ClaimRecord)
    assert result.policy_number == notification.policy_number
    assert result.loss_date == notification.loss_date
    assert result.claim_type == notification.claim_type
    assert result.estimated_amount == notification.estimated_amount
    assert CLAIM_REFERENCE_PATTERN.fullmatch(result.claim_reference)
    year = datetime.now(tz=UTC).date().year
    assert result.claim_reference.startswith(f"CLM-{year}-")
    assert (
        repository.find_matching(
            notification.policy_number,
            notification.loss_date,
            notification.claim_type,
        )
        is result
    )


@pytest.mark.parametrize(
    ("notification", "rule", "code"),
    [
        pytest.param(
            make_request(policy_number="MOT-9999", loss_date=date(2020, 1, 1)),
            "V-1",
            "POLICY_NOT_FOUND",
            id="wi0142-ac4-missing-policy-not-v2",
        ),
        pytest.param(
            make_request(policy_number="mot-4471"),
            "V-1",
            "POLICY_NOT_FOUND",
            id="EDGE-07-case-is-v1-not-later-rules",
        ),
        pytest.param(
            make_request(policy_number="MOT-4493", loss_date=date(2026, 3, 2)),
            "V-2",
            "LOSS_BEFORE_INCEPTION",
            id="wi0142-ac1-v2-refusal",
        ),
        pytest.param(
            make_request(policy_number="MOT-4500", loss_date=date(2026, 1, 8)),
            "V-7",
            "POLICY_CANCELLED",
            id="wi0158-ac4-cancelled-and-expired",
        ),
        pytest.param(
            make_request(
                policy_number="MOT-4481",
                loss_date=date(2026, 3, 27),
                claim_type="collision",
            ),
            "V-5",
            "TYPE_NOT_COVERED",
            id="EDGE-09-type-not-covered",
        ),
        pytest.param(
            make_request(
                policy_number="MOT-4502",
                estimated_amount=Decimal("26000.00"),
            ),
            "V-4",
            "AMOUNT_EXCEEDS_LIMIT",
            id="EDGE-06-amount-exceeds-limit",
        ),
    ],
)
def test_submit_notification_refuses_without_recording(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    notification: NotificationRequest,
    rule: str,
    code: str,
) -> None:
    """WI-0142 AC-1 and AC-4; WI-0158 AC-4. A refused notification is never recorded."""
    result = submit_notification(notification, policy_client, repository)
    assert isinstance(result, ValidationOutcome)
    assert result.passed is False
    assert result.rule == rule
    assert result.code == code
    assert (
        repository.find_matching(
            notification.policy_number,
            notification.loss_date,
            notification.claim_type,
        )
        is None
    )


def test_submit_notification_reports_v6_before_later_rules(
    policy_client: StubPolicyClient, repository: NotificationRepository
) -> None:
    """Contract 4.1: V-6 precedes V-5 and V-4. Duplicate detail is WI-0151 AC-2."""
    original = make_request()
    recorded = repository.record(claim_from_request(repository, original))
    duplicate = make_request(estimated_amount=Decimal("50000.01"))
    result = submit_notification(duplicate, policy_client, repository)
    assert isinstance(result, ValidationOutcome)
    assert_failed(
        result,
        rule="V-6",
        code="DUPLICATE_NOTIFICATION",
        claim_reference=recorded.claim_reference,
    )
    stored = repository.find_matching(
        original.policy_number, original.loss_date, original.claim_type
    )
    assert stored is recorded


def test_submit_notification_does_not_treat_a_refusal_as_a_duplicate(
    policy_client: StubPolicyClient, repository: NotificationRepository
) -> None:
    """WI-0151 AC-3: a previous rejection was never recorded, so V-6 does not match."""
    over_limit = make_request(estimated_amount=Decimal("50000.01"))
    first = submit_notification(over_limit, policy_client, repository)
    assert isinstance(first, ValidationOutcome)
    assert first.code == "AMOUNT_EXCEEDS_LIMIT"
    assert (
        repository.find_matching(
            over_limit.policy_number, over_limit.loss_date, over_limit.claim_type
        )
        is None
    )

    second = submit_notification(over_limit, policy_client, repository)
    assert isinstance(second, ValidationOutcome)
    assert second.code == "AMOUNT_EXCEEDS_LIMIT"
    assert second.rule == "V-4"

    accepted = submit_notification(make_request(), policy_client, repository)
    assert isinstance(accepted, ClaimRecord)


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param("timeout", id="timeout"),
        pytest.param("unreachable", id="unreachable"),
        pytest.param("unparsable", id="unparsable"),
    ],
)
def test_submit_notification_does_not_catch_policy_lookup_failed(
    repository: NotificationRepository, reason: LookupFailureReason
) -> None:
    """PolicyLookupFailed is not a rule outcome and must reach the HTTP layer."""
    notification = make_request()
    client = StubPolicyClient(fail_with=reason)
    with pytest.raises(PolicyLookupFailed) as exc_info:
        submit_notification(notification, client, repository)
    assert exc_info.value.policy_number == notification.policy_number
    assert exc_info.value.reason == reason
    assert (
        repository.find_matching(
            notification.policy_number,
            notification.loss_date,
            notification.claim_type,
        )
        is None
    )
