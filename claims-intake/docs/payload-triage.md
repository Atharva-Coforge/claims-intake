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

**The ambiguity.** EDGE-12 has 3 decimal places. In all the other requests we have 2 decimal places and therefore we do not know what to do with 3 decimal places.

**Decision.** Return malformed request.

**Authority.** In all the other requests we have 2 decimal places.

**Rejected alternative.** Accept EDGE-12. EDGE-12 has 3 decimal places and therefore we do not know what to do with 3 decimal places.

**Contract amended.** Return malformed request.

### Decision 2

**Payload.** EDGE-07

**The ambiguity.** EDGE-07 has lower case. In all the other requests we have upper case and therefore we do not know what to do with lower case.

**Decision.** Return policy not found.

**Authority.** In all the other requests we have upper case.

**Rejected alternative.** Accept EDGE-07. EDGE-07 has lower case and therefore we do not know what to do with lower case.

**Contract amended.** Return policy not found.

### Decision 3

**Payload.** EDGE-11

**The ambiguity.** EDGE-11 has flood. In all the other requests we have collision, theft, glass, liability or weather and therefore we do not know what to do with flood.

**Decision.** Return malformed request.

**Authority.** In all the other requests we have collision, theft, glass, liability or weather.

**Rejected alternative.** Accept EDGE-11. EDGE-11 has flood and therefore we do not know what to do with flood.

**Contract amended.** Return malformed request.