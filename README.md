
# AI CFO Backend
### Small Business Survival AI Agent

A FastAPI backend that turns supplier invoices and customer voice sales into financial intelligence for small shops.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    REACT DASHBOARD                       │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP / REST
┌──────────────────────▼──────────────────────────────────┐
│                  FASTAPI BACKEND                         │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │              PURCHASE PIPELINE                   │    │
│  │  Invoice Upload → OCR Agent → Invoice Parser     │    │
│  │           → Inventory Agent (+stock)             │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │               SALES PIPELINE                     │    │
│  │  Voice Recording → Whisper STT → Sales Parser   │    │
│  │           → Inventory Agent (−stock)             │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │             AI ANALYTICS AGENTS                  │    │
│  │  Profit (Pandas) | Demand (Sklearn) | Restock    │    │
│  │  GST Summary | Dashboard Aggregation             │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │              SQLITE DATABASE                     │    │
│  │  products | invoices | invoice_items             │    │
│  │  sales    | sale_items                           │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## Project Structure

```
ai_cfo_backend/
├── app/
│   ├── main.py                   # FastAPI app + startup
│   ├── core/
│   │   └── config.py             # Settings from .env
│   ├── db/
│   │   └── database.py           # Async SQLAlchemy engine + session
│   ├── models/
│   │   └── models.py             # ORM: Product, Invoice, Sale + items
│   ├── schemas/
│   │   └── schemas.py            # Pydantic request/response schemas
│   ├── agents/
│   │   ├── ocr_agent.py          # Tesseract OCR extraction
│   │   ├── invoice_parser.py     # Regex-based invoice line item parser
│   │   ├── speech_agent.py       # Whisper offline speech-to-text
│   │   ├── sales_parser.py       # NLP sales transcript parser
│   │   └── analytics_agents.py  # Profit, Demand, Restock, GST agents
│   ├── services/
│   │   ├── inventory_service.py  # Stock +/- logic, product resolution
│   │   ├── invoice_service.py    # Invoice pipeline orchestrator
│   │   └── sales_service.py      # Sales pipeline orchestrator
│   └── api/routes/
│       ├── invoices.py           # POST /upload, GET /invoices
│       ├── sales.py              # POST /voice, POST /text, GET /sales
│       ├── inventory.py          # GET/POST/PUT /inventory
│       └── analytics.py         # profit, demand, restock, gst, dashboard
└── requirements.txt
```

## Setup

### 1. System dependencies

```bash
# Ubuntu / Debian
sudo apt install tesseract-ocr poppler-utils ffmpeg

# macOS
brew install tesseract poppler ffmpeg
```

### 2. Python environment

```bash
cd ai_cfo_backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configuration

```bash
cp .env.example .env
# Edit .env — set TESSERACT_CMD, WHISPER_MODEL, etc.
```

### 4. Run

```bash
uvicorn app.main:app --reload --port 8000
```

- **Swagger UI:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
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
| GET | `/api/analytics/profit` | Profit & margin per product |
| GET | `/api/analytics/demand` | 7d/30d demand forecasts |
| GET | `/api/analytics/restock` | Restock recommendations |
| GET | `/api/analytics/gst` | Monthly GST summary |
| GET | `/api/analytics/dashboard` | Combined dashboard data |

---

## AI Agents

| Agent | Technology | Input | Output |
|-------|-----------|-------|--------|
| OCR Agent | Tesseract | Invoice image/PDF | Raw text |
| Invoice Parser | Regex + rules | OCR text | Structured line items |
| Speech Agent | Whisper (offline) | Audio file | Transcript |
| Sales Parser | NLP + regex | Transcript | Sale items |
| Profit Agent | Pandas | Sales + products | Margin analysis |
| Demand Agent | Moving Avg + LinearRegression | Sales history | Forecasts |
| Restock Agent | Formula-based | Demand + stock | Reorder qtys |
| GST Tool | Pandas | Invoice items | Monthly GST |

---

## Database Schema

```
products        — master catalogue (stock, prices, thresholds)
invoices        — supplier invoice headers
invoice_items   — parsed line items per invoice  →  products
sales           — customer sales sessions
sale_items      — items per sale session          →  products
```

**Inventory Logic:**
```
stock += purchase_quantity   # on invoice processed
stock -= sale_quantity       # on customer sale recorded
```
