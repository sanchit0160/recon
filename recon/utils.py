import csv
import io
import re
import ipaddress
from datetime import datetime
from typing import Dict, List, Tuple
from .config import REQUIRED_ITAM_FIELDS
from .state import get_recon


def normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def read_csv(file_storage) -> Tuple[List[Dict[str, str]], List[str]]:
    filename = file_storage.filename or ""
    data = file_storage.read()
    if not data:
        return [], []

    text = data.decode("utf-8-sig", errors="replace")
    buf = io.StringIO(text)
    reader = csv.DictReader(buf)
    if not reader.fieldnames:
        return [], []

    raw_headers = reader.fieldnames
    normalized_headers = [normalize_header(h) for h in raw_headers]
    header_map = {raw: norm for raw, norm in zip(raw_headers, normalized_headers)}

    rows: List[Dict[str, str]] = []
    for row in reader:
        normalized_row = {}
        for raw_key, value in row.items():
            if raw_key is None:
                continue
            normalized_key = header_map.get(raw_key, normalize_header(raw_key))
            normalized_row[normalized_key] = (value or "").strip()
        rows.append(normalized_row)

    return rows, normalized_headers


def extract_ip_set(rows: List[Dict[str, str]], headers: List[str]) -> Tuple[set, str | None]:
    candidates = ["ip_address", "ip", "ipaddress", "ip_addr", "ipaddresss", "ip_addresss", "ipaddress_"]
    ip_field = None
    for candidate in candidates:
        if candidate in headers:
            ip_field = candidate
            break

    if ip_field is None:
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


def filter_rows(rows: List[Dict[str, str]], region: str, department: str) -> List[Dict[str, str]]:
    filtered = rows
    if region:
        filtered = [row for row in filtered if row.get("region", "") == region]
    if department:
        filtered = [row for row in filtered if row.get("department", "") == department]
    return filtered


def build_department_summary(itam_rows, integrated_rows, pending_rows, status_overrides: dict | None = None):
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
            if status_overrides and status_overrides.get(submission_key(row)):
                entry["integrated"] += 1
            else:
                entry["pending"] += 1
    return sorted(summary.values(), key=lambda item: item["department"].lower())


def build_region_summary(itam_rows, integrated_rows, pending_rows, status_overrides: dict | None = None):
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
            if status_overrides and status_overrides.get(submission_key(row)):
                entry["integrated"] += 1
            else:
                entry["pending"] += 1
    return sorted(summary.values(), key=lambda item: item["region"].lower())


def build_department_map(itam_rows):
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


def build_metrics(itam_rows, integrated_rows, pending_rows):
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


def itam_lookup(hostname: str, ip_address: str, itam_id: str, department: str | None):
    data = get_recon()
    if not data:
        return None
    for row in data["itam_rows"]:
        if department and row.get("department", "") != department:
            continue
        if itam_id and row.get("itam_id", "").strip().lower() == itam_id.lower():
            return row
        if hostname and row.get("hostname", "").strip().lower() == hostname.lower():
            return row
        if ip_address and row.get("ip_address", "").strip() == ip_address:
            return row
    return None


def build_all_rows(integrated_rows, pending_rows, status_overrides: dict | None = None):
    all_rows = []
    for row in integrated_rows:
        tagged = dict(row)
        tagged["_status"] = "Integrated"
        all_rows.append(tagged)
    for row in pending_rows:
        tagged = dict(row)
        tagged["_status"] = "Pending"
        all_rows.append(tagged)
    if status_overrides:
        all_rows = apply_status_overrides(all_rows, status_overrides)
    return all_rows


def build_chart(counts: dict) -> dict:
    total = counts.get("itam_total") or (counts.get("integrated", 0) + counts.get("pending", 0))
    if total <= 0:
        return {"integrated_pct": 0, "pending_pct": 0}
    integrated_pct = round((counts.get("integrated", 0) / total) * 100)
    pending_pct = max(0, 100 - integrated_pct)
    return {"integrated_pct": integrated_pct, "pending_pct": pending_pct}


def age_days(submitted_at: str) -> int:
    try:
        dt = datetime.strptime(submitted_at, "%Y-%m-%d %H:%M:%S")
        delta = datetime.now() - dt
        return max(0, delta.days)
    except ValueError:
        return 0


def is_valid_ip(value: str) -> bool:
    raw = value.strip()
    if not raw:
        return False
    if "/" in raw:
        ip_part = raw.split("/", 1)[0].strip()
    else:
        ip_part = raw
    try:
        ipaddress.ip_address(ip_part)
        return True
    except ValueError:
        return False


def is_valid_hostname(value: str) -> bool:
    raw = value.strip()
    if not raw or len(raw) > 253:
        return False
    return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,251}[A-Za-z0-9]$", raw))


def csv_response(rows: List[Dict[str, str]], filename: str, include_status: bool = False):
    output = io.StringIO()
    fieldnames = list(REQUIRED_ITAM_FIELDS)
    if include_status and "status" not in fieldnames:
        fieldnames = ["status"] + fieldnames
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        data = {key: row.get(key, "") for key in REQUIRED_ITAM_FIELDS}
        if include_status:
            data["status"] = row.get("status", "")
        writer.writerow(data)
    return output.getvalue()


def submission_key(item: dict) -> tuple:
    itam_id = (item.get("itam_id") or "").strip().lower()
    hostname = (item.get("hostname") or "").strip().lower()
    ip_address = (item.get("ip_address") or "").strip()
    return (itam_id, hostname, ip_address)


def submission_key_fallback(item: dict) -> tuple:
    hostname = (item.get("hostname") or "").strip().lower()
    ip_address = (item.get("ip_address") or "").strip()
    return ("", hostname, ip_address)


def build_status_overrides(submissions: list) -> dict:
    overrides = {}
    for item in submissions:
        data = dict(item) if not isinstance(item, dict) else item
        sub_type = (data.get("submission_type") or "").lower()
        is_exception = bool(data.get("is_exception")) or sub_type == "exception"
        admin_status = (data.get("admin_status") or "").lower()
        if admin_status != "approved":
            continue
        if is_exception:
            overrides[submission_key(data)] = "Exception"
            overrides[submission_key_fallback(data)] = "Exception"
        elif sub_type == "proxy_integrated":
            overrides[submission_key(data)] = "Integrated (Proxy)"
            overrides[submission_key_fallback(data)] = "Integrated (Proxy)"
    return overrides


def apply_status_overrides(rows: list, overrides: dict) -> list:
    updated = []
    for row in rows:
        tagged = dict(row)
        key = submission_key(tagged)
        alt_key = submission_key_fallback(tagged)
        if key in overrides:
            tagged["_status"] = overrides[key]
        elif alt_key in overrides:
            tagged["_status"] = overrides[alt_key]
        updated.append(tagged)
    return updated


def adjust_counts(integrated_rows: list, pending_rows: list, overrides: dict) -> dict:
    proxy_or_exception = 0
    for row in pending_rows:
        key = submission_key(row)
        alt_key = submission_key_fallback(row)
        if key in overrides or alt_key in overrides:
            proxy_or_exception += 1
    integrated_count = len(integrated_rows) + proxy_or_exception
    pending_count = max(0, len(pending_rows) - proxy_or_exception)
    return {
        "integrated": integrated_count,
        "pending": pending_count,
    }
