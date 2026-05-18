"""认证接口测试：注册、登录、修改密码。"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestRegister:
    def test_register_success(self, client: TestClient):
        resp = client.post('/api/v1/auth/register', json={
            'username': 'newuser01',
            'password': 'Abcd1234',
            'email': 'new01@example.com',
            'phone': '13900000001',
        })
        assert resp.status_code == 200
        data = resp.json()['data']
        assert 'access_token' in data
        assert data['token_type'] == 'bearer'

    def test_register_duplicate_username(self, client: TestClient):
        payload = {
            'username': 'dupuser',
            'password': 'Abcd1234',
            'email': 'dup1@example.com',
            'phone': '13900000010',
        }
        client.post('/api/v1/auth/register', json=payload)
        resp = client.post('/api/v1/auth/register', json={
            **payload,
            'email': 'dup2@example.com',
            'phone': '13900000011',
        })
        assert resp.status_code == 409
        assert resp.json()['code'] == 'USERNAME_EXISTS'

    def test_register_weak_password(self, client: TestClient):
        resp = client.post('/api/v1/auth/register', json={
            'username': 'weakpwd',
            'password': 'alllower1',
            'email': 'weak@example.com',
            'phone': '13900000020',
        })
        # Pydantic 校验失败返回 422 或异常处理器返回 400/500
        assert resp.status_code in (400, 422, 500)


class TestLogin:
    def test_login_success(self, client: TestClient, admin_token: str):
        resp = client.post('/api/v1/auth/login', json={
            'identifier': 'testadmin',
            'password': 'Admin123x',
        })
        assert resp.status_code == 200
        data = resp.json()['data']
        assert 'access_token' in data

    def test_login_wrong_password(self, client: TestClient, admin_token: str):
        resp = client.post('/api/v1/auth/login', json={
            'identifier': 'testadmin',
            'password': 'WrongPass1',
        })
        assert resp.status_code == 401
        assert resp.json()['code'] == 'AUTH_FAILED'

    def test_login_nonexistent_user(self, client: TestClient):
        resp = client.post('/api/v1/auth/login', json={
            'identifier': 'ghost_user',
            'password': 'Abcd1234',
        })
        assert resp.status_code == 401


class TestChangePassword:
    def test_change_password_success(self, client: TestClient, admin_token: str):
        resp = client.post(
            '/api/v1/auth/change-password',
            json={'old_password': 'Admin123x', 'new_password': 'NewPass99'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200  # 204 wrapped to 200 by envelope

    def test_change_password_wrong_old(self, client: TestClient, admin_token: str):
        resp = client.post(
            '/api/v1/auth/change-password',
            json={'old_password': 'WrongOld1', 'new_password': 'NewPass99'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 400
        assert resp.json()['code'] == 'OLD_PASSWORD_WRONG'

    def test_change_password_same_as_old(self, client: TestClient, admin_token: str):
        resp = client.post(
            '/api/v1/auth/change-password',
            json={'old_password': 'Admin123x', 'new_password': 'Admin123x'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 400
        assert resp.json()['code'] == 'PASSWORD_UNCHANGED'

    def test_change_password_no_auth(self, client: TestClient):
        resp = client.post(
            '/api/v1/auth/change-password',
            json={'old_password': 'Admin123x', 'new_password': 'NewPass99'},
        )
        assert resp.status_code == 401
