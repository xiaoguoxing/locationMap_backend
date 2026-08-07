import pyodbc
import csv
import os
from datetime import datetime

def get_connection_string(db_config):
    # Driver might vary depending on server installation (ODBC Driver 17/18 for SQL Server)
    # Using a generic approach, you may need to adjust the Driver name
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={db_config['host']},{db_config['port']};"
        f"DATABASE={db_config['database']};"
        f"UID={db_config['username']};"
        f"PWD={db_config['password']};"
        f"TrustServerCertificate=yes;"
    )
    return conn_str

def execute_sql_to_csv(sql_file_path, output_file_path, db_config, logger):
    conn = None
    try:
        conn_str = get_connection_string(db_config)
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_query = f.read()
        
        cursor.execute(sql_query)
        columns = [column[0] for column in cursor.description]
        
        with open(output_file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            # fetchmany is better for large datasets than fetchall
            while True:
                rows = cursor.fetchmany(1000)
                if not rows:
                    break
                writer.writerows(rows)
                
        logger.info(f"Success: {os.path.basename(output_file_path)}")
        return True

    except Exception as e:
        logger.error(f"Failed {os.path.basename(sql_file_path)}: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

