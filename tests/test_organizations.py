"""公司管理接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestOrganizations:
    def test_admin_create_org(self, client: TestClient, admin_token: str):
        resp = client.post(
            '/api/v1/organizations',
            json={'name': '新建测试公司'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['name'] == '新建测试公司'
        assert 'id' in data

    def test_admin_list_orgs(self, client: TestClient, admin_token: str):
        resp = client.get(
            '/api/v1/organizations',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200
        body = resp.json()['data']
        assert body['total'] >= 1

    def test_user_list_only_own_org(self, client: TestClient, user_token: str):
        resp = client.get(
            '/api/v1/organizations',
            headers={'Authorization': f'Bearer {user_token}'},
        )
        assert resp.status_code == 200
        body = resp.json()['data']
        assert body['total'] == 1
        assert len(body['items']) == 1

    def test_admin_update_org(self, client: TestClient, admin_token: str):
        # 先创建
        resp = client.post(
            '/api/v1/organizations',
            json={'name': '待更新公司'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        org_id = resp.json()['data']['id']

        # 更新
        resp = client.patch(
            f'/api/v1/organizations/{org_id}',
            json={'name': '已更新公司'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200
        assert resp.json()['data']['name'] == '已更新公司'

    def test_admin_delete_and_restore_org(self, client: TestClient, admin_token: str):
        resp = client.post(
            '/api/v1/organizations',
            json={'name': '待删除公司'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        org_id = resp.json()['data']['id']

        # 删除
        resp = client.delete(
            f'/api/v1/organizations/{org_id}',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200  # 204 wrapped

        # 恢复
        resp = client.post(
            f'/api/v1/admin/organizations/{org_id}/restore',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200  # 204 wrapped

    def test_user_cannot_create_org(self, client: TestClient, user_token: str):
        resp = client.post(
            '/api/v1/organizations',
            json={'name': '用户不能创建'},
            headers={'Authorization': f'Bearer {user_token}'},
        )
        assert resp.status_code == 403

    def test_no_auth_rejected(self, client: TestClient):
        resp = client.get('/api/v1/organizations')
        assert resp.status_code == 401
