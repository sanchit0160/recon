from werkzeug.security import generate_password_hash
from recon.db import db_connect


def test_login_page(client):
    res = client.get('/login')
    assert res.status_code == 200


def test_login_flow(client):
    # create user
    conn = db_connect()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, department) VALUES (?, ?, ?, ?)",
            ("deptuser", generate_password_hash("pass"), "department", "IT"),
        )
        conn.commit()
    finally:
        conn.close()

    res = client.post('/login', data={'username': 'deptuser', 'password': 'pass'}, follow_redirects=False)
    assert res.status_code in (302, 303)
