# Payload Triage

Every payload in `data/fnol_edge.json` classified against `docs/api-contract.md` as you have completed it. The classification records what the contract says the service does, which is not always what the payload obviously violates.

Fill one row per payload. Where a payload is accepted, leave the rule, code, and status columns as `-`.

## Classification

| Payload | Outcome  | Rule | Code                    | Status |
| ------- | -------- | ---- | ----------------------- | ------ |
| EDGE-01 | accepted | -    | -                       | -      |
| EDGE-02 | accepted | -    | -                       | -      |
| EDGE-03 | accepted | -    | -                       | -      |
| EDGE-04 | rejected | V-7  | `POLICY_CANCELLED`      | 422    |
| EDGE-05 | rejected | V-2  | `LOSS_BEFORE_INCEPTION` | 422    |
| EDGE-06 | rejected | V-4  | `AMOUNT_EXCEEDS_LIMIT`  | 422    |
| EDGE-07 | rejected | V-1  | `POLICY_NOT_FOUND`      | 422    |
| EDGE-08 | rejected | -    | `MALFORMED_REQUEST`     | 400    |
| EDGE-09 | rejected | V-5  | `TYPE_NOT_COVERED`      | 422    |
| EDGE-10 | rejected | V-7  | `POLICY_CANCELLED`      | 422    |
| EDGE-11 | rejected | -    | `MALFORMED_REQUEST`     | 400    |
| EDGE-12 | rejected | -    | `MALFORMED_REQUEST`     | 400    |

## Decision log

Three payloads cannot be classified against the contract as it shipped, because the contract left a decision unmade. For each one, record the ambiguity, the decision, its authority, and the alternative you rejected.

A decision recorded here and nowhere else has not been made. Amend `docs/api-contract.md` so that a reader of the contract alone could not arrive at the other reading.

### Decision 1

**Payload.** EDGE-12

**The ambiguity.** Section 2.2 says two decimal places, but the contract as shipped did not say whether extra decimal places are 400 (cannot interpret) or a valid number that should be accepted.

**Decision.** Reject with `MALFORMED_REQUEST` (400).

**Authority.** `docs/api-contract.md` section 4.3 rule 3: amount must have exactly two decimal places; three decimals are 400 malformed.

**Rejected alternative.** Accept EDGE-12 as a normal decimal, because `3499.999` is still a number.

**Contract amended.** Section 4.3 rule 3.

### Decision 2

**Payload.** EDGE-07

**The ambiguity.** V-1 asks whether the policy exists, but the contract as shipped did not say whether matching is case-sensitive.

**Decision.** Reject with `POLICY_NOT_FOUND` (422).

**Authority.** `docs/api-contract.md` section 4.3 rule 1: policy numbers match exactly as typed, including case. `mot-4471` is not `MOT-4471`, so V-1 fails.

**Rejected alternative.** Treat matching as case-insensitive and accept EDGE-07 as policy `MOT-4471`.

**Contract amended.** Section 4.3 rule 1.

### Decision 3

**Payload.** EDGE-11

**The ambiguity.** `flood` is a string, so a reader could treat it as 400 (not in the 2.3 list) or as 422 `TYPE_NOT_COVERED` (V-5).

**Decision.** Reject with `MALFORMED_REQUEST` (400).

**Authority.** `docs/api-contract.md` section 4.3 rule 2: a claim type not on the vocabulary list is 400 malformed. V-5 applies only when the type is on the list but the product does not cover it.

**Rejected alternative.** Reject EDGE-11 under V-5 with `TYPE_NOT_COVERED` (422).

**Contract amended.** Section 4.3 rule 2.

## Day 2 reconciliation

Compared every way `NotificationRequest` can refuse a payload against contract section 6.

The model refuses structurally unacceptable requests: extra fields, missing required fields, empty `policy_number`, a `loss_date` that is not a calendar date, a `claim_type` outside section 2.3 (EDGE-11 `flood`), `estimated_amount` missing (EDGE-08), not greater than zero, or not exactly two decimal places (EDGE-12). Each of those is a request that cannot be interpreted (section 2.4 and section 4.3). They all become `MALFORMED_REQUEST` with status 400.

`MALFORMED_REQUEST` is already in section 6. No new code or status was added.

How this was checked: `tests/unit/test_models.py` parametrizes the realistic payloads (EDGE-08, EDGE-11, EDGE-12 fail at the model; INVALID-* and EDGE-07 survive to the rules) and a violating case for every declared field constraint. All of those failures are Pydantic `ValidationError`, which this service maps to `MALFORMED_REQUEST`. Rule codes such as `POLICY_NOT_FOUND` are produced by Day 3, not by the models, and were already listed in section 6.