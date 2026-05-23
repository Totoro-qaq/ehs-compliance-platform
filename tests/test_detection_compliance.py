from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import settings
from app.dao.detection_dao import RegulatoryLimitDAO, serialize_aliases
from app.models.db_models import LimitType, Organization, RegulatoryLimit, SampleMedium


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _seed_limit(
    db,
    *,
    indicator_name: str,
    medium: SampleMedium = SampleMedium.WORKPLACE_AIR,
    limit_type: LimitType = LimitType.PC_TWA,
    value: str | None = '6',
    unit: str = 'mg/m3',
) -> RegulatoryLimit:
    limit = RegulatoryLimit(
        indicator_name=indicator_name,
        aliases_json=serialize_aliases([indicator_name]),
        medium=medium,
        limit_type=limit_type,
        limit_value=Decimal(value) if value is not None else None,
        unit=unit,
        standard_code='TEST-LIMIT',
        standard_name='Test standard',
        clause='Table 1',
        priority=1,
    )
    db.add(limit)
    db.commit()
    db.refresh(limit)
    return limit


def test_upload_csv_calculate_and_list_results(client: TestClient, admin_token: str, db):
    _seed_limit(db, indicator_name='苯', value='6')
    csv = (
        'sample_point,indicator_name,raw_value,raw_unit,duration_minutes\n'
        '喷漆岗,苯,50000,μg/m3,60\n'
    ).encode('utf-8-sig')

    upload = client.post(
        '/api/v1/detection/reports',
        data={
            'organization_id': settings.default_organization_id,
            'report_type': 'OCCUPATIONAL_HEALTH',
            'report_name': '苯检测报告',
            'client_name': '委托客户 B',
            'project_name': '职业卫生检测项目',
            'project_code': 'JC-001',
            'service_type': '检测',
        },
        files={'file': ('benzene.csv', csv, 'text/csv')},
        headers=_auth(admin_token),
    )
    assert upload.status_code == 200
    body = upload.json()['data']
    assert body['sample_count'] == 1
    assert body['measurement_count'] == 1
    assert body['client_name'] == '委托客户 B'
    assert body['project_name'] == '职业卫生检测项目'
    assert body['project_code'] == 'JC-001'
    assert body['service_type'] == '检测'
    report_id = body['report_id']

    listed = client.get(
        '/api/v1/detection/reports',
        params={'client_name': '客户 B', 'project_name': '职业卫生', 'service_type': '检测'},
        headers=_auth(admin_token),
    )
    assert listed.status_code == 200
    listed_items = listed.json()['data']['items']
    assert any(item['id'] == report_id for item in listed_items)

    detail = client.get(f'/api/v1/detection/reports/{report_id}', headers=_auth(admin_token))
    assert detail.status_code == 200
    detail_data = detail.json()['data']
    assert detail_data['client_name'] == '委托客户 B'
    assert detail_data['project_name'] == '职业卫生检测项目'
    assert detail_data['project_code'] == 'JC-001'
    assert detail_data['service_type'] == '检测'
    assert detail_data['samples'][0]['measurements'][0]['indicator_name'] == '苯'

    calculated = client.post(
        f'/api/v1/detection/reports/{report_id}/calculate',
        headers=_auth(admin_token),
    )
    assert calculated.status_code == 200
    result = calculated.json()['data']
    assert result['status'] == 'CALCULATED'
    assert result['total'] == 1
    assert result['exceeded'] == 1
    assert result['results'][0]['status'] == 'EXCEEDED'
    assert result['results'][0]['calculated_value'] == '6.250000'
    assert result['results'][0]['limit_value'] == '6.000000'
    assert result['results'][0]['exceedance_multiple'] == '0.0417'

    results = client.get(
        f'/api/v1/detection/reports/{report_id}/results',
        headers=_auth(admin_token),
    )
    assert results.status_code == 200
    assert results.json()['data'][0]['standard_code'] == 'TEST-LIMIT'


def test_missing_limit_returns_insufficient_data(client: TestClient, admin_token: str):
    csv = 'sample_point,indicator_name,raw_value,raw_unit\nP1,未知因子,1,mg/m3\n'.encode()

    upload = client.post(
        '/api/v1/detection/reports',
        data={'report_type': 'OCCUPATIONAL_HEALTH'},
        files={'file': ('missing.csv', csv, 'text/csv')},
        headers=_auth(admin_token),
    )
    assert upload.status_code == 200
    report_id = upload.json()['data']['report_id']

    calculated = client.post(
        f'/api/v1/detection/reports/{report_id}/calculate',
        headers=_auth(admin_token),
    )
    assert calculated.status_code == 200
    result = calculated.json()['data']
    assert result['insufficient'] == 1
    assert result['results'][0]['status'] == 'INSUFFICIENT_DATA'
    assert result['results'][0]['limit_id'] is None


