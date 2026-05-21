"""单位归一与计算管线。

职责：
1. 单位换算：mg/m3 ↔ mg/L、ppm ↔ mg/m3（理想气体 25℃ 101.325 kPa）等基础换算；
2. TWA / PC-TWA / PC-STEL 计算；
3. 噪声等效声级（基础 8 小时换算）。

数值统一使用 Decimal，避免 0.1 + 0.2 之类的浮点误判。
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Literal

# 限值判断对精度要求不高，但全程使用 Decimal 仍能避免 SQLite/MySQL 与 Python 浮点之间的舍入差异
getcontext().prec = 28


class UnitConversionError(ValueError):
    """单位换算失败时抛出，调用方应记录但不阻塞整体计算。"""


# ---------------------------------------------------------------------------
# 单位归一
# ---------------------------------------------------------------------------

# 标准空气状态：25℃ 101.325 kPa，气体摩尔体积 24.45 L/mol
_GAS_MOLAR_VOLUME_L = Decimal('24.45')

# 单位别名 → 标准化
_UNIT_ALIASES: dict[str, str] = {
    'mg/m3': 'mg/m3',
    'mg/m^3': 'mg/m3',
    'mg/m³': 'mg/m3',
    'mg per m3': 'mg/m3',
    'ug/m3': 'µg/m3',
    'μg/m3': 'µg/m3',
    'µg/m3': 'µg/m3',
    'ppm': 'ppm',
    'mg/l': 'mg/L',
    'mg/L': 'mg/L',
    'ug/l': 'µg/L',
    'μg/l': 'µg/L',
    'µg/l': 'µg/L',
    'db(a)': 'dB(A)',
    'dba': 'dB(A)',
    'db': 'dB(A)',
    'dB': 'dB(A)',
    'dB(A)': 'dB(A)',
    '℃': '℃',
    '°C': '℃',
    'c': '℃',
    'C': '℃',
    'celsius': '℃',
    'wbgt': '℃',
    'wbgt ℃': '℃',
    'wbgt℃': '℃',
    'wbgt °c': '℃',
    'wbgt°c': '℃',
    'wbgt(℃)': '℃',
    'wbgt(°c)': '℃',
    'wbgt（℃）': '℃',
    'wbgt（°c）': '℃',
    'pH': 'pH',
    'ph': 'pH',
}


def normalize_unit(raw_unit: str | None) -> str | None:
    """把常见的单位写法折叠到统一字符串，未知单位原样返回。"""
    if not raw_unit:
        return None
    key = raw_unit.strip()
    if not key:
        return None
    return _UNIT_ALIASES.get(key, _UNIT_ALIASES.get(key.lower(), key))


@dataclass(frozen=True, slots=True)
class ConversionResult:
    value: Decimal
    unit: str


def convert_value(
    value: Decimal,
    from_unit: str,
    to_unit: str,
    *,
    molecular_weight: Decimal | None = None,
) -> ConversionResult:
    """单位换算白名单。仅处理已确认无歧义的换算路径，其他抛 UnitConversionError。"""
    src = normalize_unit(from_unit)
    dst = normalize_unit(to_unit)
    if src is None or dst is None:
        raise UnitConversionError(f'未识别的单位: {from_unit!r} → {to_unit!r}')
    if src == dst:
        return ConversionResult(value=value, unit=dst)

    # µg ↔ mg
    if src == 'µg/m3' and dst == 'mg/m3':
        return ConversionResult(value=value / Decimal('1000'), unit=dst)
    if src == 'mg/m3' and dst == 'µg/m3':
        return ConversionResult(value=value * Decimal('1000'), unit=dst)
    if src == 'µg/L' and dst == 'mg/L':
        return ConversionResult(value=value / Decimal('1000'), unit=dst)
    if src == 'mg/L' and dst == 'µg/L':
        return ConversionResult(value=value * Decimal('1000'), unit=dst)

    # ppm ↔ mg/m3：必须给出分子量，否则不换算（规避默认分子量带来的误判）
    if src == 'ppm' and dst == 'mg/m3':
        if molecular_weight is None or molecular_weight <= 0:
            raise UnitConversionError('ppm → mg/m3 需要分子量 (g/mol)')
        return ConversionResult(value=value * molecular_weight / _GAS_MOLAR_VOLUME_L, unit=dst)
    if src == 'mg/m3' and dst == 'ppm':
        if molecular_weight is None or molecular_weight <= 0:
            raise UnitConversionError('mg/m3 → ppm 需要分子量 (g/mol)')
        return ConversionResult(value=value * _GAS_MOLAR_VOLUME_L / molecular_weight, unit=dst)

    raise UnitConversionError(f'暂不支持的单位换算: {src} → {dst}')


# ---------------------------------------------------------------------------
# TWA / STEL / 等效声级
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TWASegment:
    """TWA 计算的单段：浓度 + 暴露时长（分钟）。"""

    concentration: Decimal
    minutes: Decimal


def calc_pc_twa_8h(segments: Iterable[TWASegment]) -> Decimal:
    """PC-TWA 8h 计算：Σ(Ci · ti) / 480。

    依据 GBZ 159 / GBZ 2.1：以 8 小时（480 min）为分母，未足 8h 的工时按未暴露段为 0 计入。
    """
    total_weighted = Decimal('0')
    for seg in segments:
        if seg.minutes <= 0:
            continue
        total_weighted += seg.concentration * seg.minutes
    return total_weighted / Decimal('480')


def calc_stel_15min(segments: Iterable[TWASegment]) -> Decimal:
    """PC-STEL：取任意连续 15 min 暴露的最大加权平均浓度（简化版：取段内最大平均值）。

    第一层只支持每段时长 ≥ 15 min 的样本；< 15 min 的段忽略不算。
    更精确的滑动窗实现放到第二层（PDF 报告解析后再做）。
    """
    max_avg = Decimal('0')
    for seg in segments:
        if seg.minutes < Decimal('15'):
            continue
        if seg.concentration > max_avg:
            max_avg = seg.concentration
    return max_avg


def calc_noise_leq_8h(level_db: Decimal, exposure_hours: Decimal) -> Decimal:
    """噪声 8h 等效声级：Leq8h = L + 10·log10(T/8)。

    参数：
    - level_db: 实测等效声级 dB(A)
    - exposure_hours: 实测暴露时长（小时），> 0
    """
    if exposure_hours <= 0:
        raise ValueError('暴露时长必须 > 0')
    ratio = float(exposure_hours) / 8.0
    delta = Decimal(str(10 * math.log10(ratio)))
    return level_db + delta


# ---------------------------------------------------------------------------
# 报告级聚合
# ---------------------------------------------------------------------------


# 第一层只覆盖标量比较所需的最小算法集；TWA 仅当样品填了 duration_minutes 时启用
CalculationKind = Literal['scalar', 'pc_twa', 'pc_stel', 'noise_leq']


@dataclass(frozen=True, slots=True)
class CalculationOutcome:
    """计算结果：值 + 单位 + 算法标签 + 警告信息。"""

    value: Decimal | None
    unit: str | None
    kind: CalculationKind
    warnings: tuple[str, ...] = ()
