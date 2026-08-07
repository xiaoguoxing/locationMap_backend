"""
Date Range SQL Template Runner

This script processes SQL templates with date placeholders [date_from] and [date_to]
to generate CSV files for multiple date ranges.

Usage:
    # Run for last 30 days with 14-day ranges
    python date_range_runner.py --days 30 --range-days 14
    
    # Run for specific date range
    python date_range_runner.py --from 2026-03-01 --to 2026-03-15
    
    # Run single day (today minus N days)
    python date_range_runner.py --days 7 --single-day
"""

import os
import sys
import argparse
import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from config_loader import get_config
from db_connector import execute_sql_to_csv
from file_manager import setup_logging, archive_old_files


def generate_date_ranges(days_back, range_days, end_date=None):
    """
    Generate date ranges for processing using backward-looking windows.
    
    For each date in the range, creates a window looking back 'range_days' days.
    Example: --from 2025-12-01 --to 2025-12-31 --range-days 14
    - Dec 1: Nov 18 → Dec 1 (14 days inclusive)
    - Dec 2: Nov 19 → Dec 2
    - etc.
    
    Args:
        days_back: Number of days to look back from end_date (determines start date)
        range_days: Number of days in each backward-looking window (inclusive)
        end_date: End date (defaults to today)
    
    Returns:
        List of tuples (date_from, date_to)
    """
    if end_date is None:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Calculate start date based on days_back
    start_date = end_date - timedelta(days=days_back)
    
    ranges = []
    
    # For each date from start to end, create a backward-looking window
    current = start_date
    while current <= end_date:
        # Calculate window start (inclusive: range_days days ending on current)
        # For 14 days ending on Dec 1: Nov 18 to Dec 1 (inclusive = 14 days)
        window_start = current - timedelta(days=range_days - 1)
        
        ranges.append((
            window_start.strftime('%Y-%m-%d'),
            current.strftime('%Y-%m-%d')
        ))
        current += timedelta(days=1)
    
    return ranges


