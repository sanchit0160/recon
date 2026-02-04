# ITAM vs PIMS Reconciliation

This Flask app reconciles ITAM servers with the PIMS Active Service report by IP address. It supports admin and department views.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000

## Default Admin (DB)

On first run, a default admin user is created:

- `admin` / `admin123`

You can override with environment variables:
- `ADMIN_USER`
- `ADMIN_PASS`

Set `SECRET_KEY` in your environment for production use.

## Expected Columns

ITAM Dump (CSV) must include:
- itam_id
- hostname
- region
- department
- environment
- ip_address

PIMS report must include a column like `ip_address` or `ip address`.
