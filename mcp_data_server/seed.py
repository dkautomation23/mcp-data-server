"""Build a small demo database so the server runs before any client data exists.

    python -m mcp_data_server.seed

Three tables with believable relationships (customers -> orders -> order_items)
and one deliberately sensitive table (`internal_notes`) used in the README to
show the allowlist blocking access.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

COUNTRIES = ["Germany", "Netherlands", "Poland", "Spain", "United Kingdom", "Bulgaria"]
CHANNELS = ["website", "marketplace", "referral", "cold_outreach"]
PRODUCTS = [
    ("Thermal sensor TS-40", 129.00),
    ("Industrial gateway G2", 480.00),
    ("Cable set 5m", 24.50),
    ("Mounting kit XL", 61.00),
    ("Service plan (annual)", 950.00),
]
STATUSES = ["paid", "paid", "paid", "pending", "refunded"]

SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    country TEXT NOT NULL,
    channel TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    ordered_at TEXT NOT NULL,
    status TEXT NOT NULL,
    total_eur REAL NOT NULL
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_eur REAL NOT NULL
);
CREATE TABLE internal_notes (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    note TEXT NOT NULL
);
"""


def build(path: Path, customers: int = 60, seed: int = 7) -> Path:
    """(Re)create the demo database at `path`. Deterministic for a given seed."""
    rng = random.Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)

    today = date(2026, 8, 18)
    order_id = 0
    item_id = 0

    for customer_id in range(1, customers + 1):
        created = today - timedelta(days=rng.randint(20, 900))
        connection.execute(
            "INSERT INTO customers VALUES (?,?,?,?,?,?,?)",
            (
                customer_id,
                f"Customer {customer_id:03d}",
                f"customer{customer_id:03d}@example.com",
                f"+49170{customer_id:07d}",
                rng.choice(COUNTRIES),
                rng.choice(CHANNELS),
                created.isoformat(),
            ),
        )
        connection.execute(
            "INSERT INTO internal_notes VALUES (?,?,?)",
            (customer_id, customer_id, rng.choice(["churn risk", "VIP", "late payer", "expansion candidate"])),
        )

        for _ in range(rng.randint(0, 5)):
            order_id += 1
            ordered = created + timedelta(days=rng.randint(1, 400))
            if ordered > today:
                ordered = today
            total = 0.0
            picked = rng.sample(PRODUCTS, rng.randint(1, 3))
            for product, price in picked:
                item_id += 1
                quantity = rng.randint(1, 4)
                total += price * quantity
                connection.execute(
                    "INSERT INTO order_items VALUES (?,?,?,?,?)",
                    (item_id, order_id, product, quantity, price),
                )
            connection.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?)",
                (order_id, customer_id, ordered.isoformat(), rng.choice(STATUSES), round(total, 2)),
            )

    connection.commit()
    connection.close()
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the demo SQLite database.")
    parser.add_argument("--path", default="demo.db", help="output file (default: demo.db)")
    parser.add_argument("--customers", type=int, default=60, help="how many customers to generate")
    args = parser.parse_args()

    path = build(Path(args.path), customers=args.customers)
    connection = sqlite3.connect(path)
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("customers", "orders", "order_items", "internal_notes")
    }
    connection.close()
    print(f"created {path} -> " + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
