import sqlite3
from flask import redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .auth import current_user
from .db import get_user_by_username, log_action


def register_routes(app):
    @app.route("/")
    def index():
        user = current_user()
        if not user:
            return redirect(url_for("login"))
        if user["role"] == "admin":
            return redirect(url_for("admin"))
        return redirect(url_for("department_view"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html")

        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        user = get_user_by_username(username)
        if not user or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Invalid username or password.")

        session["user_id"] = user["id"]
        log_action(user["username"], "login", f"role={user['role']}")
        if user["role"] == "admin":
            return redirect(url_for("admin"))
        return redirect(url_for("department_view"))

    @app.route("/logout")
    def logout():
        user = current_user()
        if user:
            log_action(user["username"], "logout", "")
        session.clear()
        return redirect(url_for("login"))
