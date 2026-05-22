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


# =============================================================================
# GBZ 2.1-2019 表1 化学有害因素职业接触限值
# 每条记录: (中文名, [别名], CAS号, 分子量, PC-TWA, PC-STEL, MAC, 致敏/皮/致癌标记)
# 单位: mg/m³（已标注的除外）
# =============================================================================

ChemicalRecord = tuple[str, list[str], str, str, str, str]

# PC-TWA 和 PC-STEL 均有的化学因素
CHEMICALS_TWA_STEL: list[ChemicalRecord] = [
    # 金属及其化合物
    ('钡及其可溶性化合物', ['Barium', 'Ba'], '7440-39-3', '137.33', '0.5', '1.5'),
    ('铍及其化合物', ['Beryllium', 'Be'], '7440-41-7', '9.01', '0.0005', '0.001'),
    ('镉及其化合物', ['Cadmium', 'Cd'], '7440-43-9', '112.41', '0.01', '0.02'),
    ('铬及其化合物', ['Chromium', 'Cr'], '7440-47-3', '52.00', '0.05', '0.15'),
    ('钴及其化合物', ['Cobalt', 'Co'], '7440-48-4', '58.93', '0.05', '0.1'),
    ('铜尘', ['Copper dust', 'Cu'], '7440-50-8', '63.55', '1', '2.5'),
    ('铜烟', ['Copper fume', 'Cu fume'], '7440-50-8', '63.55', '0.2', '0.6'),
    ('锰及其无机化合物', ['Manganese', 'Mn'], '7439-96-5', '54.94', '0.15', '0.45'),
    ('钼及其化合物', ['Molybdenum', 'Mo'], '7439-98-7', '95.94', '5', '15'),  # 不溶性
    ('镍及其化合物', ['Nickel', 'Ni'], '7440-02-0', '58.69', '1', '2.5'),  # 金属镍与难溶性
    ('铅及其无机化合物', ['Lead', 'Pb'], '7439-92-1', '207.2', '0.05', '0.15'),  # 铅尘
    ('铅烟', ['Lead fume'], '7439-92-1', '207.2', '0.03', '0.09'),
    ('锑及其化合物', ['Antimony', 'Sb'], '7440-36-0', '121.76', '0.5', '1.5'),
    ('锡及其无机化合物', ['Tin', 'Sn'], '7440-31-5', '118.71', '2', '5'),  # 不溶性
    ('钨及其不溶性化合物', ['Tungsten', 'W'], '7440-33-7', '183.84', '5', '10'),
    ('锌及其化合物', ['Zinc', 'Zn'], '7440-66-6', '65.38', '3', '5'),  # 氧化锌
    ('钒及其化合物', ['Vanadium', 'V'], '7440-62-2', '50.94', '0.05', '0.15'),  # 按V计
    ('汞-金属汞(蒸气)', ['Mercury vapor', 'Hg'], '7439-97-6', '200.59', '0.02', '0.04'),
    ('汞-有机汞化合物', ['Organic mercury'], '22967-92-6', '', '0.01', '0.03'),

    # 类金属
    ('砷及其无机化合物', ['Arsenic', 'As'], '7440-38-2', '74.92', '0.01', '0.02'),
    ('硒及其化合物', ['Selenium', 'Se'], '7782-49-2', '78.96', '0.1', '0.3'),
    ('碲及其化合物', ['Tellurium', 'Te'], '13494-80-9', '127.60', '0.1', '0.3'),

    # 烷烃
    ('正己烷', ['n-Hexane'], '110-54-3', '86.18', '100', '180'),
    ('正庚烷', ['n-Heptane'], '142-82-5', '100.20', '500', '1000'),
    ('正戊烷', ['n-Pentane'], '109-66-0', '72.15', '500', '1000'),
    ('环己烷', ['Cyclohexane'], '110-82-7', '84.16', '250', '375'),

    # 烯烃
    ('丁二烯', ['1,3-Butadiene'], '106-99-0', '54.09', '5', '12.5'),

    # 芳香烃
    ('苯', ['Benzene'], '71-43-2', '78.11', '6', '10'),
    ('甲苯', ['Toluene'], '108-88-3', '92.14', '50', '100'),
    ('二甲苯', ['Xylene', 'Xylenes', '全部异构体'], '1330-20-7', '106.17', '50', '100'),
    ('乙苯', ['Ethylbenzene'], '100-41-4', '106.17', '100', '150'),
    ('苯乙烯', ['Styrene'], '100-42-5', '104.15', '50', '100'),
    ('三甲苯', ['Trimethylbenzene', '三甲苯(1,3,5-)', 'Mesitylene'], '108-67-8', '120.19', '100', '200'),

    # 卤代烃
    ('二氯甲烷', ['Dichloromethane', 'Methylene chloride'], '75-09-2', '84.93', '200', '300'),
    ('三氯甲烷', ['Trichloromethane', 'Chloroform', '氯仿'], '67-66-3', '119.38', '20', '40'),
    ('四氯化碳', ['Carbon tetrachloride'], '56-23-5', '153.82', '15', '25'),
    ('1,2-二氯乙烷', ['1,2-Dichloroethane', 'EDC'], '107-06-2', '98.96', '7', '15'),
    ('三氯乙烯', ['Trichloroethylene'], '79-01-6', '131.39', '30', '60'),
    ('四氯乙烯', ['Tetrachloroethylene', 'Perchloroethylene'], '127-18-4', '165.83', '200', '400'),
    ('氯乙烯', ['Vinyl chloride', 'VC'], '75-01-4', '62.50', '10', '25'),
    ('氯苯', ['Chlorobenzene'], '108-90-7', '112.56', '50', '100'),
    ('1,1,1-三氯乙烷', ['1,1,1-Trichloroethane', 'Methyl chloroform'], '71-55-6', '133.40', '900', '1350'),
    ('1,2-二氯丙烷', ['1,2-Dichloropropane'], '78-87-5', '112.99', '350', '500'),
    ('氯丙烯', ['Allyl chloride', '3-氯丙烯'], '107-05-1', '76.53', '2', '4'),

    # 醇类
    ('甲醇', ['Methanol', 'Methyl alcohol'], '67-56-1', '32.04', '25', '50'),  # 皮
    ('乙醇', ['Ethanol', 'Ethyl alcohol'], '64-17-5', '46.07', '1900', '—'),
    ('异丙醇', ['Isopropanol', 'Isopropyl alcohol', 'IPA'], '67-63-0', '60.10', '350', '700'),
    ('正丁醇', ['n-Butanol', 'n-Butyl alcohol'], '71-36-3', '74.12', '100', '200'),
    ('异丁醇', ['Isobutanol', 'Isobutyl alcohol'], '78-83-1', '74.12', '100', '200'),
    ('异戊醇', ['Isoamyl alcohol'], '123-51-3', '88.15', '100', '200'),
    ('丙醇', ['n-Propanol', 'Propyl alcohol'], '71-23-8', '60.10', '200', '300'),
    ('糠醇', ['Furfuryl alcohol'], '98-00-0', '98.10', '40', '60'),  # 皮
    ('环己醇', ['Cyclohexanol'], '108-93-0', '100.16', '100', '200'),  # 皮
    ('乙二醇', ['Ethylene glycol'], '107-21-1', '62.07', '20', '40'),

    # 酚类
    ('苯酚', ['Phenol'], '108-95-2', '94.11', '10', '25'),  # 皮
    ('甲酚', ['Cresol', '全部异构体'], '1319-77-3', '108.14', '10', '25'),  # 皮
    ('间苯二酚', ['Resorcinol'], '108-46-3', '110.11', '20', '40'),
    ('对苯二酚', ['Hydroquinone'], '123-31-9', '110.11', '1', '2'),

    # 醚类
    ('乙醚', ['Ethyl ether', 'Diethyl ether'], '60-29-7', '74.12', '300', '500'),
    ('石油醚', ['Petroleum ether'], '8032-32-4', '', '300', '500'),
    ('异丙醚', ['Isopropyl ether'], '108-20-3', '102.18', '550', '850'),

    # 醛类
    ('甲醛', ['Formaldehyde'], '50-00-0', '30.03', '—', '—'),  # MAC only
    ('乙醛', ['Acetaldehyde'], '75-07-0', '44.05', '45', '90'),
    ('丙烯醛', ['Acrolein'], '107-02-8', '56.06', '0.3', '0.9'),  # 皮
    ('糠醛', ['Furfural', 'Furfuraldehyde'], '98-01-1', '96.09', '5', '12.5'),  # 皮

    # 酮类
    ('丙酮', ['Acetone'], '67-64-1', '58.08', '300', '450'),
    ('丁酮', ['Butanone', 'Methyl ethyl ketone', 'MEK'], '78-93-3', '72.11', '300', '600'),
    ('环己酮', ['Cyclohexanone'], '108-94-1', '98.15', '50', '100'),  # 皮
    ('甲基异丁基甲酮', ['MIBK', 'Methyl isobutyl ketone'], '108-10-1', '100.16', '50', '100'),
    ('异佛尔酮', ['Isophorone'], '78-59-1', '138.21', '—', '—'),  # MAC only
    ('甲基丙烯酸甲酯', ['Methyl methacrylate', 'MMA'], '80-62-6', '100.12', '100', '200'),

    # 酯类
    ('乙酸乙酯', ['Ethyl acetate'], '141-78-6', '88.11', '200', '300'),
    ('乙酸丁酯', ['Butyl acetate', 'n-Butyl acetate'], '123-86-4', '116.16', '200', '300'),
    ('乙酸甲酯', ['Methyl acetate'], '79-20-9', '74.08', '200', '400'),
    ('乙酸丙酯', ['Propyl acetate', 'n-Propyl acetate'], '109-60-4', '102.13', '200', '300'),
    ('乙酸异丁酯', ['Isobutyl acetate'], '110-19-0', '116.16', '200', '300'),
    ('乙酸戊酯', ['Amyl acetate', 'Pentyl acetate'], '628-63-7', '130.19', '100', '200'),
    ('丙烯酸甲酯', ['Methyl acrylate'], '96-33-3', '86.09', '20', '40'),  # 皮
    ('丙烯酸丁酯', ['Butyl acrylate'], '141-32-2', '128.17', '25', '75'),

    # 胺类
    ('苯胺', ['Aniline'], '62-53-3', '93.13', '3', '7.5'),  # 皮
    ('二甲基苯胺', ['Dimethylaniline', 'N,N-Dimethylaniline'], '121-69-7', '121.18', '5', '10'),  # 皮
    ('二乙胺', ['Diethylamine'], '109-89-7', '73.14', '15', '25'),  # 皮
    ('三乙胺', ['Triethylamine'], '121-44-8', '101.19', '10', '20'),
    ('二甲基甲酰胺', ['DMF', 'Dimethylformamide', 'N,N-Dimethylformamide'], '68-12-2', '73.10', '20', '40'),  # 皮
    ('二甲基乙酰胺', ['DMAc', 'Dimethylacetamide'], '127-19-5', '87.12', '20', '40'),  # 皮
    ('乙二胺', ['Ethylenediamine', '1,2-Diaminoethane'], '107-15-3', '60.10', '4', '10'),  # 皮
    ('环己胺', ['Cyclohexylamine'], '108-91-8', '99.17', '10', '20'),  # 皮
    ('乙醇胺', ['Ethanolamine', 'MEA', 'Monoethanolamine'], '141-43-5', '61.08', '—', '—'),  # usually TWA+STEL
    ('二乙醇胺', ['Diethanolamine', 'DEA'], '111-42-2', '105.14', '3', '—'),

    # 腈类
    ('乙腈', ['Acetonitrile'], '75-05-8', '41.05', '30', '60'),  # 皮
    ('丙烯腈', ['Acrylonitrile'], '107-13-1', '53.06', '1', '2'),  # 皮

    # 硝基化合物
    ('硝基苯', ['Nitrobenzene'], '98-95-3', '123.11', '2', '5'),  # 皮
    ('二硝基苯', ['Dinitrobenzene', '全部异构体'], '25154-54-5', '168.11', '1', '2.5'),  # 皮
    ('二硝基甲苯', ['Dinitrotoluene', 'DNT'], '25321-14-6', '182.14', '0.2', '0.5'),  # 皮
    ('三硝基甲苯', ['TNT', 'Trinitrotoluene'], '118-96-7', '227.13', '0.2', '0.5'),  # 皮

    # 杂环化合物
    ('吡啶', ['Pyridine'], '110-86-1', '79.10', '4', '10'),
    ('四氢呋喃', ['Tetrahydrofuran', 'THF'], '109-99-9', '72.11', '300', '450'),
    ('呋喃', ['Furan'], '110-00-9', '68.07', '5', '12.5'),

    # 无机酸
    ('硫酸及三氧化硫', ['Sulfuric acid'], '7664-93-9', '98.08', '1', '2'),
    ('盐酸', ['Hydrochloric acid', 'HCl'], '7647-01-0', '36.46', '—', '—'),  # MAC 7.5 mg/m³
    ('硝酸', ['Nitric acid', 'HNO3'], '7697-37-2', '63.01', '—', '—'),  # MAC
    ('磷酸', ['Phosphoric acid'], '7664-38-2', '98.00', '1', '3'),
    ('氢氟酸', ['Hydrofluoric acid', 'HF', '氟化氢'], '7664-39-3', '20.01', '—', '—'),  # MAC 2 mg/m³

    # 无机碱
    ('氢氧化钠', ['Sodium hydroxide', 'NaOH', '烧碱', '苛性钠'], '1310-73-2', '40.00', '—', '—'),  # MAC 2 mg/m³
    ('氢氧化钾', ['Potassium hydroxide', 'KOH'], '1310-58-3', '56.11', '—', '—'),  # MAC 2 mg/m³

    # 无机气体
    ('氨', ['Ammonia', 'NH3'], '7664-41-7', '17.03', '20', '30'),
    ('一氧化碳', ['Carbon monoxide', 'CO'], '630-08-0', '28.01', '20', '30'),  # 非高原
    ('一氧化氮', ['Nitric oxide', 'NO'], '10102-43-9', '30.01', '15', '30'),
    ('二氧化氮', ['Nitrogen dioxide', 'NO2'], '10102-44-0', '46.01', '5', '10'),
    ('二氧化硫', ['Sulfur dioxide', 'SO2'], '7446-09-5', '64.06', '5', '10'),
    ('氯气', ['Chlorine', 'Cl2'], '7782-50-5', '70.90', '—', '—'),  # MAC 1 mg/m³
    ('氰化氢', ['Hydrogen cyanide', 'HCN'], '74-90-8', '27.03', '—', '—'),  # MAC 1 mg/m³ 皮
    ('硫化氢', ['Hydrogen sulfide', 'H2S'], '7783-06-4', '34.08', '—', '—'),  # MAC 10 mg/m³
    ('臭氧', ['Ozone', 'O3'], '10028-15-6', '48.00', '—', '—'),  # MAC 0.3 mg/m³
    ('过氧化氢', ['Hydrogen peroxide', 'H2O2', '双氧水'], '7722-84-1', '34.01', '1.5', '3.75'),
    ('二氧化碳', ['Carbon dioxide', 'CO2'], '124-38-9', '44.01', '9000', '18000'),
    ('光气', ['Phosgene', 'COCl2'], '75-44-5', '98.92', '—', '—'),  # MAC 0.5 mg/m³

    # 腈/氰类
    ('氰化钾', ['Potassium cyanide', 'KCN'], '151-50-8', '65.12', '—', '—'),  # MAC 1 mg/m³ 皮

    # 硫化物
    ('二硫化碳', ['Carbon disulfide', 'CS2'], '75-15-0', '76.14', '5', '10'),  # 皮

    # 磷化合物
    ('磷化氢', ['Phosphine', 'PH3', '磷烷'], '7803-51-2', '34.00', '—', '—'),  # MAC 0.3 mg/m³
    ('五氧化二磷', ['Phosphorus pentoxide'], '1314-56-3', '141.94', '1', '3'),
    ('三氯化磷', ['Phosphorus trichloride'], '7719-12-2', '137.33', '1', '2'),
    ('三氯氧磷', ['Phosphorus oxychloride'], '10025-87-3', '153.33', '0.3', '0.6'),
    ('磷酸三丁酯', ['Tributyl phosphate', 'TBP'], '126-73-8', '266.32', '2.5', '5'),
    ('磷酸三甲苯酯', ['Tricresyl phosphate', 'TCP'], '1330-78-5', '368.37', '0.3', '0.75'),

    # 肼类
    ('肼', ['Hydrazine'], '302-01-2', '32.05', '0.06', '0.13'),  # 皮
    ('甲基肼', ['Methylhydrazine', 'Monomethylhydrazine'], '60-34-4', '46.07', '0.08', '0.24'),  # 皮
    ('偏二甲基肼', ['1,1-Dimethylhydrazine', 'UDMH'], '57-14-7', '60.10', '0.5', '1.5'),  # 皮

    # 有机磷农药
    ('对硫磷', ['Parathion'], '56-38-2', '291.26', '0.05', '0.1'),  # 皮
    ('内吸磷', ['Demeton', 'Systox'], '8065-48-3', '258.34', '0.02', '0.05'),  # 皮
    ('甲拌磷', ['Phorate', 'Thimet'], '298-02-2', '260.38', '0.01', '0.025'),  # 皮
    ('乐果', ['Dimethoate', 'Rogor'], '60-51-5', '229.26', '0.5', '1'),  # 皮
    ('敌敌畏', ['Dichlorvos', 'DDVP'], '62-73-7', '220.98', '0.15', '0.3'),  # 皮
    ('敌百虫', ['Trichlorfon'], '52-68-6', '257.44', '0.3', '0.9'),  # 皮
    ('马拉硫磷', ['Malathion'], '121-75-5', '330.36', '2', '5'),  # 皮
    ('久效磷', ['Monocrotophos'], '6923-22-4', '223.17', '0.05', '0.15'),  # 皮
    ('甲基对硫磷', ['Methyl parathion'], '298-00-0', '263.21', '0.05', '0.15'),  # 皮
    ('氧乐果', ['Omethoate'], '1113-02-6', '213.21', '0.1', '0.3'),  # 皮

    # 氨基甲酸酯类农药
    ('西维因', ['Carbaryl', 'Sevin'], '63-25-2', '201.22', '2', '5'),
    ('呋喃丹', ['Carbofuran'], '1563-66-2', '221.25', '0.05', '0.15'),  # 皮

    # 拟除虫菊酯类
    ('氰戊菊酯', ['Fenvalerate'], '51630-58-1', '419.91', '0.05', '0.15'),  # 皮
    ('溴氰菊酯', ['Deltamethrin'], '52918-63-5', '505.21', '0.03', '0.09'),  # 皮
    ('氯氰菊酯', ['Cypermethrin'], '52315-07-8', '416.30', '0.05', '0.15'),  # 皮
    ('氯菊酯', ['Permethrin'], '52645-53-1', '391.29', '0.5', '1.5'),  # 皮

    # 环氧化合物
    ('环氧乙烷', ['Ethylene oxide', 'EO'], '75-21-8', '44.05', '2', '5'),
    ('环氧丙烷', ['Propylene oxide'], '75-56-9', '58.08', '5', '12.5'),
    ('环氧氯丙烷', ['Epichlorohydrin', 'ECH'], '106-89-8', '92.52', '1', '2'),  # 皮

    # 增塑剂
    ('邻苯二甲酸二丁酯', ['Dibutyl phthalate', 'DBP'], '84-74-2', '278.35', '2.5', '6.25'),
    ('邻苯二甲酸二辛酯', ['Dioctyl phthalate', 'DOP', 'DEHP'], '117-81-7', '390.56', '3', '9'),

    # 汽油/溶剂
    ('溶剂汽油', ['Solvent naphtha', 'Gasoline'], '8006-61-9', '', '300', '450'),
    ('石脑油', ['Naphtha'], '8030-30-6', '', '300', '450'),
    ('松节油', ['Turpentine'], '8006-64-2', '', '300', '450'),
    ('液化石油气', ['LPG', 'Liquefied petroleum gas'], '68476-85-7', '', '1000', '1500'),
    ('柴油', ['Diesel fuel'], '68334-30-5', '', '—', '—'),  # MAC 100 mg/m³ (按总烃)

    # 其他有机物
    ('乙腈', ['Acetonitrile', '甲基氰'], '75-05-8', '41.05', '30', '60'),
    ('丙烯酰胺', ['Acrylamide'], '79-06-1', '71.08', '0.03', '0.09'),  # 皮
    ('己内酰胺', ['Caprolactam'], '105-60-2', '113.16', '5', '12.5'),
    ('二氯乙醚', ['Bis(2-chloroethyl)ether'], '111-44-4', '143.01', '5', '15'),  # 皮
    ('氯乙酸', ['Chloroacetic acid'], '79-11-8', '94.50', '2', '5'),  # 皮
    ('四氯乙烷', ['1,1,2,2-Tetrachloroethane'], '79-34-5', '167.85', '1', '3'),  # 皮
    ('乙酸', ['Acetic acid'], '64-19-7', '60.05', '10', '20'),
    ('甲酸', ['Formic acid'], '64-18-6', '46.03', '10', '20'),
    ('草酸', ['Oxalic acid', '乙二酸'], '144-62-7', '90.03', '1', '2'),
    ('乙酸酐', ['Acetic anhydride'], '108-24-7', '102.09', '5', '15'),
    ('邻苯二甲酸酐', ['Phthalic anhydride'], '85-44-9', '148.12', '1', '2'),
    ('马来酸酐', ['Maleic anhydride'], '108-31-6', '98.06', '0.5', '1.5'),
    ('丙烯酸', ['Acrylic acid'], '79-10-7', '72.06', '6', '15'),  # 皮
    ('甲基丙烯酸', ['Methacrylic acid'], '79-41-4', '86.09', '20', '40'),
    ('异氰酸甲酯', ['Methyl isocyanate', 'MIC'], '624-83-9', '57.05', '0.05', '0.1'),  # 皮
    ('甲苯二异氰酸酯', ['TDI', 'Toluene diisocyanate'], '26471-62-5', '174.16', '0.1', '0.2'),
    ('二苯甲烷二异氰酸酯', ['MDI', 'Diphenylmethane diisocyanate'], '101-68-8', '250.25', '0.05', '0.1'),
    ('六亚甲基二异氰酸酯', ['HDI', 'Hexamethylene diisocyanate'], '822-06-0', '168.19', '0.03', '0.09'),
    ('萘', ['Naphthalene'], '91-20-3', '128.17', '50', '75'),  # 皮
    ('四氢化萘', ['Tetralin', '1,2,3,4-Tetrahydronaphthalene'], '119-64-2', '132.20', '100', '200'),
    ('蒽', ['Anthracene'], '120-12-7', '178.23', '0.25', '0.75'),
    ('菲', ['Phenanthrene'], '85-01-8', '178.23', '0.25', '0.75'),
    ('联苯', ['Biphenyl', 'Diphenyl'], '92-52-4', '154.21', '1.5', '3.75'),
    ('茚', ['Indene'], '95-13-6', '116.16', '50', '100'),
    ('二氯苯', ['Dichlorobenzene', '邻/对二氯苯'], '106-46-7', '147.00', '50', '100'),
    ('三氯苯', ['Trichlorobenzene', '1,2,4-Trichlorobenzene'], '120-82-1', '181.45', '20', '50'),
    ('硝基氯苯', ['Chloronitrobenzene', '邻/对硝基氯苯'], '88-73-3', '157.56', '0.5', '1.5'),  # 皮
    ('对硝基苯胺', ['p-Nitroaniline'], '100-01-6', '138.13', '3', '7.5'),  # 皮
    ('苯并(a)芘', ['Benzo(a)pyrene', 'BaP'], '50-32-8', '252.31', '0.00015', '—'),
    ('多氯联苯', ['PCBs', 'Polychlorinated biphenyls'], '1336-36-3', '', '0.5', '1'),  # 皮
    ('五氯酚', ['Pentachlorophenol', 'PCP'], '87-86-5', '266.34', '0.3', '0.9'),  # 皮
    ('六六六', ['Hexachlorocyclohexane', 'BHC', '六氯环己烷'], '608-73-1', '290.83', '0.3', '0.5'),  # 皮
    ('滴滴涕', ['DDT', 'Dichlorodiphenyltrichloroethane'], '50-29-3', '354.49', '0.2', '—'),
    ('氟乙酰胺', ['Fluoroacetamide'], '640-19-7', '77.06', '0.05', '0.15'),
    ('碘甲烷', ['Methyl iodide', 'Iodomethane'], '74-88-4', '141.94', '10', '25'),  # 皮
    ('溴甲烷', ['Methyl bromide'], '74-83-9', '94.94', '2', '5'),  # 皮
    ('二溴甲烷', ['Dibromomethane'], '74-95-3', '173.83', '5', '15'),
    ('二氯乙炔', ['Dichloroacetylene'], '7572-29-4', '94.93', '—', '—'),  # MAC
    ('重氮甲烷', ['Diazomethane'], '334-88-3', '42.04', '0.35', '0.7'),
    ('对苯二甲酸', ['Terephthalic acid', 'PTA'], '100-21-0', '166.13', '8', '15'),
    ('均苯四甲酸二酐', ['PMDA', 'Pyromellitic dianhydride'], '89-32-7', '218.12', '0.5', '1'),
    ('二甲氧基乙烷', ['1,2-Dimethoxyethane'], '110-71-4', '90.12', '100', '200'),
    ('二噁烷', ['1,4-Dioxane'], '123-91-1', '88.11', '10', '25'),  # 皮
    ('氯化苄', ['Benzyl chloride'], '100-44-7', '126.58', '—', '—'),  # MAC
    ('二氯乙醚', ['Dichloroethyl ether'], '111-44-4', '143.01', '5', '15'),
]


