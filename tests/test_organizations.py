"""Organization API permission tests."""

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

    def test_org_admin_list_only_own_org(self, client: TestClient, org_admin_token: str, db):
        from app.models.db_models import Organization

        db.add(Organization(name='其他租户公司'))
        db.flush()

        resp = client.get(
            '/api/v1/organizations',
            headers={'Authorization': f'Bearer {org_admin_token}'},
        )
        assert resp.status_code == 200
        body = resp.json()['data']
        assert body['total'] == 1
        assert len(body['items']) == 1

    def test_admin_update_org(self, client: TestClient, admin_token: str):
        resp = client.post(
            '/api/v1/organizations',
            json={'name': '待更新公司'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        org_id = resp.json()['data']['id']

        resp = client.patch(
            f'/api/v1/organizations/{org_id}',
            json={'name': '已更新公司'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200
        assert resp.json()['data']['name'] == '已更新公司'

    def test_org_admin_can_update_own_org_only(
        self,
        client: TestClient,
        org_admin_token: str,
        db,
    ):
        from app.core.config import settings
        from app.models.db_models import Organization

        other_org = Organization(name='其他租户公司')
        db.add(other_org)
        db.flush()

        own_resp = client.patch(
            f'/api/v1/organizations/{settings.default_organization_id}',
            json={'contact_name': '组织管理员'},
            headers={'Authorization': f'Bearer {org_admin_token}'},
        )
        assert own_resp.status_code == 200
        assert own_resp.json()['data']['contact_name'] == '组织管理员'

        other_resp = client.patch(
            f'/api/v1/organizations/{other_org.id}',
            json={'contact_name': '越权修改'},
            headers={'Authorization': f'Bearer {org_admin_token}'},
        )
        assert other_resp.status_code == 403

    def test_user_cannot_update_own_org(self, client: TestClient, user_token: str):
        from app.core.config import settings

        resp = client.patch(
            f'/api/v1/organizations/{settings.default_organization_id}',
            json={'contact_name': '普通员工'},
            headers={'Authorization': f'Bearer {user_token}'},
        )
        assert resp.status_code == 403

    def test_admin_delete_and_restore_org(self, client: TestClient, admin_token: str):
        resp = client.post(
            '/api/v1/organizations',
            json={'name': '待删除公司'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        org_id = resp.json()['data']['id']

        resp = client.delete(
            f'/api/v1/organizations/{org_id}',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200  # 204 wrapped

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

    def test_org_admin_cannot_create_or_delete_org(
        self,
        client: TestClient,
        org_admin_token: str,
        db,
    ):
        from app.models.db_models import Organization

        create_resp = client.post(
            '/api/v1/organizations',
            json={'name': '组织管理员不能新建公司'},
            headers={'Authorization': f'Bearer {org_admin_token}'},
        )
        assert create_resp.status_code == 403

        other_org = Organization(name='组织管理员不能删除公司')
        db.add(other_org)
        db.flush()
        delete_resp = client.delete(
            f'/api/v1/organizations/{other_org.id}',
            headers={'Authorization': f'Bearer {org_admin_token}'},
        )
        assert delete_resp.status_code == 403

    def test_no_auth_rejected(self, client: TestClient):
        resp = client.get('/api/v1/organizations')
        assert resp.status_code == 401
