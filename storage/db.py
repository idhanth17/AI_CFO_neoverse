import sqlite3
import os

DB_FILE = "receipts.db"

def connect():
    return sqlite3.connect(DB_FILE)

def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    with open(schema_path, 'r') as f:
        schema = f.read()
    
    conn = connect()
    conn.executescript(schema)
    conn.commit()
    conn.close()
