# AI CFO – Small Business Survival Agent
### FastAPI Backend

> Agent-based financial intelligence for small retail shops in India.
> Converts supplier invoices and customer voice sales into actionable business insights.

---

## Quick Start

```bash
cd backend

# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux / macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Edit .env — set TESSERACT_CMD to your Tesseract install path

# 4. Run server
uvicorn app.main:app --reload --port 8000
```

- **Swagger UI:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

---

## Architecture

```
Invoice Upload  →  OCR Agent (Tesseract)  →  Invoice Parser  →  Inventory (+stock)
Voice Recording →  Speech Agent (Whisper) →  Sales Parser   →  Inventory (−stock)
                                           ↓
                               Analytics Agents (Pandas + Scikit-Learn)
                               Profit | Demand | Restock | GST Summary
```

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                    # FastAPI app + lifespan
│   ├── core/config.py             # Settings (pydantic-settings + .env)
│   ├── db/database.py             # Async SQLAlchemy engine + session dep
│   ├── models/models.py           # 5 ORM tables
│   ├── schemas/schemas.py         # All Pydantic v2 schemas
│   ├── agents/
│   │   ├── ocr_agent.py           # Tesseract OCR
│   │   ├── invoice_parser.py      # Regex invoice parser
│   │   ├── speech_agent.py        # Whisper offline STT
│   │   ├── sales_parser.py        # NLP sales transcript parser
│   │   └── analytics_agents.py    # Profit · Demand · Restock · GST
│   ├── services/
│   │   ├── inventory_service.py   # Stock +/- logic, product resolution
│   │   ├── invoice_service.py     # Invoice pipeline orchestrator
│   │   └── sales_service.py       # Sales pipeline orchestrator
│   └── api/routes/
│       ├── invoices.py            # POST /upload, GET /invoices
│       ├── sales.py               # POST /voice, POST /text, GET /sales
│       ├── inventory.py           # CRUD /inventory
│       └── analytics.py          # profit, demand, restock, gst, dashboard
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/invoices/upload` | Upload supplier invoice (image/PDF) |
| GET | `/api/invoices/` | List all invoices |
| GET | `/api/invoices/{id}` | Invoice detail + line items |
| POST | `/api/sales/voice` | Voice recording of daily sales |
| POST | `/api/sales/text` | Text fallback for sales entry |
| GET | `/api/sales/` | List all sales |
| GET | `/api/inventory/` | All products + stock levels |
| POST | `/api/inventory/` | Add product manually |
| GET | `/api/inventory/low-stock` | Products below reorder point |
| PUT | `/api/inventory/{id}` | Update product config |
| DELETE | `/api/inventory/{id}` | Soft-delete product |
| GET | `/api/analytics/profit` | Profit & margin per product |
| GET | `/api/analytics/demand` | 7d/30d demand forecasts |
| GET | `/api/analytics/restock` | Restock recommendations |
| GET | `/api/analytics/gst` | Monthly GST summary |
| GET | `/api/analytics/dashboard` | All data in one call |

---

## System Requirements

| Tool | Purpose | Install |
|------|---------|---------|
| Tesseract OCR | Invoice image processing | [tesseract-ocr.github.io](https://tesseract-ocr.github.io/tessdoc/Installation.html) |
| Poppler (optional) | PDF → image conversion | Required only for PDF invoices |
| Python ≥ 3.10 | Runtime | — |

---

## Tech Stack

`FastAPI` · `SQLAlchemy (async)` · `SQLite + aiosqlite` · `Pandas` · `Scikit-Learn` · `Tesseract OCR` · `Whisper`
