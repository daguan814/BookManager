from flask import Blueprint, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from db.database import engine

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return jsonify({"status": "error", "detail": f"database unavailable: {exc.__class__.__name__}"}), 503
    return jsonify({"status": "ok"})
