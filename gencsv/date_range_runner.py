"""日期范围 CSV 抽取命令行入口。

无参数时与前端隐藏同步按钮一致：最近 30 天、7 天滚动窗口。
"""

import argparse
import logging
from datetime import datetime

try:
    from .extraction_service import run_extraction
    from .file_manager import setup_logging
    from .config_loader import get_config
except ImportError:
    from extraction_service import run_extraction
    from file_manager import setup_logging
    from config_loader import get_config


def main() -> None:
    parser = argparse.ArgumentParser(description='Date Range SQL Template Runner')
    parser.add_argument('--days', type=int, default=30,
                        help='Number of days to look back (default: 30)')
    parser.add_argument('--range-days', type=int, default=7,
                        help='Number of days per range (default: 7)')
    parser.add_argument('--from', dest='from_date',
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to', dest='to_date',
                        help='End date (YYYY-MM-DD)')
    parser.add_argument('--single-day', action='store_true',
                        help='Process each day individually')
    # 保留旧参数兼容性；共享抽取服务固定读取 sqltemplate 下三套模板。
    parser.add_argument('--use-setting-ini', action='store_true',
                        help=argparse.SUPPRESS)
    args = parser.parse_args()

    if bool(args.from_date) != bool(args.to_date):
        parser.error('--from and --to must be specified together')

    days_back = args.days
    if args.from_date and args.to_date:
        start = datetime.strptime(args.from_date, '%Y-%m-%d')
        end = datetime.strptime(args.to_date, '%Y-%m-%d')
        days_back = (end - start).days
        if days_back < 0:
            parser.error('--from must not be later than --to')

    config = get_config()
    logger = setup_logging(config['paths']['log'], datetime.now().strftime('%Y%m%d'))
    try:
        result = run_extraction(
            days_back=days_back,
            range_days=args.range_days,
            end_date=args.to_date,
            single_day=args.single_day,
            logger=logger,
        )
        logger.info('Extraction completed: release=%s queries=%s',
                    result['taskId'], result['queryCount'])
    except Exception:
        logger.exception('CSV extraction failed')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
