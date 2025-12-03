"""Security middleware and registration helpers.

Provides:
- CORS configuration (reads `CORS_ALLOWED_ORIGINS` env)
- `RequestSigningMiddleware` to validate incoming webhook signatures
- `register_security(app)` to wire middleware into FastAPI app

The signing middleware checks `X-Guardrails-Signature` and
`X-Guardrails-Timestamp` headers for requests under `/webhooks`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import webhook_security


class RequestSigningMiddleware(BaseHTTPMiddleware):
    """Validate webhook signatures for requests under `/webhooks`.

    This middleware is opt-in: if `WEBHOOK_SIGNING_SECRET` is not set, it
    will allow requests through unchanged.
    """

    def __init__(self, app, window_seconds: int = 300):
        super().__init__(app)
        self.window_seconds = int(os.getenv("WEBHOOK_SIGNATURE_WINDOW", str(window_seconds)))

    async def dispatch(self, request: Request, call_next: Callable):
        # Only validate webhook endpoints
        path = request.url.path or ""
        if not path.startswith("/webhooks"):
            return await call_next(request)

        secret = webhook_security.get_signing_secret()
        if not secret:
            # Not configured — allow through (opt-in behavior)
            return await call_next(request)

        sig_header = request.headers.get("x-guardrails-signature")
        ts_header = request.headers.get("x-guardrails-timestamp")

        if not sig_header or not ts_header:
            return JSONResponse({"detail": "Missing signature headers"}, status_code=401)

        try:
            # Validate timestamp (prevent replay)
            ts = datetime.fromisoformat(ts_header)
            now = datetime.now(timezone.utc)
            if abs((now - ts).total_seconds()) > self.window_seconds:
                return JSONResponse(
                    {"detail": "Signature timestamp outside allowed window"},
                    status_code=401,
                )
        except Exception:
            return JSONResponse({"detail": "Invalid timestamp format"}, status_code=401)

        try:
            body_bytes = await request.body()
            # Attempt to canonicalize if JSON
            try:
                parsed = json.loads(body_bytes.decode("utf-8"))
                canonical = json.dumps(parsed, separators=(",", ":"), sort_keys=True).encode(
                    "utf-8"
                )
            except Exception:
                canonical = body_bytes

            computed = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
            # Signature header may include algorithm prefix like 'sha256='
            header_sig = sig_header.split("=")[-1]
            if not hmac.compare_digest(computed, header_sig):
                return JSONResponse({"detail": "Invalid signature"}, status_code=401)

            # Reconstruct receive so downstream can read body
            async def receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            response = await call_next(Request(request.scope, receive))
            return response
        except Exception:
            return JSONResponse({"detail": "Signature verification failed"}, status_code=401)


def register_security(app: FastAPI) -> None:
    """Register security middleware and CORS configuration on `app`."""
    # CORS
    origins = (
        os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if os.getenv("CORS_ALLOWED_ORIGINS")
        else ["*"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Request signing middleware (for inbound webhooks)
    app.add_middleware(RequestSigningMiddleware)


__all__ = ["RequestSigningMiddleware", "register_security"]
