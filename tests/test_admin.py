"""管理员接口测试：密码重置、任务恢复。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class TestAdminResetPassword:
    def test_admin_reset_password(self, client: TestClient, admin_token: str, db):
        from app.core.security import hash_password
        from app.models.db_models import Account, AccountRole

        target = Account(
            username='resetme',
            password_hash=hash_password('OldPass11'),
            role=AccountRole.USER,
            email='resetme@test.com',
            phone='13800000099',
        )
        db.add(target)
        db.flush()

        resp = client.post(
            '/api/v1/admin/reset-password',
            json={'account_id': target.id, 'new_password': 'NewPass22'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200  # 204 wrapped

        # 验证新密码可登录
        resp = client.post('/api/v1/auth/login', json={
            'identifier': 'resetme',
            'password': 'NewPass22',
        })
        assert resp.status_code == 200

    def test_admin_reset_nonexistent_account(self, client: TestClient, admin_token: str):
        resp = client.post(
            '/api/v1/admin/reset-password',
            json={'account_id': '00000000-0000-0000-0000-999999999999', 'new_password': 'NewPass22'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 404

    def test_user_cannot_reset_password(self, client: TestClient, user_token: str):
        resp = client.post(
            '/api/v1/admin/reset-password',
            json={'account_id': 'any-id', 'new_password': 'NewPass22'},
            headers={'Authorization': f'Bearer {user_token}'},
        )
        assert resp.status_code == 403


class TestAdminEndpoints:
    def test_user_cannot_access_admin(self, client: TestClient, user_token: str):
        resp = client.get(
            '/api/v1/admin/organizations',
            headers={'Authorization': f'Bearer {user_token}'},
        )
        assert resp.status_code == 403

    def test_admin_list_assessment_tasks(self, client: TestClient, admin_token: str):
        resp = client.get(
            '/api/v1/admin/assessment-tasks',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200
        body = resp.json()['data']
        assert 'items' in body
        assert 'total' in body
