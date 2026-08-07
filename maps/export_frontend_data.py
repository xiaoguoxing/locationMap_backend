#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前端数据导出脚本 —— 把 Python 侧的聚合结果导成前端可直接消费的 JSON

设计原则（重要）：
产物的 JSON 结构完全按"后端接口响应"的形态设计，即统一响应包装
{ success, code, message, data, timestamp, requestId } + GeoJSON FeatureCollection。
这样将来 Python 侧真的提供 HTTP 接口时，前端只需把 queryFn 里读静态文件
改成发请求，组件与 TypeScript 类型定义完全不用动。

导出内容（落到 apps/web/public/data/）：
  boundary/districts.json      18 区边界 GeoJSON（保留繁中属性键名）
  boundary/tpu.json            292 个 TPU 细分区边界 GeoJSON（简化后）
  metadata/parameters.json     参数元数据 + 色阶规则（前端图例与判色的唯一来源）
  metadata/date-ranges.json    可用日期区间清单
  measurement/{param}_{range}_{viewType}.json   各视图的水质数据

用法：
    python maps/export_frontend_data.py                      # 导出最新一个日期区间
    python maps/export_frontend_data.py --date-range 2026-04-10_2026-04-16
    python maps/export_frontend_data.py --all-ranges         # 导出全部区间（文件较多）
