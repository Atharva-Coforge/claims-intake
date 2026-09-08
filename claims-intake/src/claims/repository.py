"""Persistence for recorded claims.

An in-memory store is sufficient for Week 1 and is deliberate rather than a
shortcut. The rules do not know where a claim is stored, so replacing this
with a database in a later week is a change to one module.

The duplicate check that `WI-0151` describes is a query against what has been
recorded, which is why it belongs here rather than in the rule table.

Day 2 assignment. Implement against `docs/api-contract.md` section 3.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from claims.models import ClaimRecord


class NotificationRepository:
    """Stores `ClaimRecord`s and issues claim references.

    Recording, reference generation, and duplicate lookup are separate methods.
    There is no reject path: a `RuleFailure` is a different type, so WI-0151
    AC-3 is true of the design rather than of the caller remembering not to
    write.
    """

    def __init__(self) -> None:
        self._records: list[ClaimRecord] = []
        self._next_sequence: int = 1

    def issue_claim_reference(self) -> str:
        """Return the next unused `CLM-YYYY-NNNNNN`. Never reissued."""
        year = datetime.now(tz=UTC).date().year
        sequence = self._next_sequence
        self._next_sequence += 1
        return f"CLM-{year}-{sequence:06d}"

    def record(self, claim: ClaimRecord) -> ClaimRecord:
        """Persist a `ClaimRecord`.

        WI-0151 AC-3: only a `ClaimRecord` can be stored. A `NotificationRequest`
        or `RuleFailure` is refused so a rejection cannot become the match a
        later submit duplicates.
        """
        if not isinstance(claim, ClaimRecord):
            raise TypeError(
                "NotificationRepository.record stores ClaimRecord only"
            )
        self._records.append(claim)
        return claim

    def find_matching(
        self,
        policy_number: str,
        loss_date: date,
        claim_type: str,
    ) -> ClaimRecord | None:
        """Return the stored `ClaimRecord` matching all three values.

        `WI-0151` AC-1 fixes which fields constitute a match. This method reads
        `_records` only, so a refusal that was never a `ClaimRecord` cannot match.
        """
        for recorded in self._records:
            if (
                recorded.policy_number == policy_number
                and recorded.loss_date == loss_date
                and recorded.claim_type == claim_type
            ):
                return recorded
        return None
