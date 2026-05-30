from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.models.db_models import StandardDocument


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _create_approved_source(
    client: TestClient,
    admin_token: str,
    *,
    source_name: str = 'Authorized test source',
    license_no: str = 'LIC-TEST-001',
    allow_excerpt_export: bool = True,
) -> str:
    created = client.post(
        '/api/v1/standards/sources',
        json={
            'source_name': source_name,
            'source_type': 'AUTHORIZED_PURCHASE',
            'provider_name': 'Test Provider',
            'license_no': license_no,
            'license_scope': 'Unit test authorized storage and retrieval.',
            'allow_storage': True,
            'allow_vectorization': True,
            'allow_ai_retrieval': True,
            'allow_excerpt_export': allow_excerpt_export,
        },
        headers=_auth(admin_token),
    )
    assert created.status_code == 200
    source_id = created.json()['data']['id']

    reviewed = client.patch(
        f'/api/v1/standards/sources/{source_id}/review',
        json={'review_status': 'APPROVED'},
        headers=_auth(admin_token),
    )
    assert reviewed.status_code == 200
    assert reviewed.json()['data']['review_status'] == 'APPROVED'
    return source_id


def test_standard_manifest_import_and_search_without_file_upload(
    client: TestClient,
    admin_token: str,
    user_token: str,
    db,
):
    source_id = _create_approved_source(client, admin_token)
    payload = {
        'documents': [
            {
                'standard_code': 'TEST-STD-001',
                'standard_name': '测试标准',
                'domain': 'occupational_health',
                'service_type': '定期检测',
                'source_id': source_id,
                'storage_backend': 'minio',
                'bucket': 'ehs-standard-library',
                'object_key': 'raw/occupational_health/test-std-001.pdf',
                'file_hash': 'a' * 64,
                'source_format': 'pdf',
                'is_sensitive': False,
                'metadata': {'uploaded_by_user': True},
                'chunks': [
                    {
                        'chunk_index': 0,
                        'clause': '4.1',
                        'text_chunk': '测试因子甲的测试限值依据：PC-TWA 为 10 test-unit。',
                        'page_start': 12,
                        'page_end': 12,
                    }
                ],
            }
        ]
    }

    resp = client.post(
        '/api/v1/standards/manifest/import',
        json=payload,
        headers=_auth(admin_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    assert data['documents_created'] == 1
    assert data['chunks_written'] == 1

    doc = db.query(StandardDocument).filter_by(file_hash='a' * 64).one()
    assert doc.storage_backend == 'minio'
    assert doc.bucket == 'ehs-standard-library'
    assert doc.object_key == 'raw/occupational_health/test-std-001.pdf'
    assert (
        doc.source_path == 'minio://ehs-standard-library/raw/occupational_health/test-std-001.pdf'
    )
    assert doc.source_id == source_id
    assert doc.source_review_status.value == 'APPROVED'
    assert doc.allow_ai_retrieval == 1

    search = client.get(
        '/api/v1/standards/chunks/search',
        params={'q': '测试因子甲 PC-TWA', 'limit': 5},
        headers=_auth(user_token),
    )

    assert search.status_code == 200
    items = search.json()['data']['items']
    assert len(items) == 1
    assert items[0]['standard_code'] == 'TEST-STD-001'
    assert items[0]['clause'] == '4.1'
    assert items[0]['authorized'] is True
    assert items[0]['source_id'] == source_id
    assert items[0]['license_id'] == 'LIC-TEST-001'
    assert '测试因子甲的测试限值依据' in items[0]['text_chunk']


def test_standard_manifest_without_approved_source_is_not_user_searchable(
    client: TestClient,
    admin_token: str,
    user_token: str,
):
    imported = client.post(
        '/api/v1/standards/manifest/import',
        json={
            'documents': [
                {
                    'standard_code': 'TEST-PENDING-001',
                    'standard_name': 'Pending source standard',
                    'domain': 'occupational_health',
                    'file_hash': 'p' * 64,
                    'chunks': [
                        {
                            'chunk_index': 0,
                            'clause': '1.1',
                            'text_chunk': 'pending source text should not be available to users',
                        }
                    ],
                }
            ]
        },
        headers=_auth(admin_token),
    )
    assert imported.status_code == 200
    doc_result = imported.json()['data']['documents'][0]
    assert doc_result['source_review_status'] == 'PENDING'
    assert doc_result['allow_ai_retrieval'] is False

    user_search = client.get(
        '/api/v1/standards/chunks/search',
        params={'q': 'pending source text'},
        headers=_auth(user_token),
    )
    assert user_search.status_code == 200
    assert user_search.json()['data']['items'] == []

    admin_search = client.get(
        '/api/v1/standards/chunks/search',
        params={'q': 'pending source text', 'include_unapproved': True},
        headers=_auth(admin_token),
    )
    assert admin_search.status_code == 200
    data = admin_search.json()['data']
    assert data['include_unapproved'] is True
    assert len(data['items']) == 1
    assert data['items'][0]['authorized'] is False


def test_standard_sensitive_chunks_require_explicit_import_and_admin_search(
    client: TestClient,
    admin_token: str,
    user_token: str,
):
    source_id = _create_approved_source(
        client,
        admin_token,
        source_name='Authorized sensitive test source',
        license_no='LIC-SENSITIVE-001',
    )
    payload = {
        'documents': [
            {
                'standard_code': 'TEST-SENSITIVE-001',
                'standard_name': '敏感测试导则',
                'domain': 'occupational_health',
                'source_id': source_id,
                'storage_backend': 'minio',
                'object_key': 'raw/private/sensitive-guide.pdf',
                'file_hash': 'b' * 64,
                'is_sensitive': True,
                'chunks': [
                    {
                        'chunk_index': 0,
                        'clause': '1.1',
                        'text_chunk': '敏感导则条文，仅管理员显式允许后才写入。',
                        'is_sensitive': True,
                    }
                ],
            }
        ]
    }

    skipped = client.post(
        '/api/v1/standards/manifest/import',
        json=payload,
        headers=_auth(admin_token),
    )

    assert skipped.status_code == 200
    assert skipped.json()['data']['chunks_written'] == 0
    assert skipped.json()['data']['chunks_skipped_sensitive'] == 1

    imported = client.post(
        '/api/v1/standards/manifest/import',
        json={**payload, 'allow_sensitive_chunks': True},
        headers=_auth(admin_token),
    )

    assert imported.status_code == 200
    assert imported.json()['data']['chunks_written'] == 1

    user_search = client.get(
        '/api/v1/standards/chunks/search',
        params={'q': '敏感导则条文', 'include_sensitive': True},
        headers=_auth(user_token),
    )

    assert user_search.status_code == 200
    assert user_search.json()['data']['include_sensitive'] is False
    assert user_search.json()['data']['items'] == []

    admin_search = client.get(
        '/api/v1/standards/chunks/search',
        params={'q': '敏感导则条文', 'include_sensitive': True},
        headers=_auth(admin_token),
    )

    assert admin_search.status_code == 200
    assert admin_search.json()['data']['include_sensitive'] is True
    assert len(admin_search.json()['data']['items']) == 1


def test_standard_manifest_import_requires_admin(
    client: TestClient,
    user_token: str,
):
    resp = client.post(
        '/api/v1/standards/manifest/import',
        json={
            'documents': [
                {
                    'standard_code': 'TEST-STD-USER',
                    'standard_name': '普通用户不可导入',
                    'domain': 'occupational_health',
                    'file_hash': 'c' * 64,
                }
            ]
        },
        headers=_auth(user_token),
    )

    assert resp.status_code == 403


def test_standard_source_admin_api_requires_admin(
    client: TestClient,
    user_token: str,
):
    resp = client.post(
        '/api/v1/standards/sources',
        json={
            'source_name': 'Unauthorized source create',
            'source_type': 'CUSTOMER_PROVIDED',
            'allow_storage': True,
        },
        headers=_auth(user_token),
    )

    assert resp.status_code == 403


def test_agent_uses_standard_chunks_for_basis_questions(
    client: TestClient,
    admin_token: str,
    user_token: str,
    monkeypatch,
):
    call_model = AsyncMock(side_effect=RuntimeError('should not call model'))
    monkeypatch.setattr('app.services.agent_service.AgentService._call_model', call_model)
    source_id = _create_approved_source(
        client,
        admin_token,
        source_name='Authorized agent test source',
        license_no='LIC-AGENT-001',
    )

    client.post(
        '/api/v1/standards/manifest/import',
        json={
            'documents': [
                {
                    'standard_code': 'TEST-RAG-001',
                    'standard_name': '测试 RAG 标准',
                    'domain': 'occupational_health',
                    'source_id': source_id,
                    'object_key': 'raw/occupational_health/test-rag-001.pdf',
                    'file_hash': 'd' * 64,
                    'chunks': [
                        {
                            'chunk_index': 0,
                            'clause': '5.2',
                            'text_chunk': '测试因子甲的测试限值依据来自 TEST-RAG-001 第 5.2 条。',
                        }
                    ],
                }
            ]
        },
        headers=_auth(admin_token),
    )

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '测试因子甲的测试限值依据是什么'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    answer = data['assistant_message']['content']
    assert data['run']['provider'] == 'rules'
    assert data['run']['model_name'] == 'fast-summary'
    assert any(call['tool_name'] == 'search_standard_chunks' for call in data['tool_calls'])
    assert '标准条文库命中' in answer
    assert 'TEST-RAG-001' in answer
    assert '第 5.2 条' in answer
    call_model.assert_not_called()
