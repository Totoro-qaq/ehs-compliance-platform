from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.db_models import (
    AgentMessage,
    AgentMessageRole,
    AgentRun,
    AgentSession,
    AgentToolCall,
    AssessmentTask,
    ComplianceResult,
    ComplianceStatus,
    DetectionMeasurement,
    DetectionReport,
    DetectionSample,
    LimitType,
    Organization,
    ReportStatus,
    ReportType,
    SampleMedium,
    TaskStatus,
)


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_agent_chat_persists_messages_run_and_tool_call(
    client: TestClient,
    user_token: str,
    db,
    monkeypatch,
):
    call_model = AsyncMock(return_value='当前工作台正常，下一步建议先查看待处理事项。')
    monkeypatch.setattr('app.services.agent_service.AgentService._call_model', call_model)

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '总结当前工作台'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    assert data['degraded'] is False
    assert data['session']['title'] == '总结当前工作台'
    assert data['user_message']['role'] == 'USER'
    assert '当前账号可见范围内的工作台摘要' in data['assistant_message']['content']
    assert data['run']['provider'] == 'rules'
    assert data['run']['model_name'] == 'fast-summary'
    assert data['run']['status'] == 'SUCCEEDED'
    assert data['tool_calls'][0]['tool_name'] == 'get_workbench_summary'
    assert data['tool_calls'][0]['success'] is True
    call_model.assert_not_called()

    messages = db.query(AgentMessage).filter_by(session_id=data['session']['id']).all()
    assert [message.role for message in messages] == [
        AgentMessageRole.USER,
        AgentMessageRole.ASSISTANT,
    ]
    assert db.query(AgentRun).filter_by(session_id=data['session']['id']).count() == 1
    assert db.query(AgentToolCall).filter_by(session_id=data['session']['id']).count() == 1


def test_agent_chat_falls_back_when_model_unavailable(
    client: TestClient,
    user_token: str,
    monkeypatch,
):
    monkeypatch.setattr(
        'app.services.agent_service.AgentService._call_model',
        AsyncMock(side_effect=RuntimeError('ollama unavailable')),
    )

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '请解释一下职业卫生评价的整改思路'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    assert data['degraded'] is True
    assert data['run']['provider'] == 'fallback'
    assert data['run']['model_name'] == 'rules'
    assert '本次模型未响应' in data['assistant_message']['content']
    assert '建议动作' in data['assistant_message']['content']


def test_agent_workbench_summary_uses_fast_summary(
    client: TestClient,
    user_token: str,
    monkeypatch,
):
    call_model = AsyncMock(side_effect=RuntimeError('should not call model'))
    monkeypatch.setattr('app.services.agent_service.AgentService._call_model', call_model)

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '有哪些待处理事项'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    assert data['degraded'] is False
    assert data['run']['provider'] == 'rules'
    assert data['run']['model_name'] == 'fast-summary'
    assert '本次模型未响应' not in data['assistant_message']['content']
    assert '当前账号可见范围内的工作台摘要' in data['assistant_message']['content']
    call_model.assert_not_called()


def test_agent_unknown_short_prompt_defaults_to_fast_summary(
    client: TestClient,
    user_token: str,
    monkeypatch,
):
    call_model = AsyncMock(side_effect=RuntimeError('should not call model'))
    monkeypatch.setattr('app.services.agent_service.AgentService._call_model', call_model)

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '现在咋样'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    assert data['degraded'] is False
    assert data['run']['provider'] == 'rules'
    assert data['run']['model_name'] == 'fast-summary'
    assert '当前账号可见范围内的工作台摘要' in data['assistant_message']['content']
    call_model.assert_not_called()


def test_agent_lightweight_prompt_returns_guidance_without_tools(
    client: TestClient,
    user_token: str,
    monkeypatch,
):
    call_model = AsyncMock(side_effect=RuntimeError('should not call model'))
    monkeypatch.setattr('app.services.agent_service.AgentService._call_model', call_model)

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '？'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    answer = data['assistant_message']['content']
    assert data['degraded'] is False
    assert data['run']['provider'] == 'rules'
    assert data['run']['model_name'] == 'static-reply'
    assert data['tool_calls'] == []
    assert '当前账号可见范围内的工作台摘要' not in answer
    assert '可以直接问' in answer
    call_model.assert_not_called()


