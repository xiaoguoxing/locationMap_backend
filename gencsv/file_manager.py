import os
import shutil
import logging
from datetime import datetime

def setup_logging(log_folder, date_str):
    os.makedirs(log_folder, exist_ok=True)
    log_file = os.path.join(log_folder, f"{date_str}.log")
    
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Also print to console for immediate feedback during testing
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger('').addHandler(console)
    
    return logging.getLogger(__name__)

def archive_old_files(output_folder, archive_folder, today_str, logger):
    """
    Moves files with date prefix older than today_str (YYYYMMDD) to archive.
    Expects filename format: name_YYYYMMDD_HHMMSS.csv
    """
    os.makedirs(archive_folder, exist_ok=True)
    
    if not os.path.exists(output_folder):
        return

    for filename in os.listdir(output_folder):
        if not filename.endswith('.csv'):
            continue
            
        # Simple parsing: split by underscore, expect date at index -2 or similar
        # Based on spec: cl2_free_1_202603261211.csv
        # We need to extract the date part robustly.
        parts = filename.replace('.csv', '').split('_')
        
        # Heuristic: The second to last part usually contains the date if format is name_YYYYMMDD...
        # However, names might have underscores. 
        # Let's assume the date is the last block before extension, or we search for 8 digits.
        
        import re
        date_match = re.search(r'(\d{8})', filename)
        
        if date_match:
            file_date = date_match.group(1)
            if file_date < today_str:
                src = os.path.join(output_folder, filename)
                dst = os.path.join(archive_folder, filename)
                try:
                    shutil.move(src, dst)
                    logger.info(f"Archived old file: {filename}")
                except Exception as e:
                    logger.error(f"Failed to archive {filename}: {e}")


