from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

app = Flask(__name__)

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "5001"))
DATA_FILE = Path(os.getenv("DATA_FILE", "received_readings.jsonl"))
API_KEY = os.getenv("API_KEY", "")


@app.get("/health")
def health():
    """Return service status."""
    return jsonify(
        {
            "status": "ok",
            "service": "local-meter-api",
        }
    )


@app.post("/api/v1/readings")
def receive_reading():
    """Receive and store one meter reading."""
    if not API_KEY:
        return jsonify(
            {
                "status": "error",
                "message": "API_KEY is not configured",
            }
        ), 500

    supplied_key = request.headers.get("X-API-Key", "")

    if not secrets.compare_digest(supplied_key, API_KEY):
        return jsonify(
            {
                "status": "error",
                "message": "Unauthorized",
            }
        ), 401

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(
            {
                "status": "error",
                "message": "Expected JSON object",
            }
        ), 400

    meter_id = payload.get("meter_id")

    if not isinstance(meter_id, str) or not meter_id.strip():
        return jsonify(
            {
                "status": "error",
                "message": "meter_id is required",
            }
        ), 400

    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    with DATA_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps(record, ensure_ascii=False, indent=2))

    return jsonify(
        {
            "status": "accepted",
            "meter_id": meter_id,
            "received_at": record["received_at"],
        }
    ), 201


if __name__ == "__main__":
    app.run(
        host=API_HOST,
        port=API_PORT,
        debug=True,
    )