def test_agent_detection_lookup_uses_fast_summary(
    client: TestClient,
    user_token: str,
    monkeypatch,
):
    call_model = AsyncMock(side_effect=RuntimeError('should not call model'))
    monkeypatch.setattr('app.services.agent_service.AgentService._call_model', call_model)

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '检测报告还有哪些没判定'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    assert data['run']['provider'] == 'rules'
    assert data['run']['model_name'] == 'fast-summary'
    call_model.assert_not_called()


def test_agent_open_question_calls_model(
    client: TestClient,
    user_token: str,
    monkeypatch,
):
    call_model = AsyncMock(return_value='需要结合现场材料和报告结果进一步复核。')
    monkeypatch.setattr('app.services.agent_service.AgentService._call_model', call_model)

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '请解释一下职业卫生评价的整改思路'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    assert data['degraded'] is False
    assert data['assistant_message']['content'] == '需要结合现场材料和报告结果进一步复核。'
    call_model.assert_awaited_once()


def test_agent_chat_reads_only_current_user_organization(
    client: TestClient,
    user_token: str,
    db,
    monkeypatch,
):
    monkeypatch.setattr(
        'app.services.agent_service.AgentService._call_model',
        AsyncMock(side_effect=RuntimeError('force fallback')),
    )

    own_org = db.get(Organization, settings.default_organization_id)
    assert own_org is not None
    other_org = Organization(name='Other Agent Org')
    db.add(other_org)
    db.flush()
    db.add_all(
        [
            AssessmentTask(
                organization_id=own_org.id,
                task_name='本公司失败任务',
                filename='own.txt',
                content_type='text/plain',
                file_path='uploads/own.txt',
                status=TaskStatus.FAILED,
                progress=100,
                error_message='own failed',
            ),
            AssessmentTask(
                organization_id=other_org.id,
                task_name='其他公司失败任务',
                filename='other.txt',
                content_type='text/plain',
                file_path='uploads/other.txt',
                status=TaskStatus.FAILED,
                progress=100,
                error_message='other failed',
            ),
        ]
    )
    db.commit()

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '最近失败的任务是什么'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    answer = resp.json()['data']['assistant_message']['content']
    assert '本公司失败任务' in answer
    assert '其他公司失败任务' not in answer


def test_agent_failed_task_summary_sanitizes_and_deduplicates_errors(
    client: TestClient,
    user_token: str,
    db,
    monkeypatch,
):
    monkeypatch.setattr(
        'app.services.agent_service.AgentService._call_model',
        AsyncMock(side_effect=RuntimeError('force fallback')),
    )

    org = db.get(Organization, settings.default_organization_id)
    assert org is not None
    raw_format_error = (
        "无法从工作流输出解析 EHS 结构（需要包含 risks、summary；或配置 "
        "DIFY_WORKFLOW_RESULT_KEY 指向含 JSON 的输出变量）。当前 keys: ['result_json']"
    )
    db.add_all(
        [
            AssessmentTask(
                organization_id=org.id,
                task_name='sample_document_text.txt',
                client_name='委托客户 E',
                project_name='失败评价项目',
                project_code='FAIL-001',
                service_type='评价',
                filename='sample_document_text.txt',
                content_type='text/plain',
                file_path='uploads/sample_document_text.txt',
                status=TaskStatus.FAILED,
                progress=100,
                error_message=raw_format_error,
            ),
            AssessmentTask(
                organization_id=org.id,
                task_name='sample_document_text.txt',
                client_name='委托客户 E',
                project_name='失败评价项目',
                project_code='FAIL-001',
                service_type='评价',
                filename='sample_document_text.txt',
                content_type='text/plain',
                file_path='uploads/sample_document_text_dup.txt',
                status=TaskStatus.FAILED,
                progress=100,
                error_message=raw_format_error,
            ),
            AssessmentTask(
                organization_id=org.id,
                task_name='短文本样例',
                filename='short.txt',
                content_type='text/plain',
                file_path='uploads/short.txt',
                status=TaskStatus.FAILED,
                progress=100,
                error_message=(
                    'Dify 请求失败 HTTP 400: {"code":"invalid_param","message":'
                    '"document_text in input form must be less than 200 characters","status":400}'
                ),
            ),
        ]
    )
    db.commit()

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '最近失败的任务是什么'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    answer = resp.json()['data']['assistant_message']['content']
    assert answer.count('sample_document_text.txt') == 1
    assert '同类 2 条' in answer
    assert '客户：委托客户 E' in answer
    assert '项目：失败评价项目' in answer
    assert '编号：FAIL-001' in answer
    assert 'AI 工作流返回格式不符合系统要求' in answer
    assert 'AI 工作流参数校验失败' in answer
    assert 'DIFY_WORKFLOW_RESULT_KEY' not in answer
    assert 'result_json' not in answer
    assert 'document_text in input form' not in answer
    assert 'invalid_param' not in answer
    assert 'HTTP 400' not in answer


