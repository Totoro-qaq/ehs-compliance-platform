from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from app.core.db import SessionLocal
from app.dao.detection_dao import RegulatoryLimitDAO, serialize_aliases
from app.models.db_models import LimitType, SampleMedium

GBZ_21_2019 = 'GBZ 2.1-2019'
GBZ_22_2007 = 'GBZ 2.2-2007'
GBZ_22_2007_SOURCE_PAGE = 'https://www.nhc.gov.cn/wjw/pyl/200705/39019.shtml'
GBZ_22_2007_SOURCE_PDF = (
    'https://www.nhc.gov.cn/wjw/pyl/200705/39019/files/1739779655603_50074.pdf'
)


def _d(value: str) -> Decimal:
    return Decimal(value)


def _seed_chemical(
    dao: RegulatoryLimitDAO,
    *,
    indicator_name: str,
    aliases: list[str],
    cas_no: str,
    molecular_weight: str,
    pc_twa: str,
    pc_stel: str,
) -> int:
    common = {
        'cas_no': cas_no,
        'aliases_json': serialize_aliases(aliases),
        'standard_name': '工作场所有害因素职业接触限值 第1部分：化学有害因素',
        'clause': '表1',
        'basis_text': f'{GBZ_21_2019} 表1 职业接触限值',
        'effective_from': date(2020, 4, 1),
        'applicability_json': json.dumps(
            {'molecular_weight': molecular_weight},
            ensure_ascii=False,
        ),
        'priority': 100,
    }
    dao.upsert_seed(
        standard_code=GBZ_21_2019,
        indicator_name=indicator_name,
        medium=SampleMedium.WORKPLACE_AIR,
        limit_type=LimitType.PC_TWA,
        unit='mg/m3',
        limit_value=_d(pc_twa),
        **common,
    )
    dao.upsert_seed(
        standard_code=GBZ_21_2019,
        indicator_name=indicator_name,
        medium=SampleMedium.WORKPLACE_AIR,
        limit_type=LimitType.PC_STEL,
        unit='mg/m3',
        limit_value=_d(pc_stel),
        **common,
    )
    return 2


def _seed_noise(dao: RegulatoryLimitDAO) -> int:
    dao.upsert_seed(
        standard_code=GBZ_22_2007,
        indicator_name='噪声',
        medium=SampleMedium.NOISE,
        limit_type=LimitType.INSTANT,
        unit='dB(A)',
        limit_value=_d('85'),
        aliases_json=serialize_aliases(['Noise', '8h等效声级', 'LEX,8h']),
        standard_name='工作场所有害因素职业接触限值 第2部分：物理因素',
        clause='表9',
        basis_text=(
            f'{GBZ_22_2007} 表9 工作场所噪声职业接触限值；'
            f'公开来源：{GBZ_22_2007_SOURCE_PAGE}'
        ),
        effective_from=date(2007, 11, 1),
        applicability_json=json.dumps(
            {
                'source_page_url': GBZ_22_2007_SOURCE_PAGE,
                'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
                'exposure_basis': '5d/w, 8h/d or normalized 8h equivalent sound level',
            },
            ensure_ascii=False,
        ),
        priority=100,
    )
    return 1


def _seed_high_temperature(dao: RegulatoryLimitDAO) -> int:
    workload_labels = {
        'I': '轻劳动',
        'II': '中等劳动',
        'III': '重劳动',
        'IV': '极重劳动',
    }
    rows = (
        ('100', 'I', '30'),
        ('100', 'II', '28'),
        ('100', 'III', '26'),
        ('100', 'IV', '25'),
        ('75', 'I', '31'),
        ('75', 'II', '29'),
        ('75', 'III', '28'),
        ('75', 'IV', '26'),
        ('50', 'I', '32'),
        ('50', 'II', '30'),
        ('50', 'III', '29'),
        ('50', 'IV', '28'),
        ('25', 'I', '33'),
        ('25', 'II', '32'),
        ('25', 'III', '31'),
        ('25', 'IV', '30'),
    )
    for contact_rate, workload_level, limit_value in rows:
        workload_label = workload_labels[workload_level]
        indicator_name = f'高温WBGT-{workload_level}级-{contact_rate}%'
        dao.upsert_seed(
            standard_code=GBZ_22_2007,
            indicator_name=indicator_name,
            medium=SampleMedium.HIGH_TEMPERATURE,
            limit_type=LimitType.INSTANT,
            unit='℃',
            limit_value=_d(limit_value),
            aliases_json=serialize_aliases(
                [
                    f'WBGT-{workload_level}-{contact_rate}%',
                    f'高温-{workload_level}级-{contact_rate}%',
                    f'高温WBGT-{workload_label}-{contact_rate}%',
                ]
            ),
            standard_name='工作场所有害因素职业接触限值 第2部分：物理因素',
            clause='表8',
            basis_text=(
                f'{GBZ_22_2007} 表8 工作场所不同体力劳动强度 WBGT 限值；'
                f'接触时间率 {contact_rate}%，体力劳动强度 {workload_level}级（{workload_label}）；'
                f'公开来源：{GBZ_22_2007_SOURCE_PAGE}'
            ),
            effective_from=date(2007, 11, 1),
            applicability_json=json.dumps(
                {
                    'source_page_url': GBZ_22_2007_SOURCE_PAGE,
                    'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
                    'contact_time_rate_percent': int(contact_rate),
                    'physical_workload_level': workload_level,
                    'physical_workload_label': workload_label,
                    'hot_region_adjustment_celsius': (
                        'If local outside ventilation design temperature is >=30℃, '
                        'the table limit is increased by 1℃.'
                    ),
                },
                ensure_ascii=False,
            ),
            priority=100,
        )
    return len(rows)


def seed() -> int:
    with SessionLocal() as session:
        dao = RegulatoryLimitDAO(session)
        count = 0
        count += _seed_chemical(
            dao,
            indicator_name='苯',
            aliases=['Benzene'],
            cas_no='71-43-2',
            molecular_weight='78.11',
            pc_twa='6',
            pc_stel='10',
        )
        count += _seed_chemical(
            dao,
            indicator_name='甲苯',
            aliases=['Toluene'],
            cas_no='108-88-3',
            molecular_weight='92.14',
            pc_twa='50',
            pc_stel='100',
        )
        count += _seed_chemical(
            dao,
            indicator_name='二甲苯',
            aliases=['Xylene', 'Xylenes'],
            cas_no='1330-20-7',
            molecular_weight='106.17',
            pc_twa='50',
            pc_stel='100',
        )
        dao.upsert_seed(
            standard_code=GBZ_21_2019,
            indicator_name='其他粉尘',
            medium=SampleMedium.WORKPLACE_AIR,
            limit_type=LimitType.PC_TWA,
            unit='mg/m3',
            limit_value=_d('8'),
            aliases_json=serialize_aliases(['粉尘', 'Dust']),
            standard_name='工作场所有害因素职业接触限值 第1部分：化学有害因素',
            clause='表2',
            basis_text=f'{GBZ_21_2019} 表2 粉尘职业接触限值',
            effective_from=date(2020, 4, 1),
            priority=100,
        )
        count += 1
        count += _seed_noise(dao)
        count += _seed_high_temperature(dao)
        return count


if __name__ == '__main__':
    print(f'seeded_or_updated={seed()}')
