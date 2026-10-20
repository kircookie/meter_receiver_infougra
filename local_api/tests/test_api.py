import pytest

import storage
from server import create_app

API_KEY = "test-secret-key"

WATER_PAYLOAD = {
    "account": "1234567890",
    "code": "lk-code-1",
    "meter_number": "126439",
    "meter_name": "ХВС",
    "meter_type": "cold_water",
    "source": "entity:sensor.svd_15_126439_water",
    "value": 12.3,
}

ELECTRICITY_PAYLOAD = {
    "account": "1234567890",
    "code": "lk-code-1",
    "meter_number": "7701234567",
    "meter_name": "Электроснабжение",
    "meter_type": "electricity",
    "source": "entity:sensor.electricity_meter",
    "day_kwh": 1284.73,
    "night_kwh": 512.4,
}


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "readings.db", api_key=API_KEY)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture()
def client_no_key(tmp_path):
    app = create_app(db_path=tmp_path / "readings.db", api_key="")
    app.config["TESTING"] = True
    return app.test_client()


def auth_headers():
    return {"X-API-Key": API_KEY}


def db_rows(client):
    conn = storage.connect(client.application.config["DB_PATH"])
    try:
        return storage.query_readings(conn)
    finally:
        conn.close()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_post_without_key_unauthorized(client):
    response = client.post("/api/v1/readings", json=WATER_PAYLOAD)
    assert response.status_code == 401


def test_post_api_key_not_configured(client_no_key):
    response = client_no_key.post(
        "/api/v1/readings", json=WATER_PAYLOAD, headers=auth_headers()
    )
    assert response.status_code == 500


def test_post_invalid_json(client):
    response = client.post(
        "/api/v1/readings",
        data="not-json",
        headers={**auth_headers(), "Content-Type": "application/json"},
    )
    assert response.status_code == 400


def test_post_missing_meter_number(client):
    payload = {k: v for k, v in WATER_PAYLOAD.items() if k != "meter_number"}
    response = client.post("/api/v1/readings", json=payload, headers=auth_headers())
    assert response.status_code == 400


def test_post_missing_code(client):
    payload = {k: v for k, v in WATER_PAYLOAD.items() if k != "code"}
    response = client.post("/api/v1/readings", json=payload, headers=auth_headers())
    assert response.status_code == 400


def test_post_empty_code(client):
    payload = {**WATER_PAYLOAD, "code": ""}
    response = client.post("/api/v1/readings", json=payload, headers=auth_headers())
    assert response.status_code == 400


def test_post_negative_value(client):
    payload = {**WATER_PAYLOAD, "value": -1}
    response = client.post("/api/v1/readings", json=payload, headers=auth_headers())
    assert response.status_code == 400


def test_store_water_reading(client):
    response = client.post("/api/v1/readings", json=WATER_PAYLOAD, headers=auth_headers())
    assert response.status_code == 201
    body = response.get_json()
    assert body["status"] == "accepted"
    assert body["stored"] == 1
    assert body["results"][0]["tariff"] is None
    assert body["results"][0]["status"] == "ok"

    rows = db_rows(client)
    assert len(rows) == 1
    assert rows[0]["account"] == "1234567890"
    assert rows[0]["code"] == "lk-code-1"
    assert rows[0]["meter_number"] == "126439"
    assert rows[0]["meter_type"] == "cold_water"
    assert rows[0]["tariff"] is None
    assert rows[0]["value"] == 12.3
    assert rows[0]["unit"] == "м³"
    assert rows[0]["status"] == "ok"
    assert rows[0]["source"] == "entity:sensor.svd_15_126439_water"


def test_store_electricity_day_night(client):
    response = client.post(
        "/api/v1/readings", json=ELECTRICITY_PAYLOAD, headers=auth_headers()
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["stored"] == 2

    rows = db_rows(client)
    assert len(rows) == 2
    tariffs = {row["tariff"]: row["value"] for row in rows}
    assert tariffs == {"day": 1284.73, "night": 512.4}
    assert all(row["unit"] == "кВт·ч" for row in rows)


def test_electricity_day_only(client):
    payload = {**ELECTRICITY_PAYLOAD, "night_kwh": None}
    response = client.post("/api/v1/readings", json=payload, headers=auth_headers())
    assert response.status_code == 201
    assert response.get_json()["stored"] == 1
    rows = db_rows(client)
    assert [row["tariff"] for row in rows] == ["day"]


def test_electricity_rejects_plain_value(client):
    payload = {
        **ELECTRICITY_PAYLOAD,
        "day_kwh": None,
        "night_kwh": None,
        "value": 100.0,
    }
    response = client.post("/api/v1/readings", json=payload, headers=auth_headers())
    assert response.status_code == 400


def test_water_rejects_tariff_values(client):
    payload = {**WATER_PAYLOAD, "day_kwh": 1.0}
    response = client.post("/api/v1/readings", json=payload, headers=auth_headers())
    assert response.status_code == 400


def test_duplicate_not_stored(client):
    client.post("/api/v1/readings", json=WATER_PAYLOAD, headers=auth_headers())
    response = client.post("/api/v1/readings", json=WATER_PAYLOAD, headers=auth_headers())
    assert response.status_code == 201
    body = response.get_json()
    assert body["status"] == "duplicate"
    assert body["stored"] == 0
    assert len(db_rows(client)) == 1


def test_upsert_updates_value(client):
    client.post("/api/v1/readings", json=WATER_PAYLOAD, headers=auth_headers())
    updated = {**WATER_PAYLOAD, "value": 15.7}
    response = client.post("/api/v1/readings", json=updated, headers=auth_headers())
    assert response.get_json()["status"] == "accepted"

    rows = db_rows(client)
    assert len(rows) == 1
    assert rows[0]["value"] == 15.7


def test_suspicious_when_lower_than_previous(client):
    client.post("/api/v1/readings", json=WATER_PAYLOAD, headers=auth_headers())
    lowered = {**WATER_PAYLOAD, "value": 5.0}
    response = client.post("/api/v1/readings", json=lowered, headers=auth_headers())
    results = response.get_json()["results"]
    assert results[0]["status"] == "suspicious"
    assert db_rows(client)[0]["status"] == "suspicious"


def test_suspicious_per_tariff(client):
    client.post(
        "/api/v1/readings", json=ELECTRICITY_PAYLOAD, headers=auth_headers()
    )
    lowered = {**ELECTRICITY_PAYLOAD, "night_kwh": 100.0}
    response = client.post("/api/v1/readings", json=lowered, headers=auth_headers())
    statuses = {r["tariff"]: r["status"] for r in response.get_json()["results"]}
    assert statuses == {"day": "ok", "night": "suspicious"}


def test_get_readings_filter_by_account_and_type(client):
    client.post("/api/v1/readings", json=WATER_PAYLOAD, headers=auth_headers())
    client.post(
        "/api/v1/readings", json=ELECTRICITY_PAYLOAD, headers=auth_headers()
    )

    response = client.get(
        "/api/v1/readings?account=1234567890&meter_type=cold_water",
        headers=auth_headers(),
    )
    body = response.get_json()
    assert body["count"] == 1
    assert body["results"][0]["meter_number"] == "126439"

    response = client.get(
        "/api/v1/readings?meter_number=7701234567&tariff=night",
        headers=auth_headers(),
    )
    body = response.get_json()
    assert body["count"] == 1
    assert body["results"][0]["value"] == 512.4


def test_get_readings_requires_key(client):
    response = client.get("/api/v1/readings")
    assert response.status_code == 401
