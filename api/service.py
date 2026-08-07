"""业务层：把数据源的采样记录聚合成各视图的 GeoJSON

四种视图（与前端 viewType 一一对应）：
    district            18 区聚合，单参数
    detailed            采样点逐点
    district_all_param  18 区聚合，三参数合并
    tpu                 292 个 TPU 细分区聚合

本层只依赖 repository 抽象接口，不感知数据源是 CSV 还是数据库。
"""

import time
from typing import Dict, List, Optional

import pandas as pd

from api import config, geography
from api.metadata import PARAMETER_META, PARAMETER_PRIORITY, resolve_level
from api.repository import get_repository
from api.response import BusinessException, ErrorCode


def _round_value(value) -> Optional[float]:
    """测量值统一保留 2 位小数；无效值返回 None"""
    if value is None or pd.isna(value):
        return None
    return round(float(value), config.VALUE_PRECISION)


def _round_coord(value) -> float:
    return round(float(value), config.COORD_PRECISION)


def _clean_text(value) -> Optional[str]:
    """字段清洗：NaN / 'nan' / 空串统一为 None"""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return None if text.lower() in ('nan', 'none', '') else text


def _valid_coords(df: pd.DataFrame) -> pd.DataFrame:
    """
    筛掉坐标无效的行

    无效定义：空值、非数值、超出经纬度取值域。
    与 Java 后端 spec 的规则一致。
    """
    if df.empty:
        return df
    mask = (
        df['latitude'].notna()
        & df['longitude'].notna()
        & df['latitude'].between(-90, 90)
        & df['longitude'].between(-180, 180)
    )
    return df[mask]


def _build_meta(parameter: str, date_from: str, date_to: str, view_type: str,
                feature_count: int, dropped: int, total_rows: int,
                started: float) -> dict:
    """构建 FeatureCollection 的 meta（字段与 Java 后端 spec 对齐）"""
    return {
        'parameter': parameter,
        'dateFrom': date_from,
        'dateTo': date_to,
        'viewType': view_type,
        'featureCount': feature_count,
        'droppedInvalidCoordinateCount': dropped,
        'totalRows': total_rows,
        'queryDurationMs': int((time.time() - started) * 1000),
    }


def _check_feature_limit(count: int) -> None:
    """结果集熔断：超过上限直接拒绝，避免拖垮前端渲染"""
    if count > config.MAX_FEATURE_COUNT:
        raise BusinessException(
            ErrorCode.RESULT_SET_TOO_LARGE,
            'Result set exceeds {} features; please narrow date range'.format(
                config.MAX_FEATURE_COUNT))


# ==========================================
# 区级聚合（district / district_all_param 共用）
# ==========================================

def _aggregate_by_district(df: pd.DataFrame, parameter: str) -> Dict[str, dict]:
    """
    按 18 区聚合

    注意：这里用 district 字段做区名归一化，不依赖坐标，
    因此无 GPS 的记录也能计入——这是 18 区视图能填满而 TPU 视图不能的原因。

    Returns:
        {官方区名: {avg, max, min, count}}
    """
    if df.empty:
        return {}

    working = df[['district', 'value']].copy()
    working = working[working['value'].notna()]
    if working.empty:
        return {}

    working['normalized'] = working['district'].map(geography.normalize_district)
    matched = working[working['normalized'].notna()]
    if matched.empty:
        return {}

    grouped = matched.groupby('normalized')['value'].agg(['mean', 'max', 'min', 'count'])

    result = {}
    for district, row in grouped.iterrows():
        result[district] = {
            'avg': float(row['mean']),
            'max': float(row['max']),
            'min': float(row['min']),
            'count': int(row['count']),
        }
    return result


