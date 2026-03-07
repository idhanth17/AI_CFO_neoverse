# Parser Database Storage Setup

Your OCR parser can now save parsed receipt data directly to the database!

## How It Works

The parser has been enhanced with database storage capabilities:

1. **New Models**: `Receipt` and `ReceiptItem` tables for storing parsed receipts
2. **Receipt Service**: Backend service function to save parsed data
3. **Parser CLI**: Added `--save-db` option to parser.py

## Installation

First, install backend dependencies from the backend directory:

```bash
cd backend
pip install -r requirements.txt
```

## Usage

### Basic Usage (Console Output)

```bash
python parser.py receipt.jpg --pretty
```

### Save to JSON File

```bash
python parser.py receipt.jpg --output result.json --pretty
```

### Save to Database

```bash
python parser.py receipt.jpg --save-db --pretty
```

### Save Database AND JSON File

```bash
python parser.py receipt.jpg --save-db --output result.json --pretty
```

## Database Location

- **Database File**: `backend/ai_cfo.db` (SQLite)
- **Tables Created**:
  - `receipts` - Receipt headers
  - `receipt_items` - Line items from receipts
  - Plus existing `products`, `invoices`, `sales` tables

## Output

When using `--save-db`, the JSON output includes a `_receipt_id` field:

```json
{
  "vendor_name": "Now Storo X1",
  "bill_number": "vou",
  "date": "2024-03-15",
  "total": "5105.60",
  "_receipt_id": 1,
  ...
}
```

The `_receipt_id` is the primary key in the database for future reference.

## Querying Stored Receipts

You can query the stored receipts directly using Python:

```python
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "backend")

from app.db.database import AsyncSessionLocal, init_db
from app.models.models import Receipt

async def list_receipts():
    await init_db()
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(Receipt))
        receipts = result.scalars().all()
        for r in receipts:
            print(f"ID: {r.id}, Vendor: {r.vendor_name}, Total: {r.total_amount}")

asyncio.run(list_receipts())
```

## Database Schema

### receipts table

- `id` - Primary key
- `file_path` - Path to source image
- `vendor_name` - Shop/vendor name
- `bill_number` - Invoice/bill number
- `receipt_date` - Date of purchase
- `receipt_time` - Time of purchase
- `currency` - Currency code (default: INR)
- `address` - Vendor address
- `phone` - Vendor phone number
- `subtotal` - Amount before tax/discount
- `tax` - Tax amount
- `discount` - Discount amount
- `total_amount` - Final total
- `payment_method` - Cash, Card, UPI, etc.
- `raw_ocr_text` - Raw text from OCR
- `created_at` - Timestamp when saved

### receipt_items table

- `id` - Primary key
- `receipt_id` - Foreign key to receipts
- `product_id` - Optional link to product catalog
- `item_name` - Item description
- `quantity` - Quantity purchased
- `unit_price` - Price per unit
- `total_price` - Total for this line item

## Troubleshooting

**Error: Cannot import backend modules**

- Make sure you've installed dependencies: `cd backend && pip install -r requirements.txt`
- Ensure you're running parser.py from the workspace root directory

**Error: Failed to save to database**

- Check that `backend/ai_cfo.db` is writable
- Check console for detailed error messages
- Ensure database tables exist by running: `python -c "import asyncio, sys; sys.path.insert(0, 'backend'); from app.db.database import init_db; asyncio.run(init_db())"`

## Next Steps

The parsed receipt data is now:

- ✅ Saved to database for historical tracking
- ✅ Linked to the invoice/sales system
- ✅ Ready for inventory management and analytics
- ✍️ Can be further processed for:
  - Product matching with catalog
  - Automatic inventory updates
  - Financial reporting
  - Expense tracking
