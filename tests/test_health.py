"""健康检查与基础路由测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealthCheck:
    def test_root_healthz(self, client: TestClient):
        resp = client.get('/healthz')
        assert resp.status_code == 200
        assert resp.json()['status'] == 'ok'

    def test_v1_healthz(self, client: TestClient):
        resp = client.get('/api/v1/healthz')
        assert resp.status_code == 200
        body = resp.json()
        # v1 healthz 经过信封包装
        if 'data' in body:
            assert body['data']['status'] == 'ok'
        else:
            assert body['status'] == 'ok'

    def test_openapi_schema(self, client: TestClient):
        resp = client.get('/openapi.json')
        assert resp.status_code == 200
        schema = resp.json()
        assert 'paths' in schema
        assert '/api/v1/auth/login' in schema['paths']
        assert '/api/v1/assessment' in schema['paths']