"""

import argparse
import glob
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from shapely.geometry import Point, mapping, shape
from shapely.strtree import STRtree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from choropleth_mapper import (
    DISTRICT_CENTROID_ADJUSTMENTS,
    DISTRICT_NAMES_TC,
    MULTI_PARAM_DISPLAY,
    get_adjusted_centroid,
)
from district_aggregator import get_color_for_district
from multi_param_mapper import (
    PARAMETER_PRIORITY,
    aggregate_all_parameters,
    read_csv_safe,
)

# 注意：不 import location_mapper。该模块在导入时会改写 sys.stdout
# （codecs.getwriter 包装），一旦本脚本输出被重定向到文件就会抛
# AttributeError: '_io.BufferedWriter' object has no attribute 'buffer'。
# 明细视图所需的 GPS 过滤逻辑在本文件的 read_detail_csv() 中等价实现。

PROJECT_ROOT = Path(__file__).parent.parent
MAPS_DATA = Path(__file__).parent / 'data'
CSV_DIR = PROJECT_ROOT / 'gencsv' / 'output'
DISTRICT_GEOJSON = MAPS_DATA / 'hk_districts.geojson'
# 简化成品优先；原始缓存（22 MB）为可选回退，不进版本库
TPU_SIMPLIFIED = MAPS_DATA / 'hk_tpu_simplified.geojson'
TPU_RAW_CACHE = MAPS_DATA / '_tpu_raw_cache.json'

# 前端静态数据目录（与 apps/web 约定一致）
WEB_PUBLIC_DATA = Path(
    r'd:\companyProject\HK_WQMS_web\apps\web\public\data')

# TPU 边界简化容差：中精度（约 10 米），兼顾细节与体积
TPU_TOLERANCE = 0.0001

# 坐标与数值精度（与后端 spec 一致：坐标 6 位、测量值 2 位）
COORD_PRECISION = 6
VALUE_PRECISION = 2


# ==========================================
# 色阶定义（唯一来源，与 district_aggregator.get_color_for_district 严格对应）
# ==========================================
# 说明：Python 侧判色用的是连续区间，而旧 dashboard.html 图例文字写的是取整值
# （如 1.6-2.0）。此处 min/max 用于前端判色，description 用于图例展示，两者分开。
#
# 区间语义（务必与 district_aggregator.get_color_for_district 严格一致）：
#   minExclusive=True  → 下界开区间（value > min）
#   minExclusive=False → 下界闭区间（value >= min）
#   上界一律闭区间（value <= max）
# Python 侧写法是 `elif value <= 1.5: green` 这种链式判断，等价于"上界含端点"。
# 早期版本按后端 spec 的 [min, max) 半开区间导出，导致 value=1.5 / 2.0 / 3.0
# 等边界点判色与 Python 版不一致（实测 6 处），故改为下面这套。
COLOR_SCALES: Dict[str, List[dict]] = {
    # 对应 Python: value < 0.2 红 / <= 1.5 绿 / <= 2.0 橙 / <= 3.0 深红 / else 红
    'cl2_free_1': [
        {'level': 'Insufficient', 'color': 'red', 'hex': '#DC3545',
         'min': None, 'max': 0.2, 'minExclusive': False, 'maxInclusive': False,
         'description': '< 0.2'},
        {'level': 'Satisfactory', 'color': 'green', 'hex': '#198754',
         'min': 0.2, 'max': 1.5, 'minExclusive': False, 'maxInclusive': True,
         'description': '0.2 – 1.5'},
        {'level': 'SlightlyHigh', 'color': 'orange', 'hex': '#FFC107',
         'min': 1.5, 'max': 2.0, 'minExclusive': True, 'maxInclusive': True,
         'description': '1.6 – 2.0'},
        {'level': 'High', 'color': 'darkred', 'hex': '#8B0000',
         'min': 2.0, 'max': 3.0, 'minExclusive': True, 'maxInclusive': True,
         'description': '2.1 – 3.0'},
        {'level': 'VeryHigh', 'color': 'red', 'hex': '#DC3545',
         'min': 3.0, 'max': None, 'minExclusive': True, 'maxInclusive': False,
         'description': '> 3.0'},
    ],
    # 对应 Python: value == 0 绿 / > 0 红
    # 已知差异（不可达输入，不修正）：Python 侧写法是 `if value == 0: green else: red`，
    # 因此负值会被判红；此处按区间语义负值判绿。菌落计数为非负整数，负值不会出现。
    'ecoli': [
        {'level': 'Satisfactory', 'color': 'green', 'hex': '#198754',
         'min': None, 'max': 0.0, 'minExclusive': False, 'maxInclusive': True,
         'description': '0'},
        {'level': 'Unsatisfactory', 'color': 'red', 'hex': '#DC3545',
         'min': 0.0, 'max': None, 'minExclusive': True, 'maxInclusive': False,
         'description': '> 0'},
    ],
    # 对应 Python: value <= 1.5 绿 / <= 3.0 橙 / <= 10.0 深红 / else 红
    'turby': [
        {'level': 'Satisfactory', 'color': 'green', 'hex': '#198754',
         'min': None, 'max': 1.5, 'minExclusive': False, 'maxInclusive': True,
         'description': '≤ 1.5'},
        {'level': 'SlightlyHigh', 'color': 'orange', 'hex': '#FFC107',
         'min': 1.5, 'max': 3.0, 'minExclusive': True, 'maxInclusive': True,
         'description': '1.6 – 3.0'},
        {'level': 'High', 'color': 'darkred', 'hex': '#8B0000',
         'min': 3.0, 'max': 10.0, 'minExclusive': True, 'maxInclusive': True,
         'description': '3.1 – 10.0'},
        {'level': 'VeryHigh', 'color': 'red', 'hex': '#DC3545',
         'min': 10.0, 'max': None, 'minExclusive': True, 'maxInclusive': False,
         'description': '> 10.0'},
    ],
}

# 参数展示元数据（display_name / unit 与 Python 侧保持一致）
PARAMETER_META = {
    'cl2_free_1': {'displayName': 'Free Chlorine', 'unit': 'mg/L', 'shortName': 'Cl2'},
    'ecoli': {'displayName': 'E. coli', 'unit': 'cfu/100mL', 'shortName': 'E.coli'},
    'turby': {'displayName': 'Turbidity', 'unit': 'NTU', 'shortName': 'Turbidity'},
    'all_params': {'displayName': 'All Parameters', 'unit': '', 'shortName': 'All'},
}


def wrap_response(data) -> dict:
    """
    套用统一响应包装（与后端 spec 的 ApiResponse 结构一致）

    前端读静态文件与读接口拿到的外层结构完全相同，便于将来无缝切换。
    """
    return {
        'success': True,
        'code': 200,
        'message': '',
        'data': data,
        'timestamp': int(time.time() * 1000),
        'requestId': str(uuid.uuid4()),
    }


def round_coord(value: float) -> float:
    """坐标统一保留 6 位小数"""
    return round(float(value), COORD_PRECISION)


def round_value(value) -> Optional[float]:
    """测量值统一保留 2 位小数；无效值返回 None"""
    if value is None or pd.isna(value):
        return None
    return round(float(value), VALUE_PRECISION)


def resolve_level(parameter: str, value) -> Optional[str]:
    """
    按色阶区间解析等级标签

    与 get_color_for_district 同源：颜色由前端按 level 查色阶表得到，
    避免前端硬编码阈值（旧 dashboard.html 与 cluster_map.py 曾各持一套且不一致）。
    """
    if value is None or pd.isna(value):
        return None
    bands = COLOR_SCALES.get(parameter)
    if not bands:
        return None
    val = float(value)
    for band in bands:
        if band['min'] is None:
            low_ok = True
        elif band.get('minExclusive'):
            low_ok = val > band['min']
        else:
            low_ok = val >= band['min']

        if band['max'] is None:
            high_ok = True
        elif band.get('maxInclusive'):
            high_ok = val <= band['max']
        else:
            high_ok = val < band['max']

        if low_ok and high_ok:
            return band['level']
    return None


def write_json(path: Path, payload: dict) -> None:
    """写出 JSON（紧凑格式，减小体积）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(',', ':'))
    size_kb = path.stat().st_size / 1024
    rel = path.relative_to(WEB_PUBLIC_DATA) if WEB_PUBLIC_DATA in path.parents else path
    print('  [WRITE] {} ({:.0f} KB)'.format(rel, size_kb))


