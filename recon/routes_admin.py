import io
from flask import Response, redirect, render_template, request, url_for

from .auth import current_user
from .config import REQUIRED_ITAM_FIELDS
from .db import (
    get_submission,
    get_user_by_id,
    list_audit_logs,
    list_exception_submissions_filtered,
    list_users,
    log_action,
    review_exception,
    list_all_submissions,
)
from .state import get_recon, save_recon, set_recon
from .utils import (
    age_days,
    build_all_rows,
    build_chart,
    build_department_map,
    build_department_summary,
    build_metrics,
    build_region_summary,
    filter_rows,
    read_csv,
)
from .services.recon_service import reconcile_reports
from .services.export_service import build_csv_download
from .services.user_service import UserServiceError, create_user_account, update_user_account, delete_user_account, ensure_admin_can_change, ensure_admin_can_delete


def register_routes(app):
    @app.route("/admin/users", methods=["GET", "POST"])
    def admin_users():
        user = current_user()
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
                    create_user_account(
                        username,
                        password,
                        role,
                        department if role == "department" else None,
                    )
                    log_action(user["username"], "user_create", f"user={username}, role={role}, department={department}")
                    return redirect(url_for("admin_users"))
                except UserServiceError as exc:
                    error = str(exc)

        users = list_users()
        departments = []
        data = get_recon()
        if data:
            departments = sorted({row.get("department", "") for row in data["itam_rows"] if row.get("department", "")})
        return render_template(
            "admin_users.html",
            user=user,
            users=users,
            error=error,
            departments=departments,
        )

    @app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
    def admin_user_delete(user_id: int):
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login"))
        if user["id"] == user_id:
            return redirect(url_for("admin_users", error="You cannot delete your own account."))
        target = get_user_by_id(user_id)
        try:
            if target:
                ensure_admin_can_delete(target["role"])
            delete_user_account(user_id)
        except UserServiceError as exc:
            return redirect(url_for("admin_users", error=str(exc)))
        if target:
            log_action(user["username"], "user_delete", f"user={target['username']}")
        return redirect(url_for("admin_users"))

    @app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
    def admin_user_edit(user_id: int):
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login"))

        target = get_user_by_id(user_id)
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
                try:
                    ensure_admin_can_change(role, target["role"])
                    update_user_account(
                        user_id,
                        username,
                        role,
                        department if role == "department" else None,
                        password if password else None,
                    )
                    log_action(user["username"], "user_edit", f"user={username}, role={role}, department={department}")
                    return redirect(url_for("admin_users"))
                except UserServiceError as exc:
                    error = str(exc)

        departments = []
        data = get_recon()
        if data:
            departments = sorted({row.get("department", "") for row in data["itam_rows"] if row.get("department", "")})

        return render_template(
            "admin_user_edit.html",
            user=user,
            target=target,
            error=error,
            departments=departments,
        )

    @app.route("/admin", methods=["GET", "POST"])
    def admin():
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login"))

        if request.method == "POST":
            itam_file = request.files.get("itam_report")
            pims_file = request.files.get("pims_report")

            if not itam_file or not itam_file.filename:
                return render_template("admin.html", user=user, error="Please upload the ITAM Dump CSV.")
            if not pims_file or not pims_file.filename:
                return render_template("admin.html", user=user, error="Please upload the Active Service Report (PIMS) CSV.")

            itam_rows, itam_headers = read_csv(itam_file)
            pims_rows, pims_headers = read_csv(pims_file)

            missing_fields = [f for f in REQUIRED_ITAM_FIELDS if f not in itam_headers]
            if missing_fields:
                return render_template(
                    "admin.html",
                    user=user,
                    error=f"ITAM Dump is missing required columns: {', '.join(missing_fields)}",
                )

            recon, error = reconcile_reports(itam_rows, pims_rows, pims_headers)
            if error:
                return render_template(
                    "admin.html",
                    user=user,
                    error=error,
                )
            set_recon(recon)
            save_recon(recon)

            return redirect(url_for("admin"))

        region = (request.args.get("region") or "").strip()
        department = (request.args.get("department") or "").strip()
        data = get_recon()
        if not data:
            return render_template("admin.html", user=user)
        if not data.get("reconciled_at"):
            data["reconciled_at"] = "Unknown"

        filtered_itam = filter_rows(data["itam_rows"], region, department)
        integrated_filtered = filter_rows(data["integrated"], region, department)
        pending_filtered = filter_rows(data["pending"], region, department)
        filtered_departments = data["departments"]
        dept_map = build_department_map(data["itam_rows"])
        metrics = build_metrics(filtered_itam, integrated_filtered, pending_filtered)
        counts_filtered = {
            "itam_total": len(filtered_itam),
            "integrated": len(integrated_filtered),
            "pending": len(pending_filtered),
        }

        
        summary = build_department_summary(filtered_itam, integrated_filtered, pending_filtered)
        summary_regions = build_region_summary(filtered_itam, integrated_filtered, pending_filtered)
        top_regions = sorted(summary_regions, key=lambda item: item.get("pending", 0), reverse=True)[:5]
        top_departments = sorted(summary, key=lambda item: item.get("pending", 0), reverse=True)[:5]

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
            all_rows=build_all_rows(integrated_filtered, pending_filtered),
            summary=summary,
            summary_regions=summary_regions,
            top_regions=top_regions,
            top_departments=top_departments,
            filtered_counts=counts_filtered,
            metrics=metrics,
            chart=build_chart(counts_filtered),
        )

    @app.route("/admin/department/<department>")
    def admin_department(department: str):
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login"))

        data = get_recon()
        if not data:
            return redirect(url_for("admin"))

        department = department.strip()
        region = (request.args.get("region") or "").strip()
        integrated = filter_rows(data["integrated"], region, department)
        pending = filter_rows(data["pending"], region, department)

        return render_template(
            "admin_department.html",
            user=user,
            department=department,
            region=region,
            integrated=integrated,
            pending=pending,
            all_rows=build_all_rows(integrated, pending),
            counts={
                "integrated": len(integrated),
                "pending": len(pending),
            },
            chart=build_chart({"integrated": len(integrated), "pending": len(pending)}),
        )

    @app.route("/admin/exceptions")
    def admin_exceptions():
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login"))
        department = (request.args.get("department") or "").strip()
        status = (request.args.get("status") or "").strip()
        submissions = list_exception_submissions_filtered(department, status)
        submissions = [
            {**dict(item), "age_days": age_days(item["submitted_at"])} for item in submissions
        ]
        departments = []
        data = get_recon()
        if data:
            departments = sorted({row.get("department", "") for row in data["itam_rows"] if row.get("department", "")})
        return render_template(
            "admin_exceptions.html",
            user=user,
            submissions=submissions,
            departments=departments,
            department=department,
            status=status,
        )

    @app.route("/admin/exceptions/<int:submission_id>", methods=["GET", "POST"])
    def admin_exception_review(submission_id: int):
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login"))
        submission = get_submission(submission_id)
        if not submission:
            return redirect(url_for("admin_exceptions"))

        submission_dict = dict(submission)
        submission_dict["age_days"] = age_days(submission["submitted_at"])

        note_filename = None
        if submission_dict.get("exception_note_path"):
            note_filename = submission_dict["exception_note_path"].split("/")[-1]

        if request.method == "POST":
            action = (request.form.get("action") or "").strip().lower()
            remarks = (request.form.get("remarks") or "").strip()
            verified = (request.form.get("verified") or "") == "on"
            if action not in {"approved", "rejected"}:
                return render_template(
                    "admin_exception_review.html",
                    user=user,
                    submission=submission_dict,
                    note_filename=note_filename,
                    error="Choose approve or reject.",
                )
            if action == "approved" and not verified:
                return render_template(
                    "admin_exception_review.html",
                    user=user,
                    submission=submission_dict,
                    note_filename=note_filename,
                    error="Please confirm approval note verification before approving.",
                )
            review_exception(submission_id, action, remarks, user["username"], verified)
            log_action(user["username"], "exception_review", f"id={submission_id}, action={action}")
            return redirect(url_for("admin_exceptions"))

        return render_template(
            "admin_exception_review.html",
            user=user,
            submission=submission_dict,
            note_filename=note_filename,
        )

    @app.route("/admin/exceptions/bulk", methods=["POST"])
    def admin_exception_bulk():
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login"))

        ids = request.form.getlist("submission_ids")
        action = (request.form.get("action") or "").strip().lower()
        remarks = (request.form.get("remarks") or "").strip()
        verified = (request.form.get("verified") or "") == "on"

        if action not in {"approved", "rejected"} or not ids:
            return redirect(url_for("admin_exceptions"))
        if action == "approved" and not verified:
            return redirect(url_for("admin_exceptions", status="pending"))

        for raw_id in ids:
            try:
                submission_id = int(raw_id)
            except ValueError:
                continue
            review_exception(submission_id, action, remarks, user["username"], verified)
        log_action(user["username"], "exception_bulk_review", f"count={len(ids)}, action={action}")
        return redirect(url_for("admin_exceptions"))

    @app.route("/admin/submissions/export")
    def admin_export_submissions():
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login"))
        rows = list_all_submissions()
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
            "exception_reason",
            "submitted_by",
            "submitted_at",
            "admin_status",
            "admin_reviewed_by",
            "admin_reviewed_at",
            "admin_remarks",
            "review_verified",
        ]
        import csv
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})
        response = Response(output.getvalue(), mimetype="text/csv")
        response.headers["Content-Disposition"] = "attachment; filename=submissions_audit.csv"
        return response

    @app.route("/admin/audit")
    def admin_audit():
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login"))
        logs = list_audit_logs()
        return render_template("admin_audit.html", user=user, logs=logs)

    @app.route("/export/admin")
    def export_admin():
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login"))

        data = get_recon()
        if not data:
            return redirect(url_for("admin"))

        export_type = (request.args.get("type") or "").strip().lower()
        region = (request.args.get("region") or "").strip()
        department = (request.args.get("department") or "").strip()

        if export_type == "integrated":
            rows = filter_rows(data["integrated"], region, department)
            rows = [{**row, "status": "Integrated"} for row in rows]
            return build_csv_download(rows, "integrated_servers.csv", include_status=True)
        if export_type == "pending":
            rows = filter_rows(data["pending"], region, department)
            rows = [{**row, "status": "Pending"} for row in rows]
            return build_csv_download(rows, "pending_servers.csv", include_status=True)
        if export_type == "all":
            rows = filter_rows(data["itam_rows"], region, department)
            integrated_keys = {(row.get("itam_id"), row.get("ip_address")) for row in data["integrated"]}
            with_status = []
            for row in rows:
                key = (row.get("itam_id"), row.get("ip_address"))
                status = "Integrated" if key in integrated_keys else "Pending"
                with_status.append({**row, "status": status})
            return build_csv_download(with_status, "all_servers.csv", include_status=True)

        return redirect(url_for("admin"))

    @app.route("/export/admin/department/<department>")
    def export_admin_department(department: str):
        user = current_user()
        if not user or user["role"] != "admin":
            return redirect(url_for("login"))

        data = get_recon()
        if not data:
            return redirect(url_for("admin"))

        export_type = (request.args.get("type") or "").strip().lower()
        department = department.strip()
        region = (request.args.get("region") or "").strip()

        if export_type == "integrated":
            rows = filter_rows(data["integrated"], region, department)
            rows = [{**row, "status": "Integrated"} for row in rows]
            return build_csv_download(rows, "integrated_servers.csv", include_status=True)
        if export_type == "pending":
            rows = filter_rows(data["pending"], region, department)
            rows = [{**row, "status": "Pending"} for row in rows]
            return build_csv_download(rows, "pending_servers.csv", include_status=True)
        if export_type == "all":
            rows = filter_rows(data["itam_rows"], region, department)
            integrated_keys = {(row.get("itam_id"), row.get("ip_address")) for row in data["integrated"]}
            with_status = []
            for row in rows:
                key = (row.get("itam_id"), row.get("ip_address"))
                status = "Integrated" if key in integrated_keys else "Pending"
                with_status.append({**row, "status": status})
            return build_csv_download(with_status, "all_servers.csv", include_status=True)

        return redirect(url_for("admin_department", department=department))
