import sqlite3
from flask import redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .auth import current_user
from .db import get_user_by_username, log_action




def _password_strength(pwd: str) -> str | None:
    if len(pwd) < 10:
        return "Password must be at least 10 characters."
    if not any(ch.islower() for ch in pwd):
        return "Password must include a lowercase letter."
    if not any(ch.isupper() for ch in pwd):
        return "Password must include an uppercase letter."
    if not any(ch.isdigit() for ch in pwd):
        return "Password must include a number."
    if not any(ch in "!@#$%^&*()-_=+[]{}:;,.?/" for ch in pwd):
        return "Password must include a symbol."
    return None


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


    @app.route("/account/password", methods=["GET", "POST"])
    def account_password():
        user = current_user()
        if not user:
            return redirect(url_for("login"))

        error = None
        success = None
        if request.method == "POST":
            current = (request.form.get("current_password") or "").strip()
            new_password = (request.form.get("new_password") or "").strip()
            confirm = (request.form.get("confirm_password") or "").strip()

            db_user = get_user_by_username(user["username"])
            if not current or not new_password or not confirm:
                error = "All password fields are required."
            elif new_password != confirm:
                error = "New password and confirmation do not match."
            elif not db_user or not check_password_hash(db_user["password_hash"], current):
                error = "Current password is incorrect."
            else:
                strength_error = _password_strength(new_password)
                if strength_error:
                    error = strength_error
                else:
                    change_password(db_user["id"], new_password)
                    log_action(user["username"], "password_change", "self-service")
                    success = "Password updated. Please use the new password next time you log in."

        return render_template("account_password.html", user=user, error=error, success=success)