# ==========================================
# 1. 边界数据导出
# ==========================================

def export_district_boundary() -> None:
    """
    导出 18 区边界 GeoJSON

    保留原始繁中属性键名（地區號碼 / District / 地區），前端按 District 关联数据。
    另外预先算好每个区的标注锚点（含 Python 侧的手工偏移），前端直接用，
    避免在 JS 里重算 shoelace 质心和维护第二份偏移表。
    """
    with open(DISTRICT_GEOJSON, 'r', encoding='utf-8') as handle:
        geojson = json.load(handle)

    for feature in geojson['features']:
        district = feature['properties'].get('District')
        # 中文区名（来自 choropleth_mapper.DISTRICT_NAMES_TC）
        feature['properties']['districtTc'] = DISTRICT_NAMES_TC.get(district, district)

        # 标注锚点：面积加权质心 + 手工偏移（Tsuen Wan / Kwun Tong / North 等 5 个区）
        centroid = get_adjusted_centroid(district, feature['geometry'])
        if centroid:
            feature['properties']['labelAnchor'] = [
                round_coord(centroid[0]), round_coord(centroid[1])]
            adjust = DISTRICT_CENTROID_ADJUSTMENTS.get(district)
            if adjust:
                feature['properties']['labelAdjusted'] = True

    write_json(WEB_PUBLIC_DATA / 'boundary' / 'districts.json', wrap_response(geojson))


