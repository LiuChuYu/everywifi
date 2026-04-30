def test_dashboard_redirect_when_unauthenticated(client):
    rv = client.get('/account/dashboard', follow_redirects=False)
    assert rv.status_code == 302

def test_dashboard_shows_balance(auth_client):
    rv = auth_client.get('/account/dashboard', follow_redirects=True)
    assert rv.status_code == 200
    assert b'Balance' in rv.data or b'balance' in rv.data.lower()

def test_topup_valid_amount(auth_client):
    rv = auth_client.post('/account/topup', data={'amount': '100'}, follow_redirects=True)
    assert rv.status_code == 200
    assert b'100' in rv.data

def test_topup_invalid_amount(auth_client):
    rv = auth_client.post('/account/topup', data={'amount': '-10'}, follow_redirects=True)
    assert rv.status_code == 200
    assert b'between' in rv.data or b'Invalid' in rv.data

def test_transactions_page(auth_client):
    auth_client.post('/account/topup', data={'amount': '50'})
    rv = auth_client.get('/account/transactions')
    assert rv.status_code == 200
    assert b'topup' in rv.data

def test_profile_page_loads(auth_client):
    rv = auth_client.get('/account/profile')
    assert rv.status_code == 200
    assert b'testuser' in rv.data

def test_profile_email_update(auth_client):
    rv = auth_client.post('/account/profile', data={
        'email': 'newemail@example.com',
        'current_password': '',
        'new_password': '',
        'confirm_new_password': ''
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b'updated' in rv.data or b'newemail' in rv.data

def test_profile_password_change(auth_client):
    rv = auth_client.post('/account/profile', data={
        'email': '',
        'current_password': 'testpass123',
        'new_password': 'newpass456',
        'confirm_new_password': 'newpass456'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b'updated' in rv.data or b'success' in rv.data.lower()
