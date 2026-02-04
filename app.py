from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from pathlib import Path
import re
from datetime import datetime
from typing import Dict, List, Tuple

from flask import Flask, redirect, render_template, request, session, url_for, Response, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")

LAST_RECON = None
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_PATH = os.path.join(DATA_DIR, "last_recon.json")
DB_PATH = os.path.join(DATA_DIR, "app.db")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")

DEFAULT_ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
DEFAULT_ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

REQUIRED_ITAM_FIELDS = [
    "itam_id",
    "hostname",
    "region",
    "department",
    "environment",
    "ip_address",
]


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _db_connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _db_connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                department TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department TEXT NOT NULL,
                hostname TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                environment TEXT,
                region TEXT,
                status TEXT NOT NULL,
                is_exception INTEGER NOT NULL DEFAULT 0,
                exception_note_path TEXT,
                justification TEXT,
                submitted_by TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                admin_status TEXT NOT NULL DEFAULT 'pending',
                admin_reviewed_by TEXT,
                admin_reviewed_at TEXT,
                admin_remarks TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _seed_admin():
    conn = _db_connect()
    try:
        cur = conn.execute("SELECT COUNT(*) AS count FROM users")
        count = cur.fetchone()["count"]
        if count == 0:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, department) VALUES (?, ?, ?, ?)",
                (
                    DEFAULT_ADMIN_USER,
                    generate_password_hash(DEFAULT_ADMIN_PASS),
                    "admin",
                    None,
                ),
            )
            conn.commit()
    finally:
        conn.close()


def _get_user_by_username(username: str):
    conn = _db_connect()
    try:
        cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()
    finally:
        conn.close()


def _get_user_by_id(user_id: int):
    conn = _db_connect()
    try:
        cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def _list_users():
    conn = _db_connect()
    try:
        cur = conn.execute("SELECT * FROM users ORDER BY role, department, username")
        return cur.fetchall()
    finally:
        conn.close()


def _count_admins() -> int:
    conn = _db_connect()
    try:
        cur = conn.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'admin'")
        return int(cur.fetchone()["count"])
    finally:
        conn.close()


def _create_user(username: str, password: str, role: str, department: str | None):
    conn = _db_connect()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, department) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), role, department),
        )
        conn.commit()
    finally:
        conn.close()


