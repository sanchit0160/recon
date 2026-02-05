import os
from flask import Flask
from pathlib import Path
from .config import MAX_CONTENT_LENGTH
from .db import ensure_submission_columns, init_db, seed_admin
from .state import load_recon
from .routes_auth import register_routes as register_auth
from .routes_admin import register_routes as register_admin
from .routes_department import register_routes as register_department


def create_app():
    base_dir = Path(__file__).resolve().parent.parent
    app = Flask(__name__, template_folder=str(base_dir / "templates"), static_folder=str(base_dir / "static"))
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")

    init_db()
    ensure_submission_columns()
    seed_admin()
    load_recon()

    register_auth(app)
    register_admin(app)
    register_department(app)

    return app
