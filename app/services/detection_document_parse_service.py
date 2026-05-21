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

from app.core.config import settings
from app.core.exceptions import EHSException
from app.models.db_models import ReportType, SampleMedium
from app.services.detection_calculation_service import normalize_unit
from app.services.pdf_text_service import DocumentTextExtractError, extract_text_from_document_file

_ALLOWED_DOCUMENT_EXTENSIONS = frozenset({'.pdf', '.docx', '.doc', '.txt'})
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
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DetectionDocumentPreview:
    filename: str
    report_type: ReportType
    text_char_count: int
    text_excerpt: str
    rows: list[ParsedDetectionRow]
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
        raw_text = _table_raw_text(source_row)[:500]
        if exposure_value is not None:
            rows.append(
                ParsedDetectionRow(
                    row_index=next_index,
                    sample_point=current_point or current_workplace or '未识别检测点',
                    workplace=current_workplace or None,
                    post_name=current_point or None,
                    indicator_name='激光辐射-8h照射量',
                    raw_value=exposure_value,
                    raw_unit='J/cm2',
                    medium=None,
                    shift_hours=contact_hours,
                    raw_text=raw_text,
                    confidence=Decimal('0.82'),
                    is_below_detection_limit=is_below_exposure,
                    measurement_kind='laser_exposure',
                    warnings=exposure_warnings + ['物理因素预览项，暂未接入限值判定'],
                )
            )
            next_index += 1
        if irradiance_value is not None:
            rows.append(
                ParsedDetectionRow(
                    row_index=next_index,
                    sample_point=current_point or current_workplace or '未识别检测点',
                    workplace=current_workplace or None,
                    post_name=current_point or None,
                    indicator_name='激光辐射-8h辐照度',
                    raw_value=irradiance_value,
                    raw_unit='W/cm2',
                    medium=None,
                    shift_hours=contact_hours,
                    raw_text=raw_text,
                    confidence=Decimal('0.82'),
                    is_below_detection_limit=is_below_irradiance,
                    measurement_kind='laser_irradiance',
                    warnings=irradiance_warnings + ['物理因素预览项，暂未接入限值判定'],
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
        rows.append(
            ParsedDetectionRow(
                row_index=next_index,
                sample_point=current_point or current_workplace or '未识别检测点',
                workplace=current_workplace or None,
                post_name=current_point or None,
                indicator_name='工频电场',
                raw_value=value,
                raw_unit='kV/m',
                medium=None,
                shift_hours=contact_hours,
                raw_text=_table_raw_text(source_row)[:500],
                confidence=Decimal('0.84') if value is not None else Decimal('0.65'),
                is_below_detection_limit=is_below_detection_limit,
                measurement_kind='power_frequency_electric_field',
                warnings=row_warnings + ['物理因素预览项，暂未接入限值判定'],
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
        rows.append(
            ParsedDetectionRow(
                row_index=next_index,
                sample_point=current_point or current_workplace or '未识别检测点',
                workplace=current_workplace or None,
                post_name=current_point or None,
                indicator_name='照度',
                raw_value=value,
                raw_unit='lx',
                medium=None,
                raw_text=_table_raw_text(source_row)[:500],
                confidence=Decimal('0.86') if value is not None else Decimal('0.65'),
                is_below_detection_limit=is_below_detection_limit,
                measurement_kind='illumination',
                warnings=row_warnings + ['照度预览项，暂未接入测试限值判定'],
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
        try:
            text = extract_text_from_document_file(path, max_chars=_MAX_PARSE_TEXT_CHARS)
        except DocumentTextExtractError as exc:
            raise EHSException(
                f'Detection document text extraction failed: {exc}',
                code='DETECTION_DOCUMENT_TEXT_EXTRACT_FAILED',
                status_code=400,
            ) from exc

        rows, warnings = parse_detection_text(text, report_type=parsed_type)
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
        return DetectionDocumentPreview(
            filename=display_name,
            report_type=parsed_type,
            text_char_count=len(text),
            text_excerpt=text[:_MAX_PREVIEW_TEXT_CHARS],
            rows=rows,
            warnings=warnings,
        )