# MAC-only chemicals (no PC-TWA/PC-STEL)
MAC_ONLY: list[tuple[str, list[str], str, str, str]] = [
    ('甲醛', ['Formaldehyde'], '50-00-0', '30.03', '0.5'),
    ('盐酸', ['Hydrochloric acid', 'HCl', '氯化氢'], '7647-01-0', '36.46', '7.5'),
    ('氢氟酸', ['Hydrofluoric acid', 'HF', '氟化氢'], '7664-39-3', '20.01', '2'),
    ('氢氧化钠', ['Sodium hydroxide', 'NaOH', '烧碱'], '1310-73-2', '40.00', '2'),
    ('氢氧化钾', ['Potassium hydroxide', 'KOH'], '1310-58-3', '56.11', '2'),
    ('氯气', ['Chlorine', 'Cl2'], '7782-50-5', '70.90', '1'),
    ('氰化氢', ['Hydrogen cyanide', 'HCN'], '74-90-8', '27.03', '1'),
    ('氰化钾', ['Potassium cyanide', 'KCN'], '151-50-8', '65.12', '1'),
    ('硫化氢', ['Hydrogen sulfide', 'H2S'], '7783-06-4', '34.08', '10'),
    ('臭氧', ['Ozone', 'O3'], '10028-15-6', '48.00', '0.3'),
    ('光气', ['Phosgene', 'COCl2'], '75-44-5', '98.92', '0.5'),
    ('磷化氢', ['Phosphine', 'PH3'], '7803-51-2', '34.00', '0.3'),
    ('氯化苄', ['Benzyl chloride'], '100-44-7', '126.58', '5'),
    ('二氯乙炔', ['Dichloroacetylene'], '7572-29-4', '94.93', '0.4'),
    ('硝酸', ['Nitric acid', 'HNO3'], '7697-37-2', '63.01', '—'),  # 备注：暂无MAC值或已整合到其他条目
    ('柴油', ['Diesel fuel', '按总烃计'], '68334-30-5', '', '100'),  # 不属于标准MAC，按实际情形TWA
    ('异佛尔酮', ['Isophorone'], '78-59-1', '138.21', '30'),
    ('乙醇胺', ['Ethanolamine', 'MEA'], '141-43-5', '61.08', '15'),
    ('敌草隆', ['Diuron'], '330-54-1', '233.10', '5'),
    ('百草枯', ['Paraquat'], '4685-14-7', '257.16', '0.5'),
]


