"""
Simple test script to verify database connectivity
before running the full CSV generation process.
"""
import pyodbc
import sys
import os

# Add the gencsv folder to path to import config_loader
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from config_loader import get_config


def test_connection():
    """Test database connection and return status."""
    conn = None
    try:
        print("=" * 50)
        print("DATABASE CONNECTION TEST")
        print("=" * 50)
        
        # Load configuration
        print("\n[1] Loading configuration from setting.ini...")
        config = get_config()
        db_config = config['db_info']
        print(f"   [OK] Host: {db_config['host']}")
        print(f"   [OK] Port: {db_config['port']}")
        print(f"   [OK] Database: {db_config['database']}")
        print(f"   [OK] Username: {db_config['username']}")
        
        # Build connection string
        print("\n[2] Building connection string...")
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={db_config['host']},{db_config['port']};"
            f"DATABASE={db_config['database']};"
            f"UID={db_config['username']};"
            f"PWD={db_config['password']};"
        )
        print("   [OK] Connection string prepared")
        
        # Attempt connection
        print("\n[3] Attempting to connect to database...")
        conn = pyodbc.connect(conn_str, timeout=10)
        print("   [OK] Connection established successfully!")
        
        # Test query
        print("\n[4] Testing with a simple query...")
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION AS version")
        row = cursor.fetchone()
        print(f"   [OK] SQL Server version: {row[0][:50]}...")
        cursor.close()
        
        print("\n" + "=" * 50)
        print("DATABASE CONNECTION TEST PASSED")
        print("=" * 50)
        return True
        
    except pyodbc.Error as e:
        print("\n" + "=" * 50)
        print("DATABASE CONNECTION TEST FAILED")
        print("=" * 50)
        print(f"\nError Type: {type(e).__name__}")
        print(f"Error Details: {str(e)}")
        print("\nPossible causes:")
        print("  - SQL Server is not running or not accessible")
        print("  - Network/firewall blocking port 1433")
        print("  - Invalid credentials (username/password)")
        print("  - ODBC Driver 17 for SQL Server not installed")
        print("  - Database name 'labworks_wsduat' doesn't exist")
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
