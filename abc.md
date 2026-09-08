Searched for files: *db_connector*.py
Searched for files: *db_connector*.py
Viewed db_connector.py:1-57
Searched for "get_connection_string"
Searched for "db_connector"
Viewed extraction_service.py:1-60
Searched for "execute_sql_to_csv"
Ran command: `python -c "import pymssql; print(pymssql.__version__)"`
Searched for files: *python*
Viewed test_db_connection.py:1-93
Ran command: `where python`
Ran command: `Get-Command python | Select-Object -ExpandProperty Source`
Searched for files: *req*
Viewed requirements.txt:1-65
Ran command: `Test-Path .venv312`
Ran command: `.\.venv312\Scripts\python.exe -c "import pymssql; print(pymssql.__version__)"`
Viewed config_loader.py:1-33
Ran command: `.\.venv312\Scripts\pip.exe install pymssql`
Ran command: `.\.venv312\Scripts\python.exe -c "import pymssql, inspect; print(inspect.signature(pymssql.connect)); print(pymssql.connect.__doc__)"`
Ran command: `.\.venv312\Scripts\python.exe -c "import pymssql; print(dir(pymssql.Cursor))"`
Searched for "db_connector"
Viewed c:\Users\www96\Documents\WXWorkLocalPro_data\Profiles\F3BE12A25989EE3871ABEE88CA786329\Cache\chat\file\202608\hkLocatingMap\gencsv\main.py
Listed directory gencsv
Searched for "db_connector"
Viewed DATE_RANGE_ARCHITECTURE.md:1-86
Ran command: `.\.venv312\Scripts\python.exe -c "import pymssql;
try:
    pymssql.connect(server='127.0.0.1', port='1433', user='sa', password='pwd', database='db', login_timeout=1)
except Exception as e:
    print('str port exception:', type(e), e)

try:
    pymssql.connect(server='127.0.0.1', port=1433, user='sa', password='pwd', database='db', login_timeout=1)
except Exception as e:
    print('int port exception:', type(e), e)
"`
Ran command: `.\.venv312\Scripts\python.exe -c "import pymssql
try:
    pymssql.connect('server=localhost;database=test')
except Exception as e:
    print(e)
"`
Viewed setting.ini:1-34
Listed directory sqltemplate
Viewed cl2_free_1.sql:1-52
Ran command: `.\.venv312\Scripts\python.exe -c "
import unittest.mock as mock
import csv
import logging
from pathlib import Path

# Mock pymssql.connect
mock_conn = mock.MagicMock()
mock_cursor = mock.MagicMock()
mock_conn.cursor.return_value = mock_cursor
mock_cursor.description = [('id',), ('name',)]
mock_cursor.fetchmany.side_effect = [[(1, 'Alice'), (2, 'Bob')], []]

with mock.patch('pymssql.connect', return_value=mock_conn) as mock_connect:
    db_config = {
        'host': '127.0.0.1',
        'port': '1433',
        'database': 'test_db',
        'username': 'sa',
        'password': 'password123'
    }
    # Test connection kwargs
    params = {
        'server': db_config['host'],
        'port': str(db_config['port']),
        'database': db_config['database'],
        'user': db_config['username'],
        'password': db_config['password'],
        'charset': 'utf8',
    }
    conn = mock_connect(**params)
    cursor = conn.cursor()
    cursor.execute('SELECT 1')
    cols = [col[0] for col in cursor.description]
    rows = cursor.fetchmany(1000)
    print('Cols:', cols)
    print('Rows:', rows)
    conn.close()
    print('Closed called:', mock_conn.close.called)
"`
Edited db_connector.py
Viewed db_connector.py:1-62
Ran command: `.\.venv312\Scripts\python.exe -c "
import sys
import unittest.mock as mock
from pathlib import Path

# Add gencsv directory to sys.path
sys.path.insert(0, 'c:/Users/www96/Documents/WXWorkLocalPro_data/Profiles/F3BE12A25989EE3871ABEE88CA786329/Cache/chat/file/202608/hkLocatingMap/gencsv')

import db_connector
import logging

logger = logging.getLogger('test')

# 1. Test get_connection_string
cfg = {
    'host': '192.168.1.100',
    'port': '1433',
    'database': 'testdb',
    'username': 'admin',
    'password': 'secret_password'
}
params = db_connector.get_connection_string(cfg)
assert params['server'] == '192.168.1.100'
assert params['port'] == '1433'
assert params['database'] == 'testdb'
assert params['user'] == 'admin'
assert params['password'] == 'secret_password'
assert params['charset'] == 'utf8'
print('[OK] get_connection_string test passed')

# 2. Test execute_query_to_csv with mock
mock_conn = mock.MagicMock()
mock_cursor = mock.MagicMock()
mock_conn.cursor.return_value = mock_cursor
mock_cursor.description = [('id',), ('val',)]
mock_cursor.fetchmany.side_effect = [[(1, 'foo'), (2, 'bar')], []]

with mock.patch('pymssql.connect', return_value=mock_conn) as mock_connect:
    test_csv = Path('c:/Users/www96/Documents/WXWorkLocalPro_data/Profiles/F3BE12A25989EE3871ABEE88CA786329/Cache/chat/file/202608/hkLocatingMap/gencsv/_test_tmp.csv')
    try:
        db_connector.execute_query_to_csv('SELECT id, val FROM test', str(test_csv), cfg, logger)
        assert test_csv.exists()
        content = test_csv.read_text(encoding='utf-8')
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        assert lines == ['id,val', '1,foo', '2,bar']
        assert mock_conn.close.called
        print('[OK] execute_query_to_csv test passed')
    finally:
        test_csv.unlink(missing_ok=True)

print('[ALL TESTS PASSED]')
"`
Ran command: `git diff gencsv/db_connector.py`

