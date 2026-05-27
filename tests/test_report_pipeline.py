from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import current_user_from_token
from app.models.db_models import (
    AgentMemoryScopeType,
    AgentMemorySourceType,
    AgentMemoryType,
    DetectionReport,
    Organization,
    ReportStatus,
    ReportType,
)
from app.schemas.auth_context import CurrentUser
from app.services.agent_memory_service import AgentMemoryService


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _create_detection_report(
    *,
    db: Session,
    organization_id: str,
    created_by_id: str | None,
    filename: str = 'pipeline-report.csv',
) -> DetectionReport:
    report = DetectionReport(
        organization_id=organization_id,
        filename=filename,
        report_name='Pipeline Report',
        report_type=ReportType.OCCUPATIONAL_HEALTH,
        status=ReportStatus.PARSED,
        created_by_id=created_by_id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _create_citation_memory(
    *,
    db: Session,
    actor: CurrentUser,
    source_id: str,
) -> str:
    result = AgentMemoryService.upsert_memory(
        db=db,
        actor=actor,
        scope_type=AgentMemoryScopeType.SESSION,
        scope_id='report-pipeline-session',
        memory_type=AgentMemoryType.CITATION,
        content='GB test clause p.1',
        source_type=AgentMemorySourceType.HUMAN,
        source_id=source_id,
    )
    return result.memory.id


def _bootstrap_sections(client: TestClient, token: str, report_id: str) -> list[dict]:
    response = client.post(
        f'/api/v1/report-pipeline/reports/{report_id}/bootstrap-sections',
        headers=_auth(token),
    )
    assert response.status_code == 200
    return response.json()['data']


def test_report_pipeline_lists_builtin_templates(client: TestClient, user_token: str) -> None:
    response = client.get('/api/v1/report-pipeline/templates', headers=_auth(user_token))

    assert response.status_code == 200
    templates = response.json()['data']
    assert [item['section_key'] for item in templates] == [
        'summary',
        'basis',
        'findings',
        'conclusion',
        'actions',
    ]
    assert all(item['required'] for item in templates)


def test_report_pipeline_bootstrap_sections_is_idempotent(
    client: TestClient,
    user_token: str,
    db: Session,
) -> None:
    actor = current_user_from_token(user_token)
    assert actor.organization_id is not None
    report = _create_detection_report(
        db=db,
        organization_id=actor.organization_id,
        created_by_id=actor.account_id,
    )

    first_sections = _bootstrap_sections(client, user_token, report.id)
    second_sections = _bootstrap_sections(client, user_token, report.id)

    assert [section['section_key'] for section in first_sections] == [
        'summary',
        'basis',
        'findings',
        'conclusion',
        'actions',
    ]
    assert [section['id'] for section in second_sections] == [
        section['id'] for section in first_sections
    ]
    assert all(section['citation_check_status'] == 'PENDING' for section in first_sections)
    assert all(section['review_status'] == 'DRAFT' for section in first_sections)


def test_report_pipeline_upserts_section_and_validates_citations(
    client: TestClient,
    user_token: str,
    db: Session,
) -> None:
    actor = current_user_from_token(user_token)
    assert actor.organization_id is not None
    report = _create_detection_report(
        db=db,
        organization_id=actor.organization_id,
        created_by_id=actor.account_id,
    )
    citation_id = _create_citation_memory(db=db, actor=actor, source_id='pipeline-citation-1')

    response = client.post(
        '/api/v1/report-pipeline/sections',
        json={
            'report_id': report.id,
            'section_key': 'summary',
            'title': '结论摘要',
            'draft_content': '该章节仍为草稿，需人工复核后才能进入正式报告。',
            'citation_memory_ids': [citation_id, citation_id],
        },
        headers=_auth(user_token),
    )

    assert response.status_code == 200
    body = response.json()['data']
    assert body['report_id'] == report.id
    assert body['citation_memory_ids'] == [citation_id]
    assert body['citation_check_status'] == 'PASSED'
    assert body['review_status'] == 'DRAFT'

    listed = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/sections',
        headers=_auth(user_token),
    )
    assert listed.status_code == 200
    assert [item['section_key'] for item in listed.json()['data']] == ['summary']


def test_report_pipeline_blocks_user_review_and_allows_org_admin_approval(
    client: TestClient,
    user_token: str,
    org_admin_token: str,
    db: Session,
) -> None:
    actor = current_user_from_token(user_token)
    org_admin = current_user_from_token(org_admin_token)
    assert actor.organization_id is not None
    report = _create_detection_report(
        db=db,
        organization_id=actor.organization_id,
        created_by_id=actor.account_id,
    )
    citation_id = _create_citation_memory(db=db, actor=actor, source_id='pipeline-citation-2')
    section = client.post(
        '/api/v1/report-pipeline/sections',
        json={
            'report_id': report.id,
            'section_key': 'basis',
            'title': '判定依据',
            'draft_content': '该章节引用已校验的法规依据记忆。',
            'citation_memory_ids': [citation_id],
        },
        headers=_auth(user_token),
    ).json()['data']

    user_review = client.patch(
        f'/api/v1/report-pipeline/sections/{section["id"]}/review',
        json={'review_status': 'APPROVED'},
        headers=_auth(user_token),
    )
    assert user_review.status_code == 403

    admin_review = client.patch(
        f'/api/v1/report-pipeline/sections/{section["id"]}/review',
        json={'review_status': 'APPROVED', 'review_note': '人工复核通过'},
        headers=_auth(org_admin_token),
    )
    assert admin_review.status_code == 200
    reviewed = admin_review.json()['data']
    assert reviewed['review_status'] == 'APPROVED'
    assert reviewed['reviewed_by_id'] == org_admin.account_id


