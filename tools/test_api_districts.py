#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 API 能否正常加载新的 18 区边界"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.geography import district_boundary_payload

districts = district_boundary_payload()

print(f'✓ 加载 18 区成功: {len(districts["features"])} 个要素')
print(f'✓ GeoJSON 大小: {len(str(districts)) // 1024} KB')
print()
print('前 5 区:')
for feature in districts['features'][:5]:
    props = feature['properties']
    geom_type = feature['geometry']['type']
    district = props.get('District', '?')
    district_tc = props.get('districtTc', '?')
    print(f'  - {district_tc} ({district}): {geom_type}')
print()
print('✓ API 服务可以正常加载新边界')