# =============================================================================
# GBZ 2.1-2019 表2 粉尘职业接触限值 (PC-TWA only, 部分有呼尘限值)
# 格式: (中文名, [别名], CAS, PC-TWA总尘, PC-TWA呼尘)
# =============================================================================

DUST_RECORDS: list[tuple[str, list[str], str, str, str]] = [
    ('矽尘(10-50% SiO2)', ['Silica dust 10-50%', '石英尘 10-50%', '游离二氧化硅粉尘 10-50%'], '14808-60-7', '1', '0.7'),
    ('矽尘(50-80% SiO2)', ['Silica dust 50-80%', '石英尘 50-80%', '游离二氧化硅粉尘 50-80%'], '14808-60-7', '0.7', '0.5'),
    ('矽尘(>80% SiO2)', ['Silica dust >80%', '石英尘 >80%', '游离二氧化硅粉尘 >80%'], '14808-60-7', '0.5', '0.3'),
    ('煤尘', ['Coal dust'], '', '4', '2.5'),
    ('水泥粉尘', ['Cement dust', 'Portland cement'], '', '4', '1.5'),
    ('石墨粉尘', ['Graphite dust'], '7782-42-5', '4', '2'),
    ('碳化硅粉尘', ['Silicon carbide dust'], '409-21-2', '5', '2.5'),
    ('电焊烟尘', ['Welding fume'], '', '4', '—'),
    ('铸造粉尘', ['Foundry dust'], '', '4', '—'),
    ('氧化铝粉尘', ['Alumina dust', 'Aluminum oxide'], '1344-28-1', '4', '—'),
    ('二氧化钛粉尘', ['Titanium dioxide dust'], '13463-67-7', '8', '—'),
    ('谷物粉尘', ['Grain dust'], '', '4', '—'),
    ('木粉尘', ['Wood dust'], '', '3', '—'),
    ('棉尘', ['Cotton dust'], '', '1', '—'),
    ('茶尘', ['Tea dust'], '', '2', '—'),
    ('烟草尘', ['Tobacco dust'], '', '2', '—'),
    ('皮毛粉尘', ['Fur dust'], '', '8', '—'),
    ('活性炭粉尘', ['Activated carbon dust'], '', '5', '—'),
    ('聚丙烯粉尘', ['Polypropylene dust'], '9003-07-0', '5', '—'),
    ('聚氯乙烯粉尘', ['PVC dust', 'Polyvinyl chloride dust'], '9002-86-2', '5', '—'),
    ('其他粉尘', ['Other dusts', 'Dust', '不含有害物质的粉尘'], '', '8', '—'),
    ('滑石粉尘', ['Talc dust'], '14807-96-6', '3', '2'),
    ('云母粉尘', ['Mica dust'], '12001-26-2', '2', '1.5'),
    ('白云石粉尘', ['Dolomite dust'], '', '8', '4'),
    ('石灰石粉尘', ['Limestone dust'], '', '8', '4'),
    ('石膏粉尘', ['Gypsum dust'], '', '8', '4'),
    ('大理石粉尘', ['Marble dust'], '', '8', '4'),
    ('硅藻土粉尘', ['Diatomaceous earth dust'], '', '2', '—'),
    ('膨润土粉尘', ['Bentonite dust'], '', '6', '—'),
    ('萤石混合性粉尘', ['Fluorspar mixed dust'], '', '2', '—'),
    ('蛭石粉尘', ['Vermiculite dust'], '', '3', '—'),
    ('重晶石粉尘', ['Barite dust'], '', '5', '—'),
    ('陶土粉尘', ['Kaolin dust', '高岭土粉尘'], '', '4', '—'),
    ('铝尘', ['Aluminum dust', '铝金属粉尘'], '7429-90-5', '3', '—'),
    ('铁及其化合物粉尘', ['Iron dust', 'Iron oxide dust'], '', '5', '—'),
    ('锆及其化合物粉尘', ['Zirconium dust'], '', '5', '—'),
    ('碳纤维粉尘', ['Carbon fiber dust'], '', '3', '—'),
    ('玻璃棉粉尘', ['Glass wool dust'], '', '3', '—'),
    ('岩棉粉尘', ['Rock wool dust'], '', '3', '—'),
    ('矿渣棉粉尘', ['Slag wool dust'], '', '3', '—'),
    ('硅灰石粉尘', ['Wollastonite dust'], '', '5', '—'),
    ('麻尘(亚麻)', ['Flax dust', '亚麻粉尘'], '', '1.5', '—'),
    ('麻尘(苎麻)', ['Ramie dust', '苎麻粉尘'], '', '3', '—'),
    ('麻尘(黄麻)', ['Jute dust', '黄麻粉尘'], '', '4', '—'),
    ('甘蔗渣粉尘', ['Bagasse dust'], '', '3', '—'),
    ('软木粉尘', ['Cork dust'], '', '3', '—'),
    ('饲料粉尘', ['Feed dust', '配合饲料粉尘'], '', '5', '—'),
    ('洗衣粉粉尘', ['Detergent dust', '合成洗涤剂粉尘'], '', '5', '—'),
    ('稀土粉尘', ['Rare earth dust'], '', '2.5', '—'),
    ('碳黑粉尘', ['Carbon black dust'], '1333-86-4', '4', '—'),
    ('珍珠岩粉尘', ['Perlite dust'], '', '8', '4'),
    ('硅灰粉尘', ['Silica fume dust', '微硅粉'], '', '4', '1.5'),
]


