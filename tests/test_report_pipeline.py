from __future__ import annotations

import json
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import current_user_from_token
from app.models.db_models import (
    AgentMemory,
    AgentMemoryScopeType,
    AgentMemorySourceType,
    AgentMemoryType,
    ComplianceEvidence,
    ComplianceEvidenceType,
    DetectionReport,
    Organization,
    ReportStatus,
    ReportType,
)
from app.schemas.auth_context import CurrentUser
from app.services.agent_memory_service import AgentMemoryService


class _FakeDraftProvider:
    name = 'fake'
    model_name = 'fake-report-draft-model'

    def __init__(self, response: str) -> None:
        self.response = response
        self.messages: list[dict[str, str]] = []

    async def generate(self, *, messages: list[dict[str, str]]) -> str:
        self.messages = messages
        return self.response


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
    allow_excerpt_export: bool = True,
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
        metadata={
            'authorized': True,
            'allow_ai_retrieval': True,
            'allow_excerpt_export': allow_excerpt_export,
            'license_id': f'LIC-{source_id}',
            'source_review_status': 'APPROVED',
        },
    )
    return result.memory.id


def _create_compliance_evidence(*, db: Session, report_id: str, summary: str) -> str:
    evidence = ComplianceEvidence(
        report_id=report_id,
        standard_code='GBZ-TEST',
        standard_name='Test occupational health standard',
        source_uri='standard://gbz-test/1',
        evidence_type=ComplianceEvidenceType.LIMIT_MATCH,
        evidence_summary=summary,
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return evidence.id


def _bootstrap_sections(client: TestClient, token: str, report_id: str) -> list[dict]:
    response = client.post(
        f'/api/v1/report-pipeline/reports/{report_id}/bootstrap-sections',
        headers=_auth(token),
    )
    assert response.status_code == 200
    return response.json()['data']


def _approve_sections(
    *,
    client: TestClient,
    db: Session,
    actor: CurrentUser,
    user_token: str,
    org_admin_token: str,
    report_id: str,
    sections: list[dict],
) -> list[dict]:
    approved_sections: list[dict] = []
    for section in sections:
        citation_id = _create_citation_memory(
            db=db,
            actor=actor,
            source_id=f'pipeline-approved-{section["section_key"]}',
        )
        updated = client.post(
            '/api/v1/report-pipeline/sections',
            json={
                'report_id': report_id,
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
    return approved_sections


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


def test_report_pipeline_upserts_section_and_validates_evidence(
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
    citation_id = _create_citation_memory(db=db, actor=actor, source_id='pipeline-evidence-1')
    evidence_id = _create_compliance_evidence(
        db=db,
        report_id=report.id,
        summary='Limit matching evidence for report summary.',
    )

    response = client.post(
        '/api/v1/report-pipeline/sections',
        json={
            'report_id': report.id,
            'section_key': 'summary',
            'title': '证据摘要',
            'draft_content': '该章节绑定已校验的检测证据链。',
            'citation_memory_ids': [citation_id],
            'evidence_ids': [evidence_id, evidence_id],
        },
        headers=_auth(user_token),
    )

    assert response.status_code == 200
    body = response.json()['data']
    assert body['citation_check_status'] == 'PASSED'
    assert body['evidence_ids'] == [evidence_id]
    assert body['evidence_check_status'] == 'PASSED'
    assert body['review_status'] == 'DRAFT'


def test_report_pipeline_generate_draft_requires_report_evidence(
    client: TestClient,
    user_token: str,
    db: Session,
    monkeypatch,
) -> None:
    provider = _FakeDraftProvider('should not be used')
    monkeypatch.setattr(
        'app.services.report_pipeline_service.get_configured_agent_model_provider',
        lambda: provider,
    )
    actor = current_user_from_token(user_token)
    assert actor.organization_id is not None
    report = _create_detection_report(
        db=db,
        organization_id=actor.organization_id,
        created_by_id=actor.account_id,
    )

    response = client.post(
        f'/api/v1/report-pipeline/reports/{report.id}/sections/summary/generate-draft',
        json={'instruction': '生成摘要草稿'},
        headers=_auth(user_token),
    )

    assert response.status_code == 400
    assert response.json()['code'] == 'REPORT_SECTION_EVIDENCE_REQUIRED_FOR_GENERATION'
    assert provider.messages == []


def test_report_pipeline_generate_draft_binds_evidence_and_stays_draft(
    client: TestClient,
    user_token: str,
    org_admin_token: str,
    db: Session,
    monkeypatch,
) -> None:
    provider = _FakeDraftProvider('AI 草稿：仅基于 evidence_id 形成，等待人工复核。')
    monkeypatch.setattr(
        'app.services.report_pipeline_service.get_configured_agent_model_provider',
        lambda: provider,
    )
    actor = current_user_from_token(user_token)
    assert actor.organization_id is not None
    report = _create_detection_report(
        db=db,
        organization_id=actor.organization_id,
        created_by_id=actor.account_id,
    )
    evidence_id = _create_compliance_evidence(
        db=db,
        report_id=report.id,
        summary='Evidence for AI draft generation.',
    )

    response = client.post(
        f'/api/v1/report-pipeline/reports/{report.id}/sections/summary/generate-draft',
        json={'instruction': '生成报告摘要草稿'},
        headers=_auth(user_token),
    )

    assert response.status_code == 200
    body = response.json()['data']
    assert body['section_key'] == 'summary'
    assert body['title'] == '报告摘要'
    assert body['draft_content'] == 'AI 草稿：仅基于 evidence_id 形成，等待人工复核。'
    assert body['evidence_ids'] == [evidence_id]
    assert body['evidence_check_status'] == 'PASSED'
    assert body['citation_memory_ids'] == []
    assert body['citation_check_status'] == 'PENDING'
    assert body['review_status'] == 'DRAFT'
    assert evidence_id in provider.messages[-1]['content']

    approval = client.patch(
        f'/api/v1/report-pipeline/sections/{body["id"]}/review',
        json={'review_status': 'APPROVED'},
        headers=_auth(org_admin_token),
    )
    assert approval.status_code == 400
    assert approval.json()['code'] == 'REPORT_SECTION_CITATIONS_NOT_PASSED'


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


def test_report_pipeline_rejects_approval_without_passed_evidence(
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
    other_report = _create_detection_report(
        db=db,
        organization_id=actor.organization_id,
        created_by_id=actor.account_id,
        filename='pipeline-other-report.csv',
    )
    citation_id = _create_citation_memory(db=db, actor=actor, source_id='pipeline-evidence-2')
    other_evidence_id = _create_compliance_evidence(
        db=db,
        report_id=other_report.id,
        summary='Evidence that belongs to another report.',
    )

    section = client.post(
        '/api/v1/report-pipeline/sections',
        json={
            'report_id': report.id,
            'section_key': 'findings',
            'title': '结果分析',
            'draft_content': '该章节绑定了不属于本报告的证据。',
            'citation_memory_ids': [citation_id],
            'evidence_ids': [other_evidence_id],
        },
        headers=_auth(user_token),
    ).json()['data']
    assert section['citation_check_status'] == 'PASSED'
    assert section['evidence_check_status'] == 'FAILED'

    response = client.patch(
        f'/api/v1/report-pipeline/sections/{section["id"]}/review',
        json={'review_status': 'APPROVED'},
        headers=_auth(org_admin_token),
    )

    assert response.status_code == 400
    assert response.json()['code'] == 'REPORT_SECTION_EVIDENCE_NOT_PASSED'


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

    approved_sections = _approve_sections(
        client=client,
        db=db,
        actor=actor,
        user_token=user_token,
        org_admin_token=org_admin_token,
        report_id=report.id,
        sections=sections,
    )

    assert len(approved_sections) == 5
    ready_response = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/readiness',
        headers=_auth(user_token),
    )
    assert ready_response.status_code == 200
    ready_body = ready_response.json()['data']
    assert ready_body['ready'] is True
    assert ready_body['issues'] == []


def test_report_pipeline_rechecks_citation_export_authorization(
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
    sections = _bootstrap_sections(client, user_token, report.id)
    approved_sections = _approve_sections(
        client=client,
        db=db,
        actor=actor,
        user_token=user_token,
        org_admin_token=org_admin_token,
        report_id=report.id,
        sections=sections,
    )

    citation_id = approved_sections[0]['citation_memory_ids'][0]
    memory = db.get(AgentMemory, citation_id)
    assert memory is not None
    metadata = json.loads(memory.metadata_json or '{}')
    metadata['allow_excerpt_export'] = False
    memory.metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    db.commit()

    readiness = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/readiness',
        headers=_auth(user_token),
    )
    assert readiness.status_code == 200
    body = readiness.json()['data']
    assert body['ready'] is False
    assert any(issue['code'] == 'REPORT_SECTION_CITATION_EXPORT_FORBIDDEN' for issue in body['issues'])

    export = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/export?format=markdown',
        headers=_auth(user_token),
    )
    assert export.status_code == 400
    assert export.json()['code'] == 'REPORT_EXPORT_NOT_READY'


def test_report_pipeline_rechecks_evidence_before_export(
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
    sections = _bootstrap_sections(client, user_token, report.id)
    _approve_sections(
        client=client,
        db=db,
        actor=actor,
        user_token=user_token,
        org_admin_token=org_admin_token,
        report_id=report.id,
        sections=sections,
    )
    citation_id = _create_citation_memory(db=db, actor=actor, source_id='pipeline-evidence-3')
    evidence_id = _create_compliance_evidence(
        db=db,
        report_id=report.id,
        summary='Evidence that is valid before approval.',
    )
    updated = client.post(
        '/api/v1/report-pipeline/sections',
        json={
            'report_id': report.id,
            'section_key': 'summary',
            'title': '报告摘要',
            'draft_content': 'Approved draft for summary with evidence.',
            'citation_memory_ids': [citation_id],
            'evidence_ids': [evidence_id],
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

    other_report = _create_detection_report(
        db=db,
        organization_id=actor.organization_id,
        created_by_id=actor.account_id,
        filename='pipeline-evidence-moved-report.csv',
    )
    evidence = db.get(ComplianceEvidence, evidence_id)
    assert evidence is not None
    evidence.report_id = other_report.id
    db.commit()

    readiness = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/readiness',
        headers=_auth(user_token),
    )
    assert readiness.status_code == 200
    body = readiness.json()['data']
    assert body['ready'] is False
    assert any(issue['code'] == 'REPORT_SECTION_EVIDENCE_NOT_PASSED' for issue in body['issues'])

    export = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/export?format=markdown',
        headers=_auth(user_token),
    )
    assert export.status_code == 400
    assert export.json()['code'] == 'REPORT_EXPORT_NOT_READY'


def test_report_pipeline_export_requires_readiness(
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
    _bootstrap_sections(client, user_token, report.id)

    response = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/export?format=markdown',
        headers=_auth(user_token),
    )

    assert response.status_code == 400
    body = response.json()
    assert body['code'] == 'REPORT_EXPORT_NOT_READY'
    assert body['details']['issues']


def test_report_pipeline_exports_approved_sections_as_selected_format(
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
    sections = _bootstrap_sections(client, user_token, report.id)
    _approve_sections(
        client=client,
        db=db,
        actor=actor,
        user_token=user_token,
        org_admin_token=org_admin_token,
        report_id=report.id,
        sections=sections,
    )
    citation_id = _create_citation_memory(db=db, actor=actor, source_id='pipeline-export-evidence')
    evidence_id = _create_compliance_evidence(
        db=db,
        report_id=report.id,
        summary='Evidence included in exported report.',
    )
    updated = client.post(
        '/api/v1/report-pipeline/sections',
        json={
            'report_id': report.id,
            'section_key': 'summary',
            'title': '报告摘要',
            'draft_content': 'Approved draft for summary with evidence.',
            'citation_memory_ids': [citation_id],
            'evidence_ids': [evidence_id],
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

    markdown_response = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/export?format=markdown',
        headers=_auth(user_token),
    )

    assert markdown_response.status_code == 200
    assert markdown_response.headers['content-type'].startswith('text/markdown')
    assert 'attachment;' in markdown_response.headers['content-disposition']
    markdown_content = markdown_response.text
    assert markdown_content.startswith('# Pipeline Report')
    assert '## 报告信息' in markdown_content
    assert '## 报告摘要' in markdown_content
    assert 'Approved draft for summary with evidence.' in markdown_content
    assert '引用记忆：' in markdown_content
    assert '证据链：' in markdown_content
    assert evidence_id in markdown_content

    txt_response = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/export?format=txt',
        headers=_auth(user_token),
    )

    assert txt_response.status_code == 200
    assert txt_response.headers['content-type'].startswith('text/plain')
    assert txt_response.text.startswith('Pipeline Report')
    assert '# Pipeline Report' not in txt_response.text

    doc_response = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/export?format=doc',
        headers=_auth(user_token),
    )

    assert doc_response.status_code == 200
    assert doc_response.headers['content-type'].startswith('application/msword')
    assert b'<html>' in doc_response.content
    assert 'Approved draft for summary with evidence.'.encode('utf-8') in doc_response.content
    assert evidence_id.encode('utf-8') in doc_response.content

    docx_response = client.get(
        f'/api/v1/report-pipeline/reports/{report.id}/export?format=docx',
        headers=_auth(user_token),
    )

    assert docx_response.status_code == 200
    assert docx_response.headers['content-type'].startswith(
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )
    assert docx_response.content.startswith(b'PK')
    with ZipFile(BytesIO(docx_response.content)) as archive:
        document_xml = archive.read('word/document.xml').decode('utf-8')
    assert 'Approved draft for summary with evidence.' in document_xml
    assert evidence_id in document_xml


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
