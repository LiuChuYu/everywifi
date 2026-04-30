def test_register_valid(client):
    rv = client.post('/register', data={
        'username': 'newuser',
        'email': 'new@example.com',
        'password': 'password123',
        'confirm_password': 'password123'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b'Registration successful' in rv.data or b'Login' in rv.data

def test_register_duplicate_username(client):
    data = {
        'username': 'dupuser',
        'email': 'dup@example.com',
        'password': 'pass123',
        'confirm_password': 'pass123'
    }
    client.post('/register', data=data)
    rv = client.post('/register', data={
        'username': 'dupuser',
        'email': 'other@example.com',
        'password': 'pass123',
        'confirm_password': 'pass123'
    }, follow_redirects=True)
    assert b'already exists' in rv.data

def test_register_mismatched_passwords(client):
    rv = client.post('/register', data={
        'username': 'mismatch',
        'email': 'mm@example.com',
        'password': 'pass123',
        'confirm_password': 'different'
    }, follow_redirects=True)
    assert b'do not match' in rv.data

def test_login_valid(client):
    client.post('/register', data={
        'username': 'loginuser',
        'email': 'login@example.com',
        'password': 'pass123',
        'confirm_password': 'pass123'
    })
    rv = client.post('/login', data={
        'username': 'loginuser',
        'password': 'pass123'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b'Dashboard' in rv.data or b'balance' in rv.data.lower()

def test_login_invalid(client):
    rv = client.post('/login', data={
        'username': 'nobody',
        'password': 'wrong'
    }, follow_redirects=True)
    assert b'Invalid' in rv.data

def test_logout(auth_client):
    rv = auth_client.get('/logout', follow_redirects=True)
    assert rv.status_code == 200
    assert b'EveryWifi' in rv.data