def query_district_view(parameter: str, date_from: str, date_to: str) -> dict:
    """district 视图：18 区聚合，单参数"""
    started = time.time()
    repo = get_repository()
    df = repo.query_rows(parameter, date_from, date_to)
    total_rows = len(df)

    stats = _aggregate_by_district(df, parameter)
    anchors = geography.district_anchors()
    unit = PARAMETER_META[parameter]['unit']

    features = []
    for district, item in stats.items():
        anchor = anchors.get(district)
        if anchor is None:
            # 官方区界里找不到该区（理论上不会发生），跳过而非报错
            continue
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [anchor[0], anchor[1]]},
            'properties': {
                'district': district,
                'districtTc': geography.DISTRICT_NAMES_TC.get(district, district),
                'parameter': parameter,
                'avgValue': _round_value(item['avg']),
                'maxValue': _round_value(item['max']),
                'minValue': _round_value(item['min']),
                'sampleCount': item['count'],
                'unit': unit,
                'colorLevel': resolve_level(parameter, item['avg']),
            },
        })

    _check_feature_limit(len(features))
    return {
        'type': 'FeatureCollection',
        'features': features,
        'meta': _build_meta(parameter, date_from, date_to, 'district',
                            len(features), 0, total_rows, started),
    }


def query_all_param_view(date_from: str, date_to: str) -> dict:
    """
    district_all_param 视图：18 区聚合，三参数合并

    整区着色由优先级最高的可用参数驱动（cl2_free_1 → ecoli → turby）。
    """
    started = time.time()
    repo = get_repository()

    per_param: Dict[str, Dict[str, dict]] = {}
    total_rows = 0
    available: List[str] = []

    for param in PARAMETER_PRIORITY:
        df = repo.query_rows(param, date_from, date_to)
        if df.empty:
            continue
        total_rows += len(df)
        stats = _aggregate_by_district(df, param)
        if stats:
            per_param[param] = stats
            available.append(param)

    color_param = next((p for p in PARAMETER_PRIORITY if p in per_param), None)
    anchors = geography.district_anchors()

    # 汇总所有出现过的区
    districts = sorted({d for stats in per_param.values() for d in stats})

    features = []
    for district in districts:
        anchor = anchors.get(district)
        if anchor is None:
            continue

        props = {
            'district': district,
            'districtTc': geography.DISTRICT_NAMES_TC.get(district, district),
            'colorParameter': color_param,
        }

        for param in PARAMETER_PRIORITY:
            item = per_param.get(param, {}).get(district)
            if item:
                props[param] = {
                    'avgValue': _round_value(item['avg']),
                    'maxValue': _round_value(item['max']),
                    'sampleCount': item['count'],
                    'unit': PARAMETER_META[param]['unit'],
                    'colorLevel': resolve_level(param, item['avg']),
                }
            else:
                props[param] = None

        color_item = per_param.get(color_param, {}).get(district) if color_param else None
        props['colorLevel'] = (
            resolve_level(color_param, color_item['avg']) if color_item else None)

        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [anchor[0], anchor[1]]},
            'properties': props,
        })

    _check_feature_limit(len(features))
    meta = _build_meta('all_params', date_from, date_to, 'district_all_param',
                       len(features), 0, total_rows, started)
    meta['availableParameters'] = available
    meta['colorParameter'] = color_param
    return {'type': 'FeatureCollection', 'features': features, 'meta': meta}


# ==========================================
# 明细视图
# ==========================================

def query_detailed_view(parameter: str, date_from: str, date_to: str) -> dict:
    """
    detailed 视图：采样点逐点

    只输出坐标有效的记录，被剔除的数量记入 meta.droppedInvalidCoordinateCount。
    前端用聚类（Cluster）渲染这批点。
    """
    started = time.time()
    repo = get_repository()
    df = repo.query_rows(parameter, date_from, date_to)
    total_rows = len(df)

    valid = _valid_coords(df)
    # 测量值缺失的点仍保留（colorLevel 置 null），与 spec 一致
    dropped = total_rows - len(valid)
    unit = PARAMETER_META[parameter]['unit']

    _check_feature_limit(len(valid))

    features = []
    for _, row in valid.iterrows():
        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [_round_coord(row['longitude']), _round_coord(row['latitude'])],
            },
            'properties': {
                'sampleNo': _clean_text(row.get('sampleNo')),
                'locationCode': _clean_text(row.get('locationCode')),
                'locationDesc': _clean_text(row.get('locationDesc')),
                'district': _clean_text(row.get('district')),
                'collectedAt': _clean_text(row.get('collectedAt')),
                'owner': _clean_text(row.get('owner')),
                'parameter': parameter,
                'value': _round_value(row.get('value')),
                'unit': unit,
                'colorLevel': resolve_level(parameter, row.get('value')),
            },
        })

    return {
        'type': 'FeatureCollection',
        'features': features,
        'meta': _build_meta(parameter, date_from, date_to, 'detailed',
                            len(features), dropped, total_rows, started),
    }