def export_tpu_boundary() -> None:
    """
    导出 292 个 TPU 细分区边界 GeoJSON（简化后）

    数据来源：CSDI 门户规划署 TPU 数据集（OGC WFS），原始 22 MB / 867732 个顶点，
    按 tolerance=0.0001（约 10 米）简化到约 3.6 万顶点，属性只保留 TPU_NUMBER。
    """
    # 优先用已简化好的成品；没有才回退到原始缓存重新简化
    if TPU_SIMPLIFIED.exists():
        with open(TPU_SIMPLIFIED, 'r', encoding='utf-8') as handle:
            write_json(WEB_PUBLIC_DATA / 'boundary' / 'tpu.json',
                       wrap_response(json.load(handle)))
        return

    if not TPU_RAW_CACHE.exists():
        print('  [SKIP] 未找到 TPU 边界数据，跳过 TPU 导出')
        print('  [HINT] 先运行: python maps/fetch_tpu_boundary.py')
        return

    with open(TPU_RAW_CACHE, 'r', encoding='utf-8') as handle:
        raw = json.load(handle)

    features = []
    for feature in raw.get('features', []):
        geometry = feature.get('geometry')
        if not geometry:
            continue
        try:
            geom = shape(geometry).simplify(TPU_TOLERANCE, preserve_topology=True)
        except Exception:
            continue
        if geom.is_empty:
            continue
        features.append({
            'type': 'Feature',
            'properties': {
                'TPU_NUMBER': (feature.get('properties') or {}).get('TPU_NUMBER'),
            },
            'geometry': mapping(geom),
        })

    payload = {'type': 'FeatureCollection', 'features': features}
    write_json(WEB_PUBLIC_DATA / 'boundary' / 'tpu.json', wrap_response(payload))


# ==========================================
# 2. 元数据导出
# ==========================================

def export_parameter_metadata() -> None:
    """
    导出参数元数据与色阶规则

    这是前端图例与判色的唯一来源。前端不得硬编码阈值，
    必须按 colorScale 的 min/max 区间匹配 level，再由 level 取 hex 颜色。
    """
    items = []
    for param in PARAMETER_PRIORITY:
        meta = PARAMETER_META[param]
        items.append({
            'parameter': param,
            'displayName': meta['displayName'],
            'unit': meta['unit'],
            'shortName': meta['shortName'],
            'colorScale': COLOR_SCALES[param],
        })

    # all_params：色阶按 cl2_free_1 + ecoli + turby 顺序拼接（同源复用，不重新定义）
    all_bands = []
    for param in PARAMETER_PRIORITY:
        for band in COLOR_SCALES[param]:
            all_bands.append(dict(band, parameter=param))
    items.append({
        'parameter': 'all_params',
        'displayName': PARAMETER_META['all_params']['displayName'],
        'unit': '',
        'shortName': PARAMETER_META['all_params']['shortName'],
        'colorScale': all_bands,
    })

    write_json(WEB_PUBLIC_DATA / 'metadata' / 'parameters.json', wrap_response(items))


def discover_date_ranges() -> List[str]:
    """扫描 gencsv/output 下的 CSV，汇总所有可用日期区间"""
    pattern = re.compile(r'^(?:cl2_free_1|ecoli|turby)_(\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2})_')
    ranges = set()
    for path in CSV_DIR.glob('*.csv'):
        match = pattern.match(path.name)
        if match:
            ranges.add(match.group(1))
    return sorted(ranges)


def export_date_ranges(ranges: List[str], exported: List[str]) -> None:
    """
    导出日期区间清单

    排序与 Python 版 dashboard.js::processMapsData 一致：按起始日期倒序
    （最新的排最前），前端下拉框第一项即最新区间。
    exported 标记哪些区间已导出数据文件，前端据此禁用未导出的选项。
    """
    items = []
    for date_range in sorted(ranges, reverse=True):
        parts = date_range.split('_')
        items.append({
            'dateRange': date_range,
            'dateFrom': parts[0],
            'dateTo': parts[1] if len(parts) > 1 else parts[0],
            'exported': date_range in exported,
        })
    write_json(WEB_PUBLIC_DATA / 'metadata' / 'date-ranges.json', wrap_response(items))


# ==========================================
# 3. 水质数据导出（三种视图，对应 Python 版 dashboard 的 viewType）
# ==========================================

def build_meta(date_range: str, parameter: str, view_type: str,
               feature_count: int, dropped: int, duration_ms: int) -> dict:
    """构建 FeatureCollection 的 meta（字段与后端 spec 对齐）"""
    parts = date_range.split('_')
    return {
        'parameter': parameter,
        'dateFrom': parts[0],
        'dateTo': parts[1] if len(parts) > 1 else parts[0],
        'viewType': view_type,
        'featureCount': feature_count,
        'droppedInvalidCoordinateCount': dropped,
        'queryDurationMs': duration_ms,
    }


