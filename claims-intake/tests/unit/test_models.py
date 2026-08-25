from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast
import pytest
from pydantic import ValidationError

from claims.models import (
    NotificationRequest,
    Policy,
    RecordedNotification,
    RuleFailure,
)
from claims.policy_client import StubPolicyClient

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]


def load_payload(filename: str, payload_id: str) -> dict[str, Any]:
    records: list[dict[str, Any]] = json.loads((DATA_DIR / filename).read_text())
    for record in records:
        if record["id"] == payload_id:
            payload = record["payload"]
            assert isinstance(payload, dict)
            return payload
    raise KeyError(f"{payload_id} not found in {filename}")


def well_formed() -> dict[str, object]:
    return {
        "policy_number": "MOT-4471",
        "loss_date": date(2026, 4, 2),
        "claim_type": "collision",
        "estimated_amount": Decimal("4200.00"),
        "description": "Rear ended at a junction.",
    }


def without_field(field_name: str) -> dict[str, object]:
    payload = well_formed()
    del payload[field_name]
    return payload


def with_override(**changes: object) -> dict[str, object]:
    payload = well_formed()
    payload.update(changes)
    return payload


def well_formed_policy() -> dict[str, object]:
    return {
        "policy_number": "MOT-4471",
        "product": "personal_auto_standard",
        "effective_date": date(2026, 3, 1),
        "expiry_date": date(2027, 2, 28),
        "cancellation_date": None,
        "limit": Decimal("50000.00"),
        "permitted_claim_types": ["collision", "theft", "glass", "liability", "weather"],
    }


def policy_without(field_name: str) -> dict[str, object]:
    payload = well_formed_policy()
    del payload[field_name]
    return payload


def policy_with(**changes: object) -> dict[str, object]:
    payload = well_formed_policy()
    payload.update(changes)
    return payload


def well_formed_recorded() -> dict[str, object]:
    payload = well_formed()
    payload["claim_reference"] = "CLM-2026-000317"
    return payload


def recorded_without(field_name: str) -> dict[str, object]:
    payload = well_formed_recorded()
    del payload[field_name]
    return payload


def recorded_with(**changes: object) -> dict[str, object]:
    payload = well_formed_recorded()
    payload.update(changes)
    return payload


@pytest.mark.parametrize(
    ("filename", "payload_id"),
    [
        pytest.param("fnol_valid.json", "VALID-01", id="VALID-01"),
        pytest.param("fnol_valid.json", "VALID-02", id="VALID-02"),
        pytest.param("fnol_valid.json", "VALID-03", id="VALID-03"),
        pytest.param("fnol_valid.json", "VALID-04", id="VALID-04"),
        pytest.param("fnol_valid.json", "VALID-05", id="VALID-05"),
        pytest.param("fnol_valid.json", "VALID-06", id="VALID-06-no-description"),
        pytest.param("fnol_valid.json", "VALID-07", id="VALID-07"),
        pytest.param("fnol_valid.json", "VALID-08", id="VALID-08"),
        pytest.param("fnol_invalid.json", "INVALID-01", id="INVALID-01-unknown-policy"),
        pytest.param("fnol_invalid.json", "INVALID-02", id="INVALID-02-before-inception"),
        pytest.param("fnol_invalid.json", "INVALID-03", id="INVALID-03-after-expiry"),
        pytest.param("fnol_invalid.json", "INVALID-04", id="INVALID-04-over-limit"),
        pytest.param("fnol_invalid.json", "INVALID-05", id="INVALID-05-type-not-on-product"),
        pytest.param("fnol_invalid.json", "INVALID-06", id="INVALID-06-duplicate-shape"),
        pytest.param("fnol_invalid.json", "INVALID-07", id="INVALID-07-cancelled"),
        pytest.param("fnol_edge.json", "EDGE-01", id="EDGE-01-inception-day"),
        pytest.param("fnol_edge.json", "EDGE-02", id="EDGE-02-amount-at-limit"),
        pytest.param("fnol_edge.json", "EDGE-03", id="EDGE-03-last-day-of-term"),
        pytest.param("fnol_edge.json", "EDGE-04", id="EDGE-04-cancellation-day"),
        pytest.param("fnol_edge.json", "EDGE-05", id="EDGE-05-before-inception"),
        pytest.param("fnol_edge.json", "EDGE-06", id="EDGE-06-over-limit"),
        pytest.param("fnol_edge.json", "EDGE-07", id="EDGE-07-lowercase-policy"),
        pytest.param("fnol_edge.json", "EDGE-09", id="EDGE-09-collision-named-perils"),
        pytest.param("fnol_edge.json", "EDGE-10", id="EDGE-10-cancelled-and-expired"),
    ],
)
def test_notification_request_accepts_payloads_that_survive_to_rules(
    filename: str, payload_id: str
) -> None:
    NotificationRequest.model_validate(load_payload(filename, payload_id))


