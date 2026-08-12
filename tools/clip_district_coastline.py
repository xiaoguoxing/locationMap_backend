#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按海岸线裁剪 18 区行政边界

背景
----
原始的 api/data/hk_districts.geojson 存在两个问题：

1. 行政区划是沿海岸线**之外**的界线划定的，因此每个区都包含大片海域。
   实测裁剪前后面积对比：18 区合计只有 40.3% 落在陆地上，近六成是海面。
   西贡区最极端，仅 17.8% 是陆地。地图上表现为分区色块大量覆盖海面。

2. 全部 18 个要素都是单个 Polygon。离岛区实际包含大屿山、长洲、南丫岛等
   数十个独立岛屿，用单环多边形（原始数据仅 61 个顶点）只能画出一个把所有
   岛圈进去的粗略外框 —— 这正是业主反馈的「显示为外框多边形」。

做法
----
292 个 TPU（第三级规划统计区）覆盖香港全部陆地，其并集即为陆地轮廓。
用该并集与每个行政区求交集，即可裁掉海域部分，同时把几何提升为
MultiPolygon，正确表达离岛。

用法
----
    python tools/clip_district_coastline.py
    python tools/clip_district_coastline.py --output api/data/hk_districts_land.geojson

默认原地更新 hk_districts.geojson，并把原始文件备份为
hk_districts_with_sea.geojson（保留以便回退与对照）。
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GEO_DATA = PROJECT_ROOT / 'api' / 'data'
DISTRICT_GEOJSON = GEO_DATA / 'hk_districts.geojson'
DISTRICT_BACKUP = GEO_DATA / 'hk_districts_with_sea.geojson'
TPU_GEOJSON = GEO_DATA / 'hk_tpu_simplified.geojson'

# 坐标精度：与接口输出保持一致（6 位小数，约 0.1 米）
COORD_PRECISION = 6

# 裁剪后面积占比低于此阈值时告警：可能意味着该区几何或裁剪源有问题
SUSPICIOUS_KEEP_RATIO = 0.10


def count_points(coords) -> int:
    """统计坐标点数量（shapely 的 mapping() 返回 tuple，需兼容 list/tuple）"""
    if not isinstance(coords, (list, tuple)):
        return 0
    if coords and isinstance(coords[0], (int, float)):
        return 1
    return sum(count_points(item) for item in coords)


def round_coords(obj):
    """递归地把坐标保留到指定小数位，减小文件体积"""
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(v), COORD_PRECISION) for v in obj]
        return [round_coords(item) for item in obj]
    return obj


def build_land_outline(tpu_path: Path):
    """
    用 TPU 并集构建陆地轮廓

    Returns:
        (shapely 几何, 参与合并的要素数)
    """
    with open(tpu_path, 'r', encoding='utf-8') as handle:
        tpu = json.load(handle)

    geoms = []
    skipped = 0
    for feature in tpu.get('features', []):
        geometry = feature.get('geometry')
        if not geometry:
            skipped += 1
            continue
        try:
            geom = shape(geometry)
        except Exception:
            skipped += 1
            continue
        if geom.is_empty:
            skipped += 1
            continue
        # 自相交等拓扑问题用 buffer(0) 修复，否则 unary_union 会失败
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty:
            skipped += 1
            continue
        geoms.append(geom)

    if not geoms:
        raise ValueError('TPU 数据中没有有效几何，无法构建陆地轮廓')

    if skipped:
        print('  [WARN] 跳过 {} 个无效 TPU 几何'.format(skipped))

    return unary_union(geoms), len(geoms)