def test_report_pipeline_rejects_approval_without_passed_citations(
    client: TestClient,
    user_token: str,
    org_admin_token: str,
    db: Session,
) -> None:
    actor = current_user_from_token(user_token)
    assert actor.organization_id is not None
    report = _create_detection_report(
        db=db,
        organization_id=actor.organization_id,
        created_by_id=actor.account_id,
    )
    section = client.post(
        '/api/v1/report-pipeline/sections',
        json={
            'report_id': report.id,
            'section_key': 'conclusion',
            'title': '评价结论',
            'draft_content': '该章节缺少引用，不能直接批准。',
            'citation_memory_ids': [],
        },
        headers=_auth(user_token),
    ).json()['data']
    assert section['citation_check_status'] == 'PENDING'

    response = client.patch(
        f'/api/v1/report-pipeline/sections/{section["id"]}/review',
        json={'review_status': 'APPROVED'},
        headers=_auth(org_admin_token),
    )

    assert response.status_code == 400
    assert response.json()['code'] == 'REPORT_SECTION_CITATIONS_NOT_PASSED'


def test_report_pipeline_readiness_blocks_until_required_sections_are_approved(
    client: TestClient,
    user_token: str,
    org_admin_token: str,
    db: Session,
) -> None:
    actor = current_user_from_token(user_token)
    assert actor.organization_id is not None
    report = _create_detection_report(
        db=db,
        organization_id=actor.organization_id,
        created_by_id=actor.account_id,
    )

    missing_response = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/readiness',
        headers=_auth(user_token),
    )
    assert missing_response.status_code == 200
    missing_body = missing_response.json()['data']
    assert missing_body['ready'] is False
    assert {issue['code'] for issue in missing_body['issues']} == {'REPORT_SECTION_MISSING'}

    sections = _bootstrap_sections(client, user_token, report.id)
    pending_response = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/readiness',
        headers=_auth(user_token),
    )
    assert pending_response.status_code == 200
    pending_codes = {issue['code'] for issue in pending_response.json()['data']['issues']}
    assert pending_codes == {
        'REPORT_SECTION_CITATIONS_NOT_PASSED',
        'REPORT_SECTION_REVIEW_NOT_APPROVED',
    }

    approved_sections: list[dict] = []
    for section in sections:
        citation_id = _create_citation_memory(
            db=db,
            actor=actor,
            source_id=f'pipeline-readiness-{section["section_key"]}',
        )
        updated = client.post(
            '/api/v1/report-pipeline/sections',
            json={
                'report_id': report.id,
                'section_key': section['section_key'],
                'title': section['title'],
                'draft_content': f'Approved draft for {section["section_key"]}',
                'citation_memory_ids': [citation_id],
            },
            headers=_auth(user_token),
        )
        assert updated.status_code == 200
        approved = client.patch(
            f'/api/v1/report-pipeline/sections/{updated.json()["data"]["id"]}/review',
            json={'review_status': 'APPROVED'},
            headers=_auth(org_admin_token),
        )
        assert approved.status_code == 200
        approved_sections.append(approved.json()['data'])

    assert len(approved_sections) == 5
    ready_response = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/readiness',
        headers=_auth(user_token),
    )
    assert ready_response.status_code == 200
    ready_body = ready_response.json()['data']
    assert ready_body['ready'] is True
    assert ready_body['issues'] == []


def test_report_pipeline_blocks_other_org_report_access(
    client: TestClient,
    user_token: str,
    db: Session,
) -> None:
    other_org = Organization(name='Report Pipeline Hidden Org')
    db.add(other_org)
    db.flush()
    other_report = _create_detection_report(
        db=db,
        organization_id=other_org.id,
        created_by_id='other-account',
        filename='hidden-pipeline-report.csv',
    )

    response = client.get(
        f'/api/v1/report-pipeline/reports/{other_report.id}/sections',
        headers=_auth(user_token),
    )

    assert response.status_code == 403


def test_report_pipeline_blocks_other_org_readiness_access(
    client: TestClient,
    user_token: str,
    db: Session,
) -> None:
    other_org = Organization(name='Report Pipeline Readiness Hidden Org')
    db.add(other_org)
    db.flush()
    other_report = _create_detection_report(
        db=db,
        organization_id=other_org.id,
        created_by_id='other-account',
        filename='hidden-pipeline-readiness-report.csv',
    )

    response = client.get(
        f'/api/v1/report-pipeline/reports/{other_report.id}/readiness',
        headers=_auth(user_token),
    )

    assert response.status_code == 403
