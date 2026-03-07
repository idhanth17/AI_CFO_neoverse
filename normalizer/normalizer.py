import re

UNIT_MAP = {
    "pcs": "nos",
    "pc": "nos",
    "no": "nos",
    "nos": "nos",
    "m": "metre",
    "mtr": "metre",
    "meter": "metre",
    "kg": "kg",
    "kgs": "kg",
    "l": "litre",
    "ltr": "litre"
}

def normalize_product_name(name):
    if not name:
        return "Unknown Product"
    # Convert '1"' or '1"' to '1 Inch'
    name = re.sub(r'(\d+)\s*"|\'\'', r'\1 Inch', name)
    return name.title().strip()

def normalize_receipt(data):
    # Normalize vendor name if missing
    if "vendor_name" not in data:
        data["vendor_name"] = "Unknown Vendor"
        
    normalized_items = []
    
    for item in data.get("items", []):
        # Handle alternating key names from different LLM extractions (description vs name)
        raw_name = item.get("description", item.get("name", "Unknown Product"))
        raw_price = item.get("unit_price", item.get("price", 0.0))
        raw_unit = str(item.get("unit", "nos")).lower().strip()
        
        normalized_item = {
            "name": normalize_product_name(raw_name),
            "quantity": item.get("quantity", 1),
            "price": raw_price,
            "unit": UNIT_MAP.get(raw_unit, raw_unit)
        }
        normalized_items.append(normalized_item)
        
    data["items"] = normalized_items
    return data