def _update_user(user_id: int, username: str, role: str, department: str | None, password: str | None):
    conn = _db_connect()
    try:
        if password:
            conn.execute(
                "UPDATE users SET username = ?, role = ?, department = ?, password_hash = ? WHERE id = ?",
                (username, role, department, generate_password_hash(password), user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET username = ?, role = ?, department = ? WHERE id = ?",
                (username, role, department, user_id),
            )
        conn.commit()
    finally:
        conn.close()


def _delete_user(user_id: int):
    conn = _db_connect()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def _log_action(actor: str, action: str, details: str):
    conn = _db_connect()
    try:
        conn.execute(
            "INSERT INTO audit_logs (actor, action, details, created_at) VALUES (?, ?, ?, ?)",
            (actor, action, details, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    finally:
        conn.close()


def _list_audit_logs(limit: int = 200):
    conn = _db_connect()
    try:
        cur = conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,))
        return cur.fetchall()
    finally:
        conn.close()


def _create_submission(
    department: str,
    hostname: str,
    ip_address: str,
    environment: str,
    region: str,
    is_exception: bool,
    exception_note_path: str | None,
    justification: str,
    submitted_by: str,
):
    conn = _db_connect()
    try:
        conn.execute(
            """
            INSERT INTO submissions (
                department, hostname, ip_address, environment, region,
                status, is_exception, exception_note_path, justification,
                submitted_by, submitted_at, admin_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                department,
                hostname,
                ip_address,
                environment,
                region,
                "submitted",
                1 if is_exception else 0,
                exception_note_path,
                justification,
                submitted_by,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "pending",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _list_submissions_by_department(department: str):
    conn = _db_connect()
    try:
        cur = conn.execute(
            "SELECT * FROM submissions WHERE department = ? ORDER BY submitted_at DESC",
            (department,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def _list_pending_exceptions():
    conn = _db_connect()
    try:
        cur = conn.execute(
            "SELECT * FROM submissions WHERE is_exception = 1 ORDER BY submitted_at DESC"
        )
        return cur.fetchall()
    finally:
        conn.close()


def _list_all_submissions():
    conn = _db_connect()
    try:
        cur = conn.execute("SELECT * FROM submissions ORDER BY submitted_at DESC")
        return cur.fetchall()
    finally:
        conn.close()


def _get_submission(submission_id: int):
    conn = _db_connect()
    try:
        cur = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,))
        return cur.fetchone()
    finally:
        conn.close()


def _submission_exists(department: str, hostname: str, ip_address: str):
    conn = _db_connect()
    try:
        cur = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM submissions
            WHERE department = ? AND hostname = ? AND ip_address = ? AND admin_status = 'pending'
            """,
            (department, hostname, ip_address),
        )
        return cur.fetchone()["count"] > 0
    finally:
        conn.close()


def _is_valid_ip(value: str) -> bool:
    return bool(re.match(r"^\\d{1,3}(?:\\.\\d{1,3}){3}$", value.strip()))


def _review_exception(submission_id: int, status: str, remarks: str, reviewer: str):
    conn = _db_connect()
    try:
        conn.execute(
            """
            UPDATE submissions
            SET admin_status = ?, admin_remarks = ?, admin_reviewed_by = ?, admin_reviewed_at = ?
            WHERE id = ?
            """,
            (
                status,
                remarks,
                reviewer,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                submission_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _age_days(submitted_at: str) -> int:
    try:
        dt = datetime.strptime(submitted_at, "%Y-%m-%d %H:%M:%S")
        delta = datetime.now() - dt
        return max(0, delta.days)
    except ValueError:
        return 0


def _read_csv(file_storage) -> Tuple[List[Dict[str, str]], List[str]]:
    filename = secure_filename(file_storage.filename or "")
    data = file_storage.read()
    if not data:
        return [], []

    # Handle UTF-8 with BOM safely
    text = data.decode("utf-8-sig", errors="replace")
    buf = io.StringIO(text)
    reader = csv.DictReader(buf)
    if not reader.fieldnames:
        return [], []

    raw_headers = reader.fieldnames
    normalized_headers = [_normalize_header(h) for h in raw_headers]
    header_map = {raw: norm for raw, norm in zip(raw_headers, normalized_headers)}

    rows: List[Dict[str, str]] = []
    for row in reader:
        normalized_row = {}
        for raw_key, value in row.items():
            if raw_key is None:
                continue
            normalized_key = header_map.get(raw_key, _normalize_header(raw_key))
            normalized_row[normalized_key] = (value or "").strip()
        rows.append(normalized_row)

    return rows, normalized_headers


def _extract_ip_set(rows: List[Dict[str, str]], headers: List[str]) -> Tuple[set, str | None]:
    candidates = ["ip_address", "ip", "ipaddress", "ip_addr", "ipaddresss", "ip_addresss", "ipaddress_"]
    ip_field = None
    for candidate in candidates:
        if candidate in headers:
            ip_field = candidate
            break

    if ip_field is None:
        # Try to find something that looks like it starts with ip
        for header in headers:
            if header.startswith("ip"):
                ip_field = header
                break

    if ip_field is None:
        return set(), None

    ip_set = set()
    for row in rows:
        value = row.get(ip_field, "")
        if value:
            ip_set.add(value)

    return ip_set, ip_field


def _save_recon(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=True)


def _load_recon() -> dict | None:
    if not os.path.exists(DATA_PATH):
        return None
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


LAST_RECON = _load_recon()

_init_db()
_seed_admin()


def _current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = _get_user_by_id(user_id)
    if not user:
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "department": user["department"],
    }


def _filter_rows(rows: List[Dict[str, str]], region: str, department: str) -> List[Dict[str, str]]:
    filtered = rows
    if region:
        filtered = [row for row in filtered if row.get("region", "") == region]
    if department:
        filtered = [row for row in filtered if row.get("department", "") == department]
    return filtered


def _build_department_summary(itam_rows, integrated_rows, pending_rows):
    integrated_lookup = {(row.get("itam_id"), row.get("ip_address")) for row in integrated_rows}
    pending_lookup = {(row.get("itam_id"), row.get("ip_address")) for row in pending_rows}
    summary = {}
    for row in itam_rows:
        dept = row.get("department", "") or "Unknown"
        entry = summary.setdefault(dept, {"department": dept, "total": 0, "integrated": 0, "pending": 0})
        entry["total"] += 1
        key = (row.get("itam_id"), row.get("ip_address"))
        if key in integrated_lookup:
            entry["integrated"] += 1
        elif key in pending_lookup:
            entry["pending"] += 1
    return sorted(summary.values(), key=lambda item: item["department"].lower())


def _build_region_summary(itam_rows, integrated_rows, pending_rows):
    integrated_lookup = {(row.get("itam_id"), row.get("ip_address")) for row in integrated_rows}
    pending_lookup = {(row.get("itam_id"), row.get("ip_address")) for row in pending_rows}
    summary = {}
    for row in itam_rows:
        region = row.get("region", "") or "Unknown"
        entry = summary.setdefault(region, {"region": region, "total": 0, "integrated": 0, "pending": 0})
        entry["total"] += 1
        key = (row.get("itam_id"), row.get("ip_address"))
        if key in integrated_lookup:
            entry["integrated"] += 1
        elif key in pending_lookup:
            entry["pending"] += 1
    return sorted(summary.values(), key=lambda item: item["region"].lower())


def _build_department_map(itam_rows):
    mapping = {}
    all_departments = set()
    for row in itam_rows:
        dept = row.get("department", "")
        if not dept:
            continue
        region = row.get("region", "") or ""
        mapping.setdefault(region, set()).add(dept)
        all_departments.add(dept)
    mapping[""] = set(sorted(all_departments))
    return {key: sorted(values) for key, values in mapping.items()}


def _build_metrics(itam_rows, integrated_rows, pending_rows):
    total = len(itam_rows)
    pending_count = len(pending_rows)
    integrated_count = len(integrated_rows)
    region_count = len({row.get("region", "") for row in itam_rows if row.get("region", "")})
    department_count = len({row.get("department", "") for row in itam_rows if row.get("department", "")})
    pending_rate = round((pending_count / total) * 100) if total else 0
    integrated_rate = round((integrated_count / total) * 100) if total else 0
    return {
        "total": total,
        "pending_rate": pending_rate,
        "integrated_rate": integrated_rate,
        "region_count": region_count,
        "department_count": department_count,
    }

def _build_all_rows(integrated_rows, pending_rows):
    all_rows = []
    for row in integrated_rows:
        tagged = dict(row)
        tagged["_status"] = "Integrated"
        all_rows.append(tagged)
    for row in pending_rows:
        tagged = dict(row)
        tagged["_status"] = "Pending"
        all_rows.append(tagged)
    return all_rows


def _build_chart(counts: dict) -> dict:
    total = counts.get("itam_total") or (counts.get("integrated", 0) + counts.get("pending", 0))
    if total <= 0:
        return {"integrated_pct": 0, "pending_pct": 0}
    integrated_pct = round((counts.get("integrated", 0) / total) * 100)
    pending_pct = max(0, 100 - integrated_pct)
    return {"integrated_pct": integrated_pct, "pending_pct": pending_pct}


@app.route("/")
def index():
    user = _current_user()
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
    user = _get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid username or password.")

    session["user_id"] = user["id"]
    _log_action(user["username"], "login", f"role={user['role']}")
    if user["role"] == "admin":
        return redirect(url_for("admin"))
    return redirect(url_for("department_view"))


@app.route("/logout")
def logout():
    user = _current_user()
    if user:
        _log_action(user["username"], "logout", "")
    session.clear()
    return redirect(url_for("login"))


@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    user = _current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))

    error = request.args.get("error") or None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        role = (request.form.get("role") or "").strip()
        department = (request.form.get("department") or "").strip()
        if role == "department" and not department:
            error = "Department is required for department users."
        elif not username or not password or role not in {"admin", "department"}:
            error = "Please provide username, password, and role."
        else:
            try:
                _create_user(username, password, role, department if role == "department" else None)
                _log_action(user["username"], "user_create", f"user={username}, role={role}, department={department}")
                return redirect(url_for("admin_users"))
            except sqlite3.IntegrityError:
                error = "Username already exists."

    users = _list_users()
    departments = []
    if LAST_RECON:
        departments = sorted({row.get("department", "") for row in LAST_RECON["itam_rows"] if row.get("department", "")})
    return render_template(
        "admin_users.html",
        user=user,
        users=users,
        error=error,
        departments=departments,
    )


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
def admin_user_delete(user_id: int):
    user = _current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))
    if user["id"] == user_id:
        return redirect(url_for("admin_users", error="You cannot delete your own account."))
    target = _get_user_by_id(user_id)
    if target and target["role"] == "admin" and _count_admins() <= 1:
        return redirect(url_for("admin_users", error="At least one admin is required."))
    _delete_user(user_id)
    if target:
        _log_action(user["username"], "user_delete", f"user={target['username']}")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
