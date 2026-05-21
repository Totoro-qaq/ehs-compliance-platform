"""限值匹配服务：根据测量值找到最适用的法规限值。

第一层只支持「按因子名 + 介质 + (CAS) 命中候选 → 按 priority 升序取首条」。
更复杂的行业/地区适用规则放到第三层。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from app.dao.detection_dao import RegulatoryLimitDAO
from app.models.db_models import DetectionMeasurement, LimitType, RegulatoryLimit, SampleMedium

# 不同算法对应的可用 limit_type 集合
_LIMIT_TYPES_FOR_AIR: tuple[LimitType, ...] = (
    LimitType.PC_TWA,
    LimitType.PC_STEL,
    LimitType.MAC,
)
_LIMIT_TYPES_FOR_NOISE: tuple[LimitType, ...] = (LimitType.INSTANT, LimitType.DAILY_AVG)
_LIMIT_TYPES_FOR_HIGH_TEMPERATURE: tuple[LimitType, ...] = (LimitType.INSTANT,)
_LIMIT_TYPES_FOR_PHYSICAL: tuple[LimitType, ...] = (LimitType.INSTANT, LimitType.RANGE)
_LIMIT_TYPES_FOR_WATER: tuple[LimitType, ...] = (
    LimitType.DAILY_AVG,
    LimitType.INSTANT,
    LimitType.RANGE,
)


def candidate_limit_types(medium: SampleMedium) -> tuple[LimitType, ...]:
    """按介质给出可参与判定的限值类型，避免误用 PC-TWA 去判 pH。"""
    if medium == SampleMedium.WORKPLACE_AIR:
        return _LIMIT_TYPES_FOR_AIR
    if medium == SampleMedium.NOISE:
        return _LIMIT_TYPES_FOR_NOISE
    if medium == SampleMedium.HIGH_TEMPERATURE:
        return _LIMIT_TYPES_FOR_HIGH_TEMPERATURE
    if medium == SampleMedium.PHYSICAL_FACTOR:
        return _LIMIT_TYPES_FOR_PHYSICAL
    if medium == SampleMedium.WASTEWATER:
        return _LIMIT_TYPES_FOR_WATER
    if medium == SampleMedium.EXHAUST_GAS:
        return (LimitType.INSTANT, LimitType.DAILY_AVG)
    return tuple(LimitType)


class DetectionLimitService:
    """无状态服务：所有方法接受 db Session，便于在事务中复用。"""

    @staticmethod
    def match(
        *,
        db: Session,
        measurement: DetectionMeasurement,
        medium: SampleMedium,
        as_of: date | None = None,
        limit_type: LimitType | None = None,
    ) -> RegulatoryLimit | None:
        dao = RegulatoryLimitDAO(db)
        types: Sequence[LimitType] = (
            (limit_type,) if limit_type is not None else candidate_limit_types(medium)
        )
        candidates = dao.find_candidates(
            indicator_name=measurement.indicator_name,
            cas_no=measurement.cas_no,
            medium=medium,
            limit_types=types,
            as_of=as_of,
        )
        return candidates[0] if candidates else None

    @staticmethod
    def match_all(
        *,
        db: Session,
        measurement: DetectionMeasurement,
        medium: SampleMedium,
        as_of: date | None = None,
    ) -> list[RegulatoryLimit]:
        """返回该因子在介质下命中的全部限值（PC-TWA / PC-STEL / MAC 同时存在的情形）。"""
        dao = RegulatoryLimitDAO(db)
        return dao.find_candidates(
            indicator_name=measurement.indicator_name,
            cas_no=measurement.cas_no,
            medium=medium,
            limit_types=candidate_limit_types(medium),
            as_of=as_of,
        )
