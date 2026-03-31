import base64
import os
from fastapi import Request, HTTPException

_auth_user = os.environ.get("AUTH_USERNAME", "").strip()
_auth_pass = os.environ.get("AUTH_PASSWORD", "").strip()
AUTH_ENABLED = bool(_auth_user and _auth_pass)


def require_auth(request: Request):
    """Basic Auth dependency. No-op when AUTH_USERNAME/AUTH_PASSWORD are unset."""
    if not AUTH_ENABLED:
        return
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            user, password = decoded.split(":", 1)
            if user == _auth_user and password == _auth_pass:
                return
        except Exception:
            pass
    raise HTTPException(
        status_code=401,
        detail="Authentication required.",
        headers={"WWW-Authenticate": 'Basic realm="Watcharr"'},
    )
