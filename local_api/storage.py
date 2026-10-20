from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL,
    code TEXT NOT NULL DEFAULT '',
    meter_number TEXT NOT NULL,
    meter_name TEXT NOT NULL DEFAULT '',
    meter_type TEXT NOT NULL,
    tariff TEXT,
    value REAL NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    measured_at TEXT,
    received_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok',
    raw_payload TEXT NOT NULL DEFAULT '{}',
    UNIQUE (account, meter_number, tariff)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def store_reading(
    conn: sqlite3.Connection,
    *,
    account: str,
    code: str,
    meter_number: str,
    meter_name: str,
    meter_type: str,
    tariff: str | None,
    value: float,
    unit: str,
    measured_at: str | None,
    received_at: str,
    source: str,
    raw_payload: str,
) -> tuple[str, str]:
    """Сохранить показание. Возвращает (result, status).

    result: "accepted" — записано/обновлено, "duplicate" — значение не изменилось.
    status: "ok" | "suspicious" (показание меньше предыдущего).

    UPDATE/INSERT вместо UPSERT: SQLite считает NULL-значения различными
    для UNIQUE-констрейнта, поэтому ON CONFLICT не срабатывает для tariff=NULL.
    """
    row = conn.execute(
        "SELECT id, value FROM readings "
        "WHERE account = ? AND meter_number = ? AND tariff IS ?",
        (account, meter_number, tariff),
    ).fetchone()

    if row is not None and row["value"] == value:
        return "duplicate", "ok"

    if row is not None and value < row["value"]:
        status = "suspicious"
    else:
        status = "ok"

    if row is not None:
        conn.execute(
            "UPDATE readings SET code = ?, meter_name = ?, meter_type = ?, "
            "value = ?, unit = ?, measured_at = ?, received_at = ?, source = ?, "
            "status = ?, raw_payload = ? WHERE id = ?",
            (
                code,
                meter_name,
                meter_type,
                value,
                unit,
                measured_at,
                received_at,
                source,
                status,
                raw_payload,
                row["id"],
            ),
        )
    else:
        conn.execute(
            "INSERT INTO readings ("
            "account, code, meter_number, meter_name, meter_type, tariff, value, "
            "unit, measured_at, received_at, source, status, raw_payload"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                account,
                code,
                meter_number,
                meter_name,
                meter_type,
                tariff,
                value,
                unit,
                measured_at,
                received_at,
                source,
                status,
                raw_payload,
            ),
        )
    conn.commit()
    return "accepted", status


def query_readings(
    conn: sqlite3.Connection,
    *,
    account: str | None = None,
    meter_number: str | None = None,
    meter_type: str | None = None,
    tariff: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if account is not None:
        clauses.append("account = ?")
        params.append(account)
    if meter_number is not None:
        clauses.append("meter_number = ?")
        params.append(meter_number)
    if meter_type is not None:
        clauses.append("meter_type = ?")
        params.append(meter_type)
    if tariff is not None:
        clauses.append("tariff IS ?")
        params.append(tariff)

    sql = "SELECT * FROM readings"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY account, meter_number, tariff IS NOT NULL, tariff"

    return [dict(row) for row in conn.execute(sql, params).fetchall()]
