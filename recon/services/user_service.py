import sqlite3
from ..db import create_user, update_user, delete_user, count_admins, get_user_by_id, list_users


class UserServiceError(Exception):
    pass


def create_user_account(username: str, password: str, role: str, department: str | None):
    try:
        create_user(username, password, role, department)
    except sqlite3.IntegrityError as exc:
        raise UserServiceError("Username already exists.") from exc


def update_user_account(user_id: int, username: str, role: str, department: str | None, password: str | None):
    try:
        update_user(user_id, username, role, department, password)
    except sqlite3.IntegrityError as exc:
        raise UserServiceError("Username already exists.") from exc


def delete_user_account(user_id: int):
    delete_user(user_id)


def ensure_admin_can_change(target_role: str, current_role: str):
    if current_role == "admin" and target_role != "admin" and count_admins() <= 1:
        raise UserServiceError("At least one admin is required.")


def ensure_admin_can_delete(target_role: str):
    if target_role == "admin" and count_admins() <= 1:
        raise UserServiceError("At least one admin is required.")