def test_agent_session_messages_are_account_scoped(
    client: TestClient,
    user_token: str,
    admin_token: str,
    monkeypatch,
):
    monkeypatch.setattr(
        'app.services.agent_service.AgentService._call_model',
        AsyncMock(return_value='ok'),
    )
    created = client.post(
        '/api/v1/agent/chat',
        json={'content': '总结当前工作台'},
        headers=_auth(user_token),
    )
    assert created.status_code == 200
    session_id = created.json()['data']['session']['id']

    forbidden = client.get(
        f'/api/v1/agent/sessions/{session_id}/messages',
        headers=_auth(admin_token),
    )
    assert forbidden.status_code == 404


def test_agent_delete_session_soft_deletes_owned_records(
    client: TestClient,
    user_token: str,
    admin_token: str,
    db,
):
    created = client.post(
        '/api/v1/agent/chat',
        json={'content': '总结当前工作台'},
        headers=_auth(user_token),
    )
    assert created.status_code == 200
    session_id = created.json()['data']['session']['id']

    forbidden = client.delete(
        f'/api/v1/agent/sessions/{session_id}',
        headers=_auth(admin_token),
    )
    assert forbidden.status_code == 404

    deleted = client.delete(
        f'/api/v1/agent/sessions/{session_id}',
        headers=_auth(user_token),
    )
    assert deleted.status_code == 200
    assert deleted.json()['data']['deleted'] == 1

    listed = client.get('/api/v1/agent/sessions', headers=_auth(user_token))
    assert listed.status_code == 200
    assert all(item['id'] != session_id for item in listed.json()['data']['items'])

    messages = client.get(
        f'/api/v1/agent/sessions/{session_id}/messages',
        headers=_auth(user_token),
    )
    assert messages.status_code == 404

    assert db.query(AgentSession).filter_by(id=session_id, deleted_at=None).count() == 0
    assert db.query(AgentMessage).filter_by(session_id=session_id, deleted_at=None).count() == 0
    assert db.query(AgentRun).filter_by(session_id=session_id, deleted_at=None).count() == 0
    assert db.query(AgentToolCall).filter_by(session_id=session_id, deleted_at=None).count() == 0
    assert (
        db.query(AgentSession)
        .filter_by(id=session_id)
        .execution_options(include_deleted=True)
        .count()
        == 1
    )
    assert (
        db.query(AgentMessage)
        .filter_by(session_id=session_id)
        .execution_options(include_deleted=True)
        .count()
        == 2
    )
    assert (
        db.query(AgentRun)
        .filter_by(session_id=session_id)
        .execution_options(include_deleted=True)
        .count()
        == 1
    )
    assert (
        db.query(AgentToolCall)
        .filter_by(session_id=session_id)
        .execution_options(include_deleted=True)
        .count()
        == 1
    )


