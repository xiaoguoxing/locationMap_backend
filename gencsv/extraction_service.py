"""SQL Server 到 CSV 的共享抽取服务。

命令行批处理与 Flask 后台任务都调用本模块，避免维护两套抽取逻辑。
所有 CSV 先写入暂存目录，整批成功后才以目录重命名方式发布。
"""

import json
import logging
import os
import shutil
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

try:
    from .config_loader import get_config
    from .db_connector import execute_query_to_csv
except ImportError:
    from config_loader import get_config
    from db_connector import execute_query_to_csv

ProgressCallback = Callable[[str, int, int], None]
_LOCK_FILE_NAME = '.extraction.lock'


class ExtractionAlreadyRunningError(RuntimeError):
    """已有批处理或 API 抽取任务占用文件锁。"""


def generate_date_ranges(days_back: int, range_days: int,
                         end_date: Optional[str] = None,
                         single_day: bool = False) -> list[tuple[str, str]]:
    """生成向后看的滚动日期窗口，起止日期均包含。"""
    if days_back < 0 or range_days < 1:
        raise ValueError('days_back 必须大于等于 0，range_days 必须大于等于 1')
    last_day = (
        datetime.strptime(end_date, '%Y-%m-%d').date()
        if end_date else date.today()
    )
    first_day = last_day - timedelta(days=days_back)
    ranges = []
    current = first_day
    while current <= last_day:
        window_start = current if single_day else current - timedelta(days=range_days - 1)
        ranges.append((window_start.isoformat(), current.isoformat()))
        current += timedelta(days=1)
    return ranges


def generate_weekly_ranges(days_back: int = 30,
                           end_date: Optional[str] = None) -> list[tuple[str, str]]:
    """
    生成按自然周（周一到周日）划分的日期区间。
    
    Args:
        days_back: 向前回溯的天数（默认30天）
        end_date: 结束日期（可选，默认今天）
    
    Returns:
        [(周一, 周日), ...] 日期区间列表，格式 'YYYY-MM-DD'
    
    示例：
        2026-04-20（周一）到 2026-04-26（周日）
        2026-04-27（周一）到 2026-05-03（周日）
    """
    if days_back < 0:
        raise ValueError('days_back 必须大于等于 0')
    
    last_day = (
        datetime.strptime(end_date, '%Y-%m-%d').date()
        if end_date else date.today()
    )
    first_day = last_day - timedelta(days=days_back)
    
    # 找到第一个周一（向前调整）
    # weekday(): 0=周一, 6=周日
    days_since_monday = first_day.weekday()
    week_start = first_day - timedelta(days=days_since_monday)
    
    ranges = []
    current_monday = week_start
    
    while current_monday <= last_day:
        current_sunday = current_monday + timedelta(days=6)
        # 如果周日超出了结束日期，截断到结束日期
        if current_sunday > last_day:
            current_sunday = last_day
        
        ranges.append((current_monday.isoformat(), current_sunday.isoformat()))
        current_monday += timedelta(days=7)
    
    return ranges


def _acquire_lock(output_dir: Path) -> Path:
    """用独占创建实现跨进程锁，避免按钮与批处理同时抽取。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_path = output_dir / _LOCK_FILE_NAME
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ExtractionAlreadyRunningError('已有数据同步任务正在运行') from exc
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        json.dump({'pid': os.getpid(), 'startedAt': datetime.now().isoformat()}, handle)
    return lock_path


def run_extraction(days_back: int = 30, range_days: int = 7,
                   end_date: Optional[str] = None, single_day: bool = False,
                   weekly: bool = False,
                   progress: Optional[ProgressCallback] = None,
                   logger: Optional[logging.Logger] = None) -> dict:
    """
    执行完整抽取并发布批次；任一查询失败时不发布任何新 CSV。
    
    Args:
        days_back: 向前回溯的天数（默认30天）
        range_days: 每个区间的天数（默认7天，weekly=True 时忽略）
        end_date: 结束日期（可选，默认今天）
        single_day: 是否按单日查询（默认False）
        weekly: 是否按自然周（周一到周日）查询（默认False）
        progress: 进度回调函数
        logger: 日志记录器
    
    Returns:
        包含 taskId、queryCount 等信息的字典
    """
    config = get_config()
    script_dir = Path(config['paths']['script_dir'])
    template_dir = script_dir / 'sqltemplate'
    output_dir = Path(config['paths']['output'])
    releases_dir = output_dir / 'releases'
    staging_root = output_dir / '.staging'
    template_files = sorted(template_dir.glob('*.sql'))
    if not template_files:
        raise RuntimeError('未找到 SQL 模板: {}'.format(template_dir))

    # 根据模式选择日期区间生成方式
    if weekly:
        ranges = generate_weekly_ranges(days_back, end_date)
    else:
        ranges = generate_date_ranges(days_back, range_days, end_date, single_day)
    
    total = len(ranges) * len(template_files)
    task_id = str(uuid.uuid4())
    staging_dir = staging_root / task_id
    release_dir = releases_dir / task_id
    lock_path = _acquire_lock(output_dir)
    log = logger or logging.getLogger(__name__)

    try:
        staging_dir.mkdir(parents=True, exist_ok=False)
        completed = 0
        generated_files = []
        for date_from, date_to in ranges:
            for template_path in template_files:
                sql = template_path.read_text(encoding='utf-8')
                sql = sql.replace('[date_from]', "'{}'".format(date_from))
                sql = sql.replace('[date_to]', "'{}'".format(date_to))
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = '{}_{}_{}_{}.csv'.format(
                    template_path.stem, date_from, date_to, timestamp)
                output_path = staging_dir / filename
                if progress:
                    progress('extracting', completed, total)
                execute_query_to_csv(sql, output_path, config['db_info'], log)
                generated_files.append(filename)
                completed += 1
                if progress:
                    progress('extracting', completed, total)

        manifest = {
            'taskId': task_id,
            'createdAt': datetime.now().isoformat(),
            'daysBack': days_back,
            'rangeDays': 'weekly' if weekly else range_days,
            'dateFrom': ranges[0][0],
            'dateTo': ranges[-1][1],
            'queryCount': total,
            'rangeCount': len(ranges),
            'files': generated_files,
        }
        (staging_dir / 'manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        if progress:
            progress('publishing', completed, total)
        releases_dir.mkdir(parents=True, exist_ok=True)
        staging_dir.replace(release_dir)
        log.info('Published extraction release %s with %s CSV files (%s ranges)',
                 task_id, total, len(ranges))
        return manifest
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    finally:
        lock_path.unlink(missing_ok=True)
