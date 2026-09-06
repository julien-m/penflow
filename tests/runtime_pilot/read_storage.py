"""Read test SQLite in an independently executed process and report its true identity."""

import json
import os
import sqlite3
import sys
import uuid

with sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True) as connection:
    rows = connection.execute("SELECT id, amount, status FROM payments ORDER BY id").fetchall()
row = next((row for row in rows if row[0] == "payment-1"), None)
print(
    json.dumps(
        {
            "store_id": "payments",
            "key": "payment-1",
            "exists": row is not None,
            "value": {"amount": row[1], "status": row[2]} if row else None,
            "row_count": len(rows),
            "process_instance": f"{os.getpid()}:{uuid.uuid4()}",
        }
    )
)
