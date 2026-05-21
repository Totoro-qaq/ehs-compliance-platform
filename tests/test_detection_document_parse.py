from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.models.db_models import ReportType, SampleMedium
from app.services.detection_document_parse_service import parse_detection_text


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _docx_bytes(text_lines: list[str], path: Path) -> bytes:
    body = ''.join(f'<w:p><w:r><w:t>{line}</w:t></w:r></w:p>' for line in text_lines)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{body}</w:body>'
        '</w:document>'
    )
    with ZipFile(path, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    return path.read_bytes()


def test_parse_detection_text_extracts_candidate_rows():
    text = '\n'.join(
        [
            '检测点 喷漆岗 测试因子甲 50000 μg/m3 采样时长 60 min',
            '空压机房 噪声 88 dB(A) 8 h',
            '炼钢平台 WBGT 31 ℃',
        ]
    )

    rows, warnings = parse_detection_text(text, report_type=ReportType.OCCUPATIONAL_HEALTH)

    assert warnings == []
    assert len(rows) == 3
    assert rows[0].sample_point == '喷漆岗'
    assert rows[0].indicator_name == '测试因子甲'
    assert rows[0].raw_unit == 'µg/m3'
    assert rows[0].duration_minutes is not None
    assert rows[1].medium == SampleMedium.NOISE
    assert rows[2].medium == SampleMedium.HIGH_TEMPERATURE
    assert rows[2].warnings


def test_preview_detection_document_from_docx(client: TestClient, admin_token: str, tmp_path: Path):
    content = _docx_bytes(
        [
            '检测点 喷漆岗 测试因子甲 50000 μg/m3 采样时长 60 min',
            '空压机房 噪声 88 dB(A) 8 h',
        ],
        tmp_path / 'preview.docx',
    )

    resp = client.post(
        '/api/v1/detection/documents/preview',
        data={'report_type': 'OCCUPATIONAL_HEALTH'},
        files={
            'file': (
                'preview.docx',
                content,
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            )
        },
        headers=_auth(admin_token),
    )

    assert resp.status_code == 200
    body = resp.json()['data']
    assert body['filename'] == 'preview.docx'
    assert body['text_char_count'] > 0
    assert len(body['rows']) == 2
    assert body['rows'][0]['indicator_name'] == '测试因子甲'
    assert body['rows'][1]['medium'] == 'NOISE'


def test_preview_detection_document_rejects_structured_csv(
    client: TestClient, admin_token: str
):
    resp = client.post(
        '/api/v1/detection/documents/preview',
        data={'report_type': 'OCCUPATIONAL_HEALTH'},
        files={'file': ('structured.csv', b'a,b\n1,2\n', 'text/csv')},
        headers=_auth(admin_token),
    )

    assert resp.status_code == 400
    assert resp.json()['code'] == 'DETECTION_UNSUPPORTED_DOCUMENT_FORMAT'
