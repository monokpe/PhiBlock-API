import importlib
import json
import os
import sys

# Ensure repository root is on sys.path so `import app` works when run directly
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

out = {}

modules = [
    ("app.secrets", None),
    ("app.audit_encryption", None),
    ("app.rate_limiting", None),
    ("app.webhook_security", None),
    ("app.middleware", None),
]

for mod, _ in modules:
    try:
        importlib.import_module(mod)
        out[mod] = "ok"
    except Exception as e:
        out[mod] = f"error: {e}"

# small function checks
try:
    from app.webhook_security import is_allowed_webhook, sign_payload

    out["webhook_allowed_example"] = is_allowed_webhook("https://example.com")
    out["webhook_sign_example"] = list(sign_payload({"x": 1}, "secret").keys())
except Exception as e:
    out["webhook_checks"] = f"error: {e}"

try:
    from app.audit_encryption import AuditLogFilter, get_audit_encryptor

    out["audit_sensitive_ssn"] = AuditLogFilter.is_sensitive("ssn", ["HIPAA"])
    enc = get_audit_encryptor()
    out["audit_enabled"] = enc.enabled
except Exception as e:
    out["audit_checks"] = f"error: {e}"

try:
    from app.detection import detect_pii

    out["detect_pii"] = detect_pii("My SSN is 123-45-6789")
except Exception as e:
    out["detect_pii"] = f"error: {e}"

