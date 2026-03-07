import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.models import Base, Product, Customer

DATABASE_URL = "sqlite+aiosqlite:///./ai_cfo.db"

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def seed_data():
    await init_db()
    async with async_session() as session:
        # 1. Seed Products (Hardware Shop Data)
        products_data = [
            # Tools
            {"name": "Claw Hammer", "cost_price": 250.0, "selling_price": 320.0, "current_stock": 15, "unit": "pcs"},
            {"name": "Screwdriver Set", "cost_price": 180.0, "selling_price": 250.0, "current_stock": 20, "unit": "pcs"},
            {"name": "Measuring Tape 5m", "cost_price": 120.0, "selling_price": 180.0, "current_stock": 30, "unit": "pcs"},
            {"name": "Power Drill 500W", "cost_price": 2200.0, "selling_price": 2800.0, "current_stock": 5, "unit": "pcs"},
            # Materials
            {"name": "Portland Cement 50kg", "cost_price": 320.0, "selling_price": 380.0, "current_stock": 100, "unit": "bags"},
            {"name": "White Paint 10L", "cost_price": 1800.0, "selling_price": 2300.0, "current_stock": 12, "unit": "cans"},
            {"name": "Wire Nails 2 inch", "cost_price": 80.0, "selling_price": 110.0, "current_stock": 50, "unit": "kg"},
            {"name": "Sandpaper Medium", "cost_price": 15.0, "selling_price": 25.0, "current_stock": 200, "unit": "sheets"},
            # Plumbing & Electrical
            {"name": "PVC Pipe 1 inch", "cost_price": 100.0, "selling_price": 140.0, "current_stock": 40, "unit": "pcs"},
            {"name": "Copper Wire 1.5mm", "cost_price": 1200.0, "selling_price": 1550.0, "current_stock": 15, "unit": "rolls"},
            {"name": "LED Bulb 9W", "cost_price": 60.0, "selling_price": 95.0, "current_stock": 80, "unit": "pcs"},
        ]

        # 2. Seed Customers
        customers_data = [
            {"name": "Ravi", "phone": "9876543210", "total_credit": 0.0},
            {"name": "Arun Construction", "phone": "9876500000", "total_credit": 1200.0},
            {"name": "John", "phone": "9998887776", "total_credit": 500.0},
        ]

        # Insert products
        for p in products_data:
            prod = Product(
                name=p["name"],
                cost_price=p["cost_price"],
                selling_price=p["selling_price"],
                current_stock=p["current_stock"],
                unit=p["unit"],
                gst_rate=18.0,
                reorder_point=5.0,
                safety_stock=2.0,
                lead_time_days=2
            )
            session.add(prod)

        # Insert customers
        for c in customers_data:
            cust = Customer(
                name=c["name"],
                phone=c["phone"],
                total_credit=c["total_credit"]
            )
            session.add(cust)

        try:
            await session.commit()
            print("Successfully seeded hardware DB!")
        except Exception as e:
            await session.rollback()
            print(f"Error seeding data: {e}")

if __name__ == "__main__":
    asyncio.run(seed_data())
