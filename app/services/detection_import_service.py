"""Excel / CSV 检测数据导入。

第一层目标：以「职业卫生」为主，覆盖每行一条 检测点 + 检测因子 + 检测值 + 单位 的扁平表。
列名做了别名映射，最大限度兼容各检测机构常见模板。
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

from app.core.exceptions import EHSException
from app.models.db_models import DetectionMeasurement, DetectionSample, SampleMedium
from app.services.detection_calculation_service import normalize_unit

# 列名别名表：左侧为标准字段，右侧为常见列名（不区分大小写、忽略首尾空格）
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    'sample_point': ('检测点', '采样点', '采样位置', '检测位置', 'sample_point', 'point'),
    'workplace': ('车间', '工作场所', 'workplace', 'workshop'),
    'post_name': ('岗位', '工种', 'post', 'post_name'),
    'medium': ('介质', '类别', 'medium'),
    'sample_time_start': ('采样开始时间', '开始时间', 'start_time'),
    'sample_time_end': ('采样结束时间', '结束时间', 'end_time'),
    'duration_minutes': ('采样时长(分钟)', '采样时长', '采样时间(min)', '时长(分钟)', 'duration', 'duration_minutes'),
    'shift_hours': ('工时(小时)', '工时', '班次时长', 'shift_hours'),
    'indicator_name': ('检测因子', '检测项目', '项目', 'indicator', 'indicator_name'),
    'indicator_alias': ('因子别名', '别名', 'alias'),
    'cas_no': ('cas号', 'cas', 'cas_no'),
    'raw_value': ('检测值', '检测结果', '实测值', '结果', 'value', 'raw_value'),
    'raw_unit': ('单位', 'unit', 'raw_unit'),
    'detect_limit': ('检出限', '方法定量限', 'detect_limit'),
    'method_code': ('方法编号', '检测方法', 'method', 'method_code'),
}


@dataclass
class ImportRowError:
    row_index: int
    column: str | None
    message: str


@dataclass
class ImportResult:
    samples: list[DetectionSample] = field(default_factory=list)
    measurements: list[DetectionMeasurement] = field(default_factory=list)
    errors: list[ImportRowError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _build_column_map(columns: list[str]) -> dict[str, str]:
    """把上传文件的列头映射到标准字段名；多列匹配同一字段时取第一个。"""
    cleaned = {col: col.strip().lower() for col in columns}
    mapping: dict[str, str] = {}
    for std_field, aliases in _COLUMN_ALIASES.items():
        alias_set = {a.strip().lower() for a in aliases}
        for original, normalized in cleaned.items():
            if normalized in alias_set and std_field not in mapping:
                mapping[std_field] = original
                break
    return mapping


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {'nan', 'na', 'null', '-', '—'}:
            return None
        # 兼容「<0.001」「未检出」等检出限以下记法：返回 None，由调用方决定 fallback
        if text.startswith('<') or text in {'未检出', 'ND', 'nd'}:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_medium(raw: Any, fallback: SampleMedium) -> SampleMedium:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return fallback
    text = str(raw).strip().upper()
    if not text:
        return fallback
    direct = {m.value for m in SampleMedium}
    if text in direct:
        return SampleMedium(text)
    exact_map = {
        '工作场所空气': SampleMedium.WORKPLACE_AIR,
        '空气': SampleMedium.WORKPLACE_AIR,
        '废水': SampleMedium.WASTEWATER,
        '废气': SampleMedium.EXHAUST_GAS,
        '噪声': SampleMedium.NOISE,
        '高温': SampleMedium.HIGH_TEMPERATURE,
        '高温作业': SampleMedium.HIGH_TEMPERATURE,
        '高温 WBGT': SampleMedium.HIGH_TEMPERATURE,
        '高温WBGT': SampleMedium.HIGH_TEMPERATURE,
        '热应激': SampleMedium.HIGH_TEMPERATURE,
    }
    upper_map = {
        'WBGT': SampleMedium.HIGH_TEMPERATURE,
        'HEAT': SampleMedium.HIGH_TEMPERATURE,
        'HEAT_STRESS': SampleMedium.HIGH_TEMPERATURE,
    }
    original = str(raw).strip()
    return exact_map.get(original, upper_map.get(text, fallback))


def _read_dataframe(*, content: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()
    bio = io.BytesIO(content)
    if name.endswith('.csv'):
        # 兼容带 BOM 的 utf-8-sig，再退化到 gbk
        try:
            return pd.read_csv(bio, encoding='utf-8-sig')
        except UnicodeDecodeError:
            bio.seek(0)
            return pd.read_csv(bio, encoding='gbk')
    if name.endswith(('.xlsx', '.xlsm')):
        return pd.read_excel(bio, engine='openpyxl')
    if name.endswith('.xls'):
        # 旧版 xls 需 xlrd<2，本项目暂不强依赖；提示用户另存为 xlsx
        raise EHSException(
            '暂不支持 .xls 文件，请另存为 .xlsx 或 .csv 后再上传',
            code='DETECTION_UNSUPPORTED_FORMAT',
            status_code=400,
        )
    raise EHSException(
        f'不支持的文件格式: {filename}',
        code='DETECTION_UNSUPPORTED_FORMAT',
        status_code=400,
    )


class DetectionImportService:
    """无状态导入服务：解析文件 → 内存对象。落库由 Service 层串联事务。"""

    @staticmethod
    def parse(
        *,
        content: bytes,
        filename: str,
        report_id: str,
        default_medium: SampleMedium,
    ) -> ImportResult:
        result = ImportResult()
        try:
            df = _read_dataframe(content=content, filename=filename)
        except EHSException:
            raise
        except Exception as exc:
            raise EHSException(
                f'读取检测数据文件失败: {exc}',
                code='DETECTION_PARSE_FAILED',
                status_code=400,
            ) from exc

        if df.empty:
            result.warnings.append('文件中没有可读取的数据行')
            return result

        col_map = _build_column_map(list(df.columns))
        required = {'sample_point', 'indicator_name', 'raw_value'}
        missing = required - col_map.keys()
        if missing:
            raise EHSException(
                f'缺少必填列: {", ".join(sorted(missing))}',
                code='DETECTION_MISSING_COLUMNS',
                status_code=400,
                details={'expected': sorted(required), 'found': sorted(col_map.keys())},
            )

        # 同一 (sample_point, post_name, workplace) 复用同一个 sample 对象
        sample_index: dict[tuple[str, str, str, str], DetectionSample] = {}

        for idx, row in df.iterrows():
            row_no = int(idx) + 2  # 表头是第 1 行，数据从第 2 行开始

            sample_point_raw = row.get(col_map['sample_point'])
            indicator_raw = row.get(col_map['indicator_name'])
            value_raw = row.get(col_map['raw_value'])

            sample_point = str(sample_point_raw).strip() if pd.notna(sample_point_raw) else ''
            indicator_name = str(indicator_raw).strip() if pd.notna(indicator_raw) else ''
            if not sample_point:
                result.errors.append(ImportRowError(row_no, '检测点', '检测点不能为空'))
                continue
            if not indicator_name:
                result.errors.append(ImportRowError(row_no, '检测因子', '检测因子不能为空'))
                continue

            workplace = (
                str(row.get(col_map['workplace'])).strip()
                if 'workplace' in col_map and pd.notna(row.get(col_map['workplace']))
                else ''
            )
            post_name = (
                str(row.get(col_map['post_name'])).strip()
                if 'post_name' in col_map and pd.notna(row.get(col_map['post_name']))
                else ''
            )
            medium = _parse_medium(
                row.get(col_map['medium']) if 'medium' in col_map else None,
                default_medium,
            )
            key = (sample_point, post_name, workplace, medium.value)

            sample = sample_index.get(key)
            if sample is None:
                sample = DetectionSample(
                    report_id=report_id,
                    sample_point=sample_point,
                    workplace=workplace or None,
                    post_name=post_name or None,
                    medium=medium,
                    sample_time_start=_parse_datetime(
                        row.get(col_map['sample_time_start']) if 'sample_time_start' in col_map else None
                    ),
                    sample_time_end=_parse_datetime(
                        row.get(col_map['sample_time_end']) if 'sample_time_end' in col_map else None
                    ),
                    duration_minutes=_parse_decimal(
                        row.get(col_map['duration_minutes']) if 'duration_minutes' in col_map else None
                    ),
                    shift_hours=_parse_decimal(
                        row.get(col_map['shift_hours']) if 'shift_hours' in col_map else None
                    ),
                )
                sample_index[key] = sample
                result.samples.append(sample)

            raw_value = _parse_decimal(value_raw)
            raw_unit = (
                str(row.get(col_map['raw_unit'])).strip()
                if 'raw_unit' in col_map and pd.notna(row.get(col_map['raw_unit']))
                else None
            )
            measurement = DetectionMeasurement(
                sample=sample,
                indicator_name=indicator_name,
                indicator_alias=(
                    str(row.get(col_map['indicator_alias'])).strip()
                    if 'indicator_alias' in col_map
                    and pd.notna(row.get(col_map['indicator_alias']))
                    else None
                ),
                cas_no=(
                    str(row.get(col_map['cas_no'])).strip()
                    if 'cas_no' in col_map and pd.notna(row.get(col_map['cas_no']))
                    else None
                ),
                raw_value=raw_value,
                raw_unit=raw_unit,
                normalized_value=raw_value,
                normalized_unit=normalize_unit(raw_unit),
                detect_limit=_parse_decimal(
                    row.get(col_map['detect_limit']) if 'detect_limit' in col_map else None
                ),
                method_code=(
                    str(row.get(col_map['method_code'])).strip()
                    if 'method_code' in col_map and pd.notna(row.get(col_map['method_code']))
                    else None
                ),
                raw_text=str(value_raw).strip() if pd.notna(value_raw) else None,
            )
            if raw_value is None:
                # 检测值缺失：保留行但标记为需复核，由合规判定阶段处理 INSUFFICIENT_DATA
                result.warnings.append(
                    f'第 {row_no} 行检测值无法解析为数值，将标记为数据不足'
                )
            result.measurements.append(measurement)

        return result
