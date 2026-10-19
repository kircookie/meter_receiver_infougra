from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_ACCOUNT,
    CONF_ENTITY_ID,
    CONF_FORWARD_API_KEY,
    CONF_FORWARD_URL,
    CONF_METERS,
    CONF_METER_ID,
    CONF_NAME,
    CONF_TARIFFS,
    CONF_TYPE,
    DEFAULT_UNITS,
    DOMAIN,
    SOURCE_ENDPOINT,
    SOURCE_ENTITY,
)
from .http import MeterReadingsView
from .meters import METER_SCHEMA, MeterConfig
from .processing import async_process_reading, entity_values

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_FORWARD_URL): cv.string,
                vol.Optional(CONF_FORWARD_API_KEY): cv.string,
                vol.Optional(CONF_METERS): vol.All(cv.ensure_list, [METER_SCHEMA]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def _build_meter(entry: dict) -> MeterConfig:
    source_type = SOURCE_ENTITY if entry.get(CONF_ENTITY_ID) else SOURCE_ENDPOINT
    source_id = entry.get(CONF_ENTITY_ID) or entry[CONF_METER_ID]
    meter_type = entry[CONF_TYPE]
    return MeterConfig(
        source_type=source_type,
        source_id=source_id,
        account=entry[CONF_ACCOUNT],
        name=entry[CONF_NAME],
        meter_type=meter_type,
        tariffs=tuple(entry.get(CONF_TARIFFS) or ()),
        unit=DEFAULT_UNITS[meter_type],
    )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Meter Receiver integration from YAML configuration."""

    domain_config = config.get(DOMAIN) or {}

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["readings"] = {}
    hass.data[DOMAIN][CONF_FORWARD_URL] = domain_config.get(CONF_FORWARD_URL)
    hass.data[DOMAIN][CONF_FORWARD_API_KEY] = domain_config.get(CONF_FORWARD_API_KEY)

    meters = [_build_meter(entry) for entry in domain_config.get(CONF_METERS) or []]
    hass.data[DOMAIN]["meters"] = meters
    hass.data[DOMAIN]["meters_by_meter_id"] = {
        meter.source_id: meter
        for meter in meters
        if meter.source_type == SOURCE_ENDPOINT
    }
    meters_by_entity_id = {
        meter.source_id: meter
        for meter in meters
        if meter.source_type == SOURCE_ENTITY
    }
    hass.data[DOMAIN]["meters_by_entity_id"] = meters_by_entity_id

    hass.http.register_view(MeterReadingsView(hass))

    if meters_by_entity_id:
        async_track_state_change_event(
            hass,
            list(meters_by_entity_id),
            _async_entity_changed_event(hass),
        )

    _LOGGER.info(
        "Meter Receiver set up: %d meters (%d entity, %d endpoint), forward_url=%s",
        len(meters),
        len(meters_by_entity_id),
        len(meters) - len(meters_by_entity_id),
        hass.data[DOMAIN][CONF_FORWARD_URL] or "not configured",
    )

    return True


def _async_entity_changed_event(hass):
    """Фабрика обработчика изменений состояния entity-источников.

    Колбэк получает Event; hass захватывается через замыкание —
    совместимо с современными версиями Home Assistant.
    """

    async def _async_entity_changed(event) -> None:
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]
        if new_state is None or new_state.state in (None, "unknown", "unavailable"):
            return

        meter = hass.data[DOMAIN]["meters_by_entity_id"].get(entity_id)
        if meter is None:
            return

        try:
            values = entity_values(meter, new_state)
        except ValueError as err:
            _LOGGER.warning("Skipping reading from %s: %s", entity_id, err)
            return

        await async_process_reading(
            hass,
            meter,
            values,
            measured_at=new_state.last_changed,
            raw={
                "entity_id": entity_id,
                "state": new_state.state,
                "attributes": dict(new_state.attributes),
            },
        )

    return _async_entity_changed
