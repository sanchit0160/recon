import csv
import io
from flask import Response, jsonify, redirect, render_template, request, send_from_directory, url_for
from .auth import current_user
from .db import (
    list_submissions_by_department,
    submission_exists,
)
from .services.submission_service import submit_department_server
from .state import get_recon
from .utils import (
    age_days,
    build_all_rows,
    build_chart,
    filter_rows,
    is_valid_hostname,
    is_valid_ip,
    itam_lookup,
    read_csv,
)
from .services.export_service import build_csv_download


def register_routes(app):
    @app.route("/department")
    def department_view():
        user = current_user()
        if not user or user["role"] != "department":
            return redirect(url_for("login"))

        data = get_recon()
        if not data:
            return render_template("department.html", user=user, data_available=False)

        dept_name = user.get("department") or ""
        integrated = filter_rows(data["integrated"], "", dept_name)
        pending = filter_rows(data["pending"], "", dept_name)

        submissions = list_submissions_by_department(dept_name)
        submissions = [
            {**dict(item), "age_days": age_days(item["submitted_at"])} for item in submissions
        ]
        return render_template(
            "department.html",
            user=user,
            data_available=True,
            integrated=integrated,
            pending=pending,
            all_rows=build_all_rows(integrated, pending),
            counts={
                "integrated": len(integrated),
                "pending": len(pending),
            },
            submissions=submissions,
            chart=build_chart({"integrated": len(integrated), "pending": len(pending)}),
        )

    @app.route("/api/itam_lookup")
    def api_itam_lookup():
        user = current_user()
        if not user:
            return jsonify({})
        hostname = (request.args.get("hostname") or "").strip()
        ip_address = (request.args.get("ip_address") or "").strip()
        itam_id = (request.args.get("itam_id") or "").strip()
        department = user.get("department")
        match = itam_lookup(hostname, ip_address, itam_id, department)
        if not match:
            return jsonify({})
        return jsonify(match)

    @app.route("/department/submit", methods=["GET", "POST"])
    def department_submit():
        user = current_user()
        if not user or user["role"] != "department":
            return redirect(url_for("login"))

        data = get_recon()
        itam_hostnames = []
        itam_ips = []
        itam_ids = []
        itam_regions = []
        itam_envs = []

        if data:
            dept = user.get("department") or ""
            itam_hostnames = sorted(
                {
                    row.get("hostname", "")
                    for row in data["itam_rows"]
                    if row.get("hostname", "") and row.get("department", "") == dept
                }
            )
            itam_ips = sorted(
                {
                    row.get("ip_address", "")
                    for row in data["itam_rows"]
                    if row.get("ip_address", "") and row.get("department", "") == dept
                }
            )
            itam_ids = sorted(
                {
                    row.get("itam_id", "")
                    for row in data["itam_rows"]
                    if row.get("itam_id", "") and row.get("department", "") == dept
                }
            )
            itam_regions = sorted(
                {
                    row.get("region", "")
                    for row in data["itam_rows"]
                    if row.get("region", "") and row.get("department", "") == dept
                }
            )
            itam_envs = sorted(
                {
                    row.get("environment", "")
                    for row in data["itam_rows"]
                    if row.get("environment", "") and row.get("department", "") == dept
                }
            )

        error = None
        if request.method == "POST":
            itam_id = (request.form.get("itam_id") or "").strip()
            hostname = (request.form.get("hostname") or "").strip()
            ip_address = (request.form.get("ip_address") or "").strip()
            environment = (request.form.get("environment") or "").strip()
            region = (request.form.get("region") or "").strip()
            is_exception = (request.form.get("is_exception") or "") == "on"
            justification = (request.form.get("justification") or "").strip()
            exception_reason = (request.form.get("exception_reason") or "").strip()
            note_file = request.files.get("exception_note")

            if not itam_id:
                error = "ITAM ID is required."
            elif not hostname or not ip_address:
                error = "Hostname and IP address are required."
            elif not is_valid_hostname(hostname):
                error = "Please provide a valid hostname."
            elif not is_valid_ip(ip_address):
                error = "Please provide a valid IP address."
            elif is_exception and not (note_file and note_file.filename):
                error = "Approval note attachment is required for exceptions."
            elif is_exception and not exception_reason:
                error = "Please select an exception reason."
            elif submission_exists(user["department"] or "", hostname, ip_address):
                error = "A pending submission for this server already exists."
            else:
                submit_department_server(
                    department=user["department"] or "",
                    hostname=hostname,
                    ip_address=ip_address,
                    environment=environment,
                    region=region,
                    is_exception=is_exception,
                    exception_note_file=note_file,
                    justification=justification,
                    exception_reason=exception_reason,
                    submitted_by=user["username"],
                )
                return redirect(url_for("department_view"))

        return render_template(
            "department_submit.html",
            user=user,
            error=error,
            itam_hostnames=itam_hostnames,
            itam_ips=itam_ips,
            itam_ids=itam_ids,
            itam_regions=itam_regions,
            itam_envs=itam_envs,
        )

    @app.route("/uploads/<path:filename>")
    def download_upload(filename: str):
        user = current_user()
        if not user:
            return redirect(url_for("login"))
        return send_from_directory(str(UPLOADS_DIR), filename, as_attachment=True)

    @app.route("/department/bulk-upload", methods=["POST"])
    def department_bulk_upload():
        user = current_user()
        if not user or user["role"] != "department":
            return redirect(url_for("login"))

        upload = request.files.get("bulk_file")
        if not upload or not upload.filename:
            return redirect(url_for("department_submit"))

        rows, headers = read_csv(upload)
        required = {"itam_id", "hostname", "ip_address"}
        if not required.issubset(set(headers)):
            return render_template(
                "department_submit.html",
                user=user,
                error="Bulk CSV must include hostname and ip_address columns.",
                itam_hostnames=[],
                itam_ips=[],
            )

        created = 0
        skipped = 0
        errors = []
        for idx, row in enumerate(rows, start=2):
            itam_id = (row.get("itam_id") or "").strip()
            hostname = (row.get("hostname") or "").strip()
            ip_address = (row.get("ip_address") or "").strip()
            environment = (row.get("environment") or "").strip()
            region = (row.get("region") or "").strip()
            is_exception = (row.get("is_exception") or "").strip().lower() in {"yes", "true", "1"}
            justification = (row.get("justification") or "").strip()
            exception_reason = (row.get("exception_reason") or "").strip()

            if not itam_id:
                errors.append(f"Row {idx}: itam_id required.")
                skipped += 1
                continue
            if not hostname or not ip_address:
                errors.append(f"Row {idx}: hostname/ip_address required.")
                skipped += 1
                continue
            if not is_valid_hostname(hostname):
                errors.append(f"Row {idx}: invalid hostname.")
                skipped += 1
                continue
            if not is_valid_ip(ip_address):
                errors.append(f"Row {idx}: invalid IP address.")
                skipped += 1
                continue
            if is_exception and not justification:
                errors.append(f"Row {idx}: justification required for exceptions.")
                skipped += 1
                continue
            if is_exception and not exception_reason:
                errors.append(f"Row {idx}: exception_reason required for exceptions.")
                skipped += 1
                continue
            if submission_exists(user["department"] or "", hostname, ip_address):
                skipped += 1
                continue

            create_submission(
                department=user["department"] or "",
                hostname=hostname,
                ip_address=ip_address,
                environment=environment,
                region=region,
                is_exception=is_exception,
                exception_note_path=None,
                justification=justification,
                exception_reason=exception_reason,
                submitted_by=user["username"],
            )
            created += 1

        log_action(user["username"], "bulk_upload", f"created={created}, skipped={skipped}")
        itam_hostnames = []
        itam_ips = []
        itam_ids = []
        itam_regions = []
        itam_envs = []
        data = get_recon()
        if data:
            dept = user.get("department") or ""
            itam_hostnames = sorted(
                {
                    row.get("hostname", "")
                    for row in data["itam_rows"]
                    if row.get("hostname", "") and row.get("department", "") == dept
                }
            )
            itam_ips = sorted(
                {
                    row.get("ip_address", "")
                    for row in data["itam_rows"]
                    if row.get("ip_address", "") and row.get("department", "") == dept
                }
            )
            itam_ids = sorted(
                {
                    row.get("itam_id", "")
                    for row in data["itam_rows"]
                    if row.get("itam_id", "") and row.get("department", "") == dept
                }
            )
            itam_regions = sorted(
                {
                    row.get("region", "")
                    for row in data["itam_rows"]
                    if row.get("region", "") and row.get("department", "") == dept
                }
            )
            itam_envs = sorted(
                {
                    row.get("environment", "")
                    for row in data["itam_rows"]
                    if row.get("environment", "") and row.get("department", "") == dept
                }
            )
        return render_template(
            "department_submit.html",
            user=user,
            success=f"Bulk upload complete: {created} created, {skipped} skipped.",
            errors=errors,
            itam_hostnames=itam_hostnames,
            itam_ips=itam_ips,
            itam_ids=itam_ids,
            itam_regions=itam_regions,
            itam_envs=itam_envs,
        )

    @app.route("/department/bulk-template")
    def department_bulk_template():
        user = current_user()
        if not user or user["role"] != "department":
            return redirect(url_for("login"))
        output = io.StringIO()
        fieldnames = ["itam_id", "hostname", "ip_address", "environment", "region", "is_exception", "exception_reason", "justification"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        response = Response(output.getvalue(), mimetype="text/csv")
        response.headers["Content-Disposition"] = "attachment; filename=bulk_template.csv"
        return response

    @app.route("/export/department")
    def export_department():
        user = current_user()
        if not user or user["role"] != "department":
            return redirect(url_for("login"))

        data = get_recon()
        if not data:
            return redirect(url_for("department_view"))

        export_type = (request.args.get("type") or "").strip().lower()
        department = user.get("department") or ""

        if export_type == "integrated":
            rows = filter_rows(data["integrated"], "", department)
            rows = [{**row, "status": "Integrated"} for row in rows]
            return build_csv_download(rows, "integrated_servers.csv", include_status=True)
        if export_type == "pending":
            rows = filter_rows(data["pending"], "", department)
            rows = [{**row, "status": "Pending"} for row in rows]
            return build_csv_download(rows, "pending_servers.csv", include_status=True)
        if export_type == "all":
            rows = filter_rows(data["itam_rows"], "", department)
            integrated_keys = {(row.get("itam_id"), row.get("ip_address")) for row in data["integrated"]}
            with_status = []
            for row in rows:
                key = (row.get("itam_id"), row.get("ip_address"))
                status = "Integrated" if key in integrated_keys else "Pending"
                with_status.append({**row, "status": status})
            return build_csv_download(with_status, "all_servers.csv", include_status=True)

        return redirect(url_for("department_view"))
