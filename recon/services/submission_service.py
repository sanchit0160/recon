from datetime import datetime
from werkzeug.utils import secure_filename

from ..config import UPLOADS_DIR
from ..db import create_submission, log_action


def save_exception_note(user_department: str, note_file):
    safe_name = secure_filename(note_file.filename)
    note_filename = f"{user_department}_{int(datetime.now().timestamp())}_{safe_name}"
    note_path = UPLOADS_DIR / note_filename
    note_file.save(str(note_path))
    return note_filename


def submit_department_server(*,
    department: str,
    hostname: str,
    ip_address: str,
    environment: str,
    region: str,
    is_exception: bool,
    exception_note_file,
    justification: str,
    exception_reason: str,
    submitted_by: str,
    itam_id: str | None = None,
    submission_type: str = "standard",
    proxy_mgmt_ip: str | None = None,
    proxy_cluster_ip: str | None = None,
    proxy_backup_ip: str | None = None,
    proxy_details: str | None = None,
):
    note_path = None
    if exception_note_file and exception_note_file.filename:
        note_path = save_exception_note(department, exception_note_file)

    create_submission(
        department=department,
        hostname=hostname,
        ip_address=ip_address,
        environment=environment,
        region=region,
        is_exception=is_exception,
        exception_note_path=note_path,
        justification=justification,
        exception_reason=exception_reason,
        submitted_by=submitted_by,
        itam_id=itam_id,
        submission_type=submission_type,
        proxy_mgmt_ip=proxy_mgmt_ip,
        proxy_cluster_ip=proxy_cluster_ip,
        proxy_backup_ip=proxy_backup_ip,
        proxy_details=proxy_details,
    )
    log_action(submitted_by, "submission_create", f"{hostname} ({ip_address}) exception={is_exception}")
    return note_path
