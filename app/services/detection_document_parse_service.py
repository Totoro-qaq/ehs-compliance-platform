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
        medium = _infer_medium(line, report_type)
        indicator_name = _infer_indicator(line, unit, medium)
        if not indicator_name:
            continue

        row_warnings: list[str] = []
        if match.group('value'):
            row_warnings.append('检测值为低于检出限写法，预览按数值部分展示')
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
