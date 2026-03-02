from pathlib import Path

from flask import Flask

from Controller.book_controller import book_bp
from Controller.health_controller import health_bp
from Controller.inventory_controller import inventory_bp
from Controller.page_controller import page_bp
from config import settings
from db.database import ensure_runtime_schema


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="frontend",
        static_folder="frontend",
        static_url_path="",
    )

    app.register_blueprint(health_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(book_bp)
    app.register_blueprint(page_bp)

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
