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


def test_change_password(client):
    from recon.db import db_connect
    from werkzeug.security import generate_password_hash

    conn = db_connect()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, department) VALUES (?, ?, ?, ?)",
            ("user2", generate_password_hash("oldpass"), "department", "IT"),
        )
        conn.commit()
    finally:
        conn.close()

    # login
    client.post('/login', data={'username': 'user2', 'password': 'oldpass'})

    res = client.post('/account/password', data={
        'current_password': 'oldpass',
        'new_password': 'newpass',
        'confirm_password': 'newpass'
    })
    assert res.status_code == 200


def test_password_strength_enforced(client):
    from recon.db import db_connect
    from werkzeug.security import generate_password_hash

    conn = db_connect()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, department) VALUES (?, ?, ?, ?)",
            ("user3", generate_password_hash("Oldpass1!"), "department", "IT"),
        )
        conn.commit()
    finally:
        conn.close()

    client.post('/login', data={'username': 'user3', 'password': 'Oldpass1!'})

    res = client.post('/account/password', data={
        'current_password': 'Oldpass1!',
        'new_password': 'short',
        'confirm_password': 'short'
    })
    assert res.status_code == 200