def test_agent_clear_sessions_only_deletes_current_account(
    client: TestClient,
    user_token: str,
    admin_token: str,
):
    for content in ('总结当前工作台', '有哪些待处理事项'):
        resp = client.post(
            '/api/v1/agent/chat',
            json={'content': content},
            headers=_auth(user_token),
        )
        assert resp.status_code == 200

    admin_created = client.post(
        '/api/v1/agent/chat',
        json={'content': '总结当前工作台'},
        headers=_auth(admin_token),
    )
    assert admin_created.status_code == 200

    deleted = client.delete('/api/v1/agent/sessions', headers=_auth(user_token))
    assert deleted.status_code == 200
    assert deleted.json()['data']['deleted'] == 2

    user_list = client.get('/api/v1/agent/sessions', headers=_auth(user_token))
    assert user_list.status_code == 200
    assert user_list.json()['data']['total'] == 0

    admin_list = client.get('/api/v1/agent/sessions', headers=_auth(admin_token))
    assert admin_list.status_code == 200
    assert admin_list.json()['data']['total'] == 1
    assert admin_list.json()['data']['items'][0]['id'] == admin_created.json()['data']['session']['id']


def test_agent_chat_requires_auth(client: TestClient):
    resp = client.post('/api/v1/agent/chat', json={'content': '总结当前工作台'})
    assert resp.status_code == 401


def test_agent_pending_detection_prompt_uses_pending_statuses(
    client: TestClient,
    user_token: str,
    db,
    monkeypatch,
):
    monkeypatch.setattr(
        'app.services.agent_service.AgentService._call_model',
        AsyncMock(side_effect=RuntimeError('force fallback')),
    )

    org = db.get(Organization, settings.default_organization_id)
    assert org is not None
    db.add_all(
        [
            DetectionReport(
                organization_id=org.id,
                report_name='待判定检测报告',
                client_name='委托客户 D',
                project_name='待判定项目',
                project_code='PENDING-001',
                service_type='定期检测',
                filename='pending.csv',
                report_type=ReportType.OCCUPATIONAL_HEALTH,
                status=ReportStatus.PARSED,
            ),
            DetectionReport(
                organization_id=org.id,
                report_name='已判定检测报告',
                filename='done.csv',
                report_type=ReportType.OCCUPATIONAL_HEALTH,
                status=ReportStatus.CALCULATED,
            ),
        ]
    )
    db.commit()

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '检测报告还有哪些没判定'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    answer = resp.json()['data']['assistant_message']['content']
    assert '待判定检测报告' in answer
    assert '客户：委托客户 D' in answer
    assert '项目：待判定项目' in answer
    assert '编号：PENDING-001' in answer
    assert '已判定检测报告' not in answer


def test_agent_filters_detection_by_client_project_context(
    client: TestClient,
    user_token: str,
    db,
    monkeypatch,
):
    monkeypatch.setattr(
        'app.services.agent_service.AgentService._call_model',
        AsyncMock(side_effect=RuntimeError('should not call model')),
    )

    org = db.get(Organization, settings.default_organization_id)
    assert org is not None
    db.add_all(
        [
            DetectionReport(
                organization_id=org.id,
                report_name='安测 A 待判定报告',
                client_name='安测委托A',
                project_name='年度检测项目A',
                project_code='AC-A-001',
                service_type='定期检测',
                filename='client-a.csv',
                report_type=ReportType.OCCUPATIONAL_HEALTH,
                status=ReportStatus.PARSED,
            ),
            DetectionReport(
                organization_id=org.id,
                report_name='安测 B 待判定报告',
                client_name='安测委托B',
                project_name='年度检测项目B',
                project_code='AC-B-001',
                service_type='定期检测',
                filename='client-b.csv',
                report_type=ReportType.OCCUPATIONAL_HEALTH,
                status=ReportStatus.PARSED,
            ),
            AssessmentTask(
                organization_id=org.id,
                task_name='安测 A 评价任务',
                client_name='安测委托A',
                project_name='年度检测项目A',
                project_code='AC-A-001',
                service_type='评价',
                filename='client-a-assessment.txt',
                content_type='text/plain',
                file_path='uploads/client-a-assessment.txt',
                status=TaskStatus.SUCCESS,
                progress=100,
            ),
        ]
    )
    db.commit()

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '客户安测委托A 项目年度检测项目A 有哪些检测报告没判定'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    answer = data['assistant_message']['content']
    assert data['run']['provider'] == 'rules'
    assert data['run']['model_name'] == 'fast-summary'
    assert '客户/项目上下文' in answer
    assert '安测 A 待判定报告' in answer
    assert '安测 A 评价任务' in answer
    assert '安测 B 待判定报告' not in answer
    assert any(call['tool_name'] == 'get_client_project_context' for call in data['tool_calls'])


