"""服务配置

所有可变项均支持环境变量覆盖，不在代码里硬编码路径与端口。
"""

import os
from pathlib import Path

# 项目根目录（api 包的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---- 服务 ----
# 默认 5001，可通过环境变量覆盖
PORT = int(os.getenv('WQ_API_PORT', '5001'))
HOST = os.getenv('WQ_API_HOST', '0.0.0.0')
DEBUG = os.getenv('WQ_API_DEBUG', 'false').lower() == 'true'

# ---- 数据源 ----
# 当前实现读 CSV；将来切数据库时改这里的 DATA_SOURCE 即可
DATA_SOURCE = os.getenv('WQ_API_DATA_SOURCE', 'csv')

CSV_DIR = Path(os.getenv('WQ_API_CSV_DIR', str(PROJECT_ROOT / 'gencsv' / 'output')))
GEO_DATA_DIR = Path(os.getenv(
    'WQ_API_GEO_DATA', str(PROJECT_ROOT / 'api' / 'data')
))
DISTRICT_GEOJSON = GEO_DATA_DIR / 'hk_districts.geojson'
TPU_RAW_CACHE = GEO_DATA_DIR / '_tpu_raw_cache.json'
TPU_SIMPLIFIED = GEO_DATA_DIR / 'hk_tpu_simplified.geojson'

# ---- 业务约束（与 Java 后端 spec 对齐）----
# 日期跨度上限（天）
MAX_DATE_SPAN_DAYS = int(os.getenv('WQ_API_MAX_DATE_SPAN', '90'))
# 结果集 Feature 数上限，超过则拒绝以免拖垮前端渲染
MAX_FEATURE_COUNT = int(os.getenv('WQ_API_MAX_FEATURES', '50000'))

# ---- 输出精度 ----
COORD_PRECISION = 6
VALUE_PRECISION = 2

# ---- TPU 边界简化容差（度）----
# 0.0001 ≈ 10 米，兼顾海岸线细节与传输体积
TPU_TOLERANCE = float(os.getenv('WQ_API_TPU_TOLERANCE', '0.0001'))

# ---- CORS ----
# 前端 dev server 默认 9527；多个来源用逗号分隔
_origins = os.getenv('WQ_API_CORS_ORIGINS', 'http://localhost:9527,http://127.0.0.1:9527')
CORS_ALLOWED_ORIGINS = [o.strip() for o in _origins.split(',') if o.strip()]

# ---- 鉴权（扩展位，默认关闭）----
AUTH_ENABLED = os.getenv('WQ_API_AUTH_ENABLED', 'false').lower() == 'true'

# ---- 可观测性 ----
SLOW_QUERY_THRESHOLD_MS = int(os.getenv('WQ_API_SLOW_QUERY_MS', '3000'))
LOG_DIR = Path(os.getenv('WQ_API_LOG_DIR', str(PROJECT_ROOT / 'api' / 'logs')))
