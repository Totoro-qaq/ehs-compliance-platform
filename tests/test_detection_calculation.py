from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.detection_calculation_service import (
    TWASegment,
    UnitConversionError,
    calc_noise_leq_8h,
    calc_pc_twa_8h,
    calc_stel_15min,
    convert_value,
    normalize_unit,
)


def test_normalize_and_convert_mass_concentration_units():
    assert normalize_unit('ug/m3') == 'µg/m3'
    assert normalize_unit('μg/m3') == 'µg/m3'
    assert normalize_unit('WBGT(℃)') == '℃'
    assert normalize_unit('°C') == '℃'

    to_mg = convert_value(Decimal('1500'), 'μg/m3', 'mg/m3')
    assert to_mg.value == Decimal('1.5')
    assert to_mg.unit == 'mg/m3'

    to_ug = convert_value(Decimal('1.25'), 'mg/m3', 'μg/m3')
    assert to_ug.value == Decimal('1250.00')
    assert to_ug.unit == 'µg/m3'


def test_convert_ppm_requires_molecular_weight():
    with pytest.raises(UnitConversionError):
        convert_value(Decimal('1'), 'ppm', 'mg/m3')

    converted = convert_value(
        Decimal('1'),
        'ppm',
        'mg/m3',
        molecular_weight=Decimal('78.11'),
    )
    assert converted.value.quantize(Decimal('0.001')) == Decimal('3.195')


def test_pc_twa_uses_8_hour_denominator():
    value = calc_pc_twa_8h(
        [
            TWASegment(Decimal('10'), Decimal('240')),
            TWASegment(Decimal('2'), Decimal('240')),
        ]
    )
    assert value == Decimal('6')

    short_shift = calc_pc_twa_8h([TWASegment(Decimal('10'), Decimal('120'))])
    assert short_shift == Decimal('2.5')


def test_stel_skips_segments_shorter_than_15_minutes():
    value = calc_stel_15min(
        [
            TWASegment(Decimal('50'), Decimal('10')),
            TWASegment(Decimal('12'), Decimal('15')),
            TWASegment(Decimal('20'), Decimal('20')),
        ]
    )
    assert value == Decimal('20')


def test_noise_leq_8h_adjusts_for_exposure_hours():
    assert calc_noise_leq_8h(Decimal('85'), Decimal('8')).quantize(Decimal('0.001')) == Decimal(
        '85.000'
    )
    assert calc_noise_leq_8h(Decimal('88'), Decimal('4')).quantize(Decimal('0.001')) == Decimal(
        '84.990'
    )
