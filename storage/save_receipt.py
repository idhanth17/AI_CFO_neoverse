from storage.db import connect
from normalizer.normalizer import normalize_receipt

def get_or_create_vendor(cursor, vendor_name):
    cursor.execute("SELECT id FROM vendors WHERE name = ?", (vendor_name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO vendors (name) VALUES (?)", (vendor_name,))
    return cursor.lastrowid

def get_or_create_product(cursor, product_name):
    cursor.execute("SELECT id FROM products WHERE name = ?", (product_name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO products (name) VALUES (?)", (product_name,))
    return cursor.lastrowid

def save_receipt(raw_data):
    # Pass through normalizer first
    data = normalize_receipt(raw_data)
    
    conn = connect()
    cursor = conn.cursor()
    
    try:
        vendor_id = get_or_create_vendor(cursor, data.get("vendor_name", "Unknown Vendor"))
        
        cursor.execute(
            "INSERT INTO receipts (vendor_id, date, total) VALUES (?, ?, ?)",
            (vendor_id, data.get("date", "Unknown Date"), float(data.get("total", 0.0)))
        )
        receipt_id = cursor.lastrowid
        
        for item in data.get("items", []):
            product_id = get_or_create_product(cursor, item.get("name", "Unknown Product"))
            
            cursor.execute(
                "INSERT INTO receipt_items (receipt_id, product_id, quantity, unit, price) VALUES (?, ?, ?, ?, ?)",
                (
                    receipt_id,
                    product_id,
                    float(item.get("quantity", 1)),
                    item.get("unit", "nos"),
                    float(item.get("price", 0.0))
                )
            )
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
