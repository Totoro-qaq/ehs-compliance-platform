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
                indicator_name='测试因子甲',
                cas_no='71-43-2',
                medium=SampleMedium.WORKPLACE_AIR,
                limit_type=LimitType.PC_TWA,
                limit_value=Decimal('6'),
                unit='mg/m3',
                standard_code='TEST-STD 2.1-2019',
                standard_name='测试因素测试限值 第1部分：化学有害因素',
                clause='表1',
                priority=100,
            ),
            RegulatoryLimit(
                indicator_name='测试因子乙',
                cas_no='108-88-3',
                medium=SampleMedium.WORKPLACE_AIR,
                limit_type=LimitType.PC_TWA,
                limit_value=Decimal('50'),
                unit='mg/m3',
                standard_code='TEST-STD 2.1-2019',
                standard_name='测试因素测试限值 第1部分：化学有害因素',
                clause='表1',
                priority=100,
            ),
        ]
    )
    db.commit()

    resp = client.post(
        '/api/v1/agent/chat',
        json={'content': '帮我查一下测试因子甲的测试限值'},
        headers=_auth(user_token),
    )

    assert resp.status_code == 200
    data = resp.json()['data']
    answer = data['assistant_message']['content']
    assert data['run']['provider'] == 'rules'
    assert data['run']['model_name'] == 'fast-summary'
    assert '限值库命中' in answer
    assert '测试因子甲 PC_TWA 6 mg/m3' in answer
    assert '测试因子乙 PC_TWA 50 mg/m3' not in answer.split('限值库命中：', 1)[1].splitlines()[1]
    assert '限值库没有命中明确结果' not in answer
    call_model.assert_not_called()
