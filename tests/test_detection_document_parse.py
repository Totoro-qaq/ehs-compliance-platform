from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.models.db_models import ComplianceStatus, LimitType, ReportType, SampleMedium
from app.services.detection_document_parse_service import (
    _correct_noise_by_background,
    _parse_report_number,
    parse_detection_docx_tables,
    parse_detection_tables,
    parse_detection_text,
)


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
    assert rows[0].is_below_detection_limit is False
    assert rows[0].duration_minutes is not None
    assert rows[1].medium == SampleMedium.NOISE
    assert rows[2].medium == SampleMedium.HIGH_TEMPERATURE
    assert rows[2].warnings


def test_parse_detection_text_marks_below_detection_limit():
    rows, warnings = parse_detection_text(
        '喷漆岗 测试因子甲 <0.01 mg/m3',
        report_type=ReportType.OCCUPATIONAL_HEALTH,
    )

    assert warnings == []
    assert rows[0].raw_value is not None
    assert rows[0].is_below_detection_limit is True


def test_parse_report_number_handles_scientific_notation():
    value, is_below_detection_limit, warnings = _parse_report_number('5×10-4')

    assert value == Decimal('0.0005')
    assert is_below_detection_limit is False
    assert warnings == []


def test_correct_noise_by_background():
    value, warning = _correct_noise_by_background(Decimal('71.5'), Decimal('65.8'))

    assert value == Decimal('70.1')
    assert '背景噪声' in warning


def test_parse_detection_tables_handles_pdf_extracted_illumination_table():
    tables = [
        [
            ['单元名称', '岗位/作业点', '检测项目', '检测结果（lx）'],
            ['', '', '', '平均值'],
            ['第一工场', 'xx操作位', '照度', '387'],
        ]
    ]

    rows = parse_detection_tables(tables)

    assert len(rows) == 1
    assert rows[0].indicator_name == '照度'
    assert rows[0].raw_value == Decimal('387')
    assert rows[0].raw_unit == 'lx'
    assert rows[0].measurement_kind == 'illumination'


def test_parse_detection_tables_maps_generic_chemical_limit_columns():
    tables = [
        [
            ['区域', '检测岗位', '危害因素', '接触时间(h/d)', 'CTWA', 'PC-TWA', 'CSTE', 'PC-STEL'],
            ['喷涂车间', '喷漆岗', '测试因子甲', '8.0', '2.5', '6', '8.5', '10'],
        ]
    ]

    rows = parse_detection_tables(tables)

    assert len(rows) == 2
    assert rows[0].indicator_name == '测试因子甲'
    assert rows[0].limit_type == LimitType.PC_TWA
    assert rows[0].report_limit_value == Decimal('6')
    assert rows[0].preliminary_status == ComplianceStatus.COMPLIANT
    assert rows[1].limit_type == LimitType.PC_STEL
    assert rows[1].report_limit_value == Decimal('10')
    assert rows[1].preliminary_status == ComplianceStatus.COMPLIANT


def test_parse_detection_tables_prejudges_generic_chemical_exceeded():
    tables = [
        [
            ['检测点', '检测项目', '检测结果', '接触限值'],
            ['喷漆岗', '测试因子甲', '12', '6'],
        ]
    ]

    rows = parse_detection_tables(tables)

    assert len(rows) == 1
    assert rows[0].indicator_name == '测试因子甲'
    assert rows[0].limit_type is None
    assert rows[0].report_limit_value == Decimal('6')
    assert rows[0].preliminary_status == ComplianceStatus.EXCEEDED


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


def test_preview_detection_document_from_pdf_tables(
    monkeypatch, client: TestClient, admin_token: str
):
    monkeypatch.setattr(
        'app.services.detection_document_parse_service.extract_text_from_document_file',
        lambda *_args, **_kwargs: '检测项目 照度 检测结果',
    )
    monkeypatch.setattr(
        'app.services.detection_document_parse_service._store_document',
        lambda _filename, _content: Path('preview.pdf'),
    )
    monkeypatch.setattr(
        'app.services.detection_document_parse_service._pdf_tables',
        lambda _path: (
            [
                [
                    ['单元名称', '岗位/作业点', '检测项目', '检测结果（lx）'],
                    ['', '', '', '平均值'],
                    ['第一工场', 'xx操作位', '照度', '387'],
                ]
            ],
            [],
        ),
    )

    resp = client.post(
        '/api/v1/detection/documents/preview',
        data={'report_type': 'OCCUPATIONAL_HEALTH'},
        files={'file': ('preview.pdf', b'%PDF-1.7 fake', 'application/pdf')},
        headers=_auth(admin_token),
    )

    assert resp.status_code == 200
    body = resp.json()['data']
    assert len(body['rows']) == 1
    assert body['rows'][0]['indicator_name'] == '照度'
    assert body['rows'][0]['measurement_kind'] == 'illumination'
    assert body['warnings'][0].startswith('已按 PDF 表格结构解析')


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


def test_parse_detection_docx_tables_for_anonymized_sample_if_present():
    sample_dir = Path('Anonymized Sample Report')
    if not sample_dir.exists():
        return
    files = list(sample_dir.glob('*.docx'))
    if not files:
        return

    rows = parse_detection_docx_tables(files[0])

    assert len(rows) >= 190
    assert any(row.medium == SampleMedium.WORKPLACE_AIR for row in rows)
    assert any(row.medium == SampleMedium.NOISE for row in rows)
    assert any(row.medium == SampleMedium.HIGH_TEMPERATURE for row in rows)
    assert any(row.indicator_name.startswith('激光辐射') for row in rows)
    assert any(row.indicator_name == '工频电场' for row in rows)
    assert any(row.indicator_name == '照度' for row in rows)
    assert any(row.indicator_name == '其他测试颗粒物' for row in rows)
    assert any(row.indicator_name.startswith('测试热指数-C') for row in rows)
    assert any(row.is_below_detection_limit for row in rows)
    assert any(row.is_background for row in rows)
