import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security import register_security
from app.webhook_security import sign_payload


def make_app():
    app = FastAPI()
    register_security(app)

    @app.post("/webhooks/test")
    async def webhook_receiver(payload: dict):
        return {"received": True, "payload": payload}

    return app


def test_webhook_signature_accepts_valid():
    os.environ["WEBHOOK_SIGNING_SECRET"] = "test-secret"
    app = make_app()
    client = TestClient(app)

    payload = {"hello": "world"}
    headers = sign_payload(payload, "test-secret")

    r = client.post("/webhooks/test", json=payload, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["received"] is True


def test_webhook_signature_rejects_invalid():
    os.environ["WEBHOOK_SIGNING_SECRET"] = "test-secret"
    app = make_app()
    client = TestClient(app)

    payload = {"hello": "world"}
    # Produce a signature with wrong secret
    headers = sign_payload(payload, "wrong-secret")

    r = client.post("/webhooks/test", json=payload, headers=headers)
    assert r.status_code == 401
