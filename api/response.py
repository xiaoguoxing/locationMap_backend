"""统一响应包装与错误码。"""

import time
import uuid
from typing import Any, Optional

from flask import g, jsonify


class ErrorCode:
    """接口错误码字典。"""

    SUCCESS = 200
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    INTERNAL_ERROR = 500

    # 业务码
    INVALID_PARAM_VIEW_COMBO = 4001      # all_params 与 viewType 组合非法
    INVALID_VIEW_PARAM_COMBO = 4002      # district_all_param 只能配 all_params
    INVALID_DATE = 4003                  # 日期格式 / from>to / 缺失
    DATE_SPAN_EXCEEDED = 4004            # 日期跨度超限
    RESULT_SET_TOO_LARGE = 4005          # 结果集超过上限


class BusinessException(Exception):
    """业务异常：携带错误码与面向用户的安全消息"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def current_request_id() -> str:
    """取当前请求的 requestId；不在请求上下文时兜底生成"""
    return getattr(g, 'request_id', None) or str(uuid.uuid4())


def _wrap(success: bool, code: int, message: str, data: Any):
    return {
        'success': success,
        'code': code,
        'message': message,
        'data': data,
        'timestamp': int(time.time() * 1000),
        'requestId': current_request_id(),
    }


def success(data: Any = None):
    """成功响应"""
    return jsonify(_wrap(True, ErrorCode.SUCCESS, '', data))


def failure(code: int, message: str, http_status: Optional[int] = None):
    """
    失败响应

    HTTP 状态码默认与业务码解耦：业务校验失败仍返回 HTTP 200，
    由前端按 body 里的 code 分支处理。仅鉴权类错误映射到对应
    HTTP 状态，便于网关层拦截。
    """
    payload = _wrap(False, code, message, None)
    if http_status is None:
        http_status = code if code in (401, 403, 404, 500) else 200
    return jsonify(payload), http_status