def export_district_view(date_range: str, parameter: str) -> bool:
    """
    导出 district 视图：18 区聚合着色

    对应 Python 版 create_choropleth_map：每区一个 Feature，几何为区边界的
    标注锚点（Point），properties 含均值 / 最大值 / 样本数 / 色阶等级。
    """
    started = time.time()
    matches = sorted(CSV_DIR.glob('{}_{}*.csv'.format(parameter, date_range)))
    if not matches:
        return False

    df = read_csv_safe(matches[0], parameter)
    if df is None or len(df) == 0:
        return False

    merged = aggregate_all_parameters({parameter: df}, str(DISTRICT_GEOJSON))

    with open(DISTRICT_GEOJSON, 'r', encoding='utf-8') as handle:
        districts = json.load(handle)

    features = []
    for feature in districts['features']:
        district = feature['properties'].get('District')
        stats = merged.get(district, {}).get(parameter)
        if not stats or stats.get('avg') is None:
            continue

        centroid = get_adjusted_centroid(district, feature['geometry'])
        if centroid is None:
            continue

        avg = round_value(stats.get('avg'))
        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [round_coord(centroid[0]), round_coord(centroid[1])],
            },
            'properties': {
                'district': district,
                'districtTc': DISTRICT_NAMES_TC.get(district, district),
                'parameter': parameter,
                'avgValue': avg,
                'maxValue': round_value(stats.get('max')),
                'sampleCount': int(stats.get('count', 0)),
                'unit': stats.get('unit', ''),
                'colorLevel': resolve_level(parameter, stats.get('avg')),
            },
        })

    duration = int((time.time() - started) * 1000)
    payload = {
        'type': 'FeatureCollection',
        'features': features,
        'meta': build_meta(date_range, parameter, 'district', len(features), 0, duration),
    }
    write_json(
        WEB_PUBLIC_DATA / 'measurement' / '{}_{}_district.json'.format(parameter, date_range),
        wrap_response(payload))
    return True


def read_detail_csv(csv_path: Path) -> Optional[pd.DataFrame]:
    """
    读取采样明细 CSV 并做列名规整

    等价于 location_mapper.read_and_filter_csv 的读取部分：
    - 全部列按字符串读入，跳过坏行（原始 CSV 存在列数不一致的脏行）
    - 列名统一小写去空格（原始表头末列带 \\r）
    - GPS 列名兼容 loc_gps_latitude / loc_gps_latitude_value 两种写法
    坐标有效性校验留给调用方逐行处理，以便统计 dropped 数量。
    """
    try:
        df = pd.read_csv(
            csv_path,
            encoding='utf-8',
            on_bad_lines='skip',
            dtype=str,
            skipinitialspace=True,
        )
    except Exception as exc:
        print('  [WARN] 读取失败 {}: {}'.format(csv_path.name, exc))
        return None

    df.columns = [str(col).lower().strip() for col in df.columns]

    # GPS 列兼容：优先用带 _value 后缀的（Python 侧 SQL 里那列是 try_cast 后的数值）
    for target, candidates in (
        ('loc_gps_latitude', ['loc_gps_latitude', 'loc_gps_latitude_value', 'latitude', 'lat']),
        ('loc_gps_longitude', ['loc_gps_longitude', 'loc_gps_longitude_value', 'longitude', 'lon']),
    ):
        if target in df.columns and df[target].notna().any():
            continue
        for candidate in candidates:
            if candidate in df.columns and df[candidate].notna().any():
                df[target] = df[candidate]
                break

    if 'district' in df.columns:
        df['district'] = df['district'].astype(str).str.lower().str.strip()

    return df