def admin_user_edit(user_id: int):
    user = _current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))

    target = _get_user_by_id(user_id)
    if not target:
        return redirect(url_for("admin_users", error="User not found."))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        role = (request.form.get("role") or "").strip()
        department = (request.form.get("department") or "").strip()
        password = (request.form.get("password") or "").strip()

        if not username or role not in {"admin", "department"}:
            error = "Username and role are required."
        elif role == "department" and not department:
            error = "Department is required for department users."
        else:
            if target["role"] == "admin" and role != "admin" and _count_admins() <= 1:
                error = "At least one admin is required."
            else:
                try:
                    _update_user(
                        user_id,
                        username,
                        role,
                        department if role == "department" else None,
                        password if password else None,
                    )
                    _log_action(user["username"], "user_edit", f"user={username}, role={role}, department={department}")
                    return redirect(url_for("admin_users"))
                except sqlite3.IntegrityError:
                    error = "Username already exists."

    departments = []
    if LAST_RECON:
        departments = sorted({row.get("department", "") for row in LAST_RECON["itam_rows"] if row.get("department", "")})

    return render_template(
        "admin_user_edit.html",
        user=user,
        target=target,
        error=error,
        departments=departments,
    )


@app.route("/admin", methods=["GET", "POST"])
def admin():
    user = _current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))

    global LAST_RECON

    if request.method == "POST":
        itam_file = request.files.get("itam_report")
        pims_file = request.files.get("pims_report")

        if not itam_file or not itam_file.filename:
            return render_template("admin.html", user=user, error="Please upload the ITAM Dump CSV.")
        if not pims_file or not pims_file.filename:
            return render_template("admin.html", user=user, error="Please upload the Active Service Report (PIMS) CSV.")

        itam_rows, itam_headers = _read_csv(itam_file)
        pims_rows, pims_headers = _read_csv(pims_file)

        missing_fields = [f for f in REQUIRED_ITAM_FIELDS if f not in itam_headers]
        if missing_fields:
            return render_template(
                "admin.html",
                user=user,
                error=f"ITAM Dump is missing required columns: {', '.join(missing_fields)}",
            )

        pims_ips, pims_ip_field = _extract_ip_set(pims_rows, pims_headers)
        if not pims_ip_field:
            return render_template(
                "admin.html",
                user=user,
                error="Could not find an IP Address column in the PIMS report. Please include a column like 'ip_address' or 'ip address'.",
            )

        integrated = []
        pending = []

        for row in itam_rows:
            ip_value = row.get("ip_address", "")
            if ip_value and ip_value in pims_ips:
                integrated.append(row)
            else:
                pending.append(row)

        LAST_RECON = {
            "itam_rows": itam_rows,
            "integrated": integrated,
            "pending": pending,
            "counts": {
                "itam_total": len(itam_rows),
                "integrated": len(integrated),
                "pending": len(pending),
            },
            "departments": sorted({row.get("department", "") for row in itam_rows if row.get("department", "")}),
            "regions": sorted({row.get("region", "") for row in itam_rows if row.get("region", "")}),
            "reconciled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        _save_recon(LAST_RECON)

        return redirect(url_for("admin"))

    region = (request.args.get("region") or "").strip()
    department = (request.args.get("department") or "").strip()
    data = LAST_RECON
    if not data:
        return render_template("admin.html", user=user)
    if not data.get("reconciled_at"):
        data["reconciled_at"] = "Unknown"

    filtered_itam = _filter_rows(data["itam_rows"], region, department)
    integrated_filtered = _filter_rows(data["integrated"], region, department)
    pending_filtered = _filter_rows(data["pending"], region, department)
    filtered_departments = data["departments"]
    dept_map = _build_department_map(data["itam_rows"])
    metrics = _build_metrics(filtered_itam, integrated_filtered, pending_filtered)
    counts_filtered = {
        "itam_total": len(filtered_itam),
        "integrated": len(integrated_filtered),
        "pending": len(pending_filtered),
    }

    return render_template(
        "admin.html",
        user=user,
        data=data,
        region=region,
        department=department,
        filtered_departments=filtered_departments,
        dept_map=dept_map,
        integrated=integrated_filtered,
        pending=pending_filtered,
        all_rows=_build_all_rows(integrated_filtered, pending_filtered),
        summary=_build_department_summary(filtered_itam, integrated_filtered, pending_filtered),
        summary_regions=_build_region_summary(filtered_itam, integrated_filtered, pending_filtered),
        filtered_counts=counts_filtered,
        metrics=metrics,
        chart=_build_chart(counts_filtered),
    )


@app.route("/department")
def department_view():
    user = _current_user()
    if not user or user["role"] != "department":
        return redirect(url_for("login"))

    data = LAST_RECON
    if not data:
        return render_template("department.html", user=user, data_available=False)

    dept_name = user.get("department") or ""
    integrated = _filter_rows(data["integrated"], "", dept_name)
    pending = _filter_rows(data["pending"], "", dept_name)

    submissions = _list_submissions_by_department(dept_name)
    submissions = [
        {**dict(item), "age_days": _age_days(item["submitted_at"])} for item in submissions
    ]
    return render_template(
        "department.html",
        user=user,
        data_available=True,
        integrated=integrated,
        pending=pending,
        all_rows=_build_all_rows(integrated, pending),
        counts={
            "integrated": len(integrated),
            "pending": len(pending),
        },
        submissions=submissions,
        chart=_build_chart({"integrated": len(integrated), "pending": len(pending)}),
    )


@app.route("/department/submit", methods=["GET", "POST"])
def department_submit():
    user = _current_user()
    if not user or user["role"] != "department":
        return redirect(url_for("login"))

    error = None
    if request.method == "POST":
        hostname = (request.form.get("hostname") or "").strip()
        ip_address = (request.form.get("ip_address") or "").strip()
        environment = (request.form.get("environment") or "").strip()
        region = (request.form.get("region") or "").strip()
        is_exception = (request.form.get("is_exception") or "") == "on"
        justification = (request.form.get("justification") or "").strip()
        note_file = request.files.get("exception_note")

        if not hostname or not ip_address:
            error = "Hostname and IP address are required."
        elif not _is_valid_ip(ip_address):
            error = "Please provide a valid IP address."
        elif is_exception and not (justification or (note_file and note_file.filename)):
            error = "Provide a justification or upload an approval note for exceptions."
        elif _submission_exists(user["department"] or "", hostname, ip_address):
            error = "A pending submission for this server already exists."
        else:
            note_path = None
            if note_file and note_file.filename:
                safe_name = secure_filename(note_file.filename)
                note_filename = f"{user['department']}_{int(datetime.now().timestamp())}_{safe_name}"
                note_path = note_filename
                note_file.save(os.path.join(UPLOADS_DIR, note_filename))

            _create_submission(
                department=user["department"] or "",
                hostname=hostname,
                ip_address=ip_address,
                environment=environment,
                region=region,
                is_exception=is_exception,
                exception_note_path=note_path,
                justification=justification,
                submitted_by=user["username"],
            )
            _log_action(user["username"], "submission_create", f"{hostname} ({ip_address}) exception={is_exception}")
            return redirect(url_for("department_view"))

    return render_template("department_submit.html", user=user, error=error)


@app.route("/uploads/<path:filename>")
def download_upload(filename: str):
    user = _current_user()
    if not user:
        return redirect(url_for("login"))
    return send_from_directory(UPLOADS_DIR, filename, as_attachment=True)


@app.route("/admin/exceptions")
def admin_exceptions():
    user = _current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))
    submissions = _list_pending_exceptions()
    submissions = [
        {**dict(item), "age_days": _age_days(item["submitted_at"])} for item in submissions
    ]
    return render_template("admin_exceptions.html", user=user, submissions=submissions)


