"""
Receipt Service — Parse and persist receipt data to database
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Receipt, ReceiptItem


async def save_parsed_receipt(
    db: AsyncSession,
    parsed_data: Dict[str, Any],
    file_path: Optional[str] = None,
) -> Receipt:
    """
    Save parsed receipt data from parser.py to the database.
    
    Args:
        db: AsyncSession database connection
        parsed_data: Dict from parser.py with keys:
            - vendor_name, bill_number, date, time, currency
            - subtotal, tax, discount, total
            - payment_method, address, phone
            - items (list), raw_text
        file_path: Optional path to the source image
    
    Returns:
        Receipt: Saved Receipt model instance
    """
    
    # Parse date if provided
    receipt_date = None
    if parsed_data.get("date"):
        try:
            # Try common date formats
            date_str = parsed_data["date"]
            for fmt in ["%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%d"]:
                try:
                    receipt_date = datetime.strptime(date_str.split('\n')[0], fmt)
                    break
                except ValueError:
                    continue
        except Exception:
            pass
    
    # Convert string amounts to floats
    def to_float(val):
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        try:
            return float(str(val).replace(',', '').strip())
        except (ValueError, AttributeError):
            return 0.0
    
    # Create Receipt record
    receipt = Receipt(
        file_path=file_path,
        vendor_name=parsed_data.get("vendor_name"),
        bill_number=parsed_data.get("bill_number"),
        receipt_date=receipt_date,
        receipt_time=parsed_data.get("time"),
        currency=parsed_data.get("currency", "INR"),
        address=parsed_data.get("address"),
        phone=parsed_data.get("phone"),
        subtotal=to_float(parsed_data.get("subtotal")),
        tax=to_float(parsed_data.get("tax")),
        discount=to_float(parsed_data.get("discount")),
        total_amount=to_float(parsed_data.get("total")),
        payment_method=parsed_data.get("payment_method"),
        raw_ocr_text=parsed_data.get("raw_text"),
    )
    
    db.add(receipt)
    await db.flush()  # Get receipt.id
    
    # Add items
    for item_data in parsed_data.get("items", []):
        item = ReceiptItem(
            receipt_id=receipt.id,
            item_name=item_data.get("name", ""),
            quantity=to_float(item_data.get("quantity")),
            unit_price=to_float(item_data.get("unit_price")),
            total_price=to_float(item_data.get("total_price")),
        )
        db.add(item)
    
    await db.commit()
    await db.refresh(receipt)
    return receipt
