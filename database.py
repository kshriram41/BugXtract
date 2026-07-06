import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'bugxtract.db').replace('\\', '/')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bugs (
            bug_id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            source_team TEXT,
            severity TEXT,
            priority TEXT,
            area TEXT,
            recommended_team TEXT,
            root_cause TEXT,
            suggested_fix TEXT,
            confidence INTEGER,
            duplicate_status TEXT,
            similarity_score INTEGER,
            duplicate_candidate TEXT,
            health_score INTEGER,
            missing_information TEXT, -- Comma-separated fields
            clarification_message TEXT,
            severity_reasoning TEXT,
            status TEXT,
            date_fixed TEXT,
            suggested_fix_applied TEXT,
            resolution_summary TEXT,
            model_used TEXT,
            router_status TEXT,
            classification_status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Migration: Add model_used if it doesn't exist in existing databases
    try:
        cursor.execute("SELECT model_used FROM bugs LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE bugs ADD COLUMN model_used TEXT")

    # Migration: Add router_status if it doesn't exist
    try:
        cursor.execute("SELECT router_status FROM bugs LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE bugs ADD COLUMN router_status TEXT")

    # Migration: Add classification_status if it doesn't exist
    try:
        cursor.execute("SELECT classification_status FROM bugs LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE bugs ADD COLUMN classification_status TEXT")
        
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
