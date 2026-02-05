import os
from pathlib import Path
import tempfile
import pytest

from recon import create_app


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("RECON_DATA_DIR", str(tmp_path / "data"))
    app = create_app()
    app.config.update({"TESTING": True})
    return app


@pytest.fixture()
def client(app):
    return app.test_client()
