"""参数元数据与色阶规则 —— 判色的唯一来源

本模块既供 `/parameter/list` 接口对外输出，也供各视图内部计算 colorLevel，
确保后端着色与前端图例 100% 同源。

区间开闭语义：
    minExclusive=True  → 下界开区间（value > min）
    minExclusive=False → 下界闭区间（value >= min）
    maxInclusive=True  → 上界闭区间（value <= max）
    maxInclusive=False → 上界开区间（value < max）

Python 侧原始写法是 `if value < 0.2: red elif value <= 1.5: green ...` 这种
链式判断，等价于「上界含端点」。早期曾按 [min, max) 半开区间实现，
导致 1.5 / 2.0 / 3.0 / 10.0 这些边界点判色与原逻辑差一档（实测 6 处），
故改为下面这套显式标志。
"""

from typing import Dict, List, Optional

# 参数代码优先级：决定 all_params 视图由谁驱动着色
PARAMETER_PRIORITY = ['cl2_free_1', 'ecoli', 'turby']

# 参数展示元数据
PARAMETER_META = {
    'cl2_free_1': {'displayName': 'Free Chlorine', 'unit': 'mg/L', 'shortName': 'Cl2'},
    'ecoli': {'displayName': 'E. coli', 'unit': 'cfu/100mL', 'shortName': 'E.coli'},
    'turby': {'displayName': 'Turbidity', 'unit': 'NTU', 'shortName': 'Turbidity'},
    'all_params': {'displayName': 'All Parameters', 'unit': '', 'shortName': 'All'},
}

COLOR_SCALES: Dict[str, List[dict]] = {
    # 对应: value < 0.2 红 / <= 1.5 绿 / <= 2.0 橙 / <= 3.0 深红 / else 红
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
    # 对应: value == 0 绿 / > 0 红
    # 已知差异（不可达输入，不修正）：原 Python 写法下负值判红，此处判绿。
    # E.coli 为非负整数菌落计数，负值不会出现。
    'ecoli': [
        {'level': 'Satisfactory', 'color': 'green', 'hex': '#198754',
         'min': None, 'max': 0.0, 'minExclusive': False, 'maxInclusive': True,
         'description': '0'},
        {'level': 'Unsatisfactory', 'color': 'red', 'hex': '#DC3545',
         'min': 0.0, 'max': None, 'minExclusive': True, 'maxInclusive': False,
         'description': '> 0'},
    ],
    # 对应: value <= 1.5 绿 / <= 3.0 橙 / <= 10.0 深红 / else 红
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


def resolve_level(parameter: str, value) -> Optional[str]:
    """
    按色阶区间解析等级标签

    Args:
        parameter: 参数代码
        value: 测量值；None / NaN 返回 None（不抛异常、不丢弃要素）

    Returns:
        等级标签；无匹配区间时返回 None
    """
    if value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if val != val:  # NaN
        return None

    for band in COLOR_SCALES.get(parameter, []):
        if band['min'] is None:
            low_ok = True
        elif band['minExclusive']:
            low_ok = val > band['min']
        else:
            low_ok = val >= band['min']

        if band['max'] is None:
            high_ok = True
        elif band['maxInclusive']:
            high_ok = val <= band['max']
        else:
            high_ok = val < band['max']

        if low_ok and high_ok:
            return band['level']
    return None


def list_parameter_metadata() -> List[dict]:
    """
    输出全部参数元数据

    all_params 的色阶按 cl2_free_1(5) + ecoli(2) + turby(4) 顺序拼接，
    共 11 段，元素同源复用子参数定义（不重新定义阈值）。
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
    return items
