#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参考边界图层 - 纯装饰性线框叠加

在已有地图上叠加 TPU（第三级规划统计区）边界线框，仅作视觉参考，
不参与任何数据聚合与着色逻辑。

设计要点：
- 只读本地 maps/data/hk_tpu_simplified.geojson（由 fetch_tpu_boundary.py 生成）
- 文件缺失时静默跳过，不打断地图生成主流程
- 线框叠在分区色块之上（调用点放在 geojson_layer.add_to(m) 之后）
- 无填充、无 tooltip、无 popup，避免抢走分区图层的鼠标交互
"""

import json
import os
from typing import Optional

import folium

# 简化后的 TPU 边界文件路径
TPU_GEOJSON_PATH = os.path.join(os.path.dirname(__file__), 'data', 'hk_tpu_simplified.geojson')

# 线框样式：淡灰细线，压在色块上但不抢视觉重心
TPU_LINE_STYLE = {
    'fillOpacity': 0,      # 无填充，纯线框
    'color': '#888888',    # 淡灰
    'weight': 0.5,         # 细线
    'opacity': 0.4,        # 半透明
}

# 模块级缓存，避免批量生成地图时反复读同一个文件
_tpu_cache: Optional[dict] = None
_tpu_load_failed = False


def load_tpu_geojson() -> Optional[dict]:
    """
    读取本地 TPU 边界 GeoJSON（带缓存）

    Returns:
        GeoJSON 字典；文件不存在或解析失败时返回 None
    """
    global _tpu_cache, _tpu_load_failed

    if _tpu_cache is not None:
        return _tpu_cache
    if _tpu_load_failed:
        return None

    if not os.path.exists(TPU_GEOJSON_PATH):
        print('  [REF] 未找到 TPU 边界文件，跳过参考线框叠加')
        print('  [REF] 如需启用，先运行: python maps/fetch_tpu_boundary.py')
        _tpu_load_failed = True
        return None

    try:
        with open(TPU_GEOJSON_PATH, 'r', encoding='utf-8') as handle:
            _tpu_cache = json.load(handle)
    except Exception as exc:
        print('  [REF] TPU 边界文件解析失败，跳过参考线框: {}'.format(exc))
        _tpu_load_failed = True
        return None

    print('  [REF] 已加载 TPU 参考边界: {} 个要素'.format(len(_tpu_cache.get('features', []))))
    return _tpu_cache


def add_tpu_reference(m: folium.Map, layer_name: str = 'TPU 参考边界') -> bool:
    """
    在地图上叠加 TPU 参考线框

    调用位置需放在数据图层 add_to(m) 之后，这样线框才会压在分区色块上方。

    Args:
        m: 目标 folium 地图对象
        layer_name: 图层名称（用于图层控件，当前未启用 LayerControl）

    Returns:
        True 表示成功叠加，False 表示因文件缺失等原因跳过
    """
    geojson_data = load_tpu_geojson()
    if geojson_data is None:
        return False

    folium.GeoJson(
        geojson_data,
        name=layer_name,
        # 纯装饰层：样式固定，不随数据变化
        style_function=lambda feature: dict(TPU_LINE_STYLE),
        # 关掉鼠标交互，避免遮挡下层分区的 tooltip / popup 点击
        interactive=False,
        control=True,
    ).add_to(m)

    return True