def test_agent_summarizes_detection_compliance_by_client_project_context(
    client: TestClient,
    user_token: str,
    db,
    monkeypatch,
):
    monkeypatch.setattr(
        'app.services.agent_service.AgentService._call_model',
        AsyncMock(side_effect=RuntimeError('should not call model')),
    )

    org = db.get(Organization, settings.default_organization_id)
    assert org is not None
    report_a = DetectionReport(
        organization_id=org.id,
        report_name='安测 A 已判定报告',
        client_name='安测委托A',
        project_name='年度检测项目A',
        project_code='AC-A-001',
        service_type='定期检测',
        filename='client-a-calculated.csv',
        report_type=ReportType.OCCUPATIONAL_HEALTH,
        status=ReportStatus.CALCULATED,
    )
    report_b = DetectionReport(
        organization_id=org.id,
        report_name='安测 B 已判定报告',
        client_name='安测委托B',
        project_name='年度检测项目B',
        project_code='AC-B-001',
        service_type='定期检测',
        filename='client-b-calculated.csv',
        report_type=ReportType.OCCUPATIONAL_HEALTH,
        status=ReportStatus.CALCULATED,
    )
    db.add_all([report_a, report_b])
    db.flush()

    sample_a = DetectionSample(
        report_id=report_a.id,
        sample_point='A-01',
        workplace='涂装车间',
        post_name='喷漆岗',
        medium=SampleMedium.WORKPLACE_AIR,
    )
    sample_b = DetectionSample(
        report_id=report_b.id,
        sample_point='B-01',
        workplace='空压机房',
        post_name='巡检岗',
        medium=SampleMedium.NOISE,
    )
    db.add_all([sample_a, sample_b])
    db.flush()

    measurement_a = DetectionMeasurement(
        sample_id=sample_a.id,
        indicator_name='测试因子甲',
        raw_value=Decimal('8.0'),
        raw_unit='mg/m3',
        normalized_value=Decimal('8.0'),
        normalized_unit='mg/m3',
    )
    measurement_b = DetectionMeasurement(
        sample_id=sample_b.id,
        indicator_name='噪声',
        raw_value=Decimal('92'),
        raw_unit='dB(A)',
        normalized_value=Decimal('92'),
        normalized_unit='dB(A)',
    )
    db.add_all([measurement_a, measurement_b])
    db.flush()

    db.add_all(
        [
            ComplianceResult(
                report_id=report_a.id,
                sample_id=sample_a.id,
                measurement_id=measurement_a.id,
                calculated_value=Decimal('8.0'),
                calculated_unit='mg/m3',
                limit_value=Decimal('6.0'),
                limit_unit='mg/m3',
                limit_type=LimitType.PC_TWA,
                status=ComplianceStatus.EXCEEDED,
                exceedance_multiple=Decimal('0.3333'),
                standard_code='TEST-STD 2.1-2019',
                clause='第4.1条',
            ),
            ComplianceResult(
                report_id=report_b.id,
                sample_id=sample_b.id,
                measurement_id=measurement_b.id,
                calculated_value=Decimal('92'),
                calculated_unit='dB(A)',
                limit_value=Decimal('85'),
                limit_unit='dB(A)',
                limit_type=LimitType.INSTANT,
                status=ComplianceStatus.EXCEEDED,
                exceedance_multiple=Decimal('0.0824'),
                standard_code='TEST-STD 2.2-2007',
                clause='第11条',
            ),
        ]
    )
    db.commit()

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '客户安测委托A 项目年度检测项目A 哪些检测结果超标'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    answer = data['assistant_message']['content']
    assert data['run']['provider'] == 'rules'
    assert data['run']['model_name'] == 'fast-summary'
    assert '检测判定结果' in answer
    assert '超标 1 条' in answer
    assert '测试因子甲' in answer
    assert '安测 A 已判定报告' in answer
    assert '安测 B 已判定报告' not in answer
    assert '噪声' not in answer
    assert any(call['tool_name'] == 'summarize_detection_compliance' for call in data['tool_calls'])
