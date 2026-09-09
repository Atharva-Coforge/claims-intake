"""HTTP surface against `docs/api-contract.md` sections 5 and 6.

Exercises `POST /notifications` on the real app with dependency overrides.
Payloads come from `data/fnol_*.json`. Assertions cover status, `code`, and the
§5.1 detail keys for each refusal.
"""

# Suggestion. tests/integration/test_routes.py never posts EDGE-11, EDGE-12, or
# EDGE-10. Day 1 said the edge set is the source for the integration cases. The
# suite meets "one parse failure" and "one refusal per rule," but it does not
# prove the three rows that are easy to get wrong at the HTTP boundary.

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import app, get_policy_client, get_repository
from claims.policy_client import LookupFailureReason, StubPolicyClient
from claims.repository import NotificationRepository

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CLAIM_REFERENCE_PATTERN = re.compile(r"^CLM-\d{4}-\d{6}$")
ENDPOINT = "/notifications"

DETAIL_KEYS_BY_CODE: dict[str, tuple[str, ...]] = {
    "MALFORMED_REQUEST": (),
    "POLICY_NOT_FOUND": ("policy_number",),
    "LOSS_BEFORE_INCEPTION": ("loss_date", "effective_date"),
    "POLICY_CANCELLED": ("loss_date", "cancellation_date"),
    "LOSS_AFTER_EXPIRY": ("loss_date", "expiry_date"),
    "AMOUNT_EXCEEDS_LIMIT": ("estimated_amount",),
    "TYPE_NOT_COVERED": ("claim_type",),
    "DUPLICATE_NOTIFICATION": ("claim_reference",),
    "POLICY_MASTER_TIMEOUT": ("policy_number", "reason"),
    "POLICY_MASTER_UNREACHABLE": ("policy_number", "reason"),
    "POLICY_MASTER_UNPARSABLE": ("policy_number", "reason"),
}


def load_payload(filename: str, payload_id: str) -> dict[str, Any]:
    records: list[dict[str, Any]] = json.loads((DATA_DIR / filename).read_text())
    for record in records:
        if record["id"] == payload_id:
            payload = record["payload"]
            assert isinstance(payload, dict)
            return dict(payload)
    raise KeyError(f"{payload_id} not found in {filename}")


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository()


@pytest.fixture
def policy_client() -> StubPolicyClient:
    return StubPolicyClient()


@pytest.fixture
def client(
    policy_client: StubPolicyClient, repository: NotificationRepository
) -> Iterator[TestClient]:
    """Real app with a fresh stub master and empty repository per test."""
    app.dependency_overrides[get_policy_client] = lambda: policy_client
    app.dependency_overrides[get_repository] = lambda: repository
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def assert_refusal(
    response: Any,
    *,
    status: int,
    code: str,
    **detail: object,
) -> dict[str, Any]:
    """Assert status, code, §5.1 detail keys, and any expected detail values."""
    assert response.status_code == status
    body = response.json()
    assert isinstance(body, dict)
    assert body["code"] == code
    assert "message" in body
    assert isinstance(body["detail"], dict)
    for key in DETAIL_KEYS_BY_CODE[code]:
        assert key in body["detail"]
    for key, expected in detail.items():
        assert body["detail"][key] == expected
    return body


def test_acceptance_returns_201_and_claim_reference(client: TestClient) -> None:
    """VALID-01: contract §3 success response."""
    response = client.post(ENDPOINT, json=load_payload("fnol_valid.json", "VALID-01"))
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "recorded"
    assert CLAIM_REFERENCE_PATTERN.fullmatch(body["claim_reference"])


def test_v1_policy_not_found(client: TestClient) -> None:
    """EDGE-07: V-1 `POLICY_NOT_FOUND` (422)."""
    payload = load_payload("fnol_edge.json", "EDGE-07")
    response = client.post(ENDPOINT, json=payload)
    assert_refusal(
        response,
        status=422,
        code="POLICY_NOT_FOUND",
        policy_number=payload["policy_number"],
    )


def test_v2_loss_before_inception(client: TestClient) -> None:
    """EDGE-05: V-2 `LOSS_BEFORE_INCEPTION` (422)."""
    payload = load_payload("fnol_edge.json", "EDGE-05")
    response = client.post(ENDPOINT, json=payload)
    assert_refusal(
        response,
        status=422,
        code="LOSS_BEFORE_INCEPTION",
        loss_date=payload["loss_date"],
        effective_date="2026-04-15",
    )


