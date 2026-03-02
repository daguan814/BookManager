from flask import Blueprint, redirect, render_template

page_bp = Blueprint("page", __name__)


@page_bp.get("/")
def index():
    return render_template("index.html")


@page_bp.get("/login.html")
def login_page():
    return render_template("login.html")


@page_bp.get("/admin.html")
def admin_page():
    return render_template("admin.html")


@page_bp.get("/ops.html")
def ops_page():
    return render_template("ops.html")


@page_bp.get("/favicon.ico")
def favicon():
    return redirect("/index.html")
