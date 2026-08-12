"""地理数据：区界、区名归一化、标注锚点、TPU 细分区。"""

import json
import threading
from typing import Dict, List, Optional, Tuple

from api import config
from api.data.district_mapping import NEIGHBORHOOD_TO_DISTRICT
from api.geo_utils import (
    DISTRICT_CENTROID_ADJUSTMENTS,
    DISTRICT_NAMES_TC,
    get_adjusted_centroid,
)

_lock = threading.Lock()
_district_geojson: Optional[dict] = None
_district_payload: Optional[dict] = None
_district_anchors: Optional[Dict[str, Tuple[float, float]]] = None
_name_mapping: Optional[Dict[str, str]] = None
_tpu_payload: Optional[dict] = None
_tpu_geoms = None


def _round_coord(value: float) -> float:
    return round(float(value), config.COORD_PRECISION)


# ==========================================
# 18 区边界
# ==========================================

def load_district_geojson() -> dict:
    """加载原始 18 区边界 GeoJSON（带缓存）"""
    global _district_geojson
    if _district_geojson is not None:
        return _district_geojson

    with _lock:
        if _district_geojson is None:
            with open(config.DISTRICT_GEOJSON, 'r', encoding='utf-8') as handle:
                _district_geojson = json.load(handle)
    return _district_geojson


def district_boundary_payload() -> dict:
    """
    对外输出的 18 区边界

    在原始属性（含繁中键名 地區號碼 / District / 地區）之上追加：
    - districtTc：中文区名
    - labelAnchor：标注锚点 [lon, lat]，面积加权质心 + 手工偏移
    - labelAdjusted：该区是否应用了手工偏移

    锚点在后端算好下发，前端不重算，避免两边各维护一份偏移表。
    """
    global _district_payload
    if _district_payload is not None:
        return _district_payload

    source = load_district_geojson()
    features = []
    for feature in source['features']:
        props = dict(feature['properties'])
        district = props.get('District')
        props['districtTc'] = DISTRICT_NAMES_TC.get(district, district)

        centroid = get_adjusted_centroid(district, feature['geometry'])
        if centroid:
            props['labelAnchor'] = [_round_coord(centroid[0]), _round_coord(centroid[1])]
            if district in DISTRICT_CENTROID_ADJUSTMENTS:
                props['labelAdjusted'] = True

        features.append({
            'type': 'Feature',
            'geometry': feature['geometry'],
            'properties': props,
        })

    with _lock:
        _district_payload = {'type': 'FeatureCollection', 'features': features}
    return _district_payload


def district_anchors() -> Dict[str, Tuple[float, float]]:
    """区名 → 标注锚点，供聚合视图输出 Feature 几何时使用"""
    global _district_anchors
    if _district_anchors is not None:
        return _district_anchors

    anchors = {}
    for feature in load_district_geojson()['features']:
        district = feature['properties'].get('District')
        centroid = get_adjusted_centroid(district, feature['geometry'])
        if centroid:
            anchors[district] = (_round_coord(centroid[0]), _round_coord(centroid[1]))

    with _lock:
        _district_anchors = anchors
    return _district_anchors


def official_districts() -> List[str]:
    """18 个官方区名"""
    return [f['properties']['District'] for f in load_district_geojson()['features']]


# ==========================================
# 区名归一化
# ==========================================

def name_mapping() -> Dict[str, str]:
    """
    构建「CSV 里的地点名 → 官方区名」映射

    CSV 的 district 字段存的是邻里名（如 the peak / ap lei chau），
    不是 18 区区名，必须通过映射表归一化。支持邻里名、区名本身、
    去空格以及 & / and 互换等写法。
    """
    global _name_mapping
    if _name_mapping is not None:
        return _name_mapping

    mapping: Dict[str, str] = {}

    for neighborhood, district in NEIGHBORHOOD_TO_DISTRICT.items():
        key = neighborhood.lower().strip()
        mapping[key] = district
        mapping[key.replace(' ', '')] = district

    for district in official_districts():
        low = district.lower()
        mapping[low] = district
        mapping[low.replace(' ', '')] = district
        mapping[low.replace('&', 'and')] = district
        mapping[low.replace('&', 'and').replace(' ', '')] = district

    with _lock:
        _name_mapping = mapping
    return _name_mapping