# =============================================================================
# GBZ 2.2-2007 物理因素职业接触限值
# =============================================================================

def _seed_chemical(dao, *, indicator_name, aliases, cas_no, molecular_weight, pc_twa, pc_stel):
    """种子一个化学因素的 PC-TWA + PC-STEL 限值（同时有两者）。"""
    common = {
        'cas_no': cas_no,
        'aliases_json': serialize_aliases(aliases),
        'standard_name': '工作场所有害因素职业接触限值 第1部分：化学有害因素',
        'clause': '表1',
        'basis_text': f'{GBZ_21_2019} 表1 工作场所空气中化学有害因素职业接触限值',
        'effective_from': date(2020, 4, 1),
        'applicability_json': json.dumps(
            {'molecular_weight': molecular_weight} if molecular_weight else {},
            ensure_ascii=False,
        ),
        'priority': 100,
    }
    count = 0
    if pc_twa and pc_twa != '—':
        dao.upsert_seed(
            standard_code=GBZ_21_2019,
            indicator_name=indicator_name,
            medium=SampleMedium.WORKPLACE_AIR,
            limit_type=LimitType.PC_TWA,
            unit='mg/m3',
            limit_value=_d(pc_twa),
            **common,
        )
        count += 1
    if pc_stel and pc_stel != '—':
        dao.upsert_seed(
            standard_code=GBZ_21_2019,
            indicator_name=indicator_name,
            medium=SampleMedium.WORKPLACE_AIR,
            limit_type=LimitType.PC_STEL,
            unit='mg/m3',
            limit_value=_d(pc_stel),
            **common,
        )
        count += 1
    return count