已完成对 [gencsv/db_connector.py](file:///c:/Users/www96/Documents/WXWorkLocalPro_data/Profiles/F3BE12A25989EE3871ABEE88CA786329/Cache/chat/file/202608/hkLocatingMap/gencsv/db_connector.py) 的最小改动替换。

### 改动说明

1. **驱动替换**：
   - 将 `import pyodbc` 替换为 `import pymssql`。
2. **连接实现替换**：
   - 保留了 `get_connection_string(db_config)` 函数名及入参，适配 `pymssql` 的连接入参规范返回连接参数字典（`server`、`port`、`database`、`user`、`password`、`charset='utf8'`）。
   - 在 `execute_query_to_csv` 中将 `pyodbc.connect(...)` 替换为 `pymssql.connect(...)`。
3. **保持不变的部分**：
   - 函数名与签名保持原样：`get_connection_string(db_config)`、`execute_query_to_csv(sql_query, output_file_path, db_config, logger)`、`execute_sql_to_csv(sql_file_path, output_file_path, db_config, logger)`。
   - 上层游标执行（`cursor.execute`、`cursor.description` 列名解析）、1000 条分批写入 CSV（`cursor.fetchmany(1000)`）、异常清理（`output_path.unlink`）及连接关闭（`conn.close()`）等业务逻辑完全保持原样。

### 修改前后核心 Diff

```diff
--- a/gencsv/db_connector.py
+++ b/gencsv/db_connector.py
@@ -1,28 +1,33 @@
 import csv
 from pathlib import Path
 
-import pyodbc
+import pymssql
 
 def get_connection_string(db_config):
-    # Driver might vary depending on server installation (ODBC Driver 17/18 for SQL Server)
-    # Using a generic approach, you may need to adjust the Driver name
-    conn_str = (
-        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
-        f"SERVER={db_config['host']},{db_config['port']};"
-        f"DATABASE={db_config['database']};"
-        f"UID={db_config['username']};"
-        f"PWD={db_config['password']};"
-        f"TrustServerCertificate=yes;"
-    )
-    return conn_str
+    # pymssql 使用连接参数字典，保留原函数名与入参以保持兼容
+    return {
+        'server': db_config.get('host', db_config.get('server')),
+        'port': str(db_config.get('port', 1433)),
+        'database': db_config.get('database'),
+        'user': db_config.get('username', db_config.get('user')),
+        'password': db_config.get('password'),
+        'charset': 'utf8',
+    }
 
 def execute_query_to_csv(sql_query, output_file_path, db_config, logger):
     """执行固定模板生成的 SQL，并将结果写入指定暂存文件。"""
     conn = None
     output_path = Path(output_file_path)
     try:
-        conn_str = get_connection_string(db_config)
-        conn = pyodbc.connect(conn_str)
+        conn_params = get_connection_string(db_config)
+        conn = pymssql.connect(**conn_params) if isinstance(conn_params, dict) else pymssql.connect(
+            server=db_config.get('host', db_config.get('server')),
+            port=str(db_config.get('port', 1433)),
+            database=db_config.get('database'),
+            user=db_config.get('username', db_config.get('user')),
+            password=db_config.get('password'),
+            charset='utf8',
+        )
         cursor = conn.cursor()
         cursor.execute(sql_query)
```

> [!NOTE]
> 虚拟环境已验证安装 `pymssql`，并通过了函数签名与数据流的单元测试。若后续需要固化环境依赖，可在 `requirements.txt` 中将 `pyodbc` 调整为 `pymssql`。