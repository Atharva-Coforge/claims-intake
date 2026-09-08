"""Rule evaluation and notification submission.

This module owns the decision. It does not know it was reached over HTTP, which
is why it can be tested by calling a function with a typed object and asserting on
the result with no server running. It does not know where notifications are
stored either. It knows the rules.

V-6 is not in POLICY_RULES. Those entries are notification + policy only
(contract 4.2 V-2, V-7, V-3, V-5, V-4). V-6 needs the repository
(WI-0151). submit_notification runs it after V-3 and before V-5 so
section 4.1 order still holds: V-1, V-2, V-7, V-3, V-6, V-5, V-4.

`evaluate_policy_exists` ships written. It is the pattern every other rule
follows: take the notification and whatever it needs, decide, and return a
`ValidationOutcome` that names the rule and carries the values the decision was
made on. Nothing prints, nothing raises for an ordinary refusal, and nothing
reaches for a status code, because a status code is a fact about HTTP and this
module does not know about HTTP.

Day 3 assignment. Build the remaining rules test-first against
`docs/api-contract.md` section 4.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from claims.models import (
    ClaimRecord,
    ErrorCode,
    NotificationRequest,
    Policy,
    RuleFailure,
    RuleId,
)
from claims.policy_client import PolicyClient, PolicyNotFound
from claims.repository import NotificationRepository

ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]


@dataclass(frozen=True)
class ValidationOutcome:
    """The result of evaluating one rule, or of evaluating them all.

    `passed` is the only thing a caller has to branch on. When it is false, `rule`
    names the rule that decided it, `code` is the stable contract code, and
    `detail` carries the values that produced the decision so that the person
    reading the eventual error can see which input was wrong.

    There is no status code here. Contract section 6 maps a code to a status, and
    that mapping is applied at the HTTP boundary.
    """

    passed: bool
    rule: str | None = None
    code: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    claim_reference: str | None = None

    @classmethod
    def ok(cls) -> ValidationOutcome:
        return cls(passed=True)

    @classmethod
    def failed(cls, rule: str, code: str, **detail: Any) -> ValidationOutcome:
        return cls(passed=False, rule=rule, code=code, detail=detail)


PolicyRule = Callable[[NotificationRequest, Policy], ValidationOutcome]


def evaluate_policy_exists(
    notification: NotificationRequest,
    policy_client: PolicyClient,
) -> ValidationOutcome:
    """V-1. The policy must exist in the policy master.

    This rule is different from the others in one way that matters: it is the only
    one that reaches outside the service, so it is the only one that can fail for
    a reason that is not the caller's fault. `PolicyNotFound` is caught here and
    turned into an ordinary refusal, because a policy that does not exist is a
    fact about the caller's data. `PolicyLookupFailed` is deliberately not caught,
    because the caller did nothing wrong and the HTTP layer has to be able to tell
    the two apart. Contract section 6 fixes what each becomes.

    V-1 short circuits. Every other rule compares against a field on a policy, and
    if there is no policy there is nothing to compare against. Reporting
    LOSS_BEFORE_INCEPTION for a policy number that does not exist is not merely
    unhelpful, it is a false statement about the client's data (WI-0142, AC-4).
    """
    try:
        policy_client.get_policy(notification.policy_number)
    except PolicyNotFound:
        return ValidationOutcome.failed(
            rule="V-1",
            code="POLICY_NOT_FOUND",
            policy_number=notification.policy_number,
        )
    return ValidationOutcome.ok()


def evaluate_loss_after_inception(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-2. The loss must not precede policy inception.

    The boundary is stated in contract section 4.2 and in WI-0142 AC-3. A loss on
    the inception date is covered.
    """
    if notification.loss_date >= policy.effective_date:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-2",
        code="LOSS_BEFORE_INCEPTION",
        loss_date=notification.loss_date,
        effective_date=policy.effective_date,
    )


