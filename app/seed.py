from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import (
    AdminUser,
    Customer,
    CustomerType,
    Invoice,
    InvoiceItem,
    PaymentMode,
    PointsMode,
    ShopSettings,
    TimeSlab,
)
from app.security import hash_password


def seed() -> None:
    db = SessionLocal()
    try:
        admin = db.scalar(select(AdminUser).where(AdminUser.email == settings.admin_email.lower()))
        if not admin:
            admin = AdminUser(
                email=settings.admin_email.lower(),
                name=settings.admin_name,
                hashed_password=hash_password(settings.admin_password),
            )
            db.add(admin)
            db.flush()
            print(f"Created admin: {admin.email}")
        else:
            print(f"Admin exists: {admin.email}")

        if not db.scalar(select(ShopSettings).limit(1)):
            db.add(
                ShopSettings(
                    points_mode=PointsMode.RUPEES_PER_POINT,
                    rupees_per_point=Decimal("100"),
                    points_percentage=Decimal("5"),
                    points_per_quantity=Decimal("1"),
                )
            )
            print("Created shop settings")

        for name, months, is_default in [
            ("1 Month", 1, False),
            ("3 Months", 3, False),
            ("6 Months", 6, True),
            ("12 Months", 12, False),
        ]:
            if not db.scalar(select(TimeSlab).where(TimeSlab.name == name)):
                db.add(TimeSlab(name=name, months=months, is_default=is_default))
        print("Time slabs ready")

        types: dict[str, CustomerType] = {}
        for tname in ["Plumber", "Mason", "Electrician", "Contractor"]:
            row = db.scalar(select(CustomerType).where(CustomerType.name == tname))
            if not row:
                row = CustomerType(name=tname, is_active=True)
                db.add(row)
                db.flush()
            types[tname] = row

        demo_customers = [
            ("Ramesh Plumber", "9876543210", "Plumber", "Near Main Market"),
            ("Suresh Mason", "9876543211", "Mason", "Station Road"),
            ("Vikram Electrician", "9876543212", "Electrician", "Industrial Area"),
            ("Anil Contractor", "9876543213", "Contractor", "Civil Lines"),
            ("Deepak Plumber", "9876543214", "Plumber", "Old City"),
        ]
        customers: list[Customer] = []
        for name, phone, tname, address in demo_customers:
            c = db.scalar(select(Customer).where(Customer.phone == phone))
            if not c:
                c = Customer(
                    name=name,
                    phone=phone,
                    address=address,
                    type_id=types[tname].id,
                    lifetime_points=Decimal("0"),
                )
                db.add(c)
                db.flush()
            customers.append(c)

        if db.scalar(select(Invoice).limit(1)):
            db.commit()
            print("Invoices already seeded; skipping demo invoices")
            return

        today = date.today()
        samples = [
            (customers[0], 10, [("Vitrified Tile 2x2", Decimal("20"), "box", Decimal("850"))], 45),
            (customers[0], 40, [("CPVC Pipe 1 inch", Decimal("15"), "piece", Decimal("320"))], 120),
            (customers[1], 20, [("Cement Grey", Decimal("40"), "bag", Decimal("380"))], 80),
            (customers[1], 5, [("Wall Putty", Decimal("10"), "bag", Decimal("650"))], 15),
            (customers[2], 60, [("LED Panel 18W", Decimal("25"), "piece", Decimal("420"))], 150),
            (customers[3], 90, [("Sanitary Closet", Decimal("4"), "piece", Decimal("6500"))], 200),
            (customers[3], 15, [("Basin Mixer", Decimal("8"), "piece", Decimal("1800"))], 30),
            (customers[4], 70, [("Grout", Decimal("30"), "kg", Decimal("90"))], 100),
        ]

        for idx, (cust, days_ago, items, _) in enumerate(samples, start=1):
            total_qty = sum((i[1] for i in items), Decimal("0"))
            total_amount = sum((i[1] * i[3] for i in items), Decimal("0"))
            points = Decimal(int(total_amount / Decimal("100")))
            inv = Invoice(
                invoice_no=f"INV-{idx:05d}",
                customer_id=cust.id,
                created_by_admin_id=admin.id,
                purchased_at=today - timedelta(days=days_ago),
                payment_mode=PaymentMode.CASH if idx % 2 else PaymentMode.UPI,
                total_qty=total_qty,
                total_amount=total_amount,
                points_earned=points,
                points_overridden=False,
            )
            db.add(inv)
            db.flush()
            for name, qty, unit, price in items:
                db.add(
                    InvoiceItem(
                        invoice_id=inv.id,
                        item_name=name,
                        qty=qty,
                        unit=unit,
                        unit_price=price,
                        line_amount=(qty * price).quantize(Decimal("0.01")),
                        points_earned=Decimal(int(qty * price / Decimal("100"))),
                    )
                )
            cust.lifetime_points = (cust.lifetime_points or Decimal("0")) + points

        db.commit()
        print("Demo data seeded successfully")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