def _seed_chemical_mac(dao, *, indicator_name, aliases, cas_no, molecular_weight, mac_value):
    """种子 MAC（最高容许浓度）限值（仅此一项，无 PC-TWA/PC-STEL）。"""
    if mac_value == '—' or not mac_value:
        return 0
    dao.upsert_seed(
        standard_code=GBZ_21_2019,
        indicator_name=indicator_name,
        medium=SampleMedium.WORKPLACE_AIR,
        limit_type=LimitType.MAC,
        unit='mg/m3',
        limit_value=_d(mac_value),
        cas_no=cas_no,
        aliases_json=serialize_aliases(aliases),
        standard_name='工作场所有害因素职业接触限值 第1部分：化学有害因素',
        clause='表1',
        basis_text=f'{GBZ_21_2019} 表1 工作场所空气中化学有害因素职业接触限值（MAC）',
        effective_from=date(2020, 4, 1),
        applicability_json=json.dumps(
            {'molecular_weight': molecular_weight} if molecular_weight else {},
            ensure_ascii=False,
        ),
        priority=100,
    )
    return 1


def _seed_dust(dao, *, indicator_name, aliases, cas_no, pc_twa_total, pc_twa_respirable):
    """种子粉尘 PC-TWA 限值。"""
    count = 0
    common = {
        'cas_no': cas_no,
        'aliases_json': serialize_aliases(aliases),
        'standard_name': '工作场所有害因素职业接触限值 第1部分：化学有害因素',
        'clause': '表2',
        'basis_text': f'{GBZ_21_2019} 表2 工作场所空气中粉尘职业接触限值',
        'effective_from': date(2020, 4, 1),
        'applicability_json': json.dumps({}, ensure_ascii=False),
        'priority': 100,
    }
    if pc_twa_total and pc_twa_total != '—':
        dao.upsert_seed(
            standard_code=GBZ_21_2019,
            indicator_name=f'{indicator_name}(总尘)',
            medium=SampleMedium.WORKPLACE_AIR,
            limit_type=LimitType.PC_TWA,
            unit='mg/m3',
            limit_value=_d(pc_twa_total),
            **common,
        )
        count += 1
    if pc_twa_respirable and pc_twa_respirable != '—':
        dao.upsert_seed(
            standard_code=GBZ_21_2019,
            indicator_name=f'{indicator_name}(呼尘)',
            medium=SampleMedium.WORKPLACE_AIR,
            limit_type=LimitType.PC_TWA,
            unit='mg/m3',
            limit_value=_d(pc_twa_respirable),
            **common,
        )
        count += 1
    return count


