from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

import flask
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from pydantic import ValidationError

import storage
from schemas import ReadingPayload

load_dotenv()


def create_app(db_path: str | Path, api_key: str) -> Flask:
    """Приложение Local Meter API. Настройки передаются явно — удобно для тестов."""

    app = Flask(__name__)
    app.config["DB_PATH"] = str(db_path)
    app.config["API_KEY"] = api_key

    def _get_db():
        conn = flask.g.get("_db_conn")
        if conn is None:
            Path(app.config["DB_PATH"]).parent.mkdir(parents=True, exist_ok=True)
            conn = storage.connect(app.config["DB_PATH"])
            storage.init_db(conn)
            flask.g._db_conn = conn
        return conn

    @app.teardown_appcontext
    def _close_db(exception):
        conn = flask.g.pop("_db_conn", None)
        if conn is not None:
            conn.close()

    def _check_api_key():
        if not app.config["API_KEY"]:
            return (
                jsonify(
                    {"status": "error", "message": "API_KEY is not configured"}
                ),
                500,
            )
        supplied_key = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(supplied_key, app.config["API_KEY"]):
            return (
                jsonify({"status": "error", "message": "Unauthorized"}),
                401,
            )
        return None

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "local-meter-api"})

    @app.post("/api/v1/readings")
    def receive_reading():
        """Принять показание: записать/обновить последнее значение в БД."""
        auth_error = _check_api_key()
        if auth_error:
            return auth_error

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return (
                jsonify({"status": "error", "message": "Expected JSON object"}),
                400,
            )

        try:
            reading = ReadingPayload.model_validate(payload)
        except ValidationError as err:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": err.errors(include_context=False),
                    }
                ),
                400,
            )

        received_at = datetime.now(timezone.utc).isoformat()
        raw_payload = json.dumps(payload, ensure_ascii=False)

        rows: list[tuple[str | None, float]] = []
        if reading.meter_type == "electricity":
            if reading.day_kwh is not None:
                rows.append(("day", reading.day_kwh))
            if reading.night_kwh is not None:
                rows.append(("night", reading.night_kwh))
        else:
            rows.append((None, reading.value))

        results = []
        for tariff, value in rows:
            result, status = storage.store_reading(
                _get_db(),
                account=reading.account,
                code=reading.code,
                meter_number=reading.meter_number,
                meter_name=reading.meter_name,
                meter_type=reading.meter_type,
                tariff=tariff,
                value=value,
                unit=reading.unit,
                measured_at=reading.measured_at,
                received_at=received_at,
                source=reading.source,
                raw_payload=raw_payload,
            )
            results.append(
                {
                    "tariff": tariff,
                    "value": value,
                    "status": status,
                    "result": result,
                }
            )

        stored = sum(1 for item in results if item["result"] == "accepted")

        return (
            jsonify(
                {
                    "status": "accepted" if stored else "duplicate",
                    "meter_number": reading.meter_number,
                    "received_at": received_at,
                    "stored": stored,
                    "results": results,
                }
            ),
            201,
        )

    @app.get("/api/v1/readings")
    def list_readings():
        """Выборка последних показаний с фильтрами."""
        auth_error = _check_api_key()
        if auth_error:
            return auth_error

        rows = storage.query_readings(
            _get_db(),
            account=request.args.get("account"),
            meter_number=request.args.get("meter_number"),
            meter_type=request.args.get("meter_type"),
            tariff=request.args.get("tariff"),
        )
        return jsonify({"count": len(rows), "results": rows})

    with app.app_context():
        _get_db()

    return app


if __name__ == "__main__":
    app = create_app(
        db_path=os.getenv("DB_PATH", "readings.db"),
        api_key=os.getenv("API_KEY", ""),
    )
    app.run(
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "5001")),
        debug=True,
    )
