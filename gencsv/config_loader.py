import configparser
import os

def get_config():
    config = configparser.ConfigParser()
    # Ensure we look for ini in the same directory as the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ini_path = os.path.join(script_dir, 'setting.ini')
    
    if not os.path.exists(ini_path):
        raise FileNotFoundError(f"Configuration file not found: {ini_path}")
        
    config.read(ini_path, encoding='utf-8')
    
    return {
        'db_info': { # Renamed from 'db' to match main.py
            'host': config.get('DATABASE', 'host'),
            'port': config.get('DATABASE', 'port'),
            'database': config.get('DATABASE', 'database'),
            'username': config.get('DATABASE', 'username'),
            'password': config.get('DATABASE', 'password'),
            'tds_version': config.get('DATABASE', 'tds_version', fallback='7.2'),
        },
        'paths': {
            'script_dir': script_dir,
            'sql': os.path.join(script_dir, config.get('PATHS', 'sql_folder')),
            'output': os.path.join(script_dir, config.get('PATHS', 'output_folder')),
            'archive': os.path.join(script_dir, config.get('PATHS', 'archive_folder')),
            'log': os.path.join(script_dir, config.get('PATHS', 'log_folder')),
        },
        'jobs': [f.strip() for f in config.get('JOBS', 'files').split(',')],
    }

