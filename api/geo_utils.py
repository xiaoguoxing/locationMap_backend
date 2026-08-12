"""行政区名称与标注锚点计算。"""

from typing import Dict, Optional, Tuple

from shapely.geometry import shape

DISTRICT_NAMES_TC = {
    'Central & Western': '中西區', 'Eastern': '東區', 'Islands': '離島區',
    'Kowloon City': '九龍城區', 'Kwai Tsing': '葵青區', 'Kwun Tong': '觀塘區',
    'North': '北區', 'Sai Kung': '西貢區', 'Sha Tin': '沙田區',
    'Sham Shui Po': '深水埗區', 'Southern': '南區', 'Tai Po': '大埔區',
    'Tsuen Wan': '荃灣區', 'Tuen Mun': '屯門區', 'Wan Chai': '灣仔區',
    'Wong Tai Sin': '黃大仙區', 'Yau Tsim Mong': '油尖旺區',
    'Yuen Long': '元朗區',
}

DISTRICT_CENTROID_ADJUSTMENTS = {
    'Tsuen Wan': (0.018, 0.0),
    'Kwun Tong': (0.0, -0.008),
    'North': (0.005, 0.0),
    'Wong Tai Sin': (0.003, 0.0),
    'Wan Chai': (0.0, -0.008),
}


def get_adjusted_centroid(
    district: str, geometry: Dict
) -> Optional[Tuple[float, float]]:
    """返回保证位于主要陆地区域内的标注点，并应用人工微调。"""
    try:
        geom = shape(geometry)
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty:
            return None
        if geom.geom_type == 'MultiPolygon':
            geom = max(geom.geoms, key=lambda item: item.area)
        point = geom.representative_point()
        longitude, latitude = point.x, point.y
        delta_lat, delta_lon = DISTRICT_CENTROID_ADJUSTMENTS.get(
            district, (0.0, 0.0)
        )
        return longitude + delta_lon, latitude + delta_lat
    except Exception:
        return None