@app.route("/admin/exceptions/<int:submission_id>", methods=["GET", "POST"])
def admin_exception_review(submission_id: int):
    user = _current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))
    submission = _get_submission(submission_id)
    if not submission:
        return redirect(url_for("admin_exceptions"))

    submission_dict = dict(submission)
    submission_dict["age_days"] = _age_days(submission["submitted_at"])

    note_filename = None
    if submission_dict.get("exception_note_path"):
        note_filename = os.path.basename(submission_dict["exception_note_path"])

    if request.method == "POST":
        action = (request.form.get("action") or "").strip().lower()
        remarks = (request.form.get("remarks") or "").strip()
        if action not in {"approved", "rejected"}:
            return render_template(
                "admin_exception_review.html",
                user=user,
                submission=submission_dict,
                note_filename=note_filename,
                error="Choose approve or reject.",
            )
        _review_exception(submission_id, action, remarks, user["username"])
        _log_action(user["username"], "exception_review", f"id={submission_id}, action={action}")
        return redirect(url_for("admin_exceptions"))

    return render_template(
        "admin_exception_review.html",
        user=user,
        submission=submission_dict,
        note_filename=note_filename,
    )


@app.route("/admin/submissions/export")
def admin_export_submissions():
    user = _current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))
    rows = _list_all_submissions()
    output = io.StringIO()
    fieldnames = [
        "id",
        "department",
        "hostname",
        "ip_address",
        "environment",
        "region",
        "status",
        "is_exception",
        "exception_note_path",
        "justification",
        "submitted_by",
        "submitted_at",
        "admin_status",
        "admin_reviewed_by",
        "admin_reviewed_at",
        "admin_remarks",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row[key] for key in fieldnames})
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=submissions_audit.csv"
    return response