def clip_districts(district_path: Path, land) -> dict:
    """
    用陆地轮廓裁剪各行政区

    保留原有属性不变（含繁中键名 地區號碼 / District / 地區），
    仅替换 geometry，因此下游按 District 关联数据的逻辑无需改动。
    """
    with open(district_path, 'r', encoding='utf-8') as handle:
        source = json.load(handle)

    features = []
    total_before = total_after = 0.0
    warnings = []

    print()
    print('  {:22s} {:>9s} {:>9s} {:>7s} {:>8s} {:>8s}'.format(
        'District', 'area_old', 'area_new', 'keep%', 'pts_old', 'pts_new'))
    print('  ' + '-' * 70)

    for feature in source['features']:
        name = feature['properties'].get('District', '?')
        try:
            geom = shape(feature['geometry'])
        except Exception as exc:
            warnings.append('{}: 几何解析失败 {}'.format(name, exc))
            features.append(feature)
            continue

        if not geom.is_valid:
            geom = geom.buffer(0)

        points_before = count_points(feature['geometry']['coordinates'])
        clipped = geom.intersection(land)

        if clipped.is_empty:
            # 裁剪后为空说明该区与陆地轮廓无交集，保留原几何而不是丢弃该区，
            # 否则地图上会整块缺失，比边界粗糙的后果严重得多。
            warnings.append('{}: 裁剪后为空，保留原始几何'.format(name))
            features.append(feature)
            continue

        geometry = round_coords(mapping(clipped))
        points_after = count_points(geometry['coordinates'])

        keep = clipped.area / geom.area if geom.area else 0
        if keep < SUSPICIOUS_KEEP_RATIO:
            warnings.append('{}: 仅保留 {:.1f}% 面积，请核对'.format(name, keep * 100))

        total_before += geom.area
        total_after += clipped.area

        print('  {:22s} {:9.5f} {:9.5f} {:6.1f}% {:8d} {:8d}'.format(
            str(name)[:22], geom.area, clipped.area, keep * 100,
            points_before, points_after))

        features.append({
            'type': 'Feature',
            'properties': feature['properties'],
            'geometry': geometry,
        })

    print('  ' + '-' * 70)
    print('  {:22s} {:9.5f} {:9.5f} {:6.1f}%'.format(
        '合计', total_before, total_after,
        total_after / total_before * 100 if total_before else 0))

    if warnings:
        print()
        for item in warnings:
            print('  [WARN] {}'.format(item))

    return {'type': 'FeatureCollection', 'features': features}


def main() -> int:
    parser = argparse.ArgumentParser(description='按海岸线裁剪 18 区行政边界')
    parser.add_argument('--districts', default=str(DISTRICT_GEOJSON),
                        help='待裁剪的行政区 GeoJSON')
    parser.add_argument('--tpu', default=str(TPU_GEOJSON),
                        help='作为陆地轮廓的 TPU GeoJSON')
    parser.add_argument('--output', help='输出路径，默认原地更新并备份原文件')
    parser.add_argument('--no-backup', action='store_true',
                        help='原地更新时不备份原文件')
    args = parser.parse_args()

    district_path = Path(args.districts)
    tpu_path = Path(args.tpu)

    for path, label in ((district_path, '行政区'), (tpu_path, 'TPU')):
        if not path.exists():
            print('[ERROR] 未找到{}数据: {}'.format(label, path))
            if label == 'TPU':
                print('[HINT ] 先运行: python tools/fetch_tpu_boundary.py')
            return 1

    started = time.time()

    print('[LAND ] 构建陆地轮廓（TPU 并集）...')
    land, used = build_land_outline(tpu_path)
    print('[LAND ] 合并 {} 个 TPU -> {}，面积 {:.6f} 平方度'.format(
        used, land.geom_type, land.area))

    print('[CLIP ] 裁剪各行政区...')
    result = clip_districts(district_path, land)

    output_path = Path(args.output) if args.output else district_path

    # 原地更新时先备份，便于回退与前后对照
    if output_path == district_path and not args.no_backup:
        if not DISTRICT_BACKUP.exists():
            shutil.copy2(district_path, DISTRICT_BACKUP)
            print()
            print('[BACKUP] 原始文件已备份: {}'.format(DISTRICT_BACKUP.name))
        else:
            print()
            print('[BACKUP] 备份已存在，跳过: {}'.format(DISTRICT_BACKUP.name))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, separators=(',', ':'))

    size_kb = output_path.stat().st_size / 1024
    print('[SAVE ] {} ({:.0f} KB)'.format(output_path, size_kb))
    print('[DONE ] 耗时 {:.1f}s'.format(time.time() - started))
    print()
    print('[NEXT ] 接口会直接读取新文件，重启 api 服务即可生效：')
    print('        python -m api.app')
    return 0


if __name__ == '__main__':
    sys.exit(main())
