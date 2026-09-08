import csv
from pathlib import Path

import pymssql

try:
    from api.data.district_mapping import get_big_district
except ImportError:
    import sys
    _parent = Path(__file__).resolve().parent.parent
    if str(_parent) not in sys.path:
        sys.path.insert(0, str(_parent))
    try:
        from api.data.district_mapping import get_big_district
    except ImportError:
        def get_big_district(raw):
            return ''

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

        col_lower = [str(col).lower().strip() for col in columns]
        district_idx = col_lower.index('district') if 'district' in col_lower else -1
        add_big_district = (district_idx != -1) and ('big_district' not in col_lower)

        out_columns = list(columns)
        if add_big_district:
            out_columns.append('big_district')

        with output_path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            writer.writerow(out_columns)
            while True:
                rows = cursor.fetchmany(1000)
                if not rows:
                    break
                if add_big_district:
                    enriched_rows = []
                    for row in rows:
                        raw_dist = row[district_idx]
                        big_dist = get_big_district(raw_dist)
                        enriched_rows.append(list(row) + [big_dist])
                    writer.writerows(enriched_rows)
                else:
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

