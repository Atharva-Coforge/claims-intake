# Claims Intake Service: API Contract

Version 0.4. Owned by the claims intake team. Consumed by the claims portal team.

This document is the authority on what the service accepts, what it returns, and under what conditions it refuses. Where the code and this document disagree, the document is correct and the code is a defect.

Sections 1 through 3 are fixed. Do not edit them.

## 1. Purpose and scope

The claims intake service accepts a first notice of loss from the claims portal, validates it against the policy master and a table of business rules, and either records a notification and issues a claim reference or refuses the submission with a specific reason.

**In scope.** Accepting a notification, validating it, and recording it. Issuing a claim reference. Reporting the reason a notification was refused.

**Out of scope.** Adjusting, reserving, payment, and any decision about coverage beyond the rules in section 4. The service decides whether a notification is well formed and admissible. It does not decide whether the claim will be paid.

**The policy master is a dependency, not part of this service.** The service reads policy records from it and does not write to it. A policy that cannot be read is a condition this contract specifies, and it is specified separately from a policy that does not exist, because the two require different action from the caller.

**Compatibility.** Adding a field to a response is a compatible change and callers must ignore fields they do not recognize. Adding a new error code is a compatible change and callers must fall through to default handling for a code they do not recognize. Changing the meaning of an existing code, removing a field, or changing a status code for an existing condition is not compatible and does not happen without a version increment agreed with the portal team.

## 2. Request



### 2.1 Endpoint

```
POST /notifications
Content-Type: application/json
```



### 2.2 Body


| Field              | Type    | Required | Notes                                                         |
| ------------------ | ------- | -------- | ------------------------------------------------------------- |
| `policy_number`    | string  | yes      | Identifier as held in the policy master. Not empty.           |
| `loss_date`        | string  | yes      | Calendar date, `YYYY-MM-DD`.                                  |
| `claim_type`       | string  | yes      | One of the values in 2.3. Not empty.                          |
| `estimated_amount` | decimal | yes      | United States dollars, two decimal places. Greater than zero. |
| `description`      | string  | no       | Free text. Absent and `null` are equivalent.                  |


The service rejects a body carrying a field not listed above. A misspelled field name is a defect in the caller's code, and accepting the payload with the field ignored would record a notification built from data the caller did not send.

### 2.3 Claim type vocabulary

`collision`, `theft`, `glass`, `liability`, `weather`.

Which of these are admissible on a given notification depends on the product the policy is written on. The vocabulary is fixed by this contract. The permitted subset is a property of the policy record and is evaluated by rule `V-5`.

### 2.4 Well formed against acceptable

A request that cannot be interpreted is refused with status `400`. This means the body was not valid JSON, a required field was absent, a field carried a value of the wrong type, or a field was present that this contract does not define. The caller's code is wrong.

A request that was interpreted and whose content is not admissible is refused with status `422`. The caller's data is wrong, and a person needs to see the reason.

This split is stated here once and holds without exception everywhere else in this document.

## 3. Success response

A notification that passes every rule in section 4 is recorded and the service responds:

```
201 Created
Content-Type: application/json

{
  "claim_reference": "CLM-2026-000317",
  "status": "recorded"
}
```

`claim_reference` matches the pattern `CLM-YYYY-NNNNNN`, where `YYYY` is the calendar year in which the notification was recorded and `NNNNNN` is a zero padded sequence. A claim reference is unique across all recorded notifications and is never reissued. It is the value the claims handler quotes and the value every downstream system keys on.

`status` is `recorded` on every success response this contract defines. It exists because the portal displays it and because a future state that is not `recorded` is foreseeable. Callers must not treat it as constant.

A refused notification is never recorded and no claim reference is issued. There is no partial outcome: either a notification exists with a reference, or nothing was written.

## 4. Validation



### 4.1 Evaluation order

Rules are not evaluated in identifier order. They are evaluated in this order: V-1, V-2, V-7, V-3, V-6, V-5, V-4.

Evaluation stops at the first failure. The caller receives that rule's code and status only. Later rules are not evaluated and their codes are not returned, even if they would also fail.

V-1 short-circuits: if it fails, no rule that reads a policy field is evaluated (WI-0142, AC-4). Reporting a date or amount failure for a policy number that does not exist would be a false statement about the caller's data.

V-7 is evaluated before V-3 because WI-0158 AC-4 requires it. A cancelled policy whose loss also falls after the original expiry must be reported as `POLICY_CANCELLED`, not `LOSS_AFTER_EXPIRY`. Identifier order would evaluate V-3 first and violate that criterion, which is why identifier order is not used.

### 4.2 Rule table


| ID  | Condition                                                                                                 | Code                     | Status |
| --- | --------------------------------------------------------------------------------------------------------- | ------------------------ | ------ |
| V-1 | `policy_number` exists in the policy master                                                               | `POLICY_NOT_FOUND`       | 422    |
| V-2 | `loss_date` >= policy `effective_date`                                                                    | `LOSS_BEFORE_INCEPTION`  | 422    |
| V-7 | `cancellation_date` is null, or `loss_date` < `cancellation_date` | `POLICY_CANCELLED`       | 422    |
| V-3 | `loss_date` <= policy `expiry_date`                                                                       | `LOSS_AFTER_EXPIRY`      | 422    |
| V-6 | no recorded notification exists with the same `policy_number`, `loss_date`, and `claim_type`  | `DUPLICATE_NOTIFICATION` | 409    |
| V-5 | `claim_type` permitted on the policy's product                                                            | `TYPE_NOT_COVERED`       | 422    |
| V-4 | `estimated_amount` <= policy `limit`                                                                      | `AMOUNT_EXCEEDS_LIMIT`   | 422    |


