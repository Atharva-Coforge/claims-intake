# Agent decision log

Two changes the agent produced during Day 3. One was accepted. One was rejected and corrected. Each reason is a contract line, an acceptance criterion, or a failure that would have occurred. Preference is not a reason.

## Accepted: V-6 stays out of `POLICY_RULES`

**What it produced.** A comment and a call sequence in `src/claims/service.py`: `POLICY_RULES` holds only V-2, V-7, V-3, V-5, and V-4. `evaluate_not_duplicate` is a separate method. `submit_notification` runs V-1, then the first three policy rules, then V-6, then V-5 and V-4.

**What we decided.** Keep that placement.

**Reason.** Contract section 4.1 fixes the order as V-1, V-2, V-7, V-3, V-6, V-5, V-4 and stops at the first failure. V-6 needs the repository (WI-0151 AC-1). Putting `find_matching` inside `POLICY_RULES` would mix deciding with storing, which the assignment forbids. Calling V-6 after V-3 and before V-5 is the only arrangement that keeps both the order and that split. A duplicate that is also over the limit must return `DUPLICATE_NOTIFICATION`, not `AMOUNT_EXCEEDS_LIMIT`. That is the failure `test_submit_notification_reports_v6_before_later_rules` would have reported if V-6 ran last.

## Rejected: `evaluate_notification` returning `ValidationOutcome`

**What it produced.** The first draft of `tests/unit/test_validation.py` treated `evaluate_notification` like a rule: `assert_passed(outcome)` and `outcome.passed is False` on a `ValidationOutcome`.

**What we decided.** Correct the tests before any rule was implemented. Pass is `None`. Fail is `RuleFailure(rule=..., code=...)`. `ValidationOutcome` stays the return type of each rule and of `submit_notification`.

**Reason.** The Day 3 interface (C3) fixes `evaluate_notification(notification, policy) -> RuleFailure | None`. The acceptance criterion is the same: that function takes only a notification and a policy, performs no I/O, and writes nothing. Returning `ValidationOutcome` would have made it the same object as `submit_notification`, so a caller could not tell a policy-only decision from an orchestrated submit. Tomorrow’s HTTP layer calls `submit_notification` and maps `ValidationOutcome`; it is not supposed to receive that type from `evaluate_notification`. Leaving the first draft would have failed C3 and the criterion that `evaluate_notification` is a side-effect-free decision.