def export_detailed_view(date_range: str, parameter: str) -> bool:
    """
    导出 detailed 视图：采样点逐点数据

    对应 Python 版 create_detailed_point_map：每条有效 GPS 的采样记录一个 Feature，
    properties 字段与旧 popup 内容一致（样本号 / 测点编码 / 描述 / 区 / 采样日期 / 结果）。
    前端用聚类（Cluster）渲染，与 Python 版 MarkerCluster 行为对应。
    """
    started = time.time()
    matches = sorted(CSV_DIR.glob('{}_{}*.csv'.format(parameter, date_range)))
    if not matches:
        return False

    df = read_detail_csv(matches[0])
    if df is None or len(df) == 0:
        return False

    total_rows = len(df)
    unit = PARAMETER_META[parameter]['unit']
    features = []
    dropped = 0

    for _, row in df.iterrows():
        lat = row.get('loc_gps_latitude')
        lon = row.get('loc_gps_longitude')
        result = row.get('result')

        # 坐标有效性校验（与后端 spec 的规则一致）
        try:
            lat_f, lon_f = float(lat), float(lon)
        except (TypeError, ValueError):
            dropped += 1
            continue
        if not (-90 <= lat_f <= 90) or not (-180 <= lon_f <= 180):
            dropped += 1
            continue

        value = round_value(result)
        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [round_coord(lon_f), round_coord(lat_f)],
            },
            'properties': {
                'sampleNo': _clean(row.get('sampno')),
                'locationCode': _clean(row.get('loccode')),
                'locationDesc': _clean(row.get('locdescr')),
                'district': _clean(row.get('district')),
                'collectedAt': _clean(row.get('coldate')),
                'owner': _clean(row.get('owner')),
                'parameter': parameter,
                'value': value,
                'unit': unit,
                'colorLevel': resolve_level(parameter, result),
            },
        })

    duration = int((time.time() - started) * 1000)
    payload = {
        'type': 'FeatureCollection',
        'features': features,
        'meta': build_meta(date_range, parameter, 'detailed', len(features), dropped, duration),
    }
    payload['meta']['totalRows'] = total_rows
    write_json(
        WEB_PUBLIC_DATA / 'measurement' / '{}_{}_detailed.json'.format(parameter, date_range),
        wrap_response(payload))
    return True


def _clean(value) -> Optional[str]:
    """CSV 字段清洗：NaN / 'nan' / 空串统一为 None"""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if text.lower() in ('nan', 'none', ''):
        return None
    return text


def export_all_param_view(date_range: str) -> bool:
    """
    导出 district_all_param 视图：18 区同时承载三个参数

    对应 Python 版 create_multi_param_choropleth_map：每区一个 Feature，
    properties 下按参数代码分子对象；着色由优先级最高的可用参数驱动
    （PARAMETER_PRIORITY 顺序：cl2_free_1 → ecoli → turby）。
    """
    started = time.time()

    param_dataframes = {}
    for param in PARAMETER_PRIORITY:
        matches = sorted(CSV_DIR.glob('{}_{}*.csv'.format(param, date_range)))
        if not matches:
            continue
        df = read_csv_safe(matches[0], param)
        if df is not None and len(df) > 0:
            param_dataframes[param] = df

    if not param_dataframes:
        return False

    merged = aggregate_all_parameters(param_dataframes, str(DISTRICT_GEOJSON))

    # 着色参数：按优先级取第一个有数据的
    color_param = next((p for p in PARAMETER_PRIORITY if p in param_dataframes), None)

    with open(DISTRICT_GEOJSON, 'r', encoding='utf-8') as handle:
        districts = json.load(handle)

    features = []
    for feature in districts['features']:
        district = feature['properties'].get('District')
        params = merged.get(district)
        if not params:
            continue

        centroid = get_adjusted_centroid(district, feature['geometry'])
        if centroid is None:
            continue

        props = {
            'district': district,
            'districtTc': DISTRICT_NAMES_TC.get(district, district),
            'colorParameter': color_param,
        }

        for param in PARAMETER_PRIORITY:
            stats = params.get(param)
            if stats and stats.get('avg') is not None:
                props[param] = {
                    'avgValue': round_value(stats.get('avg')),
                    'maxValue': round_value(stats.get('max')),
                    'sampleCount': int(stats.get('count', 0)),
                    'unit': stats.get('unit', PARAMETER_META[param]['unit']),
                    'colorLevel': resolve_level(param, stats.get('avg')),
                }
            else:
                props[param] = None

        # 整区着色等级取自着色参数
        color_stats = params.get(color_param) if color_param else None
        props['colorLevel'] = (
            resolve_level(color_param, color_stats.get('avg'))
            if color_stats and color_stats.get('avg') is not None else None)

        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [round_coord(centroid[0]), round_coord(centroid[1])],
            },
            'properties': props,
        })

    duration = int((time.time() - started) * 1000)
    payload = {
        'type': 'FeatureCollection',
        'features': features,
        'meta': build_meta(date_range, 'all_params', 'district_all_param',
                           len(features), 0, duration),
    }
    payload['meta']['availableParameters'] = list(param_dataframes.keys())
    write_json(
        WEB_PUBLIC_DATA / 'measurement' / 'all_params_{}_district_all_param.json'.format(date_range),
        wrap_response(payload))
    return True