def test_v3_loss_after_expiry(client: TestClient) -> None:
    """INVALID-03: V-3 `LOSS_AFTER_EXPIRY` (422); not in the edge set."""
    payload = load_payload("fnol_invalid.json", "INVALID-03")
    response = client.post(ENDPOINT, json=payload)
    assert_refusal(
        response,
        status=422,
        code="LOSS_AFTER_EXPIRY",
        loss_date=payload["loss_date"],
        expiry_date="2026-02-28",
    )


def test_v4_amount_exceeds_limit(client: TestClient) -> None:
    """EDGE-06: V-4 `AMOUNT_EXCEEDS_LIMIT` (422)."""
    payload = load_payload("fnol_edge.json", "EDGE-06")
    response = client.post(ENDPOINT, json=payload)
    assert_refusal(
        response,
        status=422,
        code="AMOUNT_EXCEEDS_LIMIT",
        estimated_amount=payload["estimated_amount"],
    )


def test_v5_type_not_covered(client: TestClient) -> None:
    """EDGE-09: V-5 `TYPE_NOT_COVERED` (422)."""
    payload = load_payload("fnol_edge.json", "EDGE-09")
    response = client.post(ENDPOINT, json=payload)
    assert_refusal(
        response,
        status=422,
        code="TYPE_NOT_COVERED",
        claim_type=payload["claim_type"],
    )


def test_v6_duplicate_after_valid_01(client: TestClient) -> None:
    """INVALID-06 after recording VALID-01: V-6 `DUPLICATE_NOTIFICATION` (409)."""
    first = client.post(ENDPOINT, json=load_payload("fnol_valid.json", "VALID-01"))
    assert first.status_code == 201
    claim_reference = first.json()["claim_reference"]

    response = client.post(ENDPOINT, json=load_payload("fnol_invalid.json", "INVALID-06"))
    assert_refusal(
        response,
        status=409,
        code="DUPLICATE_NOTIFICATION",
        claim_reference=claim_reference,
    )


def test_v7_policy_cancelled(client: TestClient) -> None:
    """EDGE-04: V-7 `POLICY_CANCELLED` (422)."""
    payload = load_payload("fnol_edge.json", "EDGE-04")
    response = client.post(ENDPOINT, json=payload)
    assert_refusal(
        response,
        status=422,
        code="POLICY_CANCELLED",
        loss_date=payload["loss_date"],
        cancellation_date="2026-01-15",
    )


def test_missing_field_is_malformed_request(client: TestClient) -> None:
    """EDGE-08: missing `estimated_amount` → 400 `MALFORMED_REQUEST`."""
    response = client.post(ENDPOINT, json=load_payload("fnol_edge.json", "EDGE-08"))
    assert_refusal(response, status=400, code="MALFORMED_REQUEST")


def test_extra_field_on_valid_body_is_malformed_request(client: TestClient) -> None:
    """Extra field on a valid body is refused, not ignored. Contract §2.2 / §2.4."""
    payload = load_payload("fnol_valid.json", "VALID-01")
    payload["unexpected"] = "nope"
    response = client.post(ENDPOINT, json=payload)
    assert_refusal(response, status=400, code="MALFORMED_REQUEST")


@pytest.mark.parametrize(
    ("reason", "status", "code"),
    [
        pytest.param("timeout", 504, "POLICY_MASTER_TIMEOUT", id="timeout"),
        pytest.param("unreachable", 503, "POLICY_MASTER_UNREACHABLE", id="unreachable"),
        pytest.param("unparsable", 502, "POLICY_MASTER_UNPARSABLE", id="unparsable"),
    ],
)
def test_policy_master_lookup_failures_are_5xx(
    client: TestClient,
    policy_client: StubPolicyClient,
    reason: LookupFailureReason,
    status: int,
    code: str,
) -> None:
    """StubPolicyClient(fail_with=…): none of these is 4xx; not POLICY_NOT_FOUND."""
    policy_client.fail_with = reason
    payload = load_payload("fnol_valid.json", "VALID-01")
    response = client.post(ENDPOINT, json=payload)
    assert response.status_code >= 500
    assert_refusal(
        response,
        status=status,
        code=code,
        policy_number=payload["policy_number"],
        reason=reason,
    )
