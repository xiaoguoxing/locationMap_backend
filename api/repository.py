"""数据访问层

业务层只依赖本模块的抽象接口 `MeasurementRepository`，不感知底层是
CSV 还是数据库。将来切换到 SQL Server 时，新增一个 `SqlMeasurementRepository`
实现同一套方法并在 `get_repository()` 里切换即可，Service / Controller
与前端均无需改动。

抽象方法约定返回的行结构（统一字段名，与 CSV 列名解耦）：
    sampleNo / locationCode / locationDesc / district / collectedAt /
    owner / latitude / longitude / value
"""

import abc
import glob
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from api import config

# CSV 文件名形如 cl2_free_1_2026-04-10_2026-04-16_20260518_184254.csv
_FILENAME_PATTERN = re.compile(
    r'^(?P<param>cl2_free_1|ecoli|turby)_'
    r'(?P<from>\d{4}-\d{2}-\d{2})_(?P<to>\d{4}-\d{2}-\d{2})_\d+_\d+\.csv$'
)

# 经纬度列的候选名：SQL 里 try_cast 后的列带 _value 后缀
_LAT_COLUMNS = ['loc_gps_latitude', 'loc_gps_latitude_value', 'latitude', 'lat']
_LON_COLUMNS = ['loc_gps_longitude', 'loc_gps_longitude_value', 'longitude', 'lon']


class MeasurementRepository(abc.ABC):
    """水质测量数据访问接口"""

    @abc.abstractmethod
    def list_date_ranges(self) -> List[Dict[str, str]]:
        """列出所有可用日期区间，按起始日期倒序（最新在前）"""

    @abc.abstractmethod
    def query_rows(self, parameter: str, date_from: str, date_to: str) -> pd.DataFrame:
        """
        查询指定参数与日期区间的采样记录

        Returns:
            DataFrame，列名为抽象层统一字段名；无数据时返回空 DataFrame
        """


class CsvMeasurementRepository(MeasurementRepository):
    """
    CSV 数据源实现

    读取 `gencsv/output/*.csv`。带进程内缓存（按文件路径 + mtime），
    避免同一请求周期内反复解析同一个文件。
    """

    def __init__(self, csv_dir: Optional[Path] = None):
        self._csv_dir = Path(csv_dir or config.CSV_DIR)
        self._cache: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    # ---- 文件发现 ----

    def _scan_files(self) -> List[dict]:
        """扫描目录，解析出 (参数, 起止日期, 路径) 清单"""
        found = []
        for path in sorted(self._csv_dir.glob('*.csv')):
            match = _FILENAME_PATTERN.match(path.name)
            if not match:
                continue
            found.append({
                'parameter': match.group('param'),
                'dateFrom': match.group('from'),
                'dateTo': match.group('to'),
                'path': path,
            })
        return found

    def list_date_ranges(self) -> List[Dict[str, str]]:
        """
        汇总日期区间

        同一区间可能有多个参数的文件，这里按区间去重，
        并记录该区间实际拥有哪些参数，便于前端判断可选项。
        """
        by_range: Dict[str, dict] = {}
        for item in self._scan_files():
            key = '{}_{}'.format(item['dateFrom'], item['dateTo'])
            entry = by_range.setdefault(key, {
                'dateRange': key,
                'dateFrom': item['dateFrom'],
                'dateTo': item['dateTo'],
                'parameters': [],
            })
            if item['parameter'] not in entry['parameters']:
                entry['parameters'].append(item['parameter'])

        # 倒序：最新区间在前（与老 dashboard 的排序行为一致）
        result = sorted(by_range.values(), key=lambda x: x['dateFrom'], reverse=True)
        for entry in result:
            entry['parameters'].sort()
            # CSV 数据源下只要文件存在即可用
            entry['exported'] = True
        return result

    # ---- 数据读取 ----

    def _find_file(self, parameter: str, date_from: str, date_to: str) -> Optional[Path]:
        """
        定位匹配的 CSV

        文件名里带生成时间戳，同一参数+区间可能有多份（重复导出），
        取文件名排序最大的那个（即时间戳最新）。
        """
        pattern = str(self._csv_dir / '{}_{}_{}_*.csv'.format(parameter, date_from, date_to))
        matches = sorted(glob.glob(pattern))
        return Path(matches[-1]) if matches else None

    def _read_csv(self, path: Path) -> pd.DataFrame:
        """读取并规整 CSV（带 mtime 缓存）"""
        key = str(path)
        mtime = path.stat().st_mtime

        with self._lock:
            cached = self._cache.get(key)
            if cached and cached[0] == mtime:
                return cached[1]

        df = pd.read_csv(
            path,
            encoding='utf-8',
            # 原始 CSV 存在列数不一致的脏行，跳过而非报错（与老流程行为一致）
            on_bad_lines='skip',
            dtype=str,
            skipinitialspace=True,
        )
        df.columns = [str(col).lower().strip() for col in df.columns]
        df = self._normalize(df)

        with self._lock:
            self._cache[key] = (mtime, df)
        return df

    @staticmethod
    def _pick_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        """从候选列名里挑第一个存在且有非空值的"""
        for name in candidates:
            if name in df.columns and df[name].notna().any():
                return name
        return None

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """把 CSV 原始列名映射为抽象层统一字段名"""
        lat_col = self._pick_column(df, _LAT_COLUMNS)
        lon_col = self._pick_column(df, _LON_COLUMNS)

        out = pd.DataFrame(index=df.index)
        out['sampleNo'] = df.get('sampno')
        out['locationCode'] = df.get('loccode')
        out['locationDesc'] = df.get('locdescr')
        out['collectedAt'] = df.get('coldate')
        out['owner'] = df.get('owner')
        # district 在 CSV 里是邻里名（如 the peak），统一小写便于后续映射
        out['district'] = (
            df['district'].astype(str).str.lower().str.strip()
            if 'district' in df.columns else None
        )
        out['latitude'] = pd.to_numeric(df[lat_col], errors='coerce') if lat_col else None
        out['longitude'] = pd.to_numeric(df[lon_col], errors='coerce') if lon_col else None
        out['value'] = pd.to_numeric(df.get('result'), errors='coerce')
        return out

    def query_rows(self, parameter: str, date_from: str, date_to: str) -> pd.DataFrame:
        path = self._find_file(parameter, date_from, date_to)
        if path is None:
            return pd.DataFrame(
                columns=['sampleNo', 'locationCode', 'locationDesc', 'collectedAt',
                         'owner', 'district', 'latitude', 'longitude', 'value'])
        return self._read_csv(path)


# ==========================================
# 数据源工厂
# ==========================================

_repository: Optional[MeasurementRepository] = None
_factory_lock = threading.Lock()


def get_repository() -> MeasurementRepository:
    """
    获取数据访问实现（单例）

    切换数据源只需在此处扩展分支，业务层完全不感知。
    将来接数据库时的形态：

        if config.DATA_SOURCE == 'sqlserver':
            return SqlMeasurementRepository(dsn=...)
    """
    global _repository
    if _repository is not None:
        return _repository

    with _factory_lock:
        if _repository is None:
            if config.DATA_SOURCE == 'csv':
                _repository = CsvMeasurementRepository()
            else:
                raise ValueError(
                    '未支持的数据源: {}（当前仅实现 csv）'.format(config.DATA_SOURCE))
    return _repository
