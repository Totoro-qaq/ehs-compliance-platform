from __future__ import annotations

from app.core.exceptions import EHSException

DETECTION_SERVICE_TYPES: tuple[str, ...] = (
    '定期检测',
    '控制效果评价检测',
    '现状评价检测',
    '环保',
    '安全',
)


def clean_detection_service_type(value: str | None) -> str | None:
    cleaned = (value or '').strip()
    if not cleaned:
        return None
    cleaned = cleaned[:64]
    if cleaned not in DETECTION_SERVICE_TYPES:
        raise EHSException(
            'Invalid detection service_type',
            code='DETECTION_INVALID_SERVICE_TYPE',
            status_code=400,
            details={'allowed': list(DETECTION_SERVICE_TYPES)},
        )
    return cleaned
