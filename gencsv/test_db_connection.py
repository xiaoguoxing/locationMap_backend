"""
Simple test script to verify database connectivity
before running the full CSV generation process.
"""
import pymssql
import sys
import os

# Add the gencsv folder to path to import config_loader
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from config_loader import get_config


def test_connection():
    """Test database connection with pymssql and return status."""
    conn = None
    try:
        print("=" * 60)
        print("DATABASE CONNECTION DIAGNOSTIC (pymssql)")
        print("=" * 60)
        
        # Load configuration
        print("\n[1] Loading configuration from setting.ini...")
        config = get_config()
        db_config = config['db_info']
        host = db_config['host']
        port = str(db_config['port'])
        database = db_config['database']
        username = db_config['username']
        password = db_config['password']
        tds_version = db_config.get('tds_version', '7.2')
        
        print(f"   Host        : {host}")
        print(f"   Port        : {port}")
        print(f"   Database    : {database}")
        print(f"   Username    : {username}")
        masked_pwd = password[:2] + "*" * (len(password) - 2) if len(password) > 2 else "***"
        print(f"   Password    : {masked_pwd} (length: {len(password)})")
        print(f"   TDS Version : {tds_version}")
        
        # Environment mismatch reminder
        if '10.66.89.44' in host and database == 'labworks':
            print("\n   [!] CONFIG MISMATCH WARNING:")
            print("       Host is '10.66.89.44' (UAT), but Database is 'labworks' (Prod).")
            print("       - For Prod: Host is typically 'limsdbpr02', DB 'labworks', password 'maplocread'")
            print("       - For UAT:  Host is '10.66.89.44', DB 'labworks_wsduat', password 'maplocread'")

        # Step 2a: Test credentials without database
        print("\n[2] Step 2a: Testing login credentials (default database)...")
        try:
            conn_basic = pymssql.connect(
                server=host,
                port=port,
                database='',
                user=username,
                password=password,
                charset='utf8',
                tds_version=tds_version,
                login_timeout=10,
            )
            print("   [OK] User/Password credentials are VALID!")
            cursor = conn_basic.cursor()
            cursor.execute("SELECT DB_NAME() AS default_db")
            row = cursor.fetchone()
            default_db = row[0] if row else 'unknown'
            print(f"   [OK] Connected to user's default database: '{default_db}'")
            conn_basic.close()
        except pymssql.Error as e:
            print(f"   [FAIL] Authentication failed: {e}")
            if "18456" in str(e):
                print("\n   --> Result: Password or Username is INCORRECT on this server.")
                print(f"   --> Server '{host}' rejected user '{username}'.")
                print("   --> Please check:")
                print("       1. Is this the right host? (e.g. should it be limsdbpr02 for Prod?)")
                print("       2. Is the password correct? (e.g. maplocread vs maplocread#)")
            return False

        # Step 2b: Test connecting to target database
        print(f"\n[3] Step 2b: Testing connection to target database '{database}'...")
        conn = pymssql.connect(
            server=host,
            port=port,
            database=database,
            user=username,
            password=password,
            charset='utf8',
            tds_version=tds_version,
            login_timeout=10,
        )
        print(f"   [OK] Connection to '{database}' established successfully!")
        
        # Step 3: Test query
        print("\n[4] Step 3: Testing simple query execution...")
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION AS version")
        row = cursor.fetchone()
        print(f"   [OK] SQL Server version: {row[0][:50]}...")
        cursor.close()
        
        print("\n" + "=" * 60)
        print("DATABASE CONNECTION TEST PASSED")
        print("=" * 60)
        return True
        
    except pymssql.Error as e:
        print("\n" + "=" * 60)
        print("DATABASE CONNECTION TEST FAILED")
        print("=" * 60)
        print(f"\nError Type: {type(e).__name__}")
        print(f"Error Details: {str(e)}")
        if "18456" in str(e):
            print("\nAnalysis for Error 18456:")
            print(f"  - Target database '{database}' does not exist on '{host}',")
            print(f"    OR user '{username}' does not have permission to access '{database}'.")
        return False
        
    except Exception as e:
        print("\n" + "=" * 50)
        print("UNEXPECTED ERROR")
        print("=" * 50)
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Details: {str(e)}")
        return False
        
    finally:
        if conn:
            conn.close()
            print("\n[Cleanup] Database connection closed.")


if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