def process_sql_template(template_path, date_from, date_to):
    """
    Read SQL template and replace placeholders with actual dates.
    
    Args:
        template_path: Path to SQL template file
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
    
    Returns:
        Processed SQL query string
    """
    with open(template_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # Replace placeholders
    sql_content = sql_content.replace('[date_from]', f"'{date_from}'")
    sql_content = sql_content.replace('[date_to]', f"'{date_to}'")
    
    return sql_content


def save_processed_sql(sql_content, output_path):
    """Save processed SQL to file for debugging."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(sql_content)


def run_date_range_process(days_back, range_days, single_day=False, end_date=None, use_setting_ini=False):
    """
    Main runner for date range SQL processing.
    
    Args:
        days_back: Number of days to look back
        range_days: Number of days per range
        single_day: If True, process each day individually
        end_date: Specific end date (YYYY-MM-DD)
    """
    # Load configuration
    config = get_config()
    script_dir = config['paths']['script_dir']
    
    # Setup paths
    template_dir = os.path.join(script_dir, 'sqltemplate')
    output_dir = config['paths']['output']
    processed_sql_dir = os.path.join(script_dir, 'sql')
    log_dir = config['paths']['log']
    
    # Create directories
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(processed_sql_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    
    # Setup logging
    today_str = datetime.now().strftime('%Y%m%d')
    logger = setup_logging(log_dir, today_str)
    logger.info("=" * 60)
    logger.info("Date Range SQL Template Runner Started")
    logger.info("=" * 60)
    
    # Generate date ranges
    if single_day:
        # Generate individual days
        if end_date is None:
            end_date = datetime.now().date()
        else:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        start_date = end_date - timedelta(days=days_back)
        
        date_ranges = []
        current = start_date
        while current <= end_date:
            date_str = current.strftime('%Y-%m-%d')
            date_ranges.append((date_str, date_str))
            current += timedelta(days=1)
    else:
        date_ranges = generate_date_ranges(days_back, range_days, end_date)
    
    logger.info(f"Generated {len(date_ranges)} date ranges to process")
    
    # Get all SQL templates
    if not os.path.exists(template_dir):
        logger.error(f"Template directory not found: {template_dir}")
        return
    
    # Get SQL templates based on use_setting_ini flag
    if use_setting_ini:
        # Use files from setting.ini [JOBS] section
        template_files = config.get('jobs', [])
        if not template_files:
            logger.error("No SQL files specified in setting.ini [JOBS] section")
            return
        logger.info(f"Using {len(template_files)} SQL files from setting.ini: {', '.join(template_files)}")
    else:
        # Get all SQL templates from folder
        template_files = [f for f in os.listdir(template_dir) if f.endswith('.sql')]
        if not template_files:
            logger.error(f"No SQL templates found in {template_dir}")
            return
        logger.info(f"Found {len(template_files)} SQL templates in folder")
    
    # Process each date range
    total_success = 0
    total_failed = 0
    
    for date_from, date_to in date_ranges:
        logger.info("-" * 60)
        logger.info(f"Processing date range: {date_from} to {date_to}")
        
        for template_file in template_files:
            template_path = os.path.join(template_dir, template_file)
            
            # Process template with date placeholders
            try:
                sql_content = process_sql_template(template_path, date_from, date_to)
            except Exception as e:
                logger.error(f"Failed to process template {template_file}: {e}")
                total_failed += 1
                continue
            
            # Save processed SQL for debugging
            processed_sql_name = f"{template_file.replace('.sql', '')}_{date_from}_{date_to}.sql"
            processed_sql_path = os.path.join(processed_sql_dir, processed_sql_name)
            save_processed_sql(sql_content, processed_sql_path)
            
            # Generate output filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_name = template_file.replace('.sql', '')
            output_filename = f"{base_name}_{date_from}_{date_to}_{timestamp}.csv"
            output_path = os.path.join(output_dir, output_filename)
            
            # Execute SQL and generate CSV
            # Write SQL to temporary file for db_connector
            temp_sql_file = processed_sql_path
            
            logger.info(f"Executing: {template_file} for range {date_from} to {date_to}")
            
            success = execute_sql_to_csv(temp_sql_file, output_path, config['db_info'], logger)
            
            if success:
                total_success += 1
            else:
                total_failed += 1
    
    logger.info("=" * 60)
    logger.info("Date Range SQL Template Runner Finished")
    logger.info(f"Total Success: {total_success}, Total Failed: {total_failed}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Date Range SQL Template Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run for last 30 days with 14-day ranges
    python date_range_runner.py --days 30 --range-days 14
    
    # Run for specific date range
    python date_range_runner.py --from 2026-03-01 --to 2026-03-15
    
    # Run single day (today minus N days)
    python date_range_runner.py --days 7 --single-day
        """
    )
    
    parser.add_argument('--days', type=int, default=30,
                        help='Number of days to look back (default: 30)')
    parser.add_argument('--range-days', type=int, default=7,
                        help='Number of days per range (default: 7)')
    parser.add_argument('--from', dest='from_date', type=str,
                        help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to', dest='to_date', type=str,
                        help='End date (YYYY-MM-DD)')
    parser.add_argument('--single-day', action='store_true',
                        help='Process each day individually')
    parser.add_argument('--use-setting-ini', action='store_true',
                        help='Use SQL files listed in setting.ini [JOBS] section instead of all files in sqltemplate/')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.from_date and not args.to_date:
        parser.error("--to is required when --from is specified")
    if args.to_date and not args.from_date:
        parser.error("--from is required when --to is specified")
    
    # Run the process
    if args.from_date and args.to_date:
        # Calculate days between dates
        from_dt = datetime.strptime(args.from_date, '%Y-%m-%d')
        to_dt = datetime.strptime(args.to_date, '%Y-%m-%d')
        days_back = (to_dt - from_dt).days
        
        run_date_range_process(
            days_back=days_back,
            range_days=args.range_days,
            single_day=args.single_day,
            end_date=args.to_date,
            use_setting_ini=args.use_setting_ini
        )
    else:
        run_date_range_process(
            days_back=args.days,
            range_days=args.range_days,
            single_day=args.single_day,
            use_setting_ini=args.use_setting_ini
        )


if __name__ == "__main__":
    main()
