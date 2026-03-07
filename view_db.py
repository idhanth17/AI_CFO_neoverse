import sqlite3

def display_db_contents():
    try:
        conn = sqlite3.connect('receipts.db')
        cursor = conn.cursor()

        print("\n--- Vendors ---")
        for row in cursor.execute("SELECT * FROM vendors"):
            print(row)

        print("\n--- Receipts ---")
        for row in cursor.execute("SELECT * FROM receipts"):
            print(row)

        print("\n--- Products ---")
        for row in cursor.execute("SELECT * FROM products"):
            print(row)

        print("\n--- Receipt Items ---")
        for row in cursor.execute("SELECT * FROM receipt_items"):
            print(row)

    except sqlite3.OperationalError:
        print("Database or tables do not exist yet!")
    finally:
        conn.close()

if __name__ == "__main__":
    display_db_contents()