# ==========================================
# TPU 细分区视图
# ==========================================

def query_tpu_view(date_from: str, date_to: str) -> dict:
    """
    tpu 视图：292 个细分区聚合

    与 18 区不同，采样记录里没有 TPU 字段，只能靠经纬度做「点在多边形内」
    判定，因此本视图受 GPS 覆盖率制约——无坐标的记录无法计入。
    实测 CSV 中约三分之二的记录缺坐标，292 个 TPU 里通常只有十几个有数据。
    无数据的细分区不出现在 features 里，前端仍会按边界绘制其轮廓。

    Feature 的 geometry 为 null：几何走 /boundary/tpu 接口，
    此处只按 TPU_NUMBER 下发统计值，避免同一份多边形重复传输。
    """
    started = time.time()

    if geography.tpu_index() is None:
        raise BusinessException(
            ErrorCode.NOT_FOUND,
            'TPU boundary data is unavailable on server')

    repo = get_repository()

    # tpu_number -> parameter -> [values]
    buckets: Dict[str, Dict[str, List[float]]] = {}
    total_rows = 0
    gps_rows = 0
    outside = 0

    for param in PARAMETER_PRIORITY:
        df = repo.query_rows(param, date_from, date_to)
        if df.empty:
            continue
        total_rows += len(df)

        valid = _valid_coords(df)
        valid = valid[valid['value'].notna()]
        gps_rows += len(valid)

        for _, row in valid.iterrows():
            tpu_number = geography.locate_tpu(
                float(row['longitude']), float(row['latitude']))
            if tpu_number is None:
                outside += 1
                continue
            buckets.setdefault(tpu_number, {}).setdefault(param, []).append(
                float(row['value']))

    color_param = next(
        (p for p in PARAMETER_PRIORITY
         if any(p in params for params in buckets.values())),
        None,
    )

    features = []
    for tpu_number, params in sorted(buckets.items()):
        props = {'TPU_NUMBER': tpu_number, 'colorParameter': color_param}

        for param in PARAMETER_PRIORITY:
            values = params.get(param)
            if values:
                avg = sum(values) / len(values)
                props[param] = {
                    'avgValue': _round_value(avg),
                    'maxValue': _round_value(max(values)),
                    'sampleCount': len(values),
                    'unit': PARAMETER_META[param]['unit'],
                    'colorLevel': resolve_level(param, avg),
                }
            else:
                props[param] = None

        color_values = params.get(color_param) if color_param else None
        if color_values:
            color_avg = sum(color_values) / len(color_values)
            props['avgValue'] = _round_value(color_avg)
            props['colorLevel'] = resolve_level(color_param, color_avg)
        else:
            props['avgValue'] = None
            props['colorLevel'] = None

        features.append({'type': 'Feature', 'geometry': None, 'properties': props})

    _check_feature_limit(len(features))

    index = geography.tpu_index()
    meta = _build_meta('all_params', date_from, date_to, 'tpu',
                       len(features), total_rows - gps_rows, total_rows, started)
    meta['tpuTotal'] = len(index[1]) if index else 0
    meta['tpuWithData'] = len(features)
    meta['gpsRows'] = gps_rows
    meta['outsideTpu'] = outside
    meta['colorParameter'] = color_param
    return {'type': 'FeatureCollection', 'features': features, 'meta': meta}


# ==========================================
# 统一入口
# ==========================================

def query_measurement(parameter: str, date_from: str, date_to: str,
                      view_type: str) -> dict:
    """按 viewType 分发到对应视图（参数合法性已由 validation 层保证）"""
    if view_type == 'district':
        return query_district_view(parameter, date_from, date_to)
    if view_type == 'detailed':
        return query_detailed_view(parameter, date_from, date_to)
    if view_type == 'district_all_param':
        return query_all_param_view(date_from, date_to)
    if view_type == 'tpu':
        return query_tpu_view(date_from, date_to)
    raise BusinessException(ErrorCode.INVALID_DATE, 'unsupported viewType')


def list_date_ranges() -> List[dict]:
    """可用日期区间清单（倒序，最新在前）"""
    return get_repository().list_date_ranges()
