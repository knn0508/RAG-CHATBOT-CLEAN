"""Application factory for the RAG chatbot backend."""
import logging
import os

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_session import Session
from werkzeug.exceptions import HTTPException

from config import get_config

logger = logging.getLogger(__name__)

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(Exception)
    def handle_exception(e):
        if isinstance(e, HTTPException):
            if e.code == 404:
                return jsonify({"error": "Endpoint not found", "path": request.path}), 404
            if e.code == 405:
                return jsonify({"error": "Method not allowed", "method": request.method, "path": request.path}), 405
            return jsonify({"error": e.description}), e.code
        logger.exception("Unhandled error on %s %s", request.method, request.path)
        message = str(e) if app.debug else "Internal server error"
        return jsonify({"error": message}), 500


def _register_blob_sync(app: Flask, config) -> None:
    @app.after_request
    def sync_db_after_write(response):
        """Persist the SQLite DB to Blob Storage after document mutations (Vercel only)."""
        if (
            request.method in ("POST", "PUT", "DELETE", "PATCH")
            and request.path.startswith("/api/documents")
            and response.status_code < 500
        ):
            try:
                blob = app.extensions.get("blob_storage")
                if blob and blob.blob_enabled:
                    blob.sync_db_to_blob(config.DATABASE_FILE)
            except Exception:
                logger.exception("Blob DB sync failed")
        return response


def _register_frontend(app: Flask) -> None:
    """Serve the built React app (if present) for any non-API path."""

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        static = app.static_folder
        if path and os.path.exists(os.path.join(static, path)):
            return send_from_directory(static, path)
        index = os.path.join(static, "index.html")
        if os.path.exists(index):
            return send_from_directory(static, "index.html")
        return jsonify({"error": "Frontend not built", "path": request.path}), 404


def create_app(test_config: dict = None, rag_overrides: dict = None) -> Flask:
    """Create and configure the Flask application.

    ``test_config`` overrides Flask config keys; ``rag_overrides`` injects fake
    OpenAI client / embeddings into the RAG service (used by the test-suite).
    """
    config = get_config()
    _configure_logging(config.DEBUG)

    app = Flask(__name__, static_folder=os.path.join(BACKEND_DIR, "static"))
    app.config.update(
        SECRET_KEY=config.SECRET_KEY,
        JWT_SECRET_KEY=config.JWT_SECRET_KEY,
        JWT_EXPIRES_HOURS=config.JWT_EXPIRES_HOURS,
        DEBUG=config.DEBUG,
        MAX_CONTENT_LENGTH=config.MAX_FILE_SIZE + 1024 * 1024,  # headroom for multipart overhead
        SESSION_PERMANENT=False,
        SESSION_COOKIE_NAME="rag_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=config.COOKIE_SAMESITE,
        SESSION_COOKIE_SECURE=config.COOKIE_SECURE,
    )
    if test_config:
        app.config.update(test_config)

    # Filesystem sessions locally; plain signed-cookie sessions + JWT on Vercel.
    if not config.IS_VERCEL:
        app.config.setdefault("SESSION_TYPE", "filesystem")
        app.config.setdefault("SESSION_FILE_DIR", os.getenv("SESSION_FILE_DIR", "flask_session"))
        Session(app)

    origins = list(config.CORS_ORIGINS)
    if config.IS_VERCEL:
        for var in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
            if os.getenv(var):
                origins.append(f"https://{os.getenv(var)}")
    CORS(
        app,
        origins=origins,
        supports_credentials=True,
        allow_headers=["Content-Type", "Accept", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )

    _register_error_handlers(app)

    from app.services import init_services

    init_services(app, config, rag_overrides)
    _register_blob_sync(app, config)

    from app.blueprints import admin, auth, chat, documents, health

    for module in (auth, chat, documents, admin, health):
        app.register_blueprint(module.bp)

    if not config.IS_VERCEL:
        _register_frontend(app)

    return app
