"""Lazy proxies to the services attached to the current Flask app.

Blueprints import these names instead of closing over objects created inside a
factory function, which keeps the application factory testable.
"""
from flask import current_app
from werkzeug.local import LocalProxy


def _service(name: str) -> LocalProxy:
    return LocalProxy(lambda: current_app.extensions["rag_services"][name])


db_manager = _service("db_manager")
rag_service = _service("rag_service")
chat_service = _service("chat_service")
blob_storage = _service("blob_storage")