def test_range_limit_uses_min_and_max(client: TestClient, admin_token: str, db):
    limit = RegulatoryLimit(
        indicator_name='pH',
        medium=SampleMedium.WASTEWATER,
        limit_type=LimitType.RANGE,
        limit_min=Decimal('6'),
        limit_max=Decimal('9'),
        unit='pH',
        standard_code='TEST-PH',
        standard_name='Test pH standard',
        priority=1,
    )
    db.add(limit)
    db.commit()

    csv = 'sample_point,medium,indicator_name,raw_value,raw_unit\nOutlet,WASTEWATER,pH,9.5,pH\n'.encode()
    upload = client.post(
        '/api/v1/detection/reports',
        data={'report_type': 'WASTEWATER'},
        files={'file': ('ph.csv', csv, 'text/csv')},
        headers=_auth(admin_token),
    )
    assert upload.status_code == 200

    report_id = upload.json()['data']['report_id']
    calculated = client.post(
        f'/api/v1/detection/reports/{report_id}/calculate',
        headers=_auth(admin_token),
    )
    assert calculated.status_code == 200
    item = calculated.json()['data']['results'][0]
    assert item['status'] == 'EXCEEDED'
    assert item['limit_type'] == 'RANGE'
    assert item['limit_value'] == '9.000000'


def test_high_temperature_wbgt_limit(client: TestClient, admin_token: str, db):
    _seed_limit(
        db,
        indicator_name='高温WBGT-I级-100%',
        medium=SampleMedium.HIGH_TEMPERATURE,
        limit_type=LimitType.INSTANT,
        value='30',
        unit='℃',
    )
    csv = (
        'sample_point,medium,indicator_name,raw_value,raw_unit\n'
        '炼钢平台,高温,高温WBGT-I级-100%,31,WBGT(℃)\n'
    ).encode('utf-8-sig')

    upload = client.post(
        '/api/v1/detection/reports',
        data={'report_type': 'HIGH_TEMPERATURE'},
        files={'file': ('heat.csv', csv, 'text/csv')},
        headers=_auth(admin_token),
    )
    assert upload.status_code == 200
    report_id = upload.json()['data']['report_id']

    calculated = client.post(
        f'/api/v1/detection/reports/{report_id}/calculate',
        headers=_auth(admin_token),
    )
    assert calculated.status_code == 200
    item = calculated.json()['data']['results'][0]
    assert item['status'] == 'EXCEEDED'
    assert item['calculated_unit'] == '℃'
    assert item['limit_value'] == '30.000000'


def test_limits_crud_is_admin_only(client: TestClient, admin_token: str, user_token: str):
    payload = {
        'indicator_name': '甲苯',
        'aliases': ['Toluene'],
        'medium': 'WORKPLACE_AIR',
        'limit_type': 'PC_TWA',
        'limit_value': '50',
        'unit': 'mg/m3',
        'standard_code': 'TEST-CRUD',
        'standard_name': 'Test CRUD standard',
        'priority': 10,
    }

    forbidden = client.post('/api/v1/detection/limits', json=payload, headers=_auth(user_token))
    assert forbidden.status_code == 403

    created = client.post('/api/v1/detection/limits', json=payload, headers=_auth(admin_token))
    assert created.status_code == 200
    limit_id = created.json()['data']['id']

    listed = client.get('/api/v1/detection/limits', headers=_auth(admin_token))
    assert listed.status_code == 200
    assert listed.json()['data']['total'] >= 1

    updated = client.put(
        f'/api/v1/detection/limits/{limit_id}',
        json={'limit_value': '60'},
        headers=_auth(admin_token),
    )
    assert updated.status_code == 200
    assert updated.json()['data']['limit_value'] == '60.000000'

    deleted = client.delete(f'/api/v1/detection/limits/{limit_id}', headers=_auth(admin_token))
    assert deleted.status_code == 200


def test_user_cannot_list_other_org_reports(client: TestClient, user_token: str, db):
    other_org = Organization(name='Other Detection Org')
    db.add(other_org)
    db.commit()

    resp = client.get(
        '/api/v1/detection/reports',
        params={'organization_id': other_org.id},
        headers=_auth(user_token),
    )
    assert resp.status_code == 403


def test_seed_upsert_is_idempotent(db):
    dao = RegulatoryLimitDAO(db)
    first = dao.upsert_seed(
        standard_code='TEST-SEED',
        indicator_name='噪声',
        medium=SampleMedium.NOISE,
        limit_type=LimitType.INSTANT,
        unit='dB(A)',
        limit_value=Decimal('85'),
        standard_name='Noise seed',
        priority=10,
    )
    second = dao.upsert_seed(
        standard_code='TEST-SEED',
        indicator_name='噪声',
        medium=SampleMedium.NOISE,
        limit_type=LimitType.INSTANT,
        unit='dB(A)',
        limit_value=Decimal('80'),
        standard_name='Noise seed',
        priority=10,
    )

    assert first.id == second.id
    assert second.limit_value == Decimal('80')