@app.route("/admin/audit")
def admin_audit():
    user = _current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))
    logs = _list_audit_logs()
    return render_template("admin_audit.html", user=user, logs=logs)


@app.route("/department/bulk-upload", methods=["POST"])
def department_bulk_upload():
    user = _current_user()
    if not user or user["role"] != "department":
        return redirect(url_for("login"))

    upload = request.files.get("bulk_file")
    if not upload or not upload.filename:
        return redirect(url_for("department_submit"))

    rows, headers = _read_csv(upload)
    required = {"hostname", "ip_address"}
    if not required.issubset(set(headers)):
        return render_template(
            "department_submit.html",
            user=user,
            error="Bulk CSV must include hostname and ip_address columns.",
        )

    created = 0
    skipped = 0
    errors = []
    for idx, row in enumerate(rows, start=2):
        hostname = (row.get("hostname") or "").strip()
        ip_address = (row.get("ip_address") or "").strip()
        environment = (row.get("environment") or "").strip()
        region = (row.get("region") or "").strip()
        is_exception = (row.get("is_exception") or "").strip().lower() in {"yes", "true", "1"}
        justification = (row.get("justification") or "").strip()

        if not hostname or not ip_address:
            errors.append(f"Row {idx}: hostname/ip_address required.")
            skipped += 1
            continue
        if not _is_valid_ip(ip_address):
            errors.append(f"Row {idx}: invalid IP address.")
            skipped += 1
            continue
        if is_exception and not justification:
            errors.append(f"Row {idx}: justification required for exceptions.")
            skipped += 1
            continue
        if _submission_exists(user["department"] or "", hostname, ip_address):
            skipped += 1
            continue

        _create_submission(
            department=user["department"] or "",
            hostname=hostname,
            ip_address=ip_address,
            environment=environment,
            region=region,
            is_exception=is_exception,
            exception_note_path=None,
            justification=justification,
            submitted_by=user["username"],
        )
        created += 1

    _log_action(user["username"], "bulk_upload", f"created={created}, skipped={skipped}")
    return render_template(
        "department_submit.html",
        user=user,
        success=f"Bulk upload complete: {created} created, {skipped} skipped.",
        errors=errors,
    )