A loss on the inception date is covered: `loss_date` == policy `effective_date` satisfies V-2 (WI-0142, AC-3).

A loss on the cancellation date is not covered: `loss_date` == `cancellation_date` fails V-7 (WI-0158, AC-2). Cancellation takes effect at the start of that day.

A loss on the expiry date is covered: `loss_date` == policy `expiry_date` satisfies V-3.
An amount equal to the limit is within cover: `estimated_amount` == policy `limit` satisfies V-4.

A previous submission that was refused is not a duplicate: it was never recorded, so V-6 does not match it (WI-0151, AC-3).

### 4.3 Interpretation rules

These close readings that sections 2.2, 2.3, and 2.4 left open. A payload that fails one of them is refused before the rule table, except for exact policy-number match, which is how V-1 is evaluated.

`policy_number` is compared to the policy master character for character, including case. Section 2.2 requires the identifier as held in the master, so `mot-4471` is not `MOT-4471`. That comparison fails V-1 and returns `POLICY_NOT_FOUND`. Per WI-0142 AC-4, no later rule is evaluated.

A `claim_type` that is not one of the five values in section 2.3 cannot be interpreted. Section 2.4 maps that to status 400 and `MALFORMED_REQUEST`. V-5 is a different case: the value is in section 2.3, but it is not permitted on that policy's product.

`estimated_amount` must have exactly two decimal places, as section 2.2 states. Extra fractional digits mean the body cannot be interpreted. Section 2.4 maps that to status 400 and `MALFORMED_REQUEST`. It is not a 422 business-rule failure.

## 5. Error envelope

Every refusal uses this envelope:

{
  "code": "...",
  "message": "...",
  "detail": {}
}

`code` is a stable promise. Callers branch on it. Renaming a code is a breaking change. A code the caller does not recognize is handled by the default path in section 1.

`message` is not a stable promise. It is for a person to read. Callers must not parse it. The wording can change without a version increment.

`detail` is neither globally stable nor globally free. Its keys depend on `code`. Callers may rely only on the keys listed for that code in section 5.1. Extra keys may appear and must be ignored.

The three examples below are different kinds of failure. They are not three copies of the same handler.

A rule failure. The request was interpreted and a policy was read. A rule in section 4.2 decided. `detail` carries the values that rule compared.

{
  "code": "LOSS_BEFORE_INCEPTION",
  "message": "Loss date precedes policy inception.",
  "detail": {
    "loss_date": "2026-02-11",
    "effective_date": "2026-03-01"
  }
}

A request the service could not interpret. No rule in section 4.2 ran. `detail` has no guaranteed keys.

{
  "code": "MALFORMED_REQUEST",
  "message": "The request cannot be interpreted.",
  "detail": {}
}

A policy master that did not answer. This is not `POLICY_NOT_FOUND`: the master did not produce a usable result. No rule decided, so `detail` has no `rule` field.

{
  "code": "POLICY_MASTER_TIMEOUT",
  "message": "The policy master did not answer in time.",
  "detail": {
    "policy_number": "MOT-4471",
    "reason": "timeout"
  }
}

### 5.1 Detail fields callers may rely on

The JSON objects above are examples. Callers may rely only on the
fields listed here. Extra fields may appear and must be ignored.
A listed field is always present for that code.


| Code                        | Guaranteed `detail` fields       |
| --------------------------- | -------------------------------- |
| `MALFORMED_REQUEST`         | none (`detail` may be empty)     |
| `POLICY_NOT_FOUND`          | `policy_number`                  |
| `LOSS_BEFORE_INCEPTION`     | `loss_date`, `effective_date`    |
| `POLICY_CANCELLED`          | `loss_date`, `cancellation_date` |
| `LOSS_AFTER_EXPIRY`         | `loss_date`, `expiry_date`       |
| `AMOUNT_EXCEEDS_LIMIT`      | `estimated_amount`               |
| `TYPE_NOT_COVERED`          | `claim_type`                     |
| `DUPLICATE_NOTIFICATION`    | `claim_reference` (WI-0151 AC-2) |
| `POLICY_MASTER_TIMEOUT`     | `policy_number`, `reason`        |
| `POLICY_MASTER_UNREACHABLE` | `policy_number`, `reason`        |
| `POLICY_MASTER_UNPARSABLE`  | `policy_number`, `reason`        |


`message` is not in this table. Callers must not parse it.
`rule` may appear in `detail` and is not guaranteed.

## 6. Status code mapping


| Code                        | Status |
| --------------------------- | ------ |
| —                           | 201    |
| `MALFORMED_REQUEST`         | 400    |
| `POLICY_NOT_FOUND`          | 422    |
| `LOSS_BEFORE_INCEPTION`     | 422    |
| `POLICY_CANCELLED`          | 422    |
| `LOSS_AFTER_EXPIRY`         | 422    |
| `AMOUNT_EXCEEDS_LIMIT`      | 422    |
| `TYPE_NOT_COVERED`          | 422    |
| `DUPLICATE_NOTIFICATION`    | 409    |
| `POLICY_MASTER_TIMEOUT`     | 504    |
| `POLICY_MASTER_UNREACHABLE` | 503    |
| `POLICY_MASTER_UNPARSABLE`  | 502    |
