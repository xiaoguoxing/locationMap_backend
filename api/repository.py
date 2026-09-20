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
        """扫描历史根目录和已完整发布的批次 CSV。"""
        found = []
        paths = list(self._csv_dir.glob('*.csv'))
        releases_dir = self._csv_dir / 'releases'
        if releases_dir.exists():
            for release_dir in releases_dir.iterdir():
                if release_dir.is_dir() and (release_dir / 'manifest.json').is_file():
                    paths.extend(release_dir.glob('*.csv'))

        for path in sorted(paths, key=lambda item: str(item)):
            match = _FILENAME_PATTERN.match(path.name)
            if not match:
                continue
            # 跳过无数据记录的空文件（仅有表头通常 <= 180 字节）
            try:
                if path.stat().st_size <= 180:
                    continue
            except OSError:
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

        # 日期必须具备三项参数才可用，避免暴露不完整批次。
        required = {'cl2_free_1', 'ecoli', 'turby'}
        result = [
            entry for entry in by_range.values()
            if set(entry['parameters']) == required
        ]
        result.sort(key=lambda x: x['dateFrom'], reverse=True)
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
        candidates = [
            item['path'] for item in self._scan_files()
            if item['parameter'] == parameter
            and item['dateFrom'] == date_from
            and item['dateTo'] == date_to
        ]
        return max(candidates, key=lambda path: path.name) if candidates else None

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
        # 需求：生成地图显示 18 区时，优先依赖 CSV 中的 big_district 列
        # 若存在 big_district 且非空则优先使用；否则回退使用 district 列（邻里名）
        big_dist_col = None
        for col in ('big_district', 'big district', 'bigdistrict'):
            if col in df.columns:
                big_dist_col = col
                break

        if big_dist_col:
            s_big = df[big_dist_col].astype(str).str.strip()
            s_big = s_big.mask(s_big.str.lower().isin(['nan', 'none', '']))
            if 'district' in df.columns:
                s_dist = df['district'].astype(str).str.strip()
                s_dist = s_dist.mask(s_dist.str.lower().isin(['nan', 'none', '']))
                out['district'] = s_big.fillna(s_dist).str.lower()
            else:
                out['district'] = s_big.str.lower()
        elif 'district' in df.columns:
            out['district'] = (
                df['district'].astype(str).str.lower().str.strip()
            )
        else:
            out['district'] = None
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
