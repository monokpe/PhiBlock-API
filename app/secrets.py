"""Secrets management helper.

Provides a lightweight wrapper that prefers AWS Secrets Manager when
`USE_AWS_SECRETS` is truthy, and falls back to environment variables.

Usage:
    from app.secrets import secrets
    db_url = secrets.get('DATABASE_URL')
    db_creds = secrets.get('my/database/creds')  # may return dict

This module is intentionally dependency-light: `boto3` is optional.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Optional


class SecretsManager:
    def __init__(self) -> None:
        self.use_aws = os.getenv("USE_AWS_SECRETS", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        self.region = os.getenv("AWS_REGION")
        self.client = None
        if self.use_aws:
            try:
                import boto3  # imported lazily so boto3 is optional

                kwargs = {}
                if self.region:
                    kwargs["region_name"] = self.region
                self.client = boto3.client("secretsmanager", **kwargs)
            except Exception:
                # If boto3 isn't installed or client fails to initialize, fall back to env
                self.client = None

    @lru_cache(maxsize=128)
    def _fetch_secret_raw(self, name: str) -> Optional[Any]:
        """Fetch raw secret value from AWS Secrets Manager or env var.

        Returns parsed JSON when possible, otherwise a string.
        """
        # Try AWS Secrets Manager first
        if self.client:
            try:
                resp = self.client.get_secret_value(SecretId=name)
                secret = resp.get("SecretString") or resp.get("SecretBinary")
                if secret is None:
                    return None
                if isinstance(secret, (bytes, bytearray)):
                    try:
                        secret = secret.decode()
                    except Exception:
                        # return raw binary if decoding fails
                        return secret
                try:
                    return json.loads(secret)
                except Exception:
                    return secret
            except Exception:
                # any AWS error falls back to env variables
                pass

        # Fallback to environment variables
        value = os.getenv(name)
        if value is None:
            # Support a common pattern: allow JSON stored under an upper-case key
            # or a namespaced key mapping like 'MY_SERVICE__CREDS'
            return None
        try:
            return json.loads(value)
        except Exception:
            return value

    def get(self, name: str, key: Optional[str] = None) -> Optional[Any]:
        """Get a secret by name. If key is provided and the secret is a dict,
        return the nested value.
        """
        secret = self._fetch_secret_raw(name)
        if secret is None:
            return None
        if key and isinstance(secret, dict):
            return secret.get(key)
        return secret


# singleton instance for simple imports
secrets = SecretsManager()


__all__ = ["SecretsManager", "secrets"]
