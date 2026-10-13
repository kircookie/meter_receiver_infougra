from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_FORWARD_API_KEY,
    CONF_FORWARD_URL,
    DOMAIN,
    ELECTRICITY_ATTRIBUTE_TARIFFS,
    EVENT_READING_RECEIVED,
    METER_TYPE_ELECTRICITY,
    READING_VALUE,
    TARIFF_DAY,
    TARIFF_NIGHT,
)
from .meters import MeterConfig

_LOGGER = logging.getLogger(__name__)

FORWARD_TIMEOUT = 10


async def async_process_reading(
    hass: HomeAssistant,
    meter: MeterConfig,
    values: dict[str, float],
    measured_at: datetime | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Сохранить показание в hass.data, поднять событие и переслать во внешний API."""

    now = datetime.now(timezone.utc)
    if measured_at is None:
        measured_at = now
    elif measured_at.tzinfo is None:
        measured_at = measured_at.replace(tzinfo=timezone.utc)

    record = {
        "account": meter.account,
        "meter_id": meter.source_id,
        "meter_name": meter.name,
        "meter_type": meter.meter_type,
        "unit": meter.unit,
        "measured_at": measured_at.isoformat(),
        "received_at": now.isoformat(),
        "source": meter.source,
        "values": values,
    }

    hass.data[DOMAIN]["readings"][meter.source_id] = record

    hass.bus.async_fire(
        EVENT_READING_RECEIVED,
        {**record, "raw": raw or {}},
    )

    _LOGGER.debug("Processed meter reading: %s", record)

    forward = await async_forward(hass, meter, values, record["measured_at"])
    record["forward"] = forward
    return record


async def async_forward(
    hass: HomeAssistant,
    meter: MeterConfig,
    values: dict[str, float],
    measured_at: str,
) -> dict[str, Any]:
    """Переслать показание на forward_url, указанный в конфигурации."""

    url = hass.data[DOMAIN].get(CONF_FORWARD_URL)
    if not url:
        return {"status": "skipped"}

    api_key = hass.data[DOMAIN].get(CONF_FORWARD_API_KEY) or ""

    payload: dict[str, Any] = {
        "account": meter.account,
        "meter_id": meter.source_id,
        "meter_name": meter.name,
        "meter_type": meter.meter_type,
        "unit": meter.unit,
        "measured_at": measured_at,
        "source": meter.source,
    }
    if meter.meter_type == METER_TYPE_ELECTRICITY:
        for tariff in (TARIFF_DAY, TARIFF_NIGHT):
            if tariff in values:
                payload[f"{tariff}_kwh"] = values[tariff]
    else:
        payload[READING_VALUE] = values[READING_VALUE]

    session = async_get_clientsession(hass)

    try:
        async with asyncio.timeout(FORWARD_TIMEOUT):
            response = await session.post(
                url,
                json=payload,
                headers={"X-API-Key": api_key},
            )
            body = await response.text()
        return {
            "status": "sent",
            "http_status": response.status,
            "response": body,
        }
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Forwarding reading to %s failed: %s", url, err)
        return {"status": "failed", "error": str(err)}


def entity_values(meter: MeterConfig, state: State) -> dict[str, float]:
    """Извлечь показания из состояния entity HA.

    Для электросчётчика значения тарифов берутся из атрибутов
    (day_kwh/t1 для дня, night_kwh/t2 для ночи); для остальных —
    из состояния сенсора.
    """
    if meter.meter_type == METER_TYPE_ELECTRICITY:
        values: dict[str, float] = {}
        for tariff, aliases in ELECTRICITY_ATTRIBUTE_TARIFFS.items():
            if tariff not in meter.tariffs:
                continue
            for alias in aliases:
                if alias in state.attributes:
                    values[tariff] = float(state.attributes[alias])
                    break
        if not values:
            raise ValueError(
                f"Entity {state.entity_id} has no tariff attributes "
                f"({', '.join(a for aliases in ELECTRICITY_ATTRIBUTE_TARIFFS.values() for a in aliases)})"
            )
        return values

    try:
        return {READING_VALUE: float(state.state)}
    except (TypeError, ValueError) as err:
        raise ValueError(
            f"Entity {state.entity_id} state is not a number: {state.state!r}"
        ) from err


def endpoint_values(meter: MeterConfig, payload: dict[str, Any]) -> dict[str, float]:
    """Извлечь показания из JSON, присланного на endpoint."""
    if meter.meter_type == METER_TYPE_ELECTRICITY:
        values = {}
        for tariff in (TARIFF_DAY, TARIFF_NIGHT):
            if tariff not in meter.tariffs:
                continue
            for key in (f"{tariff}_kwh", f"t{'1' if tariff == TARIFF_DAY else '2'}"):
                if key in payload and payload[key] is not None:
                    values[tariff] = float(payload[key])
                    break
        if not values:
            raise ValueError(
                "Electricity reading requires 'day_kwh'/'night_kwh' "
                "(or 't1'/'t2') for configured tariffs"
            )
        return values

    if READING_VALUE not in payload or payload[READING_VALUE] is None:
        raise ValueError("Reading requires numeric 'value'")
    try:
        return {READING_VALUE: float(payload[READING_VALUE])}
    except (TypeError, ValueError) as err:
        raise ValueError(f"'value' is not a number: {payload[READING_VALUE]!r}") from err


def parse_measured_at(raw: Any) -> datetime | None:
    """Разобрать строку ISO-времени из payload (Z-сuffix поддерживается)."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError as err:
        raise ValueError(f"Invalid 'measured_at': {raw!r}") from err
