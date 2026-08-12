"""水质地图 JSON / GeoJSON 接口服务。"""

__all__ = ['create_app']


def create_app():
    """延迟导入，避免包初始化时就拉起 Flask 依赖"""
    from api.app import create_app as _create_app

    return _create_app()
