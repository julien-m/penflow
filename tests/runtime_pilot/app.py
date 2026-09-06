"""Serve the bounded payment test application; never imported by Penflow core."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class PaymentServer(ThreadingHTTPServer):
    """Carry explicit application state for one independently identified process."""

    def __init__(self, database: Path, port: int) -> None:
        self.database = database
        self.process_instance = f"{os.getpid()}:{uuid.uuid4()}"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY, amount INTEGER, status TEXT)"
            )
        super().__init__(("127.0.0.1", port), PaymentHandler)


class PaymentHandler(BaseHTTPRequestHandler):
    """Expose real HTTP effects and a deliberately explicit failure scenario."""

    server: PaymentServer

    def do_GET(self) -> None:
        """Serve immutable snapshotted HTML or readiness information."""
        if self.path == "/health":
            self.respond(200, {"process_instance": self.server.process_instance})
        elif self.path == "/storage":
            with sqlite3.connect(self.server.database) as connection:
                rows = connection.execute(
                    "SELECT id, amount, status FROM payments ORDER BY id"
                ).fetchall()
            row = next((row for row in rows if row[0] == "payment-1"), None)
            self.respond(
                200,
                {
                    "store_id": "payments",
                    "key": "payment-1",
                    "exists": row is not None,
                    "value": {"amount": row[1], "status": row[2]} if row else None,
                    "row_count": len(rows),
                },
            )
        elif urlsplit(self.path).path in {"/", "/details", "/receipt"}:
            self._serve_asset("index.html", "text/html; charset=utf-8")
        elif self.path in {"/inter-regular.woff2", "/inter-semibold.woff2"}:
            self._serve_asset(self.path[1:], "font/woff2")
        else:
            self.respond(404, {"error": "not_found"})

    def _serve_asset(self, filename: str, content_type: str) -> None:
        """Serve only assets selected by the fixed route allowlist."""
        body = Path(__file__).with_name(filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        """Persist one payment, enforcing permission, validation and idempotency."""
        if self.path != "/payments":
            self.respond(404, {"error": "not_found"})
            return
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        except (ValueError, json.JSONDecodeError):
            self.respond(400, {"outcome": "invalid"})
            return
        if self.headers.get("X-Actor") != "buyer":
            self.respond(403, {"outcome": "denied"})
            return
        amount = payload.get("amount") if isinstance(payload, dict) else None
        if type(amount) is not int or amount <= 0:
            self.respond(422, {"outcome": "invalid"})
            return
        if self.headers.get("X-Test-Failure") == "yes":
            self.respond(503, {"outcome": "error", "reason": "explicit_test_service_unavailable"})
            return
        if self.headers.get("X-Test-Failure") == "storage":
            try:
                with sqlite3.connect(self.server.database) as connection:
                    connection.execute(
                        "INSERT INTO payments VALUES (?, ?, ?)",
                        ("rollback-probe", amount, "pending"),
                    )
                    connection.execute("INSERT INTO deliberately_missing_table VALUES (1)")
            except sqlite3.OperationalError:
                self.respond(500, {"outcome": "error", "reason": "sqlite_transaction_failed"})
            return
        with sqlite3.connect(self.server.database) as connection:
            existing = connection.execute(
                "SELECT amount, status FROM payments WHERE id = ?", ("payment-1",)
            ).fetchone()
            if existing:
                if existing[0] != amount:
                    self.respond(409, {"outcome": "error", "reason": "idempotency_conflict"})
                else:
                    self.respond(
                        200, {"outcome": "idempotent", "amount": existing[0], "status": existing[1]}
                    )
                return
            connection.execute(
                "INSERT INTO payments VALUES (?, ?, ?)", ("payment-1", amount, "paid")
            )
        self.respond(201, {"outcome": "success", "amount": amount, "status": "paid"})

    def respond(self, status: int, value: dict[str, Any]) -> None:
        """Write structured response bytes carrying the live process identity."""
        body = json.dumps({**value, "process_instance": self.server.process_instance}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    """Run until the external pilot owner terminates this process."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    arguments = parser.parse_args()
    with PaymentServer(arguments.database, arguments.port) as server:
        print(
            json.dumps({"port": server.server_port, "process_instance": server.process_instance}),
            flush=True,
        )
        server.serve_forever()


if __name__ == "__main__":
    main()
