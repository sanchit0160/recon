from datetime import datetime
from ..utils import extract_ip_set


def reconcile_reports(itam_rows, pims_rows, pims_headers):
    pims_ips, pims_ip_field = extract_ip_set(pims_rows, pims_headers)
    if not pims_ip_field:
        return None, "Could not find an IP Address column in the PIMS report. Please include a column like 'ip_address' or 'ip address'."

    integrated = []
    pending = []
    for row in itam_rows:
        ip_value = row.get("ip_address", "")
        if ip_value and ip_value in pims_ips:
            integrated.append(row)
        else:
            pending.append(row)

    recon = {
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
    return recon, None
