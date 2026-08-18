# Demo session

Captured from the running server against the generated `demo.db`
(60 customers, 162 orders, 324 order items) with:

```
ALLOWED_TABLES=customers,orders,order_items
MASKED_COLUMNS=customers.email,customers.phone
```

Nothing here is hand-written - it is the literal tool output.

### list_tables()

```json
{
  "tables": [
    {
      "table": "customers",
      "rows": 60
    },
    {
      "table": "order_items",
      "rows": 324
    },
    {
      "table": "orders",
      "rows": 162
    }
  ],
  "allowlist_active": true
}
```

### describe_table("orders")

```json
{
  "table": "orders",
  "rows": 162,
  "columns": [
    {
      "name": "id",
      "type": "INTEGER",
      "nullable": true,
      "primary_key": true,
      "masked": false
    },
    {
      "name": "customer_id",
      "type": "INTEGER",
      "nullable": false,
      "primary_key": false,
      "masked": false
    },
    {
      "name": "ordered_at",
      "type": "TEXT",
      "nullable": false,
      "primary_key": false,
      "masked": false
    },
    {
      "name": "status",
      "type": "TEXT",
      "nullable": false,
      "primary_key": false,
      "masked": false
    },
    {
      "name": "total_eur",
      "type": "REAL",
      "nullable": false,
      "primary_key": false,
      "masked": false
    }
  ],
  "sample": [
    {
      "id": 1,
      "customer_id": 2,
      "ordered_at": "2024-05-10",
      "status": "paid",
      "total_eur": 2497.0
    },
    {
      "id": 2,
      "customer_id": 2,
      "ordered_at": "2024-05-27",
      "status": "refunded",
      "total_eur": 343.5
    },
    {
      "id": 3,
      "customer_id": 2,
      "ordered_at": "2025-02-04",
      "status": "paid",
      "total_eur": 1089.0
    }
  ]
}
```

### run_sql("SELECT status, COUNT(*) n, ROUND(SUM(total_eur)) revenue FROM orders GROUP BY 1 ORDER BY 3 DESC")

```json
{
  "sql": "SELECT status, COUNT(*) n, ROUND(SUM(total_eur)) revenue FROM orders GROUP BY 1 ORDER BY 3 DESC LIMIT 201",
  "columns": [
    "status",
    "n",
    "revenue"
  ],
  "rows": [
    [
      "paid",
      92,
      149914.0
    ],
    [
      "pending",
      39,
      64596.0
    ],
    [
      "refunded",
      31,
      45911.0
    ]
  ],
  "row_count": 3,
  "truncated": false,
  "elapsed_ms": 0
}
```

### run_sql(" ... top countries by revenue, joined ...")

```json
{
  "sql": "SELECT c.country, COUNT(DISTINCT o.id) orders, ROUND(SUM(o.total_eur)) revenue FROM orders o JOIN customers c ON c.id = o.customer_id WHERE o.status = 'paid' GROUP BY 1 ORDER BY 3 DESC LIMIT 5",
  "columns": [
    "country",
    "orders",
    "revenue"
  ],
  "rows": [
    [
      "Netherlands",
      22,
      41252.0
    ],
    [
      "Spain",
      21,
      38780.0
    ],
    [
      "Bulgaria",
      16,
      23395.0
    ],
    [
      "United Kingdom",
      14,
      19397.0
    ],
    [
      "Poland",
      10,
      14327.0
    ]
  ],
  "row_count": 5,
  "truncated": false,
  "elapsed_ms": 0
}
```

### summarize_column("orders", "status")

```json
{
  "table": "orders",
  "column": "status",
  "stats": {
    "total": 162,
    "non_null": 162,
    "distinct_values": 3,
    "min_value": "paid",
    "max_value": "refunded"
  },
  "top_values": [
    {
      "value": "paid",
      "count": 92
    },
    {
      "value": "pending",
      "count": 39
    },
    {
      "value": "refunded",
      "count": 31
    }
  ]
}
```

### search("customers", "country", "Bulgaria", limit=2)  # PII masked

```json
{
  "matches": [
    {
      "id": 6,
      "name": "Customer 006",
      "email": "***",
      "phone": "***",
      "country": "Bulgaria",
      "channel": "website",
      "created_at": "2024-11-04"
    },
    {
      "id": 10,
      "name": "Customer 010",
      "email": "***",
      "phone": "***",
      "country": "Bulgaria",
      "channel": "referral",
      "created_at": "2024-04-23"
    }
  ],
  "row_count": 2
}
```

## The guardrails, same server

### run_sql("DELETE FROM customers")

```json
{
  "error": "only SELECT (or WITH ... SELECT) statements are allowed",
  "hint": "only read-only SELECT statements are allowed"
}
```

### run_sql("SELECT 1; DROP TABLE customers")

```json
{
  "error": "only one statement per call is allowed",
  "hint": "only read-only SELECT statements are allowed"
}
```

### run_sql("SELECT * FROM internal_notes")  # table not in the allowlist

```json
{
  "error": "table 'internal_notes' is not in the allowlist (allowed: customers, orders, order_items)",
  "hint": "only read-only SELECT statements are allowed"
}
```

### run_sql("ATTACH DATABASE '/etc/passwd' AS leak")

```json
{
  "error": "only SELECT (or WITH ... SELECT) statements are allowed",
  "hint": "only read-only SELECT statements are allowed"
}
```

### describe_table("internal_notes")

```json
{
  "error": "table 'internal_notes' is not in the allowlist"
}
```

