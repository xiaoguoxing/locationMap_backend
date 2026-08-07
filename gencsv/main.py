import os
import sys
from datetime import datetime
from config_loader import get_config
from file_manager import setup_logging, archive_old_files
from db_connector import execute_sql_to_csv

def main():
    # 1. Load Config
    try:
        config = get_config()
    except Exception as e:
        print(f"Critical Error loading config: {e}")
        sys.exit(1)

    # 2. Prepare Paths & Time
    now = datetime.now()
    today_str = now.strftime('%Y%m%d')
    timestamp_str = now.strftime('%Y%m%d_%H%M%S')
    
    # Ensure output folder exists
    os.makedirs(config['paths']['output'], exist_ok=True)

    # 3. Setup Logging
    logger = setup_logging(config['paths']['log'], today_str)
    logger.info("--- Job Started ---")

    # 4. Archive Old Files (Spec Requirement #4)
    logger.info("Checking for old files to archive...")
    archive_old_files(config['paths']['output'], config['paths']['archive'], today_str, logger)

    # 5. Execute SQL Jobs
    for sql_file in config['jobs']:
        sql_path = os.path.join(config['paths']['sql'], sql_file)
        
        if not os.path.exists(sql_path):
            logger.error(f"SQL File not found: {sql_path}")
            continue

        # Generate Output Filename: original_name_datetime.csv
        # Remove .sql extension for the name
        base_name = sql_file.replace('.sql', '') 
        output_filename = f"{base_name}_{timestamp_str}.csv"
        output_path = os.path.join(config['paths']['output'], output_filename)

        logger.info(f"Processing: {sql_file}")
        execute_sql_to_csv(sql_path, output_path, config['db_info'], logger)

    logger.info("--- Job Finished ---")

if __name__ == "__main__":
    main()