def export_tpu_measurement(date_range: str) -> bool:
    """
    导出 TPU 级聚合数据

    与 18 区不同，CSV 里没有 TPU 字段，只能用采样点经纬度做「点在多边形内」判定。
    因此本视图受 GPS 覆盖率制约：CSV 中约三分之二的记录没有坐标，
    292 个 TPU 里通常只有 20 个左右能落到采样点，其余为无数据。
    前端对无数据的格子仍绘制轮廓，不做填色。
    """
    started = time.time()

    if not TPU_RAW_CACHE.exists():
        print('  [SKIP] 无 TPU 缓存，跳过 TPU 聚合')
        return False

    # 用与边界导出相同的简化结果做判定，保证前端点选与着色对得上
    with open(TPU_RAW_CACHE, 'r', encoding='utf-8') as handle:
        raw = json.load(handle)

    geoms = []
    numbers = []
    for feature in raw.get('features', []):
        geometry = feature.get('geometry')
        if not geometry:
            continue
        try:
            geom = shape(geometry).simplify(TPU_TOLERANCE, preserve_topology=True)
        except Exception:
            continue
        if geom.is_empty:
            continue
        geoms.append(geom)
        numbers.append((feature.get('properties') or {}).get('TPU_NUMBER'))

    if not geoms:
        return False

    tree = STRtree(geoms)

    # tpu_number -> parameter -> [values]
    buckets: Dict[str, Dict[str, List[float]]] = {}
    total_rows = 0
    gps_rows = 0
    outside = 0

    for param in PARAMETER_PRIORITY:
        for csv_path in sorted(CSV_DIR.glob('{}_{}*.csv'.format(param, date_range))):
            df = read_detail_csv(csv_path)
            if df is None:
                continue
            total_rows += len(df)

            for _, row in df.iterrows():
                try:
                    lat = float(row.get('loc_gps_latitude'))
                    lon = float(row.get('loc_gps_longitude'))
                    value = float(row.get('result'))
                except (TypeError, ValueError):
                    continue
                if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                    continue
                gps_rows += 1

                point = Point(lon, lat)
                matched = None
                for idx in tree.query(point):
                    if geoms[idx].contains(point):
                        matched = numbers[idx]
                        break
                if matched is None:
                    outside += 1
                    continue
                buckets.setdefault(str(matched), {}).setdefault(param, []).append(value)

    if not buckets:
        print('  [WARN] 该区间没有任何采样点落入 TPU')

    # 着色参数：与 all_params 视图一致，按优先级取首个有数据的
    color_param = None
    for param in PARAMETER_PRIORITY:
        if any(param in params for params in buckets.values()):
            color_param = param
            break

    features = []
    for tpu_number, params in buckets.items():
        props = {'TPU_NUMBER': tpu_number, 'colorParameter': color_param}
        for param in PARAMETER_PRIORITY:
            values = params.get(param)
            if values:
                avg = sum(values) / len(values)
                props[param] = {
                    'avgValue': round_value(avg),
                    'maxValue': round_value(max(values)),
                    'sampleCount': len(values),
                    'unit': PARAMETER_META[param]['unit'],
                    'colorLevel': resolve_level(param, avg),
                }
            else:
                props[param] = None

        color_stats = params.get(color_param) if color_param else None
        if color_stats:
            color_avg = sum(color_stats) / len(color_stats)
            props['avgValue'] = round_value(color_avg)
            props['colorLevel'] = resolve_level(color_param, color_avg)
        else:
            props['avgValue'] = None
            props['colorLevel'] = None

        # 几何用 TPU 编号索引，前端按编号关联边界，无需重复下发多边形
        features.append({'type': 'Feature', 'geometry': None, 'properties': props})

    duration = int((time.time() - started) * 1000)
    payload = {
        'type': 'FeatureCollection',
        'features': features,
        'meta': build_meta(date_range, 'all_params', 'district_all_param',
                           len(features), 0, duration),
    }
    payload['meta']['viewType'] = 'tpu'
    payload['meta']['tpuTotal'] = len(geoms)
    payload['meta']['tpuWithData'] = len(features)
    payload['meta']['gpsRows'] = gps_rows
    payload['meta']['totalRows'] = total_rows
    payload['meta']['outsideTpu'] = outside
    payload['meta']['colorParameter'] = color_param

    write_json(
        WEB_PUBLIC_DATA / 'measurement' / 'tpu_{}.json'.format(date_range),
        wrap_response(payload))
    print('  [TPU] {}/{} 个细分区有数据（GPS {}/{} 行）'.format(
        len(features), len(geoms), gps_rows, total_rows))
    return True