def evaluate_policy_not_cancelled(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-7. The policy must not be cancelled on the loss date.

    Contract section 4.2: `cancellation_date` is null, or `loss_date` is strictly
    before `cancellation_date`. A loss on the cancellation date is not covered.
    """
    if policy.cancellation_date is None or notification.loss_date < policy.cancellation_date:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-7",
        code="POLICY_CANCELLED",
        loss_date=notification.loss_date,
        cancellation_date=policy.cancellation_date,
    )


def evaluate_loss_before_expiry(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-3. The loss must not fall after the policy expiry date."""
    if notification.loss_date <= policy.expiry_date:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-3",
        code="LOSS_AFTER_EXPIRY",
        loss_date=notification.loss_date,
        expiry_date=policy.expiry_date,
    )


def evaluate_not_duplicate(
    notification: NotificationRequest,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """V-6. No recorded notification may share policy, loss date, and claim type.

    Contract section 4.2 and WI-0151. A previous refusal was never recorded, so it
    is not a duplicate.
    """
    recorded = repository.find_matching(
        notification.policy_number,
        notification.loss_date,
        notification.claim_type,
    )
    if recorded is None:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-6",
        code="DUPLICATE_NOTIFICATION",
        claim_reference=recorded.claim_reference,
    )


def evaluate_amount_within_limit(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-4. The estimated amount must not exceed the policy limit.

    An amount equal to the limit is within cover, per contract section 4.2.
    """
    if notification.estimated_amount <= policy.limit:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-4",
        code="AMOUNT_EXCEEDS_LIMIT",
        estimated_amount=notification.estimated_amount,
    )


def evaluate_claim_type_covered(
    notification: NotificationRequest,
    policy: Policy,
) -> ValidationOutcome:
    """V-5. The claim type must be permitted on the policy's product."""
    if notification.claim_type in policy.permitted_claim_types:
        return ValidationOutcome.ok()
    return ValidationOutcome.failed(
        rule="V-5",
        code="TYPE_NOT_COVERED",
        claim_type=notification.claim_type,
    )


POLICY_RULES: Sequence[PolicyRule] = (
    evaluate_loss_after_inception,
    evaluate_policy_not_cancelled,
    evaluate_loss_before_expiry,
    evaluate_claim_type_covered,
    evaluate_amount_within_limit,
)


def _rule_failure_from(outcome: ValidationOutcome) -> RuleFailure:
    return RuleFailure(
        rule=cast(RuleId, outcome.rule),
        code=cast(ErrorCode, outcome.code),
    )


def evaluate_notification(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """Evaluate the policy rules and return the outcome the caller sees.

    A notification can violate several rules at once and the caller sees one
    reason, so the order this function evaluates in is a caller-visible behavior.
    It is fixed by contract section 4.1 and by nothing else. If you find yourself
    choosing an order here, the contract is incomplete and the fix belongs there.
    """
    for rule in POLICY_RULES:
        outcome = rule(notification, policy)
        if not outcome.passed:
            return _rule_failure_from(outcome)
    return None


def submit_notification(
    notification: NotificationRequest,
    policy_client: PolicyClient,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """Validate, and record only if every rule passed.

    Nothing is written before the decision is made. A notification is either
    recorded with a claim reference or it does not exist, and there is no state in
    between for a later reader to interpret.
    """
    try:
        record = policy_client.get_policy(notification.policy_number)
    except PolicyNotFound:
        return ValidationOutcome.failed(
            rule="V-1",
            code="POLICY_NOT_FOUND",
            policy_number=notification.policy_number,
        )

    policy = Policy(
        policy_number=record.policy_number,
        product=record.product,
        effective_date=record.effective_date,
        expiry_date=record.expiry_date,
        cancellation_date=record.cancellation_date,
        limit=record.limit,
        permitted_claim_types=cast(list[ClaimType], list(record.permitted_claim_types)),
    )

    for rule in POLICY_RULES[:3]:
        outcome = rule(notification, policy)
        if not outcome.passed:
            return outcome

    outcome = evaluate_not_duplicate(notification, repository)
    if not outcome.passed:
        return outcome

    for rule in POLICY_RULES[3:]:
        outcome = rule(notification, policy)
        if not outcome.passed:
            return outcome

    claim = ClaimRecord(
        policy_number=notification.policy_number,
        loss_date=notification.loss_date,
        claim_type=notification.claim_type,
        estimated_amount=notification.estimated_amount,
        description=notification.description,
        claim_reference=repository.issue_claim_reference(),
    )
    stored = repository.record(claim)
    return ValidationOutcome(passed=True, claim_reference=stored.claim_reference)
