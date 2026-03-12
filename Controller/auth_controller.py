from flask import Blueprint, jsonify, request, session

from config import settings

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _error(detail: str, status_code: int):
    return jsonify({"detail": detail}), status_code


@auth_bp.get("/status")
def auth_status():
    return jsonify({"authenticated": bool(session.get("authenticated"))})


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password") or "").strip()
    if not password:
        return _error("密码不能为空", 400)
    if password != settings.web_login_password:
        return _error("密码错误", 401)

    session.clear()
    session.permanent = True
    session["authenticated"] = True
    return jsonify({"message": "登录成功", "authenticated": True})


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"message": "已退出登录", "authenticated": False})
