import csv
from pathlib import Path

import pyodbc

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

def execute_query_to_csv(sql_query, output_file_path, db_config, logger):
    """执行固定模板生成的 SQL，并将结果写入指定暂存文件。"""
    conn = None
    output_path = Path(output_file_path)
    try:
        conn_str = get_connection_string(db_config)
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute(sql_query)
        columns = [column[0] for column in cursor.description]

        with output_path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            while True:
                rows = cursor.fetchmany(1000)
                if not rows:
                    break
                writer.writerows(rows)

        logger.info('Success: %s', output_path.name)
    except Exception:
        output_path.unlink(missing_ok=True)
        logger.exception('Failed to generate %s', output_path.name)
        raise
    finally:
        if conn:
            conn.close()

def execute_sql_to_csv(sql_file_path, output_file_path, db_config, logger):
    """兼容旧调用：读取 SQL 文件后交给统一执行函数。"""
    try:
        sql_query = Path(sql_file_path).read_text(encoding='utf-8')
        execute_query_to_csv(sql_query, output_file_path, db_config, logger)
        return True
    except Exception:
        return False

