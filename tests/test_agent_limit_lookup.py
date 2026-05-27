from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.models.db_models import LimitType, RegulatoryLimit, SampleMedium


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_agent_limit_lookup_extracts_indicator_from_natural_language(
    client: TestClient,
    user_token: str,
    db,
    monkeypatch,
):
    call_model = AsyncMock(side_effect=RuntimeError('should not call model'))
    monkeypatch.setattr('app.services.agent_service.AgentService._call_model', call_model)

    db.add_all(
        [
            RegulatoryLimit(
                indicator_name='甲号测试因子',
                cas_no='AGENT-CAS-001',
                medium=SampleMedium.WORKPLACE_AIR,
                limit_type=LimitType.PC_TWA,
                limit_value=Decimal('11'),
                unit='test-unit',
                standard_code='AGENT-STD-001',
                standard_name='代理测试用虚构限值标准',
                clause='T-1',
                priority=100,
            ),
            RegulatoryLimit(
                indicator_name='乙号测试因子',
                cas_no='AGENT-CAS-002',
                medium=SampleMedium.WORKPLACE_AIR,
                limit_type=LimitType.PC_TWA,
                limit_value=Decimal('22'),
                unit='test-unit',
                standard_code='AGENT-STD-001',
                standard_name='代理测试用虚构限值标准',
                clause='T-1',
                priority=100,
            ),
        ]
    )
    db.commit()

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '查询 甲号测试因子 限值'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    answer = data['assistant_message']['content']
    assert data['run']['provider'] == 'rules'
    assert data['run']['model_name'] == 'fast-summary'
    assert '限值库命中' in answer
    assert '甲号测试因子 PC_TWA 11 test-unit' in answer
    assert '乙号测试因子 PC_TWA 22 test-unit' not in answer.split('限值库命中：', 1)[1].splitlines()[1]
    assert '限值库没有命中明确结果' not in answer
    call_model.assert_not_called()
