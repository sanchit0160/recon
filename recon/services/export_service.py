from flask import Response
from ..utils import csv_response


def build_csv_download(rows, filename: str, include_status: bool = False):
    body = csv_response(rows, filename, include_status=include_status)
    response = Response(body, mimetype="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response
