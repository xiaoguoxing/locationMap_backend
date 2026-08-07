"""水质地图数据接口服务

独立于老 dashboard 的 Flask 服务，只输出 JSON / GeoJSON。
"""

__all__ = ['create_app']


def create_app():
    """延迟导入，避免包初始化时就拉起 Flask 依赖"""
    from api.app import create_app as _create_app

    return _create_app()
