"""Flask 应用入口

只输出 JSON / GeoJSON，不做任何服务端 HTML 渲染。

启动：
    python -m api.app
"""

import logging
import logging.handlers
import time
import uuid

from flask import Flask, g, jsonify, request

from api import config, extraction, geography, security, service
from api.metadata import list_parameter_metadata
from api.response import BusinessException, ErrorCode, failure, success
from api.validation import validate_query

logger = logging.getLogger('api')


def _setup_logging() -> None:
    """控制台 + 按天切割的文件日志"""
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] [%(name)s] %(message)s')

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        config.LOG_DIR / 'api.log',
        when='midnight',
        backupCount=30,
        encoding='utf-8',
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)
    # 避免重复添加（reload 场景）
    if not root.handlers:
        root.addHandler(console)
        root.addHandler(file_handler)


def create_app() -> Flask:
    _setup_logging()
    app = Flask(__name__)
    # 保持 JSON 里中文原样输出，便于排查
    app.config['JSON_AS_ASCII'] = False

    # ---- 请求前：生成 requestId + 鉴权 ----
    @app.before_request
    def _before():
        g.request_id = request.headers.get('X-Request-Id') or str(uuid.uuid4())
        g.started_at = time.time()
        return security.check_request()

    # ---- 响应后：CORS + 访问日志 ----
    @app.after_request
    def _after(response):
        origin = request.headers.get('Origin')
        if origin and origin in config.CORS_ALLOWED_ORIGINS:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = (
                'Content-Type, Authorization, X-Request-Id')
            response.headers['Vary'] = 'Origin'

        request_id = getattr(g, 'request_id', '-')
        response.headers['X-Request-Id'] = request_id

        started = getattr(g, 'started_at', None)
        if started is not None:
            duration = int((time.time() - started) * 1000)
            message = '{} {} status={} duration={}ms requestId={}'.format(
                request.method, request.path, response.status_code, duration, request_id)
            if response.status_code >= 500:
                logger.error(message)
            elif duration > config.SLOW_QUERY_THRESHOLD_MS:
                logger.warning('SLOW %s', message)
            else:
                logger.info(message)
        return response

    # ---- 异常处理 ----
    @app.errorhandler(BusinessException)
    def _handle_business(exc: BusinessException):
        logger.info('business error code=%s message=%s requestId=%s',
                    exc.code, exc.message, getattr(g, 'request_id', '-'))
        return failure(exc.code, exc.message)

    @app.errorhandler(404)
    def _handle_404(_):
        return failure(ErrorCode.NOT_FOUND, 'Resource not found')

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        # 完整堆栈只进日志；对外只给类别简述，避免泄漏路径 / SQL / 主机名
        logger.exception('unhandled error requestId=%s', getattr(g, 'request_id', '-'))
        return failure(ErrorCode.INTERNAL_ERROR,
                       'Internal server error: {}'.format(type(exc).__name__))

    _register_routes(app)
    security.log_startup_state()
    return app


def _register_routes(app: Flask) -> None:
    """路径风格遵循 /api/{module}/{?resource}/{action}"""

    @app.route('/api/water-quality/parameter/list', methods=['GET'])
    def parameter_list():
        """参数元数据 + 色阶规则（前端判色与图例的唯一来源）"""
        return success(list_parameter_metadata())

    @app.route('/api/water-quality/measurement/date-ranges', methods=['GET'])
    def date_ranges():
        """可用日期区间清单，倒序（最新在前）"""
        return success(service.list_date_ranges())

    @app.route('/api/water-quality/boundary/districts', methods=['GET'])
    def district_boundary():
        """18 区边界，含中文区名与预算好的标注锚点"""
        return success(geography.district_boundary_payload())

    @app.route('/api/water-quality/boundary/tpu', methods=['GET'])
    def tpu_boundary():
        """292 个 TPU 细分区边界（简化后）"""
        payload = geography.tpu_boundary_payload()
        if payload is None:
            return failure(ErrorCode.NOT_FOUND,
                           'TPU boundary data is unavailable on server')
        return success(payload)

    @app.route('/api/water-quality/measurement/query', methods=['POST', 'OPTIONS'])
    def measurement_query():
        """水质数据查询，四种视图由 viewType 分发"""
        if request.method == 'OPTIONS':
            return '', 204

        payload = request.get_json(silent=True) or {}
        params = validate_query(payload)
        data = service.query_measurement(
            params['parameter'], params['dateFrom'], params['dateTo'], params['viewType'])
        return success(data)

    @app.route('/api/water-quality/extraction/refresh', methods=['POST', 'OPTIONS'])
    def extraction_refresh():
        """触发后台 CSV 同步；不接受前端传入 SQL、日期或文件路径。"""
        if request.method == 'OPTIONS':
            return '', 204
        return success(extraction.start_refresh())

    @app.route('/api/water-quality/extraction/status', methods=['GET'])
    def extraction_status():
        """查询进程内后台同步任务状态。"""
        task_id = request.args.get('taskId', '').strip()
        task = extraction.get_status(task_id) if task_id else None
        if task is None:
            return failure(ErrorCode.EXTRACTION_TASK_NOT_FOUND,
                           'Extraction task not found or service restarted')
        return success(task)

    @app.route('/actuator/health', methods=['GET'])
    def health():
        """健康检查：不套统一响应包装，不输出任何内部信息"""
        return jsonify({'status': 'UP'})


def main() -> None:
    app = create_app()
    logger.info('Starting water-quality API on %s:%s (data source: %s)',
                config.HOST, config.PORT, config.DATA_SOURCE)
    logger.info('CORS allowed origins: %s', config.CORS_ALLOWED_ORIGINS)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)


if __name__ == '__main__':
    main()