def export_range(date_range: str) -> bool:
    """导出单个日期区间的全部视图"""
    print('\n[RANGE] {}'.format(date_range))
    ok = False

    for param in PARAMETER_PRIORITY:
        if export_district_view(date_range, param):
            ok = True
        if export_detailed_view(date_range, param):
            ok = True

    if export_all_param_view(date_range):
        ok = True

    if export_tpu_measurement(date_range):
        ok = True

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description='导出前端所需的静态 JSON 数据')
    parser.add_argument('--date-range', help='指定日期区间，如 2026-04-10_2026-04-16')
    parser.add_argument('--all-ranges', action='store_true', help='导出全部日期区间')
    parser.add_argument('--output', help='覆盖输出目录（默认写入 apps/web/public/data）')
    args = parser.parse_args()

    global WEB_PUBLIC_DATA
    if args.output:
        WEB_PUBLIC_DATA = Path(args.output)

    print('[OUT] 输出目录: {}'.format(WEB_PUBLIC_DATA))

    available = discover_date_ranges()
    if not available:
        print('[ERROR] 未在 {} 找到任何 CSV'.format(CSV_DIR))
        return 1
    print('[INFO] 发现 {} 个日期区间'.format(len(available)))

    if args.all_ranges:
        targets = available
    elif args.date_range:
        if args.date_range not in available:
            print('[ERROR] 日期区间 {} 不存在。可用: {}'.format(
                args.date_range, ', '.join(available[:5])))
            return 1
        targets = [args.date_range]
    else:
        # 默认导出最新一个区间
        targets = [available[-1]]

    print('\n=== 1. 边界数据 ===')
    export_district_boundary()
    export_tpu_boundary()

    print('\n=== 2. 元数据 ===')
    export_parameter_metadata()

    print('\n=== 3. 水质数据 ===')
    exported = [r for r in targets if export_range(r)]

    export_date_ranges(available, exported)

    print('\n[DONE] 已导出 {} 个日期区间: {}'.format(len(exported), ', '.join(exported)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
