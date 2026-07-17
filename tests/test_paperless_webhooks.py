"""HTTP tests for Paperless webhook endpoints (enqueue only, no workflow execution)."""

from __future__ import annotations

from dbos import DBOS

from harness.jobs import JOBS_QUEUE


def test_webhook_requires_bearer(client):
    response = client.post("/webhooks/paperless", json={"documentId": 42})
    assert response.status_code == 401


def test_webhook_rejects_missing_document_id(client, auth_headers):
    response = client.post("/webhooks/paperless", json={}, headers=auth_headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "missing or invalid document id"


def test_webhook_accepts_document_id_in_body(client, auth_headers):
    response = client.post(
        "/webhooks/paperless",
        json={"documentId": 42},
        headers=auth_headers,
    )
    assert response.status_code == 202
    assert response.json() == {"accepted": True, "document_id": 42, "forced": False}

    queued = DBOS.list_queued_workflows(queue_name=JOBS_QUEUE)
    assert len(queued) == 1
    assert queued[0].workflow_id == "paperless:doc:42"


def test_webhook_accepts_document_id_in_url_query(client, auth_headers):
    response = client.post(
        "/webhooks/paperless",
        params={"url": "http://paperless/documents/99/"},
        headers=auth_headers,
    )
    assert response.status_code == 202
    assert response.json()["document_id"] == 99


def test_receipt_webhook_enqueues_receipt_workflow(client, auth_headers):
    response = client.post(
        "/webhooks/paperless/receipt",
        json={"document_id": 7},
        headers=auth_headers,
    )
    assert response.status_code == 202
    assert response.json() == {"accepted": True, "document_id": 7, "forced": False}

    queued = DBOS.list_queued_workflows(queue_name=JOBS_QUEUE)
    assert len(queued) == 1
    assert queued[0].workflow_id == "paperless:receipt:7"


def test_webhook_force_uses_unique_dedup_key(client, auth_headers):
    for _ in range(2):
        response = client.post(
            "/webhooks/paperless",
            json={"documentId": 42},
            params={"force": True},
            headers=auth_headers,
        )
        assert response.status_code == 202

    queued = DBOS.list_queued_workflows(queue_name=JOBS_QUEUE)
    assert len(queued) == 2
    assert queued[0].workflow_id != queued[1].workflow_id
