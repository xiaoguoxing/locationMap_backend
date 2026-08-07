#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TPU 参考边界下载脚本（一次性运行）

从 CSDI 门户的 WFS 服务拉取香港 TPU（Tertiary Planning Unit，第三级规划统计区）
边界，做几何简化后存为本地 GeoJSON，供地图生成时叠加纯装饰性参考线框使用。

设计要点：
- 仅需运行一次，产物落地到 maps/data/hk_tpu_simplified.geojson
- 地图生成流程（location_mapper / multi_param_mapper）只读本地文件，不联网
- 原始全量数据约 22 MB / 292 个 MultiPolygon，必须简化后才能内联进 HTML

用法：
    python maps/fetch_tpu_boundary.py
    python maps/fetch_tpu_boundary.py --tolerance 0.0005   # 简化更狠、文件更小
"""

import argparse
import json
import sys
from pathlib import Path

import requests
from shapely.geometry import mapping, shape

# WFS 服务地址（CSDI 门户，规划署 TPU 数据集）
WFS_URL = (
    'https://portal.csdi.gov.hk/server/services/common/'
    'pland_rcd_1637289585582_55577/MapServer/WFSServer'
)

# GetFeature 请求参数：直接让服务端转成 WGS84 经纬度，省去本地投影转换
WFS_PARAMS = {
    'service': 'wfs',
    'version': '2.0.0',
    'request': 'GetFeature',
    'typenames': 'csdi:TPU',
    'outputFormat': 'GEOJSON',
    'srsName': 'EPSG:4326',
}

# 输出路径
OUTPUT_PATH = Path(__file__).parent / 'data' / 'hk_tpu_simplified.geojson'

# 默认简化容差（单位：度）。0.0002 度 ≈ 20 米
DEFAULT_TOLERANCE = 0.0002

# 只保留这几个属性，其余（OBJECTID / SHAPE_Area 等）对线框展示无用
KEEP_PROPERTIES = ('TPU_NUMBER', 'SPU_NUMBER', 'PPU_NUMBER')


def download_tpu(verify_ssl: bool = True) -> dict:
    """
    从 WFS 服务下载 TPU 全量要素（GeoJSON 格式，WGS84 坐标）

    Args:
        verify_ssl: 是否校验 TLS 证书。portal.csdi.gov.hk 的证书链在部分
                    机器上不被信任，此时可传 False 跳过校验（有中间人攻击风险）

    Returns:
        GeoJSON FeatureCollection 字典
    """
    print('[FETCH] 请求 WFS 服务: {}'.format(WFS_URL))
    print('[FETCH] 要素类型: csdi:TPU / 输出: GeoJSON / 坐标系: EPSG:4326')

    response = requests.get(WFS_URL, params=WFS_PARAMS, timeout=180, verify=verify_ssl)
    response.raise_for_status()

    data = response.json()
    if data.get('type') != 'FeatureCollection':
        raise ValueError('返回内容不是 FeatureCollection，实际为: {}'.format(data.get('type')))

    features = data.get('features', [])
    print('[FETCH] 下载完成: {} 个要素 / {:.2f} MB'.format(
        len(features), len(response.content) / 1048576))
    return data


def simplify_features(data: dict, tolerance: float) -> dict:
    """
    简化几何并精简属性

    用 shapely 的 simplify（保留拓扑）压缩顶点数量，同时丢弃展示用不到的属性字段。

    Args:
        data: 原始 GeoJSON FeatureCollection
        tolerance: 简化容差（度）。值越大顶点越少、文件越小、边界越粗糙

    Returns:
        简化后的 GeoJSON FeatureCollection
    """
    simplified_features = []
    skipped = 0

    for feature in data.get('features', []):
        geometry = feature.get('geometry')
        if not geometry:
            skipped += 1
            continue

        try:
            geom = shape(geometry)
            # preserve_topology=True 避免简化后产生自相交的破碎多边形
            geom = geom.simplify(tolerance, preserve_topology=True)
        except Exception as exc:
            print('[WARN] 几何简化失败，跳过该要素: {}'.format(exc))
            skipped += 1
            continue

        if geom.is_empty:
            skipped += 1
            continue

        source_props = feature.get('properties') or {}
        simplified_features.append({
            'type': 'Feature',
            'properties': {
                key: source_props.get(key)
                for key in KEEP_PROPERTIES
                if source_props.get(key) is not None
            },
            'geometry': mapping(geom),
        })

    if skipped:
        print('[SIMPLIFY] 跳过 {} 个无效/空要素'.format(skipped))

    return {'type': 'FeatureCollection', 'features': simplified_features}


def count_coordinates(data: dict) -> int:
    """统计 FeatureCollection 里的坐标点总数，用于评估简化效果"""
    def walk(coords) -> int:
        # 注意：shapely 的 mapping() 返回 tuple 而非 list，两者都要认
        if not isinstance(coords, (list, tuple)):
            return 0
        # 到达 [lon, lat] 这一层
        if coords and isinstance(coords[0], (int, float)):
            return 1
        return sum(walk(item) for item in coords)

    return sum(
        walk((feature.get('geometry') or {}).get('coordinates', []))
        for feature in data.get('features', [])
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='下载并简化 CSDI TPU 参考边界')
    parser.add_argument(
        '--tolerance', type=float, default=DEFAULT_TOLERANCE,
        help='几何简化容差（度），默认 {}（约 20 米）'.format(DEFAULT_TOLERANCE))
    parser.add_argument(
        '--insecure', action='store_true',
        help='跳过 TLS 证书校验。portal.csdi.gov.hk 证书链不受信任时使用，有安全风险')
    args = parser.parse_args()

    if args.insecure:
        print('[WARN] 已跳过 TLS 证书校验，存在中间人攻击风险，仅建议在可信网络下使用')
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    try:
        raw = download_tpu(verify_ssl=not args.insecure)
    except requests.exceptions.SSLError as exc:
        print('[ERROR] TLS 证书校验失败: {}'.format(exc))
        print('[HINT ] 该站点证书链在本机不受信任。可安装港府根证书，'
              '或临时加 --insecure 参数跳过校验')
        return 1
    except Exception as exc:
        print('[ERROR] 下载失败: {}'.format(exc))
        return 1

    raw_points = count_coordinates(raw)
    simplified = simplify_features(raw, args.tolerance)
    simplified_points = count_coordinates(simplified)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # separators 去掉多余空格，进一步压小文件
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as handle:
        json.dump(simplified, handle, ensure_ascii=False, separators=(',', ':'))

    size_mb = OUTPUT_PATH.stat().st_size / 1048576
    print('[SAVE ] 输出: {}'.format(OUTPUT_PATH))
    print('[SAVE ] 要素: {} 个 / 坐标点: {} -> {}（压缩 {:.1f}%）'.format(
        len(simplified['features']), raw_points, simplified_points,
        (1 - simplified_points / raw_points) * 100 if raw_points else 0))
    print('[SAVE ] 文件大小: {:.2f} MB'.format(size_mb))

    if size_mb > 1.0:
        print('[WARN ] 文件超过 1 MB，内联进 HTML 后可能拖慢浏览器。'
              '建议加大 --tolerance 重新生成，例如 --tolerance 0.0005')

    return 0


if __name__ == '__main__':
    sys.exit(main())