@app.route("/admin/department/<department>")
def admin_department(department: str):
    user = _current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))

    data = LAST_RECON
    if not data:
        return redirect(url_for("admin"))

    department = department.strip()
    region = (request.args.get("region") or "").strip()
    integrated = _filter_rows(data["integrated"], region, department)
    pending = _filter_rows(data["pending"], region, department)

    return render_template(
        "admin_department.html",
        user=user,
        department=department,
        region=region,
        integrated=integrated,
        pending=pending,
        all_rows=_build_all_rows(integrated, pending),
        counts={
            "integrated": len(integrated),
            "pending": len(pending),
        },
        chart=_build_chart({"integrated": len(integrated), "pending": len(pending)}),
    )


def _csv_response(rows: List[Dict[str, str]], filename: str) -> Response:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=REQUIRED_ITAM_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in REQUIRED_ITAM_FIELDS})
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


@app.route("/export/admin")
def export_admin():
    user = _current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))

    data = LAST_RECON
    if not data:
        return redirect(url_for("admin"))

    export_type = (request.args.get("type") or "").strip().lower()
    region = (request.args.get("region") or "").strip()
    department = (request.args.get("department") or "").strip()

    if export_type == "integrated":
        rows = _filter_rows(data["integrated"], region, department)
        return _csv_response(rows, "integrated_servers.csv")
    if export_type == "pending":
        rows = _filter_rows(data["pending"], region, department)
        return _csv_response(rows, "pending_servers.csv")
    if export_type == "all":
        rows = _filter_rows(data["itam_rows"], region, department)
        return _csv_response(rows, "all_servers.csv")

    return redirect(url_for("admin"))


