"""WSGI entrypoint.

Development:  python wsgi.py
Production:   gunicorn wsgi:app
"""
from app import create_app
from config import get_config

app = create_app()

if __name__ == "__main__":
    cfg = get_config()
    app.run(host="0.0.0.0", port=int(__import__("os").getenv("PORT", 5000)), debug=cfg.DEBUG, use_reloader=False)
