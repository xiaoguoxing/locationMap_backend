import csv
from pathlib import Path

import pymssql

def get_connection_string(db_config):
    # pymssql 使用连接参数字典，保留原函数名与入参以保持兼容
    return {
        'server': db_config.get('host', db_config.get('server')),
        'port': str(db_config.get('port', 1433)),
        'database': db_config.get('database'),
        'user': db_config.get('username', db_config.get('user')),
        'password': db_config.get('password'),
        'charset': 'utf8',
        'tds_version': db_config.get('tds_version', '7.2'),
    }

def execute_query_to_csv(sql_query, output_file_path, db_config, logger):
    """执行固定模板生成的 SQL，并将结果写入指定暂存文件。"""
    conn = None
    output_path = Path(output_file_path)
    try:
        conn_params = get_connection_string(db_config)
        conn = pymssql.connect(**conn_params) if isinstance(conn_params, dict) else pymssql.connect(
            server=db_config.get('host', db_config.get('server')),
            port=str(db_config.get('port', 1433)),
            database=db_config.get('database'),
            user=db_config.get('username', db_config.get('user')),
            password=db_config.get('password'),
            charset='utf8',
            tds_version=db_config.get('tds_version', '7.2'),
        )
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

