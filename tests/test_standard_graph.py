from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import settings
from app.dao.detection_dao import serialize_aliases
from app.models.db_models import LimitType, RegulatoryLimit, SampleMedium


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _create_approved_source(client: TestClient, admin_token: str, *, license_no: str) -> str:
    created = client.post(
        '/api/v1/standards/sources',
        json={
            'source_name': f'Graph test source {license_no}',
            'source_type': 'AUTHORIZED_PURCHASE',
            'provider_name': 'Graph Test Provider',
            'license_no': license_no,
            'license_scope': 'Unit test authorized storage and retrieval.',
            'allow_storage': True,
            'allow_vectorization': True,
            'allow_ai_retrieval': True,
            'allow_excerpt_export': True,
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
    return source_id


def _import_standard_document(
    client: TestClient,
    admin_token: str,
    *,
    standard_code: str,
    standard_name: str,
    file_hash: str,
    source_id: str | None = None,
) -> str:
    imported = client.post(
        '/api/v1/standards/manifest/import',
        json={
            'documents': [
                {
                    'standard_code': standard_code,
                    'standard_name': standard_name,
                    'domain': 'occupational_health',
                    'source_id': source_id,
                    'storage_backend': 'minio',
                    'bucket': 'ehs-standard-library',
                    'object_key': f'raw/{standard_code.lower()}.pdf',
                    'file_hash': file_hash,
                    'source_format': 'pdf',
                }
            ]
        },
        headers=_auth(admin_token),
    )
    assert imported.status_code == 200
    return imported.json()['data']['documents'][0]['document_id']


def _create_clause(
    client: TestClient,
    admin_token: str,
    *,
    document_id: str,
    standard_code: str,
    standard_name: str,
    clause_code: str,
    clause_title: str = 'Unit test clause',
) -> dict[str, object]:
    created = client.post(
        '/api/v1/standards/clauses',
        json={
            'document_id': document_id,
            'standard_code': standard_code,
            'standard_name': standard_name,
            'version': '2026',
            'clause_code': clause_code,
            'clause_title': clause_title,
            'clause_type': 'LIMIT',
            'page_start': 1,
            'page_end': 2,
            'source_uri': f'minio://ehs-standard-library/raw/{standard_code.lower()}.pdf',
            'status': 'ACTIVE',
        },
        headers=_auth(admin_token),
    )
    assert created.status_code == 200
    return created.json()['data']


def _add_limit_fixture(db, *, indicator_name: str) -> RegulatoryLimit:
    limit = RegulatoryLimit(
        indicator_name=indicator_name,
        aliases_json=serialize_aliases([indicator_name]),
        medium=SampleMedium.WORKPLACE_AIR,
        limit_type=LimitType.PC_TWA,
        limit_value=Decimal('10'),
        unit='mg/m3',
        standard_code='TEST-LIMIT',
        standard_name='Test limit standard',
        clause='Table 1',
        priority=1,
    )
    db.add(limit)
    db.commit()
    db.refresh(limit)
    return limit


def _add_ranked_limit(
    db,
    *,
    indicator_name: str,
    standard_code: str,
    standard_name: str,
    clause: str,
    value: str,
    priority: int,
) -> RegulatoryLimit:
    limit = RegulatoryLimit(
        indicator_name=indicator_name,
        aliases_json=serialize_aliases([indicator_name]),
        medium=SampleMedium.WORKPLACE_AIR,
        limit_type=LimitType.PC_TWA,
        limit_value=Decimal(value),
        unit='mg/m3',
        standard_code=standard_code,
        standard_name=standard_name,
        clause=clause,
        priority=priority,
    )
    db.add(limit)
    db.commit()
    db.refresh(limit)
    return limit


def test_standard_clause_list_hides_unapproved_documents(
    client: TestClient,
    admin_token: str,
    user_token: str,
):
    source_id = _create_approved_source(client, admin_token, license_no='LIC-GRAPH-VISIBLE')
    approved_document_id = _import_standard_document(
        client,
        admin_token,
        standard_code='GRAPH-APPROVED',
        standard_name='Graph approved standard',
        file_hash='graph-approved-001',
        source_id=source_id,
    )
    pending_document_id = _import_standard_document(
        client,
        admin_token,
        standard_code='GRAPH-PENDING',
        standard_name='Graph pending standard',
        file_hash='graph-pending-001',
    )
    _create_clause(
        client,
        admin_token,
        document_id=approved_document_id,
        standard_code='GRAPH-APPROVED',
        standard_name='Graph approved standard',
        clause_code='1.1',
    )
    pending_clause = _create_clause(
        client,
        admin_token,
        document_id=pending_document_id,
        standard_code='GRAPH-PENDING',
        standard_name='Graph pending standard',
        clause_code='9.9',
    )

    user_list = client.get(
        '/api/v1/standards/clauses',
        params={'page_size': 100},
        headers=_auth(user_token),
    )
    assert user_list.status_code == 200
    user_codes = {item['standard_code'] for item in user_list.json()['data']['items']}
    assert 'GRAPH-APPROVED' in user_codes
    assert 'GRAPH-PENDING' not in user_codes

    admin_list = client.get(
        '/api/v1/standards/clauses',
        params={'include_unapproved': True, 'page_size': 100},
        headers=_auth(admin_token),
    )
    assert admin_list.status_code == 200
    admin_ids = {item['id'] for item in admin_list.json()['data']['items']}
    assert pending_clause['id'] in admin_ids


def test_standard_graph_relation_and_rules_api(
    client: TestClient,
    admin_token: str,
    user_token: str,
):
    source_id = _create_approved_source(client, admin_token, license_no='LIC-GRAPH-RULES')
    document_id = _import_standard_document(
        client,
        admin_token,
        standard_code='GRAPH-RULES',
        standard_name='Graph rules standard',
        file_hash='graph-rules-001',
        source_id=source_id,
    )
    clause = _create_clause(
        client,
        admin_token,
        document_id=document_id,
        standard_code='GRAPH-RULES',
        standard_name='Graph rules standard',
        clause_code='4.2',
    )

    relation_payload = {
        'subject_type': 'CLAUSE',
        'subject_id': clause['id'],
        'relation_type': 'CITES',
        'object_type': 'STANDARD',
        'object_id': 'GRAPH-REFERENCE',
        'confidence': '0.9500',
        'source_type': 'HUMAN',
        'is_verified': True,
        'metadata': {'reason': 'unit-test'},
    }
    forbidden = client.post(
        '/api/v1/standards/relations',
        json=relation_payload,
        headers=_auth(user_token),
    )
    assert forbidden.status_code == 403

    created_relation = client.post(
        '/api/v1/standards/relations',
        json=relation_payload,
        headers=_auth(admin_token),
    )
    assert created_relation.status_code == 200
    relation = created_relation.json()['data']
    assert relation['subject_id'] == clause['id']
    assert relation['is_verified'] is True

    listed_relations = client.get(
        '/api/v1/standards/relations',
        params={'subject_id': clause['id']},
        headers=_auth(user_token),
    )
    assert listed_relations.status_code == 200
    assert listed_relations.json()['data']['items'][0]['id'] == relation['id']

    created_applicability = client.post(
        '/api/v1/standards/applicability-rules',
        json={
            'standard_code': 'GRAPH-RULES',
            'clause_id': clause['id'],
            'report_type': 'OCCUPATIONAL_HEALTH',
            'medium': 'WORKPLACE_AIR',
            'indicator_name': 'graph-factor',
            'applicability': {'service_type': 'periodic'},
            'priority': 10,
            'review_status': 'APPROVED',
        },
        headers=_auth(admin_token),
    )
    assert created_applicability.status_code == 200

    listed_applicability = client.get(
        '/api/v1/standards/applicability-rules',
        params={'standard_code': 'GRAPH-RULES'},
        headers=_auth(user_token),
    )
    assert listed_applicability.status_code == 200
    assert listed_applicability.json()['data']['items'][0]['clause_id'] == clause['id']

    created_precedence = client.post(
        '/api/v1/standards/precedence-rules',
        json={
            'rule_name': 'Local standard precedence',
            'domain': 'occupational_health',
            'higher_standard_code': 'GRAPH-RULES',
            'lower_standard_code': 'GRAPH-REFERENCE',
            'condition': {'region': 'test-region'},
            'priority': 5,
            'reason': 'Unit test precedence',
            'source_clause_id': clause['id'],
            'review_status': 'APPROVED',
        },
        headers=_auth(admin_token),
    )
    assert created_precedence.status_code == 200

    listed_precedence = client.get(
        '/api/v1/standards/precedence-rules',
        params={'standard_code': 'GRAPH-RULES'},
        headers=_auth(user_token),
    )
    assert listed_precedence.status_code == 200
    assert listed_precedence.json()['data']['items'][0]['source_clause_id'] == clause['id']


def test_compliance_evidence_is_created_from_detection_results(
    client: TestClient,
    admin_token: str,
    user_token: str,
    db,
):
    indicator_name = 'graph-evidence-factor'
    source_id = _create_approved_source(client, admin_token, license_no='LIC-GRAPH-EVIDENCE')
    document_id = _import_standard_document(
        client,
        admin_token,
        standard_code='TEST-LIMIT',
        standard_name='Test limit standard',
        file_hash='graph-evidence-001',
        source_id=source_id,
    )
    clause = _create_clause(
        client,
        admin_token,
        document_id=document_id,
        standard_code='TEST-LIMIT',
        standard_name='Test limit standard',
        clause_code='Table 1',
    )
    limit = _add_limit_fixture(db, indicator_name=indicator_name)
    csv = (
        'sample_point,indicator_name,raw_value,raw_unit,duration_minutes\n'
        f'P1,{indicator_name},100000,ug/m3,60\n'
    ).encode()

    upload = client.post(
        '/api/v1/detection/reports',
        data={
            'organization_id': settings.default_organization_id,
            'report_type': 'OCCUPATIONAL_HEALTH',
        },
        files={'file': ('graph-evidence.csv', csv, 'text/csv')},
        headers=_auth(admin_token),
    )
    assert upload.status_code == 200
    report_id = upload.json()['data']['report_id']

    calculated = client.post(
        f'/api/v1/detection/reports/{report_id}/calculate',
        headers=_auth(admin_token),
    )
    assert calculated.status_code == 200
    result = calculated.json()['data']['results'][0]
    assert result['limit_id'] == limit.id
    assert result['standard_code'] == 'TEST-LIMIT'

    evidence_response = client.get(
        '/api/v1/standards/evidence',
        params={'report_id': report_id, 'page_size': 10},
        headers=_auth(user_token),
    )
    assert evidence_response.status_code == 200
    evidence_items = evidence_response.json()['data']['items']
    evidence_types = {item['evidence_type'] for item in evidence_items}
    assert {'LIMIT_MATCH', 'CALCULATION'} <= evidence_types
    assert all(item['report_id'] == report_id for item in evidence_items)
    assert any(item['limit_id'] == limit.id for item in evidence_items)
    assert any(item['clause_id'] == clause['id'] for item in evidence_items)


def test_graph_rules_rank_limit_candidates_and_emit_evidence(
    client: TestClient,
    admin_token: str,
    user_token: str,
    db,
):
    indicator_name = 'graph-rule-ranked-factor'
    source_id = _create_approved_source(client, admin_token, license_no='LIC-GRAPH-RANKING')
    local_document_id = _import_standard_document(
        client,
        admin_token,
        standard_code='LOCAL-LIMIT',
        standard_name='Local limit standard',
        file_hash='graph-local-limit-001',
        source_id=source_id,
    )
    national_document_id = _import_standard_document(
        client,
        admin_token,
        standard_code='NATIONAL-LIMIT',
        standard_name='National limit standard',
        file_hash='graph-national-limit-001',
        source_id=source_id,
    )
    local_clause = _create_clause(
        client,
        admin_token,
        document_id=local_document_id,
        standard_code='LOCAL-LIMIT',
        standard_name='Local limit standard',
        clause_code='Table Local',
    )
    national_clause = _create_clause(
        client,
        admin_token,
        document_id=national_document_id,
        standard_code='NATIONAL-LIMIT',
        standard_name='National limit standard',
        clause_code='Table National',
    )
    local_limit = _add_ranked_limit(
        db,
        indicator_name=indicator_name,
        standard_code='LOCAL-LIMIT',
        standard_name='Local limit standard',
        clause='Table Local',
        value='5',
        priority=50,
    )
    national_limit = _add_ranked_limit(
        db,
        indicator_name=indicator_name,
        standard_code='NATIONAL-LIMIT',
        standard_name='National limit standard',
        clause='Table National',
        value='10',
        priority=1,
    )

    applicability = client.post(
        '/api/v1/standards/applicability-rules',
        json={
            'standard_code': 'LOCAL-LIMIT',
            'clause_id': local_clause['id'],
            'report_type': 'OCCUPATIONAL_HEALTH',
            'medium': 'WORKPLACE_AIR',
            'indicator_name': indicator_name,
            'priority': 1,
            'review_status': 'APPROVED',
        },
        headers=_auth(admin_token),
    )
    assert applicability.status_code == 200

    precedence = client.post(
        '/api/v1/standards/precedence-rules',
        json={
            'rule_name': 'Local overrides national for graph test',
            'higher_standard_code': 'LOCAL-LIMIT',
            'lower_standard_code': 'NATIONAL-LIMIT',
            'condition': {'report_type': 'OCCUPATIONAL_HEALTH'},
            'priority': 1,
            'source_clause_id': local_clause['id'],
            'review_status': 'APPROVED',
        },
        headers=_auth(admin_token),
    )
    assert precedence.status_code == 200

    csv = (
        'sample_point,indicator_name,raw_value,raw_unit,duration_minutes\n'
        f'P1,{indicator_name},6,mg/m3,480\n'
    ).encode()
    upload = client.post(
        '/api/v1/detection/reports',
        data={
            'organization_id': settings.default_organization_id,
            'report_type': 'OCCUPATIONAL_HEALTH',
        },
        files={'file': ('graph-rule-ranking.csv', csv, 'text/csv')},
        headers=_auth(admin_token),
    )
    assert upload.status_code == 200
    report_id = upload.json()['data']['report_id']

    calculated = client.post(
        f'/api/v1/detection/reports/{report_id}/calculate',
        headers=_auth(admin_token),
    )
    assert calculated.status_code == 200
    result = calculated.json()['data']['results'][0]
    assert result['limit_id'] == local_limit.id
    assert result['limit_id'] != national_limit.id
    assert result['standard_code'] == 'LOCAL-LIMIT'
    assert result['limit_value'] == '5.000000'
    assert result['status'] == 'EXCEEDED'

    evidence_response = client.get(
        '/api/v1/standards/evidence',
        params={'report_id': report_id, 'page_size': 20},
        headers=_auth(user_token),
    )
    assert evidence_response.status_code == 200
    evidence_items = evidence_response.json()['data']['items']
    evidence_types = {item['evidence_type'] for item in evidence_items}
    assert {'LIMIT_MATCH', 'APPLICABILITY', 'PRECEDENCE', 'CALCULATION'} <= evidence_types
    assert any(item['clause_id'] == local_clause['id'] for item in evidence_items)
    assert all(item['clause_id'] != national_clause['id'] for item in evidence_items)
