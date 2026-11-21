"""JWT helpers and auth decorators (JWT bearer token first, cookie session second)."""
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, jsonify, request, session

logger = logging.getLogger(__name__)


def create_auth_token(user_id, username, role):
    """Create a signed JWT for stateless authentication."""
    cfg = current_app.config
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": now + timedelta(hours=cfg["JWT_EXPIRES_HOURS"]),
        "iat": now,
    }
    return jwt.encode(payload, cfg["JWT_SECRET_KEY"], algorithm="HS256")


def get_token_identity():
    """Return the JWT payload from the Authorization header, or None."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    try:
        return jwt.decode(auth_header[7:], current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"])
    except jwt.InvalidTokenError:  # includes ExpiredSignatureError
        return None


def login_required(f):
    """Require an authenticated user (JWT or session)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        identity = get_token_identity()
        if identity:
            session["user_id"] = identity["user_id"]
            session["username"] = identity["username"]
            session["role"] = identity.get("role", "user")
            return f(*args, **kwargs)
        if "user_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    """Require an authenticated user with the admin role."""

    @wraps(f)
    def decorated(*args, **kwargs):
        identity = get_token_identity()
        if identity:
            if identity.get("role") != "admin":
                return jsonify({"error": "Admin access required"}), 403
            session["user_id"] = identity["user_id"]
            session["username"] = identity["username"]
            session["role"] = identity["role"]
            return f(*args, **kwargs)
        if "user_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        if session.get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)

    return decorated
