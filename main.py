from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, redirect, request, session

from Controller.auth_controller import auth_bp
from Controller.book_controller import book_bp
from Controller.health_controller import health_bp
from Controller.inventory_controller import inventory_bp
from Controller.page_controller import page_bp
from config import settings
from db.database import ensure_runtime_schema

PUBLIC_PATHS = {
    "/health",
    "/login.html",
    "/favicon.ico",
}
PUBLIC_PREFIXES = (
    "/api/auth/",
    "/vendor/",
)
SCRIPT_TOKEN_PATHS = {
    "/api/inventory/isbn-query",
    "/api/inventory/confirm",
}
PUBLIC_SUFFIXES = (
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".ico",
    ".webp",
)


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return True
    return path.endswith(PUBLIC_SUFFIXES)


def _is_script_token_valid() -> bool:
    if request.path not in SCRIPT_TOKEN_PATHS:
        return False
    expected = settings.script_api_token.strip()
    provided = (request.headers.get("X-Bookmanager-Token") or "").strip()
    return bool(expected) and provided == expected


def _is_authenticated() -> bool:
    return bool(session.get("authenticated")) or _is_script_token_valid()


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="frontend",
        static_folder="frontend",
        static_url_path="",
    )
    app.secret_key = settings.app_secret_key
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=settings.session_days)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = bool(settings.ssl_cert_file and settings.ssl_key_file)

    app.register_blueprint(auth_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(book_bp)
    app.register_blueprint(page_bp)

    @app.before_request
    def enforce_auth():
        path = request.path or "/"
        if _is_public_path(path):
            return None
        if _is_authenticated():
            return None
        if path.startswith("/api/"):
            return jsonify({"detail": "未登录或脚本 token 无效"}), 401
        next_path = request.full_path if request.query_string else request.path
        return redirect(f"/login.html?next={next_path.rstrip('?')}")

    with app.app_context():
        ensure_runtime_schema()

    return app


app = create_app()


if __name__ == "__main__":
    ssl_context = None
    cert_file = settings.ssl_cert_file
    key_file = settings.ssl_key_file
    if cert_file and key_file and Path(cert_file).exists() and Path(key_file).exists():
        ssl_context = (cert_file, key_file)
    app.run(host=settings.app_host, port=settings.app_port, ssl_context=ssl_context)
