"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.

Day 2 assignment. Implement these against `docs/api-contract.md` sections 2 and 3.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Distinct vocabularies from contract section 4.2. Separate types so a rule
# identifier cannot be passed where an error code is expected.
RuleId = Literal["V-1", "V-2", "V-3", "V-4", "V-5", "V-6", "V-7"]
ErrorCode = Literal[
    "POLICY_NOT_FOUND",
    "LOSS_BEFORE_INCEPTION",
    "LOSS_AFTER_EXPIRY",
    "AMOUNT_EXCEEDS_LIMIT",
    "TYPE_NOT_COVERED",
    "DUPLICATE_NOTIFICATION",
    "POLICY_CANCELLED",
]


class NotificationRequest(BaseModel):
    """A first notice of loss as submitted by the claims portal.

    Fields and their constraints are specified in contract section 2.2. The model
    is responsible for the shape of the request and for nothing else. Whether the
    policy exists, whether the loss falls inside the term, and whether the amount
    is within the limit are rules, and rules live in `service.py`.

    `policy_number` is declared so that the V-1 rule in `service.py` has something
    to read. Every other field, and every constraint on every field including this
    one, is Day 2's work.
    """

    model_config = ConfigDict(extra='forbid')

    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: Literal['collision', 'theft', 'glass', 'liability', 'weather'] 
    estimated_amount: Decimal = Field(gt=0, decimal_places=2)
    description: str | None = None


class Policy(BaseModel):
    """A policy as this service works with it.

    Built from the `PolicyRecord` the policy client returns. The fields the rules
    compare against are the reason this model exists.

    Day 2 assignment: declare the fields.
    """

    model_config = ConfigDict(extra='forbid')

    policy_number: str = Field(min_length=1) 
    effective_date: date 
    expiry_date: date
    product: str
    cancellation_date: date | None
    limit: Decimal = Field(gt=0, decimal_places=2)
    permitted_claim_types: list[Literal['collision', 'theft', 'glass', 'liability', 'weather']]

class ClaimRecord(BaseModel):
    """A recorded claim: an accepted notification plus its issued reference.

    This is the only type the repository stores. A refused notification is a
    `NotificationRequest` plus a `RuleFailure` and can never be a `ClaimRecord`.
    """

    model_config = ConfigDict(extra='forbid')

    policy_number: str = Field(min_length=1)
    loss_date: date
    claim_type: Literal['collision', 'theft', 'glass', 'liability', 'weather']
    estimated_amount: Decimal = Field(gt=0, decimal_places=2)
    description: str | None = None
    # Contract section 3: CLM-YYYY-NNNNNN. A free string would let a bad
    # reference become the value every downstream system keys on.
    claim_reference: str = Field(pattern=r"^CLM-\d{4}-\d{6}$")

class RuleFailure(BaseModel):
    """A rule that refused a notification, with the contract code it produced.

    `rule` and `code` are different types so `V-1` cannot be stored as a `code`
    and `POLICY_NOT_FOUND` cannot be stored as a `rule`. Frozen so a later
    reader cannot rewrite the decision.
    """

    model_config = ConfigDict(frozen=True)
    rule: RuleId
    code: ErrorCode
