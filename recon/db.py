import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash
from .config import DATA_DIR, UPLOADS_DIR, DB_PATH, DEFAULT_ADMIN_USER, DEFAULT_ADMIN_PASS


def db_connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_connect()
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
                exception_reason TEXT,
                status TEXT NOT NULL,
                is_exception INTEGER NOT NULL DEFAULT 0,
                exception_note_path TEXT,
                justification TEXT,
                submitted_by TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                admin_status TEXT NOT NULL DEFAULT 'pending',
                admin_reviewed_by TEXT,
                admin_reviewed_at TEXT,
                admin_remarks TEXT,
                review_verified INTEGER
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


def ensure_submission_columns():
    conn = db_connect()
    try:
        cur = conn.execute("PRAGMA table_info(submissions)")
        existing = {row["name"] for row in cur.fetchall()}
        if "exception_reason" not in existing:
            conn.execute("ALTER TABLE submissions ADD COLUMN exception_reason TEXT")
        if "review_verified" not in existing:
            conn.execute("ALTER TABLE submissions ADD COLUMN review_verified INTEGER")
        conn.commit()
    finally:
        conn.close()


def seed_admin():
    conn = db_connect()
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


def get_user_by_username(username: str):
    conn = db_connect()
    try:
        cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id: int):
    conn = db_connect()
    try:
        cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def list_users():
    conn = db_connect()
    try:
        cur = conn.execute("SELECT * FROM users ORDER BY role, department, username")
        return cur.fetchall()
    finally:
        conn.close()


def count_admins() -> int:
    conn = db_connect()
    try:
        cur = conn.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'admin'")
        return int(cur.fetchone()["count"])
    finally:
        conn.close()


def create_user(username: str, password: str, role: str, department: str | None):
    conn = db_connect()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, department) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), role, department),
        )
        conn.commit()
    finally:
        conn.close()


def update_user(user_id: int, username: str, role: str, department: str | None, password: str | None):
    conn = db_connect()
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


def delete_user(user_id: int):
    conn = db_connect()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def log_action(actor: str, action: str, details: str):
    conn = db_connect()
    try:
        conn.execute(
            "INSERT INTO audit_logs (actor, action, details, created_at) VALUES (?, ?, ?, ?)",
            (actor, action, details, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    finally:
        conn.close()


def list_audit_logs(limit: int = 200):
    conn = db_connect()
    try:
        cur = conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,))
        return cur.fetchall()
    finally:
        conn.close()


def create_submission(
    department: str,
    hostname: str,
    ip_address: str,
    environment: str,
    region: str,
    is_exception: bool,
    exception_note_path: str | None,
    justification: str,
    exception_reason: str,
    submitted_by: str,
):
    conn = db_connect()
    try:
        conn.execute(
            """
            INSERT INTO submissions (
                department, hostname, ip_address, environment, region, exception_reason,
                status, is_exception, exception_note_path, justification,
                submitted_by, submitted_at, admin_status, review_verified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                department,
                hostname,
                ip_address,
                environment,
                region,
                exception_reason,
                "submitted",
                1 if is_exception else 0,
                exception_note_path,
                justification,
                submitted_by,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "pending",
                0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_submissions_by_department(department: str):
    conn = db_connect()
    try:
        cur = conn.execute(
            "SELECT * FROM submissions WHERE department = ? ORDER BY submitted_at DESC",
            (department,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def list_exception_submissions_filtered(department: str, status: str):
    conn = db_connect()
    try:
        query = "SELECT * FROM submissions WHERE is_exception = 1"
        params = []
        if department:
            query += " AND department = ?"
            params.append(department)
        if status:
            query += " AND admin_status = ?"
            params.append(status)
        query += " ORDER BY submitted_at DESC"
        cur = conn.execute(query, tuple(params))
        return cur.fetchall()
    finally:
        conn.close()


def list_all_submissions():
    conn = db_connect()
    try:
        cur = conn.execute("SELECT * FROM submissions ORDER BY submitted_at DESC")
        return cur.fetchall()
    finally:
        conn.close()


def get_submission(submission_id: int):
    conn = db_connect()
    try:
        cur = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,))
        return cur.fetchone()
    finally:
        conn.close()


def submission_exists(department: str, hostname: str, ip_address: str):
    conn = db_connect()
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


def review_exception(submission_id: int, status: str, remarks: str, reviewer: str, verified: bool):
    conn = db_connect()
    try:
        conn.execute(
            """
            UPDATE submissions
            SET admin_status = ?, admin_remarks = ?, admin_reviewed_by = ?, admin_reviewed_at = ?, review_verified = ?
            WHERE id = ?
            """,
            (
                status,
                remarks,
                reviewer,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                1 if verified else 0,
                submission_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_user_password(user_id: int, password: str):
    from werkzeug.security import generate_password_hash
    conn = db_connect()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user_id),
        )
        conn.commit()
    finally:
        conn.close()
