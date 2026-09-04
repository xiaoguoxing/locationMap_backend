#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证裁剪后的 18 区 GeoJSON 质量"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DISTRICT_FILE = PROJECT_ROOT / 'api' / 'data' / 'hk_districts.geojson'

with open(DISTRICT_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f'✓ 要素总数: {len(data["features"])}')
print()

# 几何类型分布
types = {}
for feature in data['features']:
    geom_type = feature['geometry']['type']
    types[geom_type] = types.get(geom_type, 0) + 1

print('几何类型分布:')
for geom_type, count in types.items():
    print(f'  {geom_type}: {count}')
print()

# MultiPolygon 详情
multi_polys = [f for f in data['features'] if f['geometry']['type'] == 'MultiPolygon']
if multi_polys:
    print(f'MultiPolygon 区域（共 {len(multi_polys)} 个）:')
    for feature in multi_polys:
        name = feature['properties']['District']
        poly_count = len(feature['geometry']['coordinates'])
        print(f'  {name}: {poly_count} 个独立多边形')
print()

# 顶点统计
def count_points(coords):
    if not isinstance(coords, (list, tuple)):
        return 0
    if coords and isinstance(coords[0], (int, float)):
        return 1
    return sum(count_points(item) for item in coords)

print('各区顶点数量:')
for feature in data['features']:
    name = feature['properties']['District']
    points = count_points(feature['geometry']['coordinates'])
    print(f'  {name}: {points} 个顶点')
print()

print('✓ 验证完成')
