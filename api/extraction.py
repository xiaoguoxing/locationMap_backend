"""CSV 后台同步任务。

任务只负责生成并发布新批次，不主动刷新前端日期或地图缓存。
"""

import logging
import threading
import time
import uuid
from copy import deepcopy
from typing import Optional

from gencsv.extraction_service import (
    ExtractionAlreadyRunningError,
    generate_date_ranges,
    generate_weekly_ranges,
    run_extraction,
)

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_active_task_id: Optional[str] = None
_tasks: dict[str, dict] = {}


def _now_ms() -> int:
    return int(time.time() * 1000)


def start_refresh(weekly: bool = True) -> dict:
    """创建最近 30 天后台同步任务（默认使用按自然周 --weekly 模式）。"""
    global _active_task_id
    with _lock:
        if _active_task_id:
            active = _tasks.get(_active_task_id)
            if active and active['status'] in ('queued', 'running', 'publishing'):
                result = deepcopy(active)
                result['reused'] = True
                return result

        try:
            if weekly:
                expected_queries = len(generate_weekly_ranges(days_back=30)) * 3
            else:
                expected_queries = len(generate_date_ranges(days_back=30, range_days=7)) * 3
        except Exception:
            expected_queries = 15 if weekly else 93

        task_id = str(uuid.uuid4())
        task = {
            'taskId': task_id,
            'status': 'queued',
            'stage': 'queued',
            'completedQueries': 0,
            'totalQueries': expected_queries,
            'startedAt': None,
            'finishedAt': None,
            'releaseId': None,
            'errorMessage': None,
            'reused': False,
        }
        _tasks[task_id] = task
        _active_task_id = task_id

    thread = threading.Thread(target=_run_task, args=(task_id, weekly), daemon=True)
    thread.start()
    return deepcopy(task)


def _run_task(task_id: str, weekly: bool = True) -> None:
    global _active_task_id

    def update_progress(stage: str, completed: int, total: int) -> None:
        with _lock:
            task = _tasks[task_id]
            task['stage'] = stage
            task['status'] = 'publishing' if stage == 'publishing' else 'running'
            task['completedQueries'] = completed
            task['totalQueries'] = total

    with _lock:
        _tasks[task_id]['status'] = 'running'
        _tasks[task_id]['stage'] = 'extracting'
        _tasks[task_id]['startedAt'] = _now_ms()

    try:
        if weekly:
            result = run_extraction(days_back=30, weekly=True,
                                    progress=update_progress, logger=logger)
        else:
            result = run_extraction(days_back=30, range_days=7,
                                    progress=update_progress, logger=logger)
        with _lock:
            task = _tasks[task_id]
            task['status'] = 'succeeded'
            task['stage'] = 'completed'
            task['releaseId'] = result['taskId']
            task['completedQueries'] = result['queryCount']
            task['totalQueries'] = result['queryCount']
    except ExtractionAlreadyRunningError:
        with _lock:
            _tasks[task_id]['status'] = 'failed'
            _tasks[task_id]['stage'] = 'failed'
            _tasks[task_id]['errorMessage'] = '已有数据同步任务正在运行'
    except Exception:
        logger.exception('Data extraction task failed: %s', task_id)
        with _lock:
            _tasks[task_id]['status'] = 'failed'
            _tasks[task_id]['stage'] = 'failed'
            _tasks[task_id]['errorMessage'] = '数据同步失败，请联系管理员查看服务日志'
    finally:
        with _lock:
            _tasks[task_id]['finishedAt'] = _now_ms()
            if _active_task_id == task_id:
                _active_task_id = None


def get_status(task_id: str) -> Optional[dict]:
    """读取当前进程内的任务状态。"""
    with _lock:
        task = _tasks.get(task_id)
        return deepcopy(task) if task else None