# ---------------------------------------------------------------------------
# GBZ 2.2-2007 物理因素
# ---------------------------------------------------------------------------

def _seed_high_frequency_em_field(dao):
    """高频电磁场（100 kHz–30 MHz）GBZ 2.2-2007 表1"""
    count = 0
    spec = {
        'standard_name': '工作场所有害因素职业接触限值 第2部分：物理因素',
        'standard_code': GBZ_22_2007,
        'clause': '表1',
        'effective_from': date(2007, 11, 1),
        'priority': 100,
        'applicability_json': json.dumps(
            {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
             'frequency_range': '100 kHz ~ 30 MHz'},
            ensure_ascii=False,
        ),
        'basis_text': (f'{GBZ_22_2007} 表1 工作场所高频电磁场职业接触限值；'
                       f'频率 f=0.1~3.0 MHz 时电场 ≤50 V/m，磁场 ≤5 A/m；'
                       f'f=3.0~30 MHz 时电场 ≤25 V/m；'
                       f'公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
    }

    # 0.1–3.0 MHz: 电场 ≤50 V/m, 磁场 ≤5 A/m
    dao.upsert_seed(
        indicator_name='高频电磁场-电场(0.1-3.0MHz)',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='V/m',
        limit_value=_d('50'),
        aliases_json=serialize_aliases(['HF EM field E', '高频电场强度 0.1-3.0MHz']),
        **spec,
    )
    dao.upsert_seed(
        indicator_name='高频电磁场-磁场(0.1-3.0MHz)',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='A/m',
        limit_value=_d('5'),
        aliases_json=serialize_aliases(['HF EM field H', '高频磁场强度 0.1-3.0MHz']),
        **spec,
    )
    # 3.0–30 MHz: 电场 ≤25 V/m
    dao.upsert_seed(
        indicator_name='高频电磁场-电场(3.0-30MHz)',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='V/m',
        limit_value=_d('25'),
        aliases_json=serialize_aliases(['HF EM field E 3-30MHz', '高频电场强度 3.0-30MHz']),
        **spec,
    )
    count += 3
    return count


def _seed_uhf_radiation(dao):
    """超高频辐射（30–300 MHz）GBZ 2.2-2007 表2"""
    spec = {
        'standard_name': '工作场所有害因素职业接触限值 第2部分：物理因素',
        'standard_code': GBZ_22_2007,
        'clause': '表2',
        'effective_from': date(2007, 11, 1),
        'priority': 100,
        'applicability_json': json.dumps(
            {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
             'frequency_range': '30 ~ 300 MHz'},
            ensure_ascii=False,
        ),
        'basis_text': (f'{GBZ_22_2007} 表2 工作场所超高频辐射职业接触限值；'
                       f'连续波：功率密度 ≤0.05 mW/cm² (8h)；脉冲波：≤0.025 mW/cm² (8h)；'
                       f'公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
    }
    count = 0
    dao.upsert_seed(
        indicator_name='超高频辐射-连续波',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='mW/cm2',
        limit_value=_d('0.05'),
        aliases_json=serialize_aliases(['UHF continuous wave', 'UHF CW', '30-300MHz 连续波']),
        **spec,
    )
    count += 1
    dao.upsert_seed(
        indicator_name='超高频辐射-脉冲波',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='mW/cm2',
        limit_value=_d('0.025'),
        aliases_json=serialize_aliases(['UHF pulse wave', 'UHF PW', '30-300MHz 脉冲波']),
        **spec,
    )
    count += 1
    return count


def _seed_microwave_radiation(dao):
    """微波辐射（300 MHz–300 GHz）GBZ 2.2-2007 表3"""
    spec = {
        'standard_name': '工作场所有害因素职业接触限值 第2部分：物理因素',
        'standard_code': GBZ_22_2007,
        'clause': '表3',
        'effective_from': date(2007, 11, 1),
        'priority': 100,
        'applicability_json': json.dumps(
            {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
             'frequency_range': '300 MHz ~ 300 GHz'},
            ensure_ascii=False,
        ),
        'basis_text': (f'{GBZ_22_2007} 表3 工作场所微波辐射职业接触限值；'
                       f'全身辐射连续波日剂量 ≤400 μW·h/cm²，脉冲波 ≤200 μW·h/cm²；'
                       f'肢体局部辐射连续波日剂量 ≤4000 μW·h/cm²，脉冲波 ≤2000 μW·h/cm²；'
                       f'瞬时功率密度 ≤5 mW/cm² (连续波) / ≤2.5 mW/cm² (脉冲波)；'
                       f'公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
    }
    count = 0
    records = [
        ('微波辐射-全身-连续波-日剂量', ['Microwave WB CW dose'], 'μW·h/cm2', '400'),
        ('微波辐射-全身-脉冲波-日剂量', ['Microwave WB PW dose'], 'μW·h/cm2', '200'),
        ('微波辐射-肢体-连续波-日剂量', ['Microwave limb CW dose'], 'μW·h/cm2', '4000'),
        ('微波辐射-肢体-脉冲波-日剂量', ['Microwave limb PW dose'], 'μW·h/cm2', '2000'),
        ('微波辐射-连续波-瞬时功率密度', ['Microwave CW peak PD'], 'mW/cm2', '5'),
        ('微波辐射-脉冲波-瞬时功率密度', ['Microwave PW peak PD'], 'mW/cm2', '2.5'),
    ]
    for name, aliases, unit, value in records:
        dao.upsert_seed(
            indicator_name=name,
            medium=SampleMedium.PHYSICAL_FACTOR,
            limit_type=LimitType.INSTANT,
            unit=unit,
            limit_value=_d(value),
            aliases_json=serialize_aliases(aliases),
            **spec,
        )
        count += 1
    return count


def _seed_uv_radiation(dao):
    """紫外辐射 GBZ 2.2-2007 表4"""
    spec = {
        'standard_name': '工作场所有害因素职业接触限值 第2部分：物理因素',
        'standard_code': GBZ_22_2007,
        'clause': '表4',
        'effective_from': date(2007, 11, 1),
        'priority': 100,
        'applicability_json': json.dumps(
            {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
             'wavelength_range': '100 ~ 400 nm'},
            ensure_ascii=False,
        ),
        'basis_text': (f'{GBZ_22_2007} 表4 工作场所紫外辐射职业接触限值；'
                       f'8h 辐照度限值因波长而异；公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
    }
    count = 0
    # 不同波段的紫外辐射限值（照射限值，单位 μW/cm² 或 mJ/cm²）
    dao.upsert_seed(
        indicator_name='紫外辐射(中波紫外线 UVB/短波紫外线 UVC)',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='μW/cm2',
        limit_value=_d('0.5'),  # 8h 辐照度（近似，实际按 ACGIH TLV 对照）
        aliases_json=serialize_aliases(['UV radiation', 'UVB/UVC', '紫外辐射 280-315nm']),
        **spec,
    )
    count += 1
    dao.upsert_seed(
        indicator_name='紫外辐射(长波紫外线 UVA)',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='mW/cm2',
        limit_value=_d('1.0'),  # 8h 总辐照度
        aliases_json=serialize_aliases(['UVA', '黑光', '315-400nm']),
        **spec,
    )
    count += 1
    return count


def _seed_laser_radiation(dao):
    """激光辐射 GBZ 2.2-2007 表5（眼和皮肤最大允许照射量 MPE）"""
    spec = {
        'standard_name': '工作场所有害因素职业接触限值 第2部分：物理因素',
        'standard_code': GBZ_22_2007,
        'clause': '表5',
        'effective_from': date(2007, 11, 1),
        'priority': 100,
        'applicability_json': json.dumps(
            {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF},
            ensure_ascii=False,
        ),
        'basis_text': (f'{GBZ_22_2007} 表5 激光辐射职业接触限值（眼和皮肤 MPE）；'
                       f'具体限值因波长和照射时间而异；公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
    }
    count = 0
    # 代表性波段：可见光/近红外连续激光 (400–1400 nm)，照射时间 >10 s
    dao.upsert_seed(
        indicator_name='激光辐射(可见光/近红外-眼直射)',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='W/cm2',
        limit_value=_d('0.001'),  # 角膜照射 MPE (400-700nm 连续 >10s ≈ 1 mW/cm²)
        aliases_json=serialize_aliases(['Laser eye', 'Laser 400-1400nm', '激光眼照射']),
        **spec,
    )
    count += 1
    dao.upsert_seed(
        indicator_name='激光辐射(远红外-皮肤/角膜 CO2激光)',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='W/cm2',
        limit_value=_d('0.1'),  # 10.6 μm CO2 激光，>10 s 皮肤/角膜 MPE ≈ 0.1 W/cm²
        aliases_json=serialize_aliases(['CO2 laser', 'Laser 10600nm', 'CO2激光皮肤']),
        **spec,
    )
    count += 1
    return count


def _seed_hand_transmitted_vibration(dao):
    """手传振动 GBZ 2.2-2007 表6"""
    dao.upsert_seed(
        standard_code=GBZ_22_2007,
        indicator_name='手传振动',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='m/s2',
        limit_value=_d('5'),  # 4h 等能量频率计权振动加速度
        aliases_json=serialize_aliases(
            ['Hand-transmitted vibration', 'Hand-arm vibration', 'HAV', '手臂振动', '局部振动']
        ),
        standard_name='工作场所有害因素职业接触限值 第2部分：物理因素',
        clause='表6',
        basis_text=(f'{GBZ_22_2007} 表6 手传振动职业接触限值；4h 等能量频率计权振动加速度 ≤5 m/s²；'
                    f'公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
        effective_from=date(2007, 11, 1),
        applicability_json=json.dumps(
            {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
             'exposure_duration_h': 4, 'measurement': '等能量频率计权振动加速度'},
            ensure_ascii=False,
        ),
        priority=100,
    )
    return 1


def _seed_whole_body_vibration(dao):
    """全身振动 GBZ 2.2-2007 表7"""
    dao.upsert_seed(
        standard_code=GBZ_22_2007,
        indicator_name='全身振动',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='m/s2',
        limit_value=_d('0.62'),  # 8h 等能量频率计权振动加速度 (Z轴)
        aliases_json=serialize_aliases(
            ['Whole-body vibration', 'WBV', '全身振动 Z轴']
        ),
        standard_name='工作场所有害因素职业接触限值 第2部分：物理因素',
        clause='表7',
        basis_text=(f'{GBZ_22_2007} 表7 全身振动职业接触限值；8h 等能量频率计权振动加速度 (Z轴) ≤0.62 m/s²；'
                    f'公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
        effective_from=date(2007, 11, 1),
        applicability_json=json.dumps(
            {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
             'exposure_duration_h': 8, 'axis': 'Z', 'measurement': '等能量频率计权振动加速度'},
            ensure_ascii=False,
        ),
        priority=100,
    )
    return 1


def _seed_physical_labor_intensity(dao):
    """体力劳动强度 GBZ 2.2-2007 表10（体力劳动强度指数 I）及 GBZ 1"""
    dao.upsert_seed(
        standard_code=GBZ_22_2007,
        indicator_name='体力劳动强度指数',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.RANGE,
        unit='—',
        limit_min=_d('0'),
        limit_max=_d('25'),  # GBZ 1 对 I>25 的限值约束
        aliases_json=serialize_aliases(
            ['Physical labor intensity index', 'I', '体力劳动强度分级指数', '劳动强度指数']
        ),
        standard_name='工作场所有害因素职业接触限值 第2部分：物理因素',
        clause='表10',
        basis_text=(f'{GBZ_22_2007} 表10 体力劳动强度分级；'
                    f'I≤15 为I级(轻)，15<I≤20 为II级(中)，20<I≤25 为III级(重)，I>25 为IV级(极重)；'
                    f'公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
        effective_from=date(2007, 11, 1),
        applicability_json=json.dumps(
            {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF},
            ensure_ascii=False,
        ),
        priority=100,
    )
    return 1


def _seed_illuminance(dao):
    """照度（GBZ 1-2010 工业企业设计卫生标准 / GB 50034 建筑照明设计标准引用）"""
    spec = {
        'standard_name': 'GBZ 1-2010 工业企业设计卫生标准（照明）',
        'standard_code': 'GBZ 1-2010',
        'clause': '6.8',
        'effective_from': date(2010, 8, 1),
        'priority': 100,
        'applicability_json': json.dumps(
            {'reference': 'GB 50034 建筑照明设计标准及 GBZ 1-2010'},
            ensure_ascii=False,
        ),
    }
    count = 0
    # 照度通常是下限（RANGE 限值），不同作业类型有不同要求
    dao.upsert_seed(
        indicator_name='照度(一般作业面)',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.RANGE,
        unit='lx',
        limit_min=_d('300'),  # GB 50034 一般作业面最小照度
        limit_max=None,
        aliases_json=serialize_aliases(['Illuminance general', '一般照明', '工作台面照度']),
        basis_text='GBZ 1-2010 §6.8 作业场所照明要求；一般作业面 ≥300 lx（参考 GB 50034）',
        **spec,
    )
    dao.upsert_seed(
        indicator_name='照度(精细作业面)',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.RANGE,
        unit='lx',
        limit_min=_d('500'),
        limit_max=None,
        aliases_json=serialize_aliases(['Illuminance fine work', '精细照明', '精密作业照度']),
        basis_text='GBZ 1-2010 §6.8 精细作业面 ≥500 lx（参考 GB 50034）',
        **spec,
    )
    count += 2
    return count


def _seed_elf_electric_magnetic_fields(dao):
    """1Hz–100kHz 电场/磁场（GBZ 2.2-2007 表11 + 职业卫生 IC 标准引用）"""
    spec = {
        'standard_name': '工作场所有害因素职业接触限值 第2部分：物理因素',
        'standard_code': GBZ_22_2007,
        'clause': '表11',
        'effective_from': date(2007, 11, 1),
        'priority': 100,
        'applicability_json': json.dumps(
            {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
             'frequency_range': '1 Hz ~ 100 kHz'},
            ensure_ascii=False,
        ),
    }
    count = 0
    # 工频电场 50 Hz — 已有 seed，此处补充低频磁场
    dao.upsert_seed(
        indicator_name='工频磁场(50Hz)',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='μT',
        limit_value=_d('100'),  # 职业暴露参考水平 (ICNIRP 2010)
        aliases_json=serialize_aliases(['Power-frequency magnetic field', '50Hz 磁场', 'ELF MF 50Hz']),
        basis_text=(f'{GBZ_22_2007} 表11 + ICNIRP 2010 导则；'
                    f'工频磁场 50 Hz 职业暴露参考水平 100 μT (8h)；公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
        **spec,
    )
    count += 1
    # 1Hz–100kHz 电场（非工频段），取典型值
    dao.upsert_seed(
        indicator_name='低频电场(1Hz-100kHz)',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='kV/m',
        limit_value=_d('5'),  # 职业暴露参考水平 (8h, 取 0.025-0.82 kHz 参考值 5 kV/m)
        aliases_json=serialize_aliases(['ELF electric field', '低频电场', '1Hz-100kHz E-field']),
        basis_text=(f'{GBZ_22_2007} 表11 + ICNIRP 2010 导则；'
                    f'1Hz–100kHz 电场职业暴露参考水平；公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
        **spec,
    )
    count += 1
    return count


def _seed_noise(dao):
    """噪声 GBZ 2.2-2007 表9（已有此函数，保留以确保幂等）"""
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
        basis_text=(f'{GBZ_22_2007} 表9 工作场所噪声职业接触限值；'
                    f'8h 等效声级 ≤85 dB(A)；公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
        effective_from=date(2007, 11, 1),
        applicability_json=json.dumps(
            {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
             'exposure_basis': '5d/w, 8h/d 等效声级'},
            ensure_ascii=False,
        ),
        priority=100,
    )
    return 1


def _seed_high_temperature(dao):
    """高温 WBGT GBZ 2.2-2007 表8"""
    workload_labels = {'I': '轻劳动', 'II': '中等劳动', 'III': '重劳动', 'IV': '极重劳动'}
    rows = (
        ('100', 'I', '30'), ('100', 'II', '28'), ('100', 'III', '26'), ('100', 'IV', '25'),
        ('75', 'I', '31'), ('75', 'II', '29'), ('75', 'III', '28'), ('75', 'IV', '26'),
        ('50', 'I', '32'), ('50', 'II', '30'), ('50', 'III', '29'), ('50', 'IV', '28'),
        ('25', 'I', '33'), ('25', 'II', '32'), ('25', 'III', '31'), ('25', 'IV', '30'),
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
                [f'WBGT-{workload_level}-{contact_rate}%',
                 f'高温-{workload_level}级-{contact_rate}%',
                 f'高温WBGT-{workload_label}-{contact_rate}%']
            ),
            standard_name='工作场所有害因素职业接触限值 第2部分：物理因素',
            clause='表8',
            basis_text=(f'{GBZ_22_2007} 表8 高温 WBGT 限值；'
                        f'接触时间率 {contact_rate}%，体力劳动强度 {workload_level}级 ({workload_label})；'
                        f'公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
            effective_from=date(2007, 11, 1),
            applicability_json=json.dumps(
                {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
                 'contact_time_rate_percent': int(contact_rate),
                 'physical_workload_level': workload_level,
                 'physical_workload_label': workload_label},
                ensure_ascii=False,
            ),
            priority=100,
        )
    return len(rows)


def _seed_power_frequency_electric_field(dao):
    """工频电场 50 Hz GBZ 2.2-2007 表11"""
    dao.upsert_seed(
        standard_code=GBZ_22_2007,
        indicator_name='工频电场',
        medium=SampleMedium.PHYSICAL_FACTOR,
        limit_type=LimitType.INSTANT,
        unit='kV/m',
        limit_value=_d('5'),
        aliases_json=serialize_aliases(['Power-frequency electric field', '50Hz 电场', '工频电场强度']),
        standard_name='工作场所有害因素职业接触限值 第2部分：物理因素',
        clause='表11',
        basis_text=(f'{GBZ_22_2007} 表11 工频电场职业接触限值；8h 工作日 ≤5 kV/m；'
                    f'公开来源：{GBZ_22_2007_SOURCE_PAGE}'),
        effective_from=date(2007, 11, 1),
        applicability_json=json.dumps(
            {'source_page_url': GBZ_22_2007_SOURCE_PAGE, 'source_pdf_url': GBZ_22_2007_SOURCE_PDF,
             'frequency_hz': 50, 'exposure_basis': '8h 工作日'},
            ensure_ascii=False,
        ),
        priority=100,
    )
    return 1


# =============================================================================
# 主入口
# =============================================================================

def seed():
    with SessionLocal() as session:
        dao = RegulatoryLimitDAO(session)
        count = 0

        # --- GBZ 2.1-2019 表1 化学因素 PC-TWA + PC-STEL ---
        for name, aliases, cas, mw, twa, stel in CHEMICALS_TWA_STEL:
            count += _seed_chemical(
                dao,
                indicator_name=name,
                aliases=aliases,
                cas_no=cas,
                molecular_weight=mw,
                pc_twa=twa,
                pc_stel=stel,
            )

        # --- GBZ 2.1-2019 表1 化学因素 MAC ---
        for name, aliases, cas, mw, mac in MAC_ONLY:
            count += _seed_chemical_mac(
                dao,
                indicator_name=name,
                aliases=aliases,
                cas_no=cas,
                molecular_weight=mw,
                mac_value=mac,
            )

        # --- GBZ 2.1-2019 表2 粉尘 ---
        for name, aliases, cas, twa_total, twa_resp in DUST_RECORDS:
            count += _seed_dust(
                dao,
                indicator_name=name,
                aliases=aliases,
                cas_no=cas,
                pc_twa_total=twa_total,
                pc_twa_respirable=twa_resp,
            )

        # --- GBZ 2.2-2007 物理因素 ---
        count += _seed_noise(dao)
        count += _seed_high_temperature(dao)
        count += _seed_power_frequency_electric_field(dao)
        count += _seed_high_frequency_em_field(dao)
        count += _seed_uhf_radiation(dao)
        count += _seed_microwave_radiation(dao)
        count += _seed_uv_radiation(dao)
        count += _seed_laser_radiation(dao)
        count += _seed_hand_transmitted_vibration(dao)
        count += _seed_whole_body_vibration(dao)
        count += _seed_physical_labor_intensity(dao)
        count += _seed_illuminance(dao)
        count += _seed_elf_electric_magnetic_fields(dao)

        return count


if __name__ == '__main__':
    print(f'seeded_or_updated={seed()}')
