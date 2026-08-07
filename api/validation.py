"""请求参数校验

校验顺序短路：命中第一个失败即抛异常，message 明确指出失败字段。
顺序与 Java 后端 spec 一致：必填/枚举 → 参数×视图组合 → 日期格式 → 日期跨度。
"""

import re
from datetime import date, datetime
from typing import Tuple

from api import config
from api.metadata import PARAMETER_PRIORITY
from api.response import BusinessException, ErrorCode

DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')

VALID_PARAMETERS = set(PARAMETER_PRIORITY) | {'all_params'}
VALID_VIEW_TYPES = {'district', 'detailed', 'district_all_param', 'tpu'}

# all_params 允许的视图：整区三参数、以及 TPU 细分区
_ALL_PARAMS_VIEWS = {'district_all_param', 'tpu'}


def parse_date(value: str, field: str) -> date:
    """解析 YYYY-MM-DD；格式非法抛 4003 并指出字段名"""
    if not value or not isinstance(value, str):
        raise BusinessException(ErrorCode.INVALID_DATE, '{} is required'.format(field))
    if not DATE_PATTERN.match(value):
        raise BusinessException(
            ErrorCode.INVALID_DATE,
            '{} must match YYYY-MM-DD, got "{}"'.format(field, value))
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        raise BusinessException(
            ErrorCode.INVALID_DATE, '{} is not a valid date: "{}"'.format(field, value))


def validate_date_range(date_from: str, date_to: str) -> Tuple[date, date]:
    """
    校验日期区间

    Raises:
        BusinessException: 4003 格式非法 / from > to；4004 跨度超限
    """
    start = parse_date(date_from, 'dateFrom')
    end = parse_date(date_to, 'dateTo')

    if start > end:
        raise BusinessException(
            ErrorCode.INVALID_DATE, 'dateFrom must not be later than dateTo')

    span = (end - start).days
    if span > config.MAX_DATE_SPAN_DAYS:
        raise BusinessException(
            ErrorCode.DATE_SPAN_EXCEEDED,
            'Date range exceeds {} days'.format(config.MAX_DATE_SPAN_DAYS))

    return start, end


def validate_query(payload: dict) -> dict:
    """
    校验测量查询请求

    Returns:
        规整后的参数字典 {parameter, dateFrom, dateTo, viewType}
    """
    if not isinstance(payload, dict):
        raise BusinessException(ErrorCode.INVALID_DATE, 'request body is required')

    parameter = payload.get('parameter')
    view_type = payload.get('viewType')

    # 1. 必填与枚举合法性
    if not parameter:
        raise BusinessException(ErrorCode.INVALID_DATE, 'parameter is required')
    if parameter not in VALID_PARAMETERS:
        raise BusinessException(
            ErrorCode.INVALID_DATE,
            'parameter must be one of {}'.format(sorted(VALID_PARAMETERS)))
    if not view_type:
        raise BusinessException(ErrorCode.INVALID_DATE, 'viewType is required')
    if view_type not in VALID_VIEW_TYPES:
        raise BusinessException(
            ErrorCode.INVALID_DATE,
            'viewType must be one of {}'.format(sorted(VALID_VIEW_TYPES)))

    # 2. 参数 × 视图组合合法性
    if parameter == 'all_params' and view_type not in _ALL_PARAMS_VIEWS:
        raise BusinessException(
            ErrorCode.INVALID_PARAM_VIEW_COMBO,
            'all_params only supports viewType in {}'.format(sorted(_ALL_PARAMS_VIEWS)))
    if parameter != 'all_params' and view_type == 'district_all_param':
        raise BusinessException(
            ErrorCode.INVALID_VIEW_PARAM_COMBO,
            'viewType=district_all_param only supports parameter=all_params')

    # 3-4. 日期格式与跨度
    validate_date_range(payload.get('dateFrom'), payload.get('dateTo'))

    return {
        'parameter': parameter,
        'dateFrom': payload['dateFrom'],
        'dateTo': payload['dateTo'],
        'viewType': view_type,
    }
