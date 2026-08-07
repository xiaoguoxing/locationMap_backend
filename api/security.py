"""鉴权扩展位

当前默认关闭（对齐内网无鉴权现状）。把环境变量 WQ_API_AUTH_ENABLED
设为 true 即启用，业务代码无需任何改动。

启用后的行为：
- 校验请求头 `Authorization: Bearer <token>`
- 缺失 / 空 / 校验失败 → 401
- 已认证但无权限 → 403（权限码机制留待接入具体权限系统时实现）
"""

import logging
from typing import Optional

from flask import request

from api import config
from api.response import ErrorCode, failure

logger = logging.getLogger(__name__)

# 不需要鉴权的路径前缀（健康检查等）
_PUBLIC_PATHS = ('/actuator/',)


def verify_token(token: str) -> bool:
    """
    校验 Token

    当前是占位实现：接入真实鉴权系统时替换本函数即可
    （对接 JWT 校验、或调用统一认证服务）。
    """
    # TODO: 接入实际的 Token 校验逻辑
    return bool(token)


def extract_token() -> Optional[str]:
    """从 Authorization 头提取 Bearer Token"""
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None
    token = header[len('Bearer '):].strip()
    return token or None


def check_request():
    """
    请求鉴权检查

    Returns:
        None 表示放行；否则返回错误响应（由 before_request 直接短路返回）
    """
    if not config.AUTH_ENABLED:
        return None

    path = request.path
    if path.startswith(_PUBLIC_PATHS) or request.method == 'OPTIONS':
        return None
    if not path.startswith('/api/'):
        return None

    token = extract_token()
    if not token:
        return failure(ErrorCode.UNAUTHORIZED, 'Authorization token is required')
    if not verify_token(token):
        return failure(ErrorCode.UNAUTHORIZED, 'Invalid or expired token')
    return None


def log_startup_state():
    """启动时明确输出鉴权状态，避免误以为已启用"""
    if config.AUTH_ENABLED:
        logger.info('Security enabled: /api/** requires Bearer token')
    else:
        logger.warning('Security disabled: all API endpoints are public')
