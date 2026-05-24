"""非结构化检测报告解析预览。

第二层先做保守的“文本抽取 + 候选行识别”，不直接入库。用户确认后再复用第一层结构化导入与判定。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EHSException
from app.core.patterns import is_uuid
from app.dao.detection_dao import DetectionReportDAO
from app.dao.organization_dao import OrganizationDAO
from app.models.db_models import (
    ComplianceStatus,
    DetectionMeasurement,
    DetectionSample,
    LimitType,
    ReportStatus,
    ReportType,
    SampleMedium,
)
from app.schemas.auth_context import CurrentUser
from app.schemas.detection_schema import (
    DetectionDocumentImportRequest,
    DetectionReportCreateResponse,
)
from app.services.access_control import ensure_client_org_id_allowed
from app.services.detection_calculation_service import normalize_unit
from app.services.detection_service_types import clean_detection_service_type
from app.services.pdf_text_service import DocumentTextExtractError, extract_text_from_document_file

_ALLOWED_DOCUMENT_EXTENSIONS = frozenset({'.pdf', '.docx', '.doc', '.txt', '.zip'})
_MAX_PREVIEW_TEXT_CHARS = 4000
_MAX_PARSE_TEXT_CHARS = 200_000

_UNIT_PATTERN = (
    r'mg/m3|mg/m³|mg/m\^3|µg/m3|μg/m3|ug/m3|mg/L|mg/l|µg/L|μg/L|ug/l|'
    r'dB\(A\)|dBA|db\(a\)|℃|°C|WBGT\(℃\)|WBGT\(°C\)|pH|ppm'
)
_VALUE_UNIT_RE = re.compile(
    rf'(?P<value><\s*)?(?P<number>-?\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_PATTERN})',
    re.IGNORECASE,
)
_CAS_RE = re.compile(r'\b\d{2,7}-\d{2}-\d\b')
_WORD_NAMESPACE = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
_PDF_TABLE_SETTINGS = {
    'vertical_strategy': 'lines',
    'horizontal_strategy': 'lines',
    'snap_tolerance': 3,
    'join_tolerance': 3,
    'intersection_tolerance': 5,
    'text_tolerance': 3,
}

_INDICATOR_HINTS: tuple[str, ...] = (
    '高温WBGT',
    'WBGT',
    '其他测试颗粒物',
    '测试颗粒物',
    '测试因子丙',
    '测试因子乙',
    '测试因子甲',
    '噪声',
    'pH',
)


def _clean_display_name(value: str | None) -> str | None:
    cleaned = (value or '').strip()
    return cleaned[:255] if cleaned else None


def _report_type_label(report_type: ReportType) -> str:
    return {
        ReportType.OCCUPATIONAL_HEALTH: '职业卫生',
        ReportType.WASTEWATER: '废水',
        ReportType.EXHAUST_GAS: '废气',
        ReportType.NOISE: '噪声',
        ReportType.HIGH_TEMPERATURE: '高温WBGT',
    }.get(report_type, report_type.value)


def _default_report_name(
    organization_name: str | None,
    report_type: ReportType,
    service_type: str | None = None,
) -> str:
    org_name = (organization_name or '默认公司').strip() or '默认公司'
    business_type = service_type or f'{_report_type_label(report_type)}检测'
    return f'{org_name} {business_type}报告 {date.today().isoformat()}'[:255]


@dataclass(slots=True)
class ParsedDetectionRow:
    row_index: int
    sample_point: str
    indicator_name: str
    raw_value: Decimal | None
    raw_unit: str | None
    medium: SampleMedium | None = None
    workplace: str | None = None
    post_name: str | None = None
    duration_minutes: Decimal | None = None
    shift_hours: Decimal | None = None
    cas_no: str | None = None
    raw_text: str = ''
    confidence: Decimal = Decimal('0.50')
    is_below_detection_limit: bool = False
    is_background: bool = False
    measurement_kind: str | None = None
    limit_type: LimitType | None = None
    report_limit_value: Decimal | None = None
    report_limit_unit: str | None = None
    preliminary_status: ComplianceStatus | None = None
    preliminary_message: str | None = None
    source_file: str | None = None  # ZIP 多文件时标记来源
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DetectionDocumentPreview:
    filename: str
    report_type: ReportType
    text_char_count: int
    text_excerpt: str
    rows: list[ParsedDetectionRow]
    source_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _default_medium(report_type: ReportType) -> SampleMedium:
    if report_type == ReportType.OCCUPATIONAL_HEALTH:
        return SampleMedium.WORKPLACE_AIR
    if report_type == ReportType.WASTEWATER:
        return SampleMedium.WASTEWATER
    if report_type == ReportType.EXHAUST_GAS:
        return SampleMedium.EXHAUST_GAS
    if report_type == ReportType.NOISE:
        return SampleMedium.NOISE
    if report_type == ReportType.HIGH_TEMPERATURE:
        return SampleMedium.HIGH_TEMPERATURE
    return SampleMedium.WORKPLACE_AIR


def _row_medium(row: ParsedDetectionRow) -> SampleMedium:
    if row.medium is not None:
        return row.medium
    if row.measurement_kind in {
        'laser_exposure',
        'laser_irradiance',
        'power_frequency_electric_field',
        'illumination',
    }:
        return SampleMedium.PHYSICAL_FACTOR
    return SampleMedium.WORKPLACE_AIR


def _validate_report_type(raw: str | ReportType) -> ReportType:
    if isinstance(raw, ReportType):
        return raw
    try:
        return ReportType(raw)
    except ValueError as exc:
        raise EHSException(
            'Invalid detection report type',
            code='DETECTION_INVALID_REPORT_TYPE',
            status_code=400,
            details={'allowed': [item.value for item in ReportType]},
        ) from exc


def _validate_filename(filename: str | None) -> str:
    if not filename or not filename.strip():
        raise EHSException('Upload filename is required', code='DETECTION_INVALID_UPLOAD_FILENAME', status_code=400)
    name = Path(filename).name
    if name != filename or '..' in filename or '/' in filename or '\\' in filename:
        raise EHSException('Upload filename is invalid', code='DETECTION_INVALID_UPLOAD_FILENAME', status_code=400)
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_DOCUMENT_EXTENSIONS:
        raise EHSException(
            'Unsupported detection document type',
            code='DETECTION_UNSUPPORTED_DOCUMENT_FORMAT',
            status_code=400,
            details={'allowed': sorted(_ALLOWED_DOCUMENT_EXTENSIONS)},
        )
    return name


def _store_document(filename: str, content: bytes) -> Path:
    suffix = Path(filename).suffix.lower()
    stem = Path(filename).stem or 'file'
    safe_stem = re.sub(r'[^\w.-]', '_', stem).strip('._') or 'file'
    safe_stem = safe_stem[:120]
    today = date.today()
    day_dir = (
        Path(settings.upload_dir)
        / 'detection_documents'
        / str(today.year)
        / f'{today.month:02d}'
        / f'{today.day:02d}'
    )
    day_dir.mkdir(parents=True, exist_ok=True)
    target = day_dir / f'{uuid.uuid4().hex}_{safe_stem}{suffix}'
    target.write_bytes(content)
    return target


def _split_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = re.sub(r'\s+', ' ', raw).strip()
        if line:
            lines.append(line)
    return lines


def _parse_decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(raw.strip())
    except (InvalidOperation, AttributeError):
        return None


def _parse_report_number(raw: str | None) -> tuple[Decimal | None, bool, list[str]]:
    text = (raw or '').strip()
    if not text or text in {'/', '-', '—'}:
        return None, False, []
    warnings: list[str] = []
    is_below_detection_limit = False
    if text.startswith('<'):
        is_below_detection_limit = True
        text = text[1:].strip()
    scientific_match = re.search(
        r'(?P<base>-?\d+(?:\.\d+)?)\s*(?:[×xX*]\s*10|[eE])\s*\^?\s*(?P<exponent>[+-]?\d+)',
        text,
    )
    if scientific_match:
        base = _parse_decimal(scientific_match.group('base'))
        exponent = int(scientific_match.group('exponent'))
        if base is not None:
            return base * (Decimal(10) ** exponent), is_below_detection_limit, warnings
    match = re.search(r'-?\d+(?:\.\d+)?', text)
    if not match:
        return None, is_below_detection_limit, warnings
    return _parse_decimal(match.group(0)), is_below_detection_limit, warnings


def _correct_noise_by_background(measured: Decimal, background: Decimal) -> tuple[Decimal | None, str]:
    difference = measured - background
    if difference < Decimal('3'):
        return None, '测量噪声与背景噪声差值小于 3dB(A)，需按规范人工复核修正'
    if difference >= Decimal('10'):
        return measured, '背景噪声低于测量噪声 10dB(A) 以上，检测值无需修正'
    measured_energy = Decimal(10) ** (measured / Decimal(10))
    background_energy = Decimal(10) ** (background / Decimal(10))
    corrected_energy = measured_energy - background_energy
    if corrected_energy <= 0:
        return None, '背景噪声修正后能量值无效，需人工复核'
    corrected = Decimal(10) * corrected_energy.log10()
    return corrected.quantize(Decimal('0.1')), f'已按背景噪声 {background}dB(A) 修正'


def _parse_hours(raw: str | None) -> Decimal | None:
    text = (raw or '').strip()
    if not text or text in {'/', '-', '—'}:
        return None
    match = re.search(r'\d+(?:\.\d+)?', text)
    return _parse_decimal(match.group(0)) if match else None


def _hours_to_minutes(hours: Decimal | None) -> Decimal | None:
    return hours * Decimal('60') if hours is not None else None


def _clean_indicator(raw: str) -> str:
    return raw.strip().rstrip('#').strip()


def _roman_level(raw: str) -> str | None:
    text = (raw or '').strip().upper()
    mapping = {
        'Ⅰ': 'I',
        'Ⅱ': 'II',
        'Ⅲ': 'III',
        'Ⅳ': 'IV',
        'I': 'I',
        'II': 'II',
        'III': 'III',
        'IV': 'IV',
    }
    return mapping.get(text)


def _find_header_index(header_rows: list[list[str]], *needles: str) -> int | None:
    compact_needles = [_compact_text(needle) for needle in needles]
    for row in header_rows:
        for idx, cell in enumerate(row):
            compact_cell = _compact_text(cell)
            if all(needle in compact_cell for needle in compact_needles):
                return idx
    return None


def _compact_text(raw: str) -> str:
    return re.sub(r'\s+', '', raw or '')


def _normalize_table_cell(raw: object) -> str:
    text = '' if raw is None else str(raw)
    return re.sub(r'\s+', ' ', text).strip()


def _row_has_any(row: list[str], *needles: str) -> bool:
    joined = _compact_text(' '.join(row))
    return any(_compact_text(needle) in joined for needle in needles)


def _is_empty_or_placeholder(raw: str | None) -> bool:
    text = (raw or '').strip()
    return not text or text in {'/', '-', '—'}


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ''
    return row[idx].strip()


def _table_raw_text(row: list[str]) -> str:
    return ' | '.join(cell for cell in row if cell).strip()


def _docx_tables(path: Path) -> list[list[list[str]]]:
    try:
        with ZipFile(path) as archive:
            xml_bytes = archive.read('word/document.xml')
    except (FileNotFoundError, KeyError, BadZipFile):
        return []
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return []

    tables: list[list[list[str]]] = []
    for table in root.findall('.//w:tbl', _WORD_NAMESPACE):
        rows: list[list[str]] = []
        for tr in table.findall('./w:tr', _WORD_NAMESPACE):
            cells: list[str] = []
            for tc in tr.findall('./w:tc', _WORD_NAMESPACE):
                texts = [node.text for node in tc.findall('.//w:t', _WORD_NAMESPACE) if node.text]
                cells.append(_normalize_table_cell(''.join(texts)))
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def _pdf_tables(path: Path) -> tuple[list[list[list[str]]], list[str]]:
    try:
        import pdfplumber
    except ImportError:
        return [], ['PDF 表格解析需要安装 pdfplumber；当前已回退到文本层识别']

    tables: list[list[list[str]]] = []
    warnings: list[str] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                try:
                    page_tables = page.extract_tables(table_settings=_PDF_TABLE_SETTINGS) or []
                except Exception as exc:
                    warnings.append(f'PDF 第 {page_number} 页表格抽取失败，已跳过该页：{exc}')
                    continue
                for raw_table in page_tables:
                    rows: list[list[str]] = []
                    for raw_row in raw_table:
                        cells = [_normalize_table_cell(cell) for cell in raw_row]
                        if any(cells):
                            rows.append(cells)
                    if rows:
                        tables.append(rows)
    except Exception as exc:
        return [], [f'PDF 表格解析失败，已回退到文本层识别：{exc}']
    return tables, warnings


def _parse_chemical_table(
    table: list[list[str]],
    *,
    start_index: int,
) -> tuple[list[ParsedDetectionRow], int]:
    header_rows = table[:2]
    value_idx = _find_header_index(header_rows, 'CTWA')
    if value_idx is None:
        value_idx = _find_header_index(header_rows, '检测值')
    if value_idx is None:
        value_idx = 4

    rows: list[ParsedDetectionRow] = []
    current_workplace = ''
    current_point = ''
    next_index = start_index
    for source_row in table[2:]:
        if len(source_row) < 5:
            continue
        current_workplace = source_row[0].strip() or current_workplace
        current_point = source_row[1].strip() or current_point
        indicator = _clean_indicator(source_row[2]) if len(source_row) > 2 else ''
        if not indicator or indicator in {'职业病危害因素名称', '危害因素'}:
            continue
        value, is_below_detection_limit, row_warnings = _parse_report_number(_cell(source_row, value_idx))
        if value is None:
            value, is_below_detection_limit, row_warnings = _parse_report_number(_cell(source_row, 4))
        contact_hours = _parse_hours(_cell(source_row, 3))
        if contact_hours is None:
            row_warnings.append('接触时间为空，入库前请人工确认')
        raw_text = _table_raw_text(source_row)
        rows.append(
            ParsedDetectionRow(
                row_index=next_index,
                sample_point=current_point or current_workplace or '未识别检测点',
                workplace=current_workplace or None,
                post_name=current_point or None,
                indicator_name=indicator,
                raw_value=value,
                raw_unit='mg/m3',
                medium=SampleMedium.WORKPLACE_AIR,
                duration_minutes=_hours_to_minutes(contact_hours),
                shift_hours=contact_hours,
                raw_text=raw_text[:500],
                confidence=Decimal('0.88') if value is not None else Decimal('0.70'),
                is_below_detection_limit=is_below_detection_limit,
                measurement_kind='chemical',
                warnings=row_warnings,
            )
        )
        next_index += 1
    return rows, next_index


def _parse_noise_table(
    table: list[list[str]],
    *,
    start_index: int,
) -> tuple[list[ParsedDetectionRow], int]:
    header_rows = table[:2]
    value_idx = _find_header_index(header_rows, '8h等效声级')
    fallback_idx = _find_header_index(header_rows, '检测值') or 4
    rows: list[ParsedDetectionRow] = []
    current_workplace = ''
    current_point = ''
    next_index = start_index
    previous_measurement: ParsedDetectionRow | None = None
    for source_row in table[2:]:
        if len(source_row) < 5:
            continue
        current_workplace = source_row[0].strip() or current_workplace
        current_point = source_row[1].strip() or current_point
        indicator = _clean_indicator(source_row[2]) if len(source_row) > 2 else ''
        if indicator != '噪声':
            continue
        value, is_below_detection_limit, row_warnings = _parse_report_number(_cell(source_row, value_idx))
        if value is None:
            value, is_below_detection_limit, row_warnings = _parse_report_number(_cell(source_row, fallback_idx))
        contact_hours = _parse_hours(_cell(source_row, 3))
        is_background = contact_hours is None or '背景' in current_point
        if contact_hours is None:
            row_warnings.append('接触时间为空，可能是背景噪声或辅助行，入库前请确认')
        row = ParsedDetectionRow(
            row_index=next_index,
            sample_point=current_point or current_workplace or '未识别检测点',
            workplace=current_workplace or None,
            post_name=current_point or None,
            indicator_name='噪声',
            raw_value=value,
            raw_unit='dB(A)',
            medium=SampleMedium.NOISE,
            shift_hours=contact_hours,
            raw_text=_table_raw_text(source_row)[:500],
            confidence=Decimal('0.90') if value is not None else Decimal('0.70'),
            is_below_detection_limit=is_below_detection_limit,
            is_background=is_background,
            measurement_kind='noise',
            warnings=row_warnings,
        )
        if is_background and previous_measurement and previous_measurement.raw_value is not None and value is not None:
            corrected_value, correction_warning = _correct_noise_by_background(previous_measurement.raw_value, value)
            if corrected_value is not None:
                previous_measurement.raw_value = corrected_value
            previous_measurement.warnings.append(correction_warning)
        if not is_background:
            previous_measurement = row
        rows.append(row)
        next_index += 1
    return rows, next_index


def _parse_heat_table(
    table: list[list[str]],
    *,
    start_index: int,
) -> tuple[list[ParsedDetectionRow], int]:
    rows: list[ParsedDetectionRow] = []
    current_workplace = ''
    current_point = ''
    next_index = start_index
    for source_row in table[2:]:
        if len(source_row) < 6:
            continue
        current_workplace = source_row[0].strip() or current_workplace
        current_point = source_row[1].strip() or current_point
        contact_hours = _parse_hours(_cell(source_row, 2))
        contact_rate = _cell(source_row, 3).rstrip('%')
        workload_level = _roman_level(_cell(source_row, 4))
        value, is_below_detection_limit, row_warnings = _parse_report_number(_cell(source_row, 5))
        if value is None:
            continue
        if contact_hours is None:
            row_warnings.append('接触时间为空，入库前请人工确认')
        if workload_level and contact_rate:
            indicator = f'高温WBGT-{workload_level}级-{contact_rate}%'
        else:
            indicator = '高温WBGT'
            row_warnings.append('高温 WBGT 需人工确认劳动强度和接触时间率后再匹配精确限值')
        rows.append(
            ParsedDetectionRow(
                row_index=next_index,
                sample_point=current_point or current_workplace or '未识别检测点',
                workplace=current_workplace or None,
                post_name=current_point or None,
                indicator_name=indicator,
                raw_value=value,
                raw_unit='℃',
                medium=SampleMedium.HIGH_TEMPERATURE,
                shift_hours=contact_hours,
                raw_text=_table_raw_text(source_row)[:500],
                confidence=Decimal('0.92') if indicator != '高温WBGT' else Decimal('0.75'),
                is_below_detection_limit=is_below_detection_limit,
                measurement_kind='heat_wbgt',
                warnings=row_warnings,
            )
        )
        next_index += 1
    return rows, next_index


def _parse_laser_table(
    table: list[list[str]],
    *,
    start_index: int,
) -> tuple[list[ParsedDetectionRow], int]:
    rows: list[ParsedDetectionRow] = []
    next_index = start_index
    current_workplace = ''
    current_point = ''
    for source_row in table[2:]:
        if len(source_row) < 7:
            continue
        current_workplace = source_row[0].strip() or current_workplace
        current_point = source_row[1].strip() or current_point
        indicator = _clean_indicator(_cell(source_row, 3))
        if indicator != '激光辐射':
            continue
        contact_hours = _parse_hours(_cell(source_row, 4))
        exposure_value, is_below_exposure, exposure_warnings = _parse_report_number(_cell(source_row, 5))
        irradiance_value, is_below_irradiance, irradiance_warnings = _parse_report_number(_cell(source_row, 6))
        exposure_limit, _, _ = _parse_report_number(_cell(source_row, 7))
        irradiance_limit, _, _ = _parse_report_number(_cell(source_row, 8))
        raw_text = _table_raw_text(source_row)[:500]
        if exposure_value is not None:
            exposure_status, exposure_message = _prejudge_physical_report_limit(
                value=exposure_value,
                report_limit=exposure_limit,
                is_below_detection_limit=is_below_exposure,
                label='激光照射量',
            )
            rows.append(
                ParsedDetectionRow(
                    row_index=next_index,
                    sample_point=current_point or current_workplace or '未识别检测点',
                    workplace=current_workplace or None,
                    post_name=current_point or None,
                    indicator_name='激光辐射-8h照射量',
                    raw_value=exposure_value,
                    raw_unit='J/cm2',
                    medium=SampleMedium.PHYSICAL_FACTOR,
                    shift_hours=contact_hours,
                    raw_text=raw_text,
                    confidence=Decimal('0.82'),
                    is_below_detection_limit=is_below_exposure,
                    measurement_kind='laser_exposure',
                    limit_type=LimitType.INSTANT,
                    report_limit_value=exposure_limit,
                    report_limit_unit='J/cm2' if exposure_limit is not None else None,
                    preliminary_status=exposure_status,
                    preliminary_message=exposure_message,
                    warnings=exposure_warnings
                    + [
                        exposure_message
                        or '激光辐射限值依赖波长、照射部位和暴露条件；缺少报告内限值时需人工复核'
                    ],
                )
            )
            next_index += 1
        if irradiance_value is not None:
            irradiance_status, irradiance_message = _prejudge_physical_report_limit(
                value=irradiance_value,
                report_limit=irradiance_limit,
                is_below_detection_limit=is_below_irradiance,
                label='激光辐照度',
            )
            rows.append(
                ParsedDetectionRow(
                    row_index=next_index,
                    sample_point=current_point or current_workplace or '未识别检测点',
                    workplace=current_workplace or None,
                    post_name=current_point or None,
                    indicator_name='激光辐射-8h辐照度',
                    raw_value=irradiance_value,
                    raw_unit='W/cm2',
                    medium=SampleMedium.PHYSICAL_FACTOR,
                    shift_hours=contact_hours,
                    raw_text=raw_text,
                    confidence=Decimal('0.82'),
                    is_below_detection_limit=is_below_irradiance,
                    measurement_kind='laser_irradiance',
                    limit_type=LimitType.INSTANT,
                    report_limit_value=irradiance_limit,
                    report_limit_unit='W/cm2' if irradiance_limit is not None else None,
                    preliminary_status=irradiance_status,
                    preliminary_message=irradiance_message,
                    warnings=irradiance_warnings
                    + [
                        irradiance_message
                        or '激光辐射限值依赖波长、照射部位和暴露条件；缺少报告内限值时需人工复核'
                    ],
                )
            )
            next_index += 1
    return rows, next_index


def _parse_power_frequency_table(
    table: list[list[str]],
    *,
    start_index: int,
) -> tuple[list[ParsedDetectionRow], int]:
    rows: list[ParsedDetectionRow] = []
    next_index = start_index
    current_workplace = ''
    current_point = ''
    for source_row in table[2:]:
        if len(source_row) < 6:
            continue
        current_workplace = source_row[0].strip() or current_workplace
        current_point = source_row[1].strip() or current_point
        indicator = _clean_indicator(_cell(source_row, 2))
        if indicator != '工频电场':
            continue
        contact_hours = _parse_hours(_cell(source_row, 3))
        value, is_below_detection_limit, row_warnings = _parse_report_number(_cell(source_row, 5))
        if value is None:
            value, is_below_detection_limit, row_warnings = _parse_report_number(_cell(source_row, 4))
        report_limit, _, _ = _parse_report_number(_cell(source_row, 6))
        status, message = _prejudge_physical_report_limit(
            value=value,
            report_limit=report_limit,
            is_below_detection_limit=is_below_detection_limit,
            label='工频电场',
        )
        rows.append(
            ParsedDetectionRow(
                row_index=next_index,
                sample_point=current_point or current_workplace or '未识别检测点',
                workplace=current_workplace or None,
                post_name=current_point or None,
                indicator_name='工频电场',
                raw_value=value,
                raw_unit='kV/m',
                medium=SampleMedium.PHYSICAL_FACTOR,
                shift_hours=contact_hours,
                raw_text=_table_raw_text(source_row)[:500],
                confidence=Decimal('0.84') if value is not None else Decimal('0.65'),
                is_below_detection_limit=is_below_detection_limit,
                measurement_kind='power_frequency_electric_field',
                limit_type=LimitType.INSTANT,
                report_limit_value=report_limit,
                report_limit_unit='kV/m' if report_limit is not None else None,
                preliminary_status=status,
                preliminary_message=message,
                warnings=row_warnings + ([message] if message else []),
            )
        )
        next_index += 1
    return rows, next_index


def _parse_illumination_table(
    table: list[list[str]],
    *,
    start_index: int,
) -> tuple[list[ParsedDetectionRow], int]:
    rows: list[ParsedDetectionRow] = []
    next_index = start_index
    current_workplace = ''
    current_point = ''
    for source_row in table[2:]:
        if len(source_row) < 4:
            continue
        current_workplace = source_row[0].strip() or current_workplace
        current_point = source_row[1].strip() or current_point
        indicator = _clean_indicator(_cell(source_row, 2))
        if indicator != '照度':
            continue
        value, is_below_detection_limit, row_warnings = _parse_report_number(_cell(source_row, 3))
        report_limit, _, _ = _parse_report_number(_cell(source_row, 4))
        status, message = _prejudge_physical_report_limit(
            value=value,
            report_limit=report_limit,
            is_below_detection_limit=is_below_detection_limit,
            label='照度',
            limit_type=LimitType.RANGE,
        )
        rows.append(
            ParsedDetectionRow(
                row_index=next_index,
                sample_point=current_point or current_workplace or '未识别检测点',
                workplace=current_workplace or None,
                post_name=current_point or None,
                indicator_name='照度',
                raw_value=value,
                raw_unit='lx',
                medium=SampleMedium.PHYSICAL_FACTOR,
                raw_text=_table_raw_text(source_row)[:500],
                confidence=Decimal('0.86') if value is not None else Decimal('0.65'),
                is_below_detection_limit=is_below_detection_limit,
                measurement_kind='illumination',
                limit_type=LimitType.RANGE,
                report_limit_value=report_limit,
                report_limit_unit='lx' if report_limit is not None else None,
                preliminary_status=status,
                preliminary_message=message,
                warnings=row_warnings
                + [
                    message
                    or '照度限值依赖作业场所/作业面类型；缺少报告内限值时需人工复核'
                ],
            )
        )
        next_index += 1
    return rows, next_index


def _classify_chemical_column(header: str) -> LimitType | None:
    text = _compact_text(header).upper()
    if 'CTWA' in text or '时间加权' in header:
        return LimitType.PC_TWA
    if 'CSTE' in text or ('短时间' in header and '限值' not in header):
        return LimitType.PC_STEL
    if ('检测值' in header or '检测结果' in header) and ('MAC' in text or '最高' in header):
        return LimitType.MAC
    return None


def _classify_limit_header(header: str) -> LimitType | None:
    text = _compact_text(header).upper()
    if 'PC-TWA' in text or 'PCTWA' in text:
        return LimitType.PC_TWA
    if 'PC-STEL' in text or 'PCSTEL' in text:
        return LimitType.PC_STEL
    if 'MAC' in text or '最高容许' in header:
        return LimitType.MAC
    return None


def _infer_table_unit(header_text: str, fallback: str = 'mg/m3') -> str:
    if 'mg/m3' in header_text or 'mg/m^3' in header_text or 'mg/m³' in header_text:
        return 'mg/m3'
    if 'μg/m3' in header_text or 'µg/m3' in header_text or 'ug/m3' in header_text:
        return 'μg/m3'
    return fallback


def _header_candidates(table: list[list[str]]) -> list[tuple[int, list[str]]]:
    return [(idx, row) for idx, row in enumerate(table[:4]) if _row_has_any(row, '危害因素', '检测项目', '项目名称')]


def _find_named_column(header_rows: list[list[str]], *needles: str) -> int | None:
    return _find_header_index(header_rows, *needles)


def _report_limit_for_type(
    *,
    source_row: list[str],
    header_rows: list[list[str]],
    limit_type: LimitType | None,
) -> Decimal | None:
    if limit_type is not None:
        for row in header_rows:
            for idx, cell in enumerate(row):
                if _classify_limit_header(cell) == limit_type:
                    value, _, _ = _parse_report_number(_cell(source_row, idx))
                    if value is not None:
                        return value
    if limit_type is None:
        idx = _find_named_column(header_rows, '接触限值')
        if idx is None:
            idx = _find_named_column(header_rows, '限值')
        if idx is None:
            idx = _find_named_column(header_rows, '标准值')
    elif limit_type == LimitType.PC_TWA:
        idx = _find_named_column(header_rows, 'PC-TWA')
    elif limit_type == LimitType.PC_STEL:
        idx = _find_named_column(header_rows, 'PC-STEL')
    else:
        idx = _find_named_column(header_rows, 'MAC')
    value, _, _ = _parse_report_number(_cell(source_row, idx))
    return value


def _prejudge_by_report_limit(
    *,
    value: Decimal | None,
    report_limit: Decimal | None,
    is_below_detection_limit: bool,
    limit_type: LimitType | None,
) -> tuple[ComplianceStatus | None, str | None]:
    limit_label = limit_type.value if limit_type is not None else '报告内'
    if is_below_detection_limit and limit_type != LimitType.RANGE:
        return ComplianceStatus.COMPLIANT, '检测值低于检出限，报告内预判为合格'
    if value is None:
        return ComplianceStatus.INSUFFICIENT_DATA, '检测值缺失，无法报告内预判'
    if report_limit is None:
        return ComplianceStatus.NEEDS_REVIEW, f'未识别到 {limit_label} 限值，需入库后按法规限值库判定'
    if limit_type == LimitType.RANGE:
        if value < report_limit:
            return ComplianceStatus.EXCEEDED, f'检测值低于{limit_label}下限'
        return ComplianceStatus.COMPLIANT, f'检测值不低于{limit_label}下限'
    if value > report_limit:
        return ComplianceStatus.EXCEEDED, f'检测值超过{limit_label}限值'
    return ComplianceStatus.COMPLIANT, f'检测值未超过{limit_label}限值'


def _prejudge_physical_report_limit(
    *,
    value: Decimal | None,
    report_limit: Decimal | None,
    is_below_detection_limit: bool,
    label: str,
    limit_type: LimitType = LimitType.INSTANT,
) -> tuple[ComplianceStatus | None, str | None]:
    status, message = _prejudge_by_report_limit(
        value=value,
        report_limit=report_limit,
        is_below_detection_limit=is_below_detection_limit,
        limit_type=limit_type,
    )
    if message and report_limit is not None:
        message = message.replace(limit_type.value, label)
    return status, message


def _parse_generic_chemical_table(
    table: list[list[str]],
    *,
    start_index: int,
) -> tuple[list[ParsedDetectionRow], int]:
    header_candidates = _header_candidates(table)
    if not header_candidates:
        return [], start_index
    header_start = header_candidates[0][0]
    header_end = header_start + 1
    for idx in range(header_start + 1, min(header_start + 4, len(table))):
        row = table[idx]
        if _row_has_any(row, 'CTWA', 'CSTE', '检测值', '检测结果', 'PC-TWA', 'PC-STEL', 'MAC', '限值'):
            header_end = idx + 1
            continue
        break
    header_rows = table[header_start:header_end]
    header_text = ' '.join(' '.join(row) for row in header_rows)
    indicator_idx = _find_named_column(header_rows, '危害因素')
    if indicator_idx is None:
        indicator_idx = _find_named_column(header_rows, '检测项目')
    if indicator_idx is None:
        indicator_idx = _find_named_column(header_rows, '项目名称')
    if indicator_idx is None:
        return [], start_index
    point_idx = _find_named_column(header_rows, '岗位')
    if point_idx is None:
        point_idx = _find_named_column(header_rows, '作业点')
    if point_idx is None:
        point_idx = _find_named_column(header_rows, '检测点')
    workplace_idx = _find_named_column(header_rows, '单元')
    duration_idx = _find_named_column(header_rows, '接触时间')
    unit = _infer_table_unit(header_text)

    value_columns: list[tuple[int, LimitType | None, str]] = []
    for row in header_rows:
        for idx, cell in enumerate(row):
            limit_type = _classify_chemical_column(cell)
            if limit_type and not any(item[0] == idx and item[1] == limit_type for item in value_columns):
                value_columns.append((idx, limit_type, cell))
    if not value_columns:
        for row in header_rows:
            for idx, cell in enumerate(row):
                compact = _compact_text(cell)
                if '检测值' in compact or '检测结果' in compact or compact == '结果':
                    value_columns.append((idx, None, cell))
                    break
            if value_columns:
                break
    if not value_columns:
        return [], start_index

    rows: list[ParsedDetectionRow] = []
    current_workplace = ''
    current_point = ''
    next_index = start_index
    for source_row in table[header_start + len(header_rows) :]:
        if len(source_row) <= indicator_idx:
            continue
        current_workplace = _cell(source_row, workplace_idx) or current_workplace
        current_point = _cell(source_row, point_idx) or current_point
        indicator = _clean_indicator(_cell(source_row, indicator_idx))
        if not indicator or _row_has_any([indicator], '合计', '小计', '危害因素', '检测项目', '项目名称'):
            continue
        contact_hours = _parse_hours(_cell(source_row, duration_idx))
        # 短时间采样口径回填：≤15min 自动从 PC_TWA 修正为 PC_STEL
        def _effective_limit_type(raw_lt: LimitType | None, contact_hours: Decimal | None) -> LimitType | None:
            if contact_hours is not None and contact_hours <= Decimal('0.25') and raw_lt == LimitType.PC_TWA:
                return LimitType.PC_STEL
            return raw_lt

        for value_idx, limit_type, header in value_columns:
            raw_value_text = _cell(source_row, value_idx)
            if _is_empty_or_placeholder(raw_value_text):
                continue
            value, is_below_detection_limit, row_warnings = _parse_report_number(raw_value_text)
            report_limit = _report_limit_for_type(
                source_row=source_row,
                header_rows=header_rows,
                limit_type=limit_type,
            )
            status, message = _prejudge_by_report_limit(
                value=value,
                report_limit=report_limit,
                is_below_detection_limit=is_below_detection_limit,
                limit_type=_effective_limit_type(limit_type, contact_hours),
            )
            if contact_hours is None:
                row_warnings.append('接触时间为空，入库前请人工确认')
            if message:
                row_warnings.append(message)
            effective_lt = _effective_limit_type(limit_type, contact_hours)
            if effective_lt != limit_type:
                row_warnings.append(
                    f'采样时长≤15min，限值类型从表头”{header}”({limit_type.value})自动修正为 {effective_lt.value}'
                )
            rows.append(
                ParsedDetectionRow(
                    row_index=next_index,
                    sample_point=current_point or current_workplace or '未识别检测点',
                    workplace=current_workplace or None,
                    post_name=current_point or None,
                    indicator_name=indicator,
                    raw_value=value,
                    raw_unit=unit,
                    medium=SampleMedium.WORKPLACE_AIR,
                    duration_minutes=_hours_to_minutes(contact_hours),
                    shift_hours=contact_hours,
                    raw_text=_table_raw_text(source_row)[:500],
                    confidence=Decimal('0.74') if status != ComplianceStatus.NEEDS_REVIEW else Decimal('0.66'),
                    is_below_detection_limit=is_below_detection_limit,
                    measurement_kind=(
                        f'generic_chemical_{effective_lt.value.lower()}'
                        if effective_lt is not None
                        else 'generic_chemical_report_limit'
                    ),
                    limit_type=effective_lt,
                    report_limit_value=report_limit,
                    report_limit_unit=unit if report_limit is not None else None,
                    preliminary_status=status,
                    preliminary_message=message,
                    warnings=row_warnings
                    + [
                        f'按表头”{header}”映射法规限值类型 {effective_lt.value}'
                        if effective_lt is not None
                        else f'按表头”{header}”使用报告内限值预判，入库后需匹配法规限值类型'
                    ],
                )
            )
            next_index += 1
    return rows, next_index


def parse_detection_tables(tables: list[list[list[str]]]) -> list[ParsedDetectionRow]:
    rows: list[ParsedDetectionRow] = []
    next_index = 1
    for table in tables:
        joined_header = _compact_text(' '.join(' '.join(row) for row in table[:3]))
        parsed: list[ParsedDetectionRow] = []
        if 'WBGT均值' in joined_header and 'WBGT限值' in joined_header:
            parsed, next_index = _parse_heat_table(table, start_index=next_index)
        elif '检测结果dB' in joined_header and '8h等效声级' in joined_header:
            parsed, next_index = _parse_noise_table(table, start_index=next_index)
        elif '危害因素' in joined_header and ('8h照射量' in joined_header or '8h辐照度' in joined_header):
            parsed, next_index = _parse_laser_table(table, start_index=next_index)
        elif '检测项目' in joined_header and 'kV/m' in joined_header and '接触限值' in joined_header:
            parsed, next_index = _parse_power_frequency_table(table, start_index=next_index)
        elif '检测项目' in joined_header and '检测结果' in joined_header and 'lx' in joined_header:
            parsed, next_index = _parse_illumination_table(table, start_index=next_index)
        elif '职业病危害因素名称' in joined_header and '检测结果及测试限值' in joined_header:
            parsed, next_index = _parse_chemical_table(table, start_index=next_index)
        elif (
            ('危害因素' in joined_header or '检测项目' in joined_header or '项目名称' in joined_header)
            and (
                'CTWA' in joined_header.upper()
                or 'CSTE' in joined_header.upper()
                or 'PC-TWA' in joined_header.upper()
                or 'PC-STEL' in joined_header.upper()
                or 'MAC' in joined_header.upper()
                or '检测值' in joined_header
                or '检测结果' in joined_header
            )
        ):
            parsed, next_index = _parse_generic_chemical_table(table, start_index=next_index)
        rows.extend(parsed)
    return rows


def parse_detection_docx_tables(path: str | Path) -> list[ParsedDetectionRow]:
    return parse_detection_tables(_docx_tables(Path(path)))


def parse_detection_pdf_tables(path: str | Path) -> tuple[list[ParsedDetectionRow], list[str]]:
    tables, warnings = _pdf_tables(Path(path))
    return parse_detection_tables(tables), warnings


def _infer_medium(line: str, report_type: ReportType) -> SampleMedium:
    upper = line.upper()
    if '噪声' in line or 'DB(A)' in upper or 'DBA' in upper:
        return SampleMedium.NOISE
    if '高温' in line or 'WBGT' in upper:
        return SampleMedium.HIGH_TEMPERATURE
    if '废水' in line or '污水' in line:
        return SampleMedium.WASTEWATER
    if '废气' in line:
        return SampleMedium.EXHAUST_GAS
    return _default_medium(report_type)


def _infer_indicator(line: str, unit: str | None, medium: SampleMedium) -> str | None:
    for item in _INDICATOR_HINTS:
        if item.lower() in line.lower():
            if item == 'WBGT':
                return '高温WBGT'
            return item
    if medium == SampleMedium.NOISE:
        return '噪声'
    if medium == SampleMedium.HIGH_TEMPERATURE:
        return '高温WBGT'
    if unit and normalize_unit(unit) == 'pH':
        return 'pH'
    return None


def _infer_sample_point(line: str, indicator_name: str) -> str:
    before_indicator = line.split(indicator_name, 1)[0].strip(' ：:，,;；|-')
    if before_indicator:
        tokens = re.split(r'\s+', before_indicator)
        if tokens:
            return tokens[-1][-80:]
    return '未识别检测点'


def _extract_duration_minutes(line: str) -> Decimal | None:
    match = re.search(r'(?P<num>\d+(?:\.\d+)?)\s*(?:min|分钟)', line, re.IGNORECASE)
    return _parse_decimal(match.group('num')) if match else None


def _extract_shift_hours(line: str) -> Decimal | None:
    match = re.search(r'(?P<num>\d+(?:\.\d+)?)\s*(?:h|小时)', line, re.IGNORECASE)
    return _parse_decimal(match.group('num')) if match else None


def parse_detection_text(text: str, *, report_type: ReportType) -> tuple[list[ParsedDetectionRow], list[str]]:
    rows: list[ParsedDetectionRow] = []
    warnings: list[str] = []
    seen: set[tuple[str, str, Decimal | None, str | None, str]] = set()

    for line_no, line in enumerate(_split_lines(text), start=1):
        match = _VALUE_UNIT_RE.search(line)
        if not match:
            continue
        unit = normalize_unit(match.group('unit')) or match.group('unit')
        value = _parse_decimal(match.group('number'))
        is_below_detection_limit = bool(match.group('value'))
        medium = _infer_medium(line, report_type)
        indicator_name = _infer_indicator(line, unit, medium)
        if not indicator_name:
            continue

        row_warnings: list[str] = []
        if indicator_name == '高温WBGT' and medium == SampleMedium.HIGH_TEMPERATURE:
            row_warnings.append('高温 WBGT 需人工确认劳动强度和接触时间率后再匹配精确限值')

        sample_point = _infer_sample_point(line, indicator_name)
        cas_match = _CAS_RE.search(line)
        key = (sample_point, indicator_name, value, unit, line)
        if key in seen:
            continue
        seen.add(key)

        confidence = Decimal('0.75')
        if sample_point == '未识别检测点':
            confidence -= Decimal('0.15')
        if row_warnings:
            confidence -= Decimal('0.10')

        rows.append(
            ParsedDetectionRow(
                row_index=line_no,
                sample_point=sample_point,
                indicator_name=indicator_name,
                raw_value=value,
                raw_unit=unit,
                medium=medium,
                duration_minutes=_extract_duration_minutes(line),
                shift_hours=_extract_shift_hours(line),
                cas_no=cas_match.group(0) if cas_match else None,
                raw_text=line[:500],
                confidence=confidence,
                is_below_detection_limit=is_below_detection_limit,
                warnings=row_warnings,
            )
        )

    if not rows:
        warnings.append('未识别到检测结果行；可上传文本层 PDF/DOCX，或等待人工模板适配')
    return rows, warnings


def _measurement_indicator_for_storage(row: ParsedDetectionRow) -> str:
    if row.measurement_kind in {'laser_exposure', 'laser_irradiance'}:
        return '激光辐射'
    return row.indicator_name


def _measurement_method_code(row: ParsedDetectionRow) -> str | None:
    if row.limit_type is None and not row.measurement_kind:
        return None
    parts = []
    if row.measurement_kind:
        parts.append(row.measurement_kind)
    if row.limit_type:
        parts.append(f'limit_type={row.limit_type.value}')
    return ';'.join(parts)


def _row_to_sample(report_id: str, row: ParsedDetectionRow) -> DetectionSample:
    return DetectionSample(
        report_id=report_id,
        sample_point=row.sample_point or '未识别检测点',
        workplace=row.workplace,
        post_name=row.post_name,
        medium=_row_medium(row),
        duration_minutes=row.duration_minutes,
        shift_hours=row.shift_hours,
        raw_payload_json=None,
        measurements=[
            DetectionMeasurement(
                indicator_name=_measurement_indicator_for_storage(row),
                indicator_alias=row.indicator_name
                if row.indicator_name != _measurement_indicator_for_storage(row)
                else None,
                cas_no=row.cas_no,
                raw_value=row.raw_value,
                raw_unit=row.raw_unit,
                normalized_value=row.raw_value,
                normalized_unit=normalize_unit(row.raw_unit),
                detect_limit=row.raw_value if row.is_below_detection_limit else None,
                source_limit_value=row.report_limit_value,
                source_limit_unit=row.report_limit_unit,
                source_limit_type=row.limit_type,
                method_code=_measurement_method_code(row),
                raw_text=row.raw_text[:255] if row.raw_text else None,
            )
        ],
    )


class DetectionDocumentParseService:
    @staticmethod
    def preview(
        *,
        filename: str | None,
        content: bytes,
        report_type: str | ReportType,
    ) -> DetectionDocumentPreview:
        if len(content) > settings.max_upload_bytes:
            raise EHSException(
                'Upload file is too large',
                code='FILE_TOO_LARGE',
                status_code=413,
                details={'max_upload_bytes': settings.max_upload_bytes},
            )
        parsed_type = _validate_report_type(report_type)
        display_name = _validate_filename(filename)
        path = _store_document(display_name, content)
        # ZIP 压缩包：逐文件解析后合并
        if path.suffix.lower() == '.zip':
            return DetectionDocumentParseService._preview_zip(
                path=path,
                display_name=display_name,
                parsed_type=parsed_type,
            )
        # 单文件解析
        rows, warnings, text = DetectionDocumentParseService._preview_single_file(
            path=path,
            parsed_type=parsed_type,
        )
        return DetectionDocumentPreview(
            filename=display_name,
            report_type=parsed_type,
            text_char_count=len(text),
            text_excerpt=text[:_MAX_PREVIEW_TEXT_CHARS],
            rows=rows,
            warnings=warnings,
        )

    @staticmethod
    def _preview_single_file(
        *,
        path: Path,
        parsed_type: ReportType,
    ) -> tuple[list[ParsedDetectionRow], list[str], str]:
        """解析单个文件，返回 (rows, warnings, text)。"""
        extract_warnings: list[str] = []
        try:
            text = extract_text_from_document_file(path, max_chars=_MAX_PARSE_TEXT_CHARS)
        except DocumentTextExtractError as exc:
            text = '[文件文本抽取失败]'
            extract_warnings.append(
                f'文本抽取失败：{exc}；请确认文件是否为扫描件（可启用 OCR），或改为人工录入'
            )

        rows, warnings = parse_detection_text(text, report_type=parsed_type)
        warnings = [*extract_warnings, *warnings]
        if path.suffix.lower() == '.docx':
            table_rows = parse_detection_docx_tables(path)
            if table_rows:
                rows = table_rows
                warnings = [
                    '已按 DOCX 表格结构解析；请在入库前人工核对检测点、因子、单位和数值'
                ]
        elif path.suffix.lower() == '.pdf':
            table_rows, table_warnings = parse_detection_pdf_tables(path)
            warnings.extend(table_warnings)
            if table_rows:
                rows = table_rows
                warnings = [
                    '已按 PDF 表格结构解析；请在入库前人工核对检测点、因子、单位和数值',
                    *table_warnings,
                ]
        if not text.strip():
            warnings.append('文件未抽取到可用文本；如为扫描 PDF，需要开启 OCR 或先转为文本层 PDF')
        # 4.4 异常报告兜底：有文本但未识别到检测行时，生成 NEEDS_REVIEW 占位行
        if not rows and text.strip():
            rows = [
                ParsedDetectionRow(
                    row_index=1,
                    sample_point='待人工确认',
                    indicator_name='待人工确认',
                    raw_value=None,
                    raw_unit=None,
                    medium=_default_medium(parsed_type),
                    raw_text=text[:_MAX_PREVIEW_TEXT_CHARS][:500],
                    confidence=Decimal('0.30'),
                    measurement_kind='needs_review',
                    preliminary_status=ComplianceStatus.NEEDS_REVIEW,
                    preliminary_message='未识别到结构化检测行，请在人工确认页录入检测点/因子/数值/单位后入库',
                    warnings=['未识别到结构化检测行，请人工录入字段后入库；必要时标注为背景行并取消勾选'],
                )
            ]
            warnings.append('未识别到检测结果行，已生成待人工确认占位行')
        return rows, warnings, text

    @staticmethod
    def _preview_zip(
        *,
        path: Path,
        display_name: str,
        parsed_type: ReportType,
    ) -> DetectionDocumentPreview:
        """解压 ZIP，逐个解析支持的文件，合并结果并标记 source_file。"""
        import tempfile

        try:
            zf = ZipFile(path, 'r')
            entries = [e for e in zf.infolist() if not e.is_dir()]
            zf.close()
        except BadZipFile as exc:
            raise EHSException(
                'ZIP 文件损坏或不是有效的 ZIP 压缩包',
                code='DETECTION_INVALID_ZIP',
                status_code=400,
            ) from exc

        if not entries:
            raise EHSException(
                'ZIP 压缩包为空',
                code='DETECTION_EMPTY_ZIP',
                status_code=400,
            )

        supported_entries = [
            e for e in entries
            if Path(e.filename).suffix.lower() in _ALLOWED_DOCUMENT_EXTENSIONS
            and Path(e.filename).suffix.lower() != '.zip'
        ]

        if not supported_entries:
            raise EHSException(
                f'ZIP 中未找到支持的文件格式（支持：.pdf .docx .doc .txt），'
                f'共 {len(entries)} 个文件',
                code='DETECTION_ZIP_NO_SUPPORTED_FILES',
                status_code=400,
            )

        all_rows: list[ParsedDetectionRow] = []
        all_warnings: list[str] = []
        source_files: list[str] = []
        total_chars = 0
        text_excerpt_parts: list[str] = []
        row_offset = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            zf = ZipFile(path, 'r')
            for entry in supported_entries:
                entry_name = Path(entry.filename).name
                source_files.append(entry_name)
                zf.extract(entry, tmpdir)
                entry_path = Path(tmpdir) / entry.filename
                rows, warnings, text = DetectionDocumentParseService._preview_single_file(
                    path=entry_path,
                    parsed_type=parsed_type,
                )
                # 标记来源文件并调整行索引
                for r in rows:
                    r.source_file = entry_name
                    r.row_index += row_offset
                row_offset += len(rows)
                all_rows.extend(rows)
                all_warnings.extend(
                    [f'[{entry_name}] {w}' for w in warnings]
                )
                total_chars += len(text)
                if len(text_excerpt_parts) < 3 and text.strip():
                    excerpt = text[:300].strip()
                    text_excerpt_parts.append(f'[{entry_name}] {excerpt}')
            zf.close()

        if not all_rows:
            all_warnings.insert(0, 'ZIP 内所有文件均未识别到检测行，请人工核对文件内容')

        return DetectionDocumentPreview(
            filename=display_name,
            report_type=parsed_type,
            text_char_count=total_chars,
            text_excerpt=' ... '.join(text_excerpt_parts)[:_MAX_PREVIEW_TEXT_CHARS],
            rows=all_rows,
            source_files=source_files,
            warnings=all_warnings,
        )

    @staticmethod
    def import_preview(
        *,
        db: Session,
        actor: CurrentUser,
        payload: DetectionDocumentImportRequest,
    ) -> DetectionReportCreateResponse:
        organization_id = payload.organization_id or actor.organization_id or settings.default_organization_id
        ensure_client_org_id_allowed(actor, requested_organization_id=organization_id)
        if not is_uuid(organization_id):
            raise EHSException(
                'organization_id must be a valid UUID',
                code='INVALID_ORGANIZATION_ID',
                status_code=400,
            )
        organization = OrganizationDAO(db).get_by_id(organization_id)
        if organization is None:
            raise EHSException('Organization not found', code='ORG_NOT_FOUND', status_code=404)
        if not payload.rows:
            raise EHSException(
                'No parsed rows to import',
                code='DETECTION_DOCUMENT_IMPORT_EMPTY',
                status_code=400,
            )

        display_name = _validate_filename(payload.filename)
        parsed_type = _validate_report_type(payload.report_type)
        cleaned_service_type = clean_detection_service_type(payload.service_type)
        business_name = _clean_display_name(payload.report_name) or _default_report_name(
            organization.name,
            parsed_type,
            cleaned_service_type,
        )
        report_dao = DetectionReportDAO(db)
        report = report_dao.create_report(
            organization_id=organization_id,
            filename=display_name,
            report_name=business_name,
            client_name=_clean_display_name(payload.client_name),
            project_name=_clean_display_name(payload.project_name),
            project_code=_clean_display_name(payload.project_code)[:64]
            if _clean_display_name(payload.project_code)
            else None,
            service_type=cleaned_service_type,
            report_type=parsed_type,
            file_path=None,
            created_by_id=actor.account_id,
        )
        try:
            parsed_rows = [
                ParsedDetectionRow(
                    row_index=row.row_index,
                    sample_point=row.sample_point,
                    workplace=row.workplace,
                    post_name=row.post_name,
                    medium=row.medium,
                    indicator_name=row.indicator_name,
                    cas_no=row.cas_no,
                    raw_value=row.raw_value,
                    raw_unit=row.raw_unit,
                    duration_minutes=row.duration_minutes,
                    shift_hours=row.shift_hours,
                    raw_text=row.raw_text,
                    confidence=row.confidence,
                    is_below_detection_limit=row.is_below_detection_limit,
                    is_background=row.is_background,
                    measurement_kind=row.measurement_kind,
                    limit_type=row.limit_type,
                    report_limit_value=row.report_limit_value,
                    report_limit_unit=row.report_limit_unit,
                    preliminary_status=row.preliminary_status,
                    preliminary_message=row.preliminary_message,
                    warnings=row.warnings,
                )
                for row in payload.rows
                if not row.is_background and row.raw_value is not None
            ]
            if not parsed_rows:
                raise EHSException(
                    'No importable parsed rows remain after filtering background or empty rows',
                    code='DETECTION_DOCUMENT_IMPORT_EMPTY',
                    status_code=400,
                )
            samples = [_row_to_sample(report.id, row) for row in parsed_rows]
            db.add_all(samples)
            db.commit()
            report = report_dao.update_status(report_id=report.id, status=ReportStatus.PARSED) or report
            return DetectionReportCreateResponse(
                report_id=report.id,
                report_name=report.report_name,
                client_name=report.client_name,
                project_name=report.project_name,
                project_code=report.project_code,
                service_type=report.service_type,
                status=report.status,
                report_type=report.report_type,
                sample_count=len(samples),
                measurement_count=len(samples),
                warnings=[
                    '已从解析预览确认入库；请运行合规判定并复核低置信度或需复核项目',
                    *payload.warnings,
                ],
            )
        except EHSException as exc:
            db.rollback()
            report_dao.update_status(
                report_id=report.id,
                status=ReportStatus.FAILED,
                error_message=exc.message,
            )
            raise
        except Exception as exc:
            db.rollback()
            report_dao.update_status(
                report_id=report.id,
                status=ReportStatus.FAILED,
                error_message=str(exc),
            )
            raise