@pytest.mark.parametrize(
    ("filename", "payload_id"),
    [
        pytest.param("fnol_edge.json", "EDGE-08", id="EDGE-08-amount-omitted"),
        pytest.param("fnol_edge.json", "EDGE-11", id="EDGE-11-flood"),
        pytest.param("fnol_edge.json", "EDGE-12", id="EDGE-12-three-decimals"),
    ],
)
def test_notification_request_rejects_payloads_that_fail_at_the_model(
    filename: str, payload_id: str
) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(load_payload(filename, payload_id))


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(without_field("policy_number"), id="missing-policy-number"),
        pytest.param(without_field("loss_date"), id="missing-loss-date"),
        pytest.param(without_field("claim_type"), id="missing-claim-type"),
        pytest.param(without_field("estimated_amount"), id="missing-estimated-amount"),
        pytest.param(with_override(policy_number=""), id="empty-policy-number"),
        pytest.param(with_override(loss_date="not-a-date"), id="loss-date-not-yyyy-mm-dd"),
        pytest.param(with_override(claim_type="flood"), id="claim-type-not-in-vocabulary"),
        pytest.param(with_override(claim_type=""), id="empty-claim-type"),
        pytest.param(
            with_override(estimated_amount=Decimal("0.00")), id="amount-zero"
        ),
        pytest.param(
            with_override(estimated_amount=Decimal("-1.00")), id="amount-negative"
        ),
        pytest.param(
            with_override(estimated_amount=Decimal("3499.999")),
            id="amount-three-decimal-places",
        ),
        pytest.param(with_override(unexpected="nope"), id="extra-field-forbidden"),
    ],
)
def test_notification_request_rejects_each_declared_constraint(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        NotificationRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("payload", "expected_date", "expected_amount"),
    [
        pytest.param(
            well_formed(),
            date(2026, 4, 2),
            Decimal("4200.00"),
            id="typed-python-values",
        ),
        pytest.param(
            load_payload("fnol_valid.json", "VALID-01"),
            date(2026, 4, 2),
            Decimal("4200.00"),
            id="VALID-01-from-json",
        ),
        pytest.param(
            with_override(description=None),
            date(2026, 4, 2),
            Decimal("4200.00"),
            id="description-null",
        ),
    ],
)
def test_accepted_request_stores_date_and_decimal_not_strings(
    payload: dict[str, object],
    expected_date: date,
    expected_amount: Decimal,
) -> None:
    request = NotificationRequest.model_validate(payload)
    assert request.loss_date == expected_date
    assert type(request.loss_date) is date
    assert request.estimated_amount == expected_amount
    assert type(request.estimated_amount) is Decimal


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(well_formed_policy(), id="standard-not-cancelled"),
        pytest.param(
            policy_with(cancellation_date=date(2026, 1, 15)),
            id="cancelled-policy-has-a-date",
        ),
        pytest.param(
            policy_with(
                product="personal_auto_named_perils",
                permitted_claim_types=["theft", "glass", "weather", "liability"],
            ),
            id="named-perils-subset",
        ),
        pytest.param(policy_without("cancellation_date"), id="omitted-cancellation-is-none"),
    ],
)
def test_policy_accepts_well_formed_records(payload: dict[str, object]) -> None:
    Policy.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(policy_without("policy_number"), id="missing-policy-number"),
        pytest.param(policy_without("product"), id="missing-product"),
        pytest.param(policy_without("effective_date"), id="missing-effective-date"),
        pytest.param(policy_without("expiry_date"), id="missing-expiry-date"),
        pytest.param(policy_without("limit"), id="missing-limit"),
        pytest.param(policy_without("permitted_claim_types"), id="missing-permitted-types"),
        pytest.param(policy_with(policy_number=""), id="empty-policy-number"),
        pytest.param(policy_with(effective_date="not-a-date"), id="effective-date-garbage"),
        pytest.param(policy_with(expiry_date="not-a-date"), id="expiry-date-garbage"),
        pytest.param(policy_with(limit=Decimal("0.00")), id="limit-zero"),
        pytest.param(policy_with(limit=Decimal("-1.00")), id="limit-negative"),
        pytest.param(policy_with(limit=Decimal("50000.999")), id="limit-three-decimals"),
        pytest.param(
            policy_with(permitted_claim_types=["collision", "flood"]),
            id="permitted-type-not-in-vocabulary",
        ),
        pytest.param(policy_with(unexpected="nope"), id="extra-field-forbidden"),
    ],
)
def test_policy_rejects_each_declared_constraint(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Policy.model_validate(payload)


@pytest.mark.parametrize(
    ("policy_number", "expect_cancelled"),
    [
        pytest.param("MOT-4471", False, id="MOT-4471-cancellation-absent"),
        pytest.param("MOT-4481", False, id="MOT-4481-named-perils"),
        pytest.param("MOT-4497", True, id="MOT-4497-cancellation-present"),
    ],
)
def test_policy_builds_from_policy_record_with_date_and_decimal(
    policy_number: str, expect_cancelled: bool
) -> None:
    record = StubPolicyClient().get_policy(policy_number)
    policy = Policy(
        policy_number=record.policy_number,
        product=record.product,
        effective_date=record.effective_date,
        expiry_date=record.expiry_date,
        cancellation_date=record.cancellation_date,
        limit=record.limit,
        permitted_claim_types=cast(list[ClaimType], list(record.permitted_claim_types)),
    )
    assert type(policy.effective_date) is date
    assert type(policy.expiry_date) is date
    assert type(policy.limit) is Decimal
    if expect_cancelled:
        assert policy.cancellation_date is not None
        assert type(policy.cancellation_date) is date
    else:
        assert policy.cancellation_date is None


@pytest.mark.parametrize(
    ("rule", "code"),
    [
        pytest.param("V-1", "POLICY_NOT_FOUND", id="policy-not-found"),
        pytest.param("V-7", "POLICY_CANCELLED", id="policy-cancelled"),
        pytest.param("V-6", "DUPLICATE_NOTIFICATION", id="duplicate"),
    ],
)
def test_rule_failure_keeps_rule_and_code_separate(rule: str, code: str) -> None:
    failure = RuleFailure(rule=rule, code=code)
    assert failure.rule == rule
    assert failure.code == code


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="missing-both-fields"),
        pytest.param({"rule": "V-1"}, id="missing-code"),
        pytest.param({"code": "POLICY_NOT_FOUND"}, id="missing-rule"),
    ],
)
def test_rule_failure_requires_both_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RuleFailure.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("rule", "V-2", id="cannot-change-rule"),
        pytest.param("code", "LOSS_BEFORE_INCEPTION", id="cannot-change-code"),
    ],
)
def test_rule_failure_is_immutable(field: str, value: str) -> None:
    failure = RuleFailure(rule="V-1", code="POLICY_NOT_FOUND")
    with pytest.raises(ValidationError):
        setattr(failure, field, value)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(well_formed_recorded(), id="full-recorded-notification"),
        pytest.param(recorded_with(description=None), id="description-null"),
        pytest.param(recorded_without("description"), id="description-omitted"),
    ],
)
def test_recorded_notification_accepts_well_formed_records(
    payload: dict[str, object],
) -> None:
    RecordedNotification.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(recorded_without("policy_number"), id="missing-policy-number"),
        pytest.param(recorded_without("loss_date"), id="missing-loss-date"),
        pytest.param(recorded_without("claim_type"), id="missing-claim-type"),
        pytest.param(recorded_without("estimated_amount"), id="missing-amount"),
        pytest.param(recorded_without("claim_reference"), id="missing-claim-reference"),
        pytest.param(recorded_with(policy_number=""), id="empty-policy-number"),
        pytest.param(recorded_with(claim_type="flood"), id="claim-type-not-in-vocabulary"),
        pytest.param(recorded_with(estimated_amount=Decimal("0.00")), id="amount-zero"),
        pytest.param(
            recorded_with(estimated_amount=Decimal("3499.999")),
            id="amount-three-decimals",
        ),
        pytest.param(recorded_with(unexpected="nope"), id="extra-field-forbidden"),
    ],
)
def test_recorded_notification_rejects_each_declared_constraint(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        RecordedNotification.model_validate(payload)


@pytest.mark.parametrize(
    ("payload", "expected_date", "expected_amount", "expected_reference"),
    [
        pytest.param(
            well_formed_recorded(),
            date(2026, 4, 2),
            Decimal("4200.00"),
            "CLM-2026-000317",
            id="typed-python-values",
        ),
    ],
)
def test_recorded_notification_stores_date_decimal_and_reference(
    payload: dict[str, object],
    expected_date: date,
    expected_amount: Decimal,
    expected_reference: str,
) -> None:
    recorded = RecordedNotification.model_validate(payload)
    assert recorded.loss_date == expected_date
    assert type(recorded.loss_date) is date
    assert recorded.estimated_amount == expected_amount
    assert type(recorded.estimated_amount) is Decimal
    assert recorded.claim_reference == expected_reference