@app.route("/export/department")
def export_department():
    user = _current_user()
    if not user or user["role"] != "department":
        return redirect(url_for("login"))

    data = LAST_RECON
    if not data:
        return redirect(url_for("department_view"))

    export_type = (request.args.get("type") or "").strip().lower()
    department = user.get("department") or ""

    if export_type == "integrated":
        rows = _filter_rows(data["integrated"], "", department)
        return _csv_response(rows, "integrated_servers.csv")
    if export_type == "pending":
        rows = _filter_rows(data["pending"], "", department)
        return _csv_response(rows, "pending_servers.csv")
    if export_type == "all":
        rows = _filter_rows(data["itam_rows"], "", department)
        return _csv_response(rows, "all_servers.csv")

    return redirect(url_for("department_view"))


@app.route("/export/admin/department/<department>")
def export_admin_department(department: str):
    user = _current_user()
    if not user or user["role"] != "admin":
        return redirect(url_for("login"))

    data = LAST_RECON
    if not data:
        return redirect(url_for("admin"))

    export_type = (request.args.get("type") or "").strip().lower()
    department = department.strip()
    region = (request.args.get("region") or "").strip()

    if export_type == "integrated":
        rows = _filter_rows(data["integrated"], region, department)
        return _csv_response(rows, "integrated_servers.csv")
    if export_type == "pending":
        rows = _filter_rows(data["pending"], region, department)
        return _csv_response(rows, "pending_servers.csv")
    if export_type == "all":
        rows = _filter_rows(data["itam_rows"], region, department)
        return _csv_response(rows, "all_servers.csv")

    return redirect(url_for("admin_department", department=department))


if __name__ == "__main__":
    _init_db()
    _seed_admin()
    app.run(debug=True)