def normalize_district(raw) -> Optional[str]:
    """
    把 CSV 里的地点名归一化为官方区名

    Returns:
        官方区名；无法识别时返回 None（调用方据此计入 unmatched）
    """
    if raw is None:
        return None
    name = str(raw).strip().lower()
    if not name or name in ('nan', 'none'):
        return None

    mapping = name_mapping()
    if name in mapping:
        return mapping[name]

    no_space = name.replace(' ', '')
    if no_space in mapping:
        return mapping[no_space]

    for token in ('&', 'and', '-'):
        variant = name.replace(token, ' ')
        if variant in mapping:
            return mapping[variant]
        if variant.replace(' ', '') in mapping:
            return mapping[variant.replace(' ', '')]

    return None


# ==========================================
# TPU 细分区
# ==========================================

def _simplify_tpu(raw: dict) -> dict:
    """按容差简化 TPU 几何，只保留 TPU_NUMBER 属性"""
    from shapely.geometry import mapping, shape

    features = []
    for feature in raw.get('features', []):
        geometry = feature.get('geometry')
        if not geometry:
            continue
        try:
            geom = shape(geometry).simplify(config.TPU_TOLERANCE, preserve_topology=True)
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
    return {'type': 'FeatureCollection', 'features': features}


def tpu_boundary_payload() -> Optional[dict]:
    """
    对外输出的 TPU 边界

    优先读已简化好的文件；没有则从原始缓存实时简化。
    两者都缺失时返回 None（接口以 404 告知，前端可降级为只显示 18 区）。
    """
    global _tpu_payload
    if _tpu_payload is not None:
        return _tpu_payload

    with _lock:
        if _tpu_payload is not None:
            return _tpu_payload

        if config.TPU_SIMPLIFIED.exists():
            with open(config.TPU_SIMPLIFIED, 'r', encoding='utf-8') as handle:
                _tpu_payload = json.load(handle)
        elif config.TPU_RAW_CACHE.exists():
            with open(config.TPU_RAW_CACHE, 'r', encoding='utf-8') as handle:
                _tpu_payload = _simplify_tpu(json.load(handle))
        else:
            return None

    return _tpu_payload


def tpu_index():
    """
    构建 TPU 空间索引

    TPU 聚合需要「点在多边形内」判定，用 STRtree 做粗筛再精确判断，
    避免对 292 个多边形逐个 contains。

    Returns:
        (geoms, numbers, tree) 三元组；TPU 数据缺失时返回 None
    """
    global _tpu_geoms
    if _tpu_geoms is not None:
        return _tpu_geoms

    payload = tpu_boundary_payload()
    if payload is None:
        return None

    from shapely.geometry import shape
    from shapely.strtree import STRtree

    geoms = []
    numbers = []
    for feature in payload['features']:
        try:
            geoms.append(shape(feature['geometry']))
        except Exception:
            continue
        numbers.append(str(feature['properties'].get('TPU_NUMBER')))

    with _lock:
        _tpu_geoms = (geoms, numbers, STRtree(geoms))
    return _tpu_geoms


def locate_tpu(longitude: float, latitude: float) -> Optional[str]:
    """判断坐标落在哪个 TPU 内；不在任何 TPU 内返回 None"""
    index = tpu_index()
    if index is None:
        return None

    from shapely.geometry import Point

    geoms, numbers, tree = index
    point = Point(longitude, latitude)
    for idx in tree.query(point):
        if geoms[idx].contains(point):
            return numbers[idx]
    return None
