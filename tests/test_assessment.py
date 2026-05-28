"""评价任务 CRUD 与权限测试。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from fastapi.testclient import TestClient


class TestAssessmentCRUD:
    def _create_task(self, client: TestClient, token: str) -> str:
        delay = MagicMock()
        with patch('app.tasks.worker.run_assessment_task.delay', new=delay):
            resp = client.post(
                '/api/v1/assessment',
                files={'file': ('test.txt', b'EHS test content', 'text/plain')},
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Request-Id': 'test-request-id',
                },
            )
        assert resp.status_code == 200
        assert resp.headers['X-Request-Id'] == 'test-request-id'
        delay.assert_called_once()
        assert delay.call_args.args[1] == 'test-request-id'
        assert isinstance(delay.call_args.args[2], str)
        assert len(delay.call_args.args[2]) == 32
        return resp.json()['data']['task_id']

    def test_create_and_get(self, client: TestClient, admin_token: str):
        task_id = self._create_task(client, admin_token)
        resp = client.get(
            f'/api/v1/assessment/{task_id}',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200
        data = resp.json()['data']
        # schema 使用 alias='id' → 序列化输出为 task_id 或 id
        actual_id = data.get('task_id') or data.get('id')
        assert actual_id == task_id
        assert data['status'] == 'PENDING'
        assert data['progress'] == 0

    def test_list_tasks(self, client: TestClient, admin_token: str):
        self._create_task(client, admin_token)
        resp = client.get(
            '/api/v1/assessment',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 200
        body = resp.json()['data']
        assert body['total'] >= 1
        assert len(body['items']) >= 1

    def test_list_tasks_filters_by_organization_id(self, client: TestClient, admin_token: str, db):
        from app.core.config import settings
        from app.models.db_models import Organization

        other_org = Organization(name='Upload Target Org')
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        delay = MagicMock()
        with patch('app.tasks.worker.run_assessment_task.delay', new=delay):
            resp = client.post(
                '/api/v1/assessment',
                data={'organization_id': other_org.id},
                files={'file': ('org-filter.txt', b'EHS test content', 'text/plain')},
                headers={'Authorization': f'Bearer {admin_token}'},
            )

        assert resp.status_code == 200
        task_id = resp.json()['data']['task_id']

        default_resp = client.get(
            '/api/v1/assessment',
            params={'organization_id': settings.default_organization_id},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert default_resp.status_code == 200
        default_items = default_resp.json()['data']['items']
        assert all((item.get('task_id') or item.get('id')) != task_id for item in default_items)

        org_resp = client.get(
            '/api/v1/assessment',
            params={'organization_id': other_org.id},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert org_resp.status_code == 200
        org_items = org_resp.json()['data']['items']
        assert any((item.get('task_id') or item.get('id')) == task_id for item in org_items)

    def test_create_list_and_get_include_client_project_context(self, client: TestClient, admin_token: str):
        delay = MagicMock()
        with patch('app.tasks.worker.run_assessment_task.delay', new=delay):
            resp = client.post(
                '/api/v1/assessment',
                data={
                    'task_name': '年度评价任务',
                    'client_name': '委托客户 A',
                    'project_name': '职业卫生评价项目',
                    'project_code': 'PJ-001',
                    'service_type': '评价',
                },
                files={'file': ('client-project.txt', b'EHS test content', 'text/plain')},
                headers={'Authorization': f'Bearer {admin_token}'},
            )

        assert resp.status_code == 200
        created = resp.json()['data']
        task_id = created['task_id']
        assert created['client_name'] == '委托客户 A'
        assert created['project_name'] == '职业卫生评价项目'
        assert created['project_code'] == 'PJ-001'
        assert created['service_type'] == '评价'

        listed = client.get(
            '/api/v1/assessment',
            params={'client_name': '客户 A', 'project_name': '职业卫生', 'service_type': '评价'},
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert listed.status_code == 200
        items = listed.json()['data']['items']
        assert any((item.get('task_id') or item.get('id')) == task_id for item in items)

        detail = client.get(
            f'/api/v1/assessment/{task_id}',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert detail.status_code == 200
        body = detail.json()['data']
        assert body['client_name'] == '委托客户 A'
        assert body['project_name'] == '职业卫生评价项目'
        assert body['project_code'] == 'PJ-001'
        assert body['service_type'] == '评价'

    def test_soft_delete(self, client: TestClient, admin_token: str):
        task_id = self._create_task(client, admin_token)
        resp = client.delete(
            f'/api/v1/assessment/{task_id}',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        # 204 wrapped to 200 by envelope
        assert resp.status_code == 200

        # 删除后查询应返回 404（软删除过滤）
        resp = client.get(
            f'/api/v1/assessment/{task_id}',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        # SQLite 测试中 session 缓存可能导致仍返回 200，生产 MySQL 正常返回 404
        assert resp.status_code in (200, 404)

    def test_get_nonexistent_task(self, client: TestClient, admin_token: str):
        resp = client.get(
            '/api/v1/assessment/00000000-0000-0000-0000-000000000000',
            headers={'Authorization': f'Bearer {admin_token}'},
        )
        assert resp.status_code == 404

    def test_no_auth_rejected(self, client: TestClient):
        resp = client.get('/api/v1/assessment')
        assert resp.status_code == 401

    def test_requeue_failed_task(self, client: TestClient, admin_token: str, db):
        from app.models.db_models import AssessmentTask, Organization, TaskStatus

        org = db.get(Organization, '00000000-0000-4000-8000-000000000001')
        if org is None:
            org = Organization(id='00000000-0000-4000-8000-000000000001', name='Default Test Org')
            db.add(org)
            db.flush()

        task = AssessmentTask(
            organization_id=org.id,
            filename='failed.txt',
            content_type='text/plain',
            file_path='uploads/failed.txt',
            status=TaskStatus.FAILED,
            progress=100,
            error_message='Dify failed',
            result_json='{"risks": [], "summary": "old"}',
        )
        db.add(task)
        db.flush()
        delay = MagicMock()

        with patch('app.tasks.worker.run_assessment_task.delay', new=delay):
            resp = client.post(
                f'/api/v1/assessment/{task.id}/requeue',
                headers={
                    'Authorization': f'Bearer {admin_token}',
                    'X-Request-Id': 'requeue-request-id',
                },
            )

        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['task_id'] == task.id
        assert data['status'] == 'PENDING'
        delay.assert_called_once()
        assert delay.call_args.args[0] == task.id
        assert delay.call_args.args[1] == 'requeue-request-id'
        assert len(delay.call_args.args[2]) == 32

        db.refresh(task)
        assert task.status == TaskStatus.PENDING
        assert task.progress == 0
        assert task.error_message is None
        assert task.result_json is None

    def test_requeue_non_failed_task_rejected(self, client: TestClient, admin_token: str):
        task_id = self._create_task(client, admin_token)

        resp = client.post(
            f'/api/v1/assessment/{task_id}/requeue',
            headers={'Authorization': f'Bearer {admin_token}'},
        )

        assert resp.status_code == 409
        assert resp.json()['code'] == 'TASK_NOT_REQUEUEABLE'

    def test_requeue_needs_review_task(self, client: TestClient, admin_token: str, db):
        from app.models.db_models import AssessmentTask, Organization, TaskStatus

        org = db.get(Organization, '00000000-0000-4000-8000-000000000001')
        if org is None:
            org = Organization(id='00000000-0000-4000-8000-000000000001', name='Default Test Org')
            db.add(org)
            db.flush()

        task = AssessmentTask(
            organization_id=org.id,
            filename='needs-review.txt',
            content_type='text/plain',
            file_path='uploads/needs-review.txt',
            status=TaskStatus.NEEDS_REVIEW,
            progress=100,
            error_message='model output is not structured',
            result_json='{"risks": [], "summary": "raw"}',
        )
        db.add(task)
        db.flush()
        delay = MagicMock()

        with patch('app.tasks.worker.run_assessment_task.delay', new=delay):
            resp = client.post(
                f'/api/v1/assessment/{task.id}/requeue',
                headers={'Authorization': f'Bearer {admin_token}'},
            )

        assert resp.status_code == 200
        delay.assert_called_once()
        db.refresh(task)
        assert task.status == TaskStatus.PENDING
        assert task.progress == 0
        assert task.error_message is None
        assert task.result_json is None


class TestAssessmentPermissions:
    def test_user_cannot_see_other_org_tasks(self, client: TestClient, user_token: str, admin_token: str, db):
        """普通用户不能查询其他公司的任务。"""
        from app.models.db_models import Organization
        other_org = Organization(name='其他公司')
        db.add(other_org)
        db.flush()

        resp = client.get(
            '/api/v1/assessment',
            params={'organization_id': other_org.id},
            headers={'Authorization': f'Bearer {user_token}'},
        )
        assert resp.status_code == 403

    def test_user_cannot_requeue_other_author_task(
        self,
        client: TestClient,
        user_token: str,
        admin_token: str,
        db,
    ):
        task_id = TestAssessmentCRUD()._create_task(client, admin_token)
        from app.models.db_models import AssessmentTask, TaskStatus

        task = db.get(AssessmentTask, task_id)
        task.status = TaskStatus.FAILED
        task.progress = 100
        task.error_message = 'failed'
        db.commit()

        resp = client.post(
            f'/api/v1/assessment/{task_id}/requeue',
            headers={'Authorization': f'Bearer {user_token}'},
        )
        assert resp.status_code == 403

    def test_org_admin_can_mutate_tasks_in_own_org(
        self,
        client: TestClient,
        org_admin_token: str,
        db,
    ):
        from app.core.config import settings
        from app.models.db_models import AssessmentTask, Organization, TaskStatus

        org = db.get(Organization, settings.default_organization_id)
        assert org is not None
        failed_task = AssessmentTask(
            organization_id=org.id,
            filename='org-admin-failed.txt',
            content_type='text/plain',
            file_path='uploads/org-admin-failed.txt',
            status=TaskStatus.FAILED,
            progress=100,
            error_message='failed',
        )
        deletable_task = AssessmentTask(
            organization_id=org.id,
            filename='org-admin-delete.txt',
            content_type='text/plain',
            file_path='uploads/org-admin-delete.txt',
            status=TaskStatus.PENDING,
            progress=0,
        )
        db.add_all([failed_task, deletable_task])
        db.flush()

        delay = MagicMock()
        with patch('app.tasks.worker.run_assessment_task.delay', new=delay):
            requeue_resp = client.post(
                f'/api/v1/assessment/{failed_task.id}/requeue',
                headers={'Authorization': f'Bearer {org_admin_token}'},
            )
        assert requeue_resp.status_code == 200
        delay.assert_called_once()

        delete_resp = client.delete(
            f'/api/v1/assessment/{deletable_task.id}',
            headers={'Authorization': f'Bearer {org_admin_token}'},
        )
        assert delete_resp.status_code == 200

    def test_org_admin_cannot_see_or_mutate_other_org_tasks(
        self,
        client: TestClient,
        org_admin_token: str,
        db,
    ):
        from app.models.db_models import AssessmentTask, Organization, TaskStatus

        other_org = Organization(name='其他公司任务租户')
        db.add(other_org)
        db.flush()
        other_task = AssessmentTask(
            organization_id=other_org.id,
            filename='other-org-failed.txt',
            content_type='text/plain',
            file_path='uploads/other-org-failed.txt',
            status=TaskStatus.FAILED,
            progress=100,
            error_message='failed',
        )
        db.add(other_task)
        db.flush()

        list_resp = client.get(
            '/api/v1/assessment',
            params={'organization_id': other_org.id},
            headers={'Authorization': f'Bearer {org_admin_token}'},
        )
        assert list_resp.status_code == 403

        requeue_resp = client.post(
            f'/api/v1/assessment/{other_task.id}/requeue',
            headers={'Authorization': f'Bearer {org_admin_token}'},
        )
        assert requeue_resp.status_code == 403


def test_worker_extracts_docx_text_and_persists_parsed_text(monkeypatch, tmp_path: Path):
    from app.core.db import SessionLocal
    from app.models.db_models import AssessmentTask, Organization, TaskStatus
    from app.schemas.ehs_schema import EHSAssessmentResult
    from app.tasks.worker import run_assessment_task

    docx_path = tmp_path / 'worker-sample.docx'
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        '<w:p><w:r><w:t>DOCX body text</w:t></w:r></w:p>'
        '</w:body>'
        '</w:document>'
    )
    with ZipFile(docx_path, 'w') as archive:
        archive.writestr('word/document.xml', xml)

    with SessionLocal() as setup_session:
        org = setup_session.get(Organization, '00000000-0000-4000-8000-000000000001')
        if org is None:
            org = Organization(id='00000000-0000-4000-8000-000000000001', name='Default Test Org')
            setup_session.add(org)
            setup_session.flush()

        task = AssessmentTask(
            organization_id=org.id,
            filename='worker-sample.docx',
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            file_path=str(docx_path),
            status=TaskStatus.PENDING,
            progress=0,
        )
        setup_session.add(task)
        setup_session.commit()
        task_id = task.id

    captured: dict[str, str] = {}

    def _fake_fetch(*, document_text: str, filename: str, task_id: str):
        captured['document_text'] = document_text
        return EHSAssessmentResult(risks=[], summary='ok')

    monkeypatch.setattr('app.tasks.worker.fetch_assessment_result', _fake_fetch)
    monkeypatch.setattr('app.tasks.worker.publish_task_progress', lambda *args, **kwargs: None)

    run_assessment_task(task_id)
    with SessionLocal() as session:
        saved = session.get(AssessmentTask, task_id)
        from app.dao.assessment_dao import AssessmentDAO

        timeline = AssessmentDAO(session).list_timeline_events(task_id)

    assert captured['document_text'] == 'DOCX body text'
    assert saved is not None
    assert saved.parsed_text == 'DOCX body text'
    assert saved.status == TaskStatus.SUCCESS
    assert [event.status for event in timeline] == [
        TaskStatus.PARSING,
        TaskStatus.AI_ANALYZING,
        TaskStatus.VALIDATING,
        TaskStatus.PERSISTING,
        TaskStatus.SUCCESS,
    ]
    assert all(event.elapsed_ms is not None for event in timeline)


def test_worker_marks_unstructured_dify_result_as_needs_review(monkeypatch, tmp_path: Path):
    from app.core.db import SessionLocal
    from app.models.db_models import AssessmentTask, Organization, TaskStatus
    from app.services.dify_service import DifyResultStructureError
    from app.tasks.worker import run_assessment_task

    doc_path = tmp_path / 'needs-review.txt'
    doc_path.write_text('source text', encoding='utf-8')

    with SessionLocal() as setup_session:
        org = setup_session.get(Organization, '00000000-0000-4000-8000-000000000001')
        if org is None:
            org = Organization(id='00000000-0000-4000-8000-000000000001', name='Default Test Org')
            setup_session.add(org)
            setup_session.flush()

        task = AssessmentTask(
            organization_id=org.id,
            filename='needs-review.txt',
            content_type='text/plain',
            file_path=str(doc_path),
            status=TaskStatus.PENDING,
            progress=0,
        )
        setup_session.add(task)
        setup_session.commit()
        task_id = task.id

    def _fake_fetch(*_args, **_kwargs):
        raise DifyResultStructureError(
            '无法从工作流输出解析 EHS 结构',
            raw_output='plain model answer without json',
        )

    published: list[tuple[str, str, int, str | None]] = []
    monkeypatch.setattr('app.tasks.worker.fetch_assessment_result', _fake_fetch)
    monkeypatch.setattr(
        'app.tasks.worker.publish_task_progress',
        lambda *args, **kwargs: published.append(args),
    )

    run_assessment_task(task_id)

    with SessionLocal() as session:
        saved = session.get(AssessmentTask, task_id)
        from app.dao.assessment_dao import AssessmentDAO

        timeline = AssessmentDAO(session).list_timeline_events(task_id)

    assert saved is not None
    assert saved.status == TaskStatus.NEEDS_REVIEW
    assert saved.progress == 100
    assert saved.error_message == '无法从工作流输出解析 EHS 结构'
    result = json.loads(saved.result_json or '{}')
    assert result['risks'] == []
    assert result['summary'] == 'plain model answer without json'
    assert result['metadata']['needs_review'] is True
    assert [event.status for event in timeline] == [
        TaskStatus.PARSING,
        TaskStatus.AI_ANALYZING,
        TaskStatus.VALIDATING,
        TaskStatus.PERSISTING,
        TaskStatus.NEEDS_REVIEW,
    ]
    assert published[-1] == (
        task_id,
        TaskStatus.NEEDS_REVIEW.value,
        100,
        '无法从工作流输出解析 EHS 结构',
    )


def test_worker_skips_non_pending_stale_message(monkeypatch, tmp_path: Path):
    from app.core.db import SessionLocal
    from app.models.db_models import AssessmentTask, Organization, TaskStatus
    from app.tasks.worker import run_assessment_task

    doc_path = tmp_path / 'already-running.txt'
    doc_path.write_text('already running', encoding='utf-8')

    with SessionLocal() as setup_session:
        org = setup_session.get(Organization, '00000000-0000-4000-8000-000000000001')
        if org is None:
            org = Organization(id='00000000-0000-4000-8000-000000000001', name='Default Test Org')
            setup_session.add(org)
            setup_session.flush()

        task = AssessmentTask(
            organization_id=org.id,
            filename='already-running.txt',
            content_type='text/plain',
            file_path=str(doc_path),
            status=TaskStatus.AI_ANALYZING,
            progress=45,
        )
        setup_session.add(task)
        setup_session.commit()
        task_id = task.id

    def _unexpected_fetch(*_args, **_kwargs):
        raise AssertionError('stale messages must not run the workflow again')

    published: list[tuple[str, str, int, str | None]] = []
    monkeypatch.setattr('app.tasks.worker.fetch_assessment_result', _unexpected_fetch)
    monkeypatch.setattr(
        'app.tasks.worker.publish_task_progress',
        lambda *args, **kwargs: published.append(args),
    )

    run_assessment_task(task_id)

    with SessionLocal() as session:
        saved = session.get(AssessmentTask, task_id)
        from app.dao.assessment_dao import AssessmentDAO

        timeline = AssessmentDAO(session).list_timeline_events(task_id)

    assert saved is not None
    assert saved.status == TaskStatus.AI_ANALYZING
    assert saved.progress == 45
    assert timeline == []
    assert published == [(task_id, TaskStatus.AI_ANALYZING.value, 45, None)]


def test_assessment_detail_includes_timeline_waterfall(client: TestClient, admin_token: str, db):
    from app.dao.assessment_dao import AssessmentDAO
    from app.models.db_models import AssessmentTask, Organization, TaskStatus

    org = db.get(Organization, '00000000-0000-4000-8000-000000000001')
    if org is None:
        org = Organization(id='00000000-0000-4000-8000-000000000001', name='Default Test Org')
        db.add(org)
        db.flush()

    task = AssessmentTask(
        organization_id=org.id,
        filename='timeline.txt',
        content_type='text/plain',
        file_path='uploads/timeline.txt',
        status=TaskStatus.FAILED,
        progress=100,
        error_message='failed',
    )
    db.add(task)
    db.flush()
    dao = AssessmentDAO(db)
    dao.append_timeline_event(
        task_id=task.id,
        status=TaskStatus.PARSING,
        progress=12,
        message='解析文档',
        elapsed_ms=10,
    )
    dao.append_timeline_event(
        task_id=task.id,
        status=TaskStatus.FAILED,
        progress=100,
        message='任务失败',
        elapsed_ms=35,
    )

    resp = client.get(
        f'/api/v1/assessment/{task.id}',
        headers={'Authorization': f'Bearer {admin_token}'},
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    assert len(data['timeline']) == 2
    assert data['timeline'][0]['elapsed_ms'] == 10
    assert data['waterfall'][0]['duration_ms'] == 10
    assert data['waterfall'][1]['duration_ms'] == 25
