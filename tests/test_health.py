"""健康检查与基础路由测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealthCheck:
    def test_root_healthz(self, client: TestClient):
        resp = client.get('/healthz')
        assert resp.status_code == 200
        assert resp.json()['status'] == 'ok'

    def test_request_context_headers(self, client: TestClient):
        trace_id = '1234567890abcdef1234567890abcdef'
        resp = client.get(
            '/healthz',
            headers={
                'X-Request-Id': 'unit-request-id',
                'traceparent': f'00-{trace_id}-1234567890abcdef-01',
            },
        )

        assert resp.status_code == 200
        assert resp.headers['X-Request-Id'] == 'unit-request-id'
        assert resp.headers['traceparent'].startswith(f'00-{trace_id}-')
        assert resp.headers['X-Process-Time-Ms'].isdigit()

    def test_v1_healthz(self, client: TestClient):
        resp = client.get('/api/v1/healthz')
        assert resp.status_code == 200
        body = resp.json()
        # v1 healthz 经过信封包装
        if 'data' in body:
            assert body['data']['status'] == 'ok'
        else:
            assert body['status'] == 'ok'

    def test_v1_readyz(self, client: TestClient, monkeypatch):
        monkeypatch.setattr('app.api.v1.endpoints.system._check_database', lambda: (True, None))
        monkeypatch.setattr('app.api.v1.endpoints.system._check_redis', lambda: (True, None))

        resp = client.get('/api/v1/readyz')
        assert resp.status_code == 200
        body = resp.json()
        data = body.get('data') or body
        assert data['status'] == 'ready'
        assert data['checks']['database']['ok'] is True
        assert data['checks']['redis']['ok'] is True

    def test_v1_readyz_returns_503_when_dependency_fails(self, client: TestClient, monkeypatch):
        monkeypatch.setattr('app.api.v1.endpoints.system._check_database', lambda: (True, None))
        monkeypatch.setattr('app.api.v1.endpoints.system._check_redis', lambda: (False, 'RedisError'))

        resp = client.get('/api/v1/readyz')
        assert resp.status_code == 503
        body = resp.json()
        assert body['status'] == 'degraded'
        assert body['checks']['redis']['ok'] is False

    def test_openapi_schema(self, client: TestClient):
        resp = client.get('/openapi.json')
        assert resp.status_code == 200
        schema = resp.json()
        assert 'paths' in schema
        assert '/api/v1/auth/login' in schema['paths']
        assert '/api/v1/assessment' in schema['paths']
