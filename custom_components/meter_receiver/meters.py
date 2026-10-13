from __future__ import annotations

from dataclasses import dataclass, field

import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ACCOUNT,
    CONF_ENTITY_ID,
    CONF_METER_ID,
    CONF_NAME,
    CONF_TARIFFS,
    CONF_TYPE,
    ELECTRICITY_TARIFFS,
    METER_TYPE_ELECTRICITY,
    METER_TYPES,
    SOURCE_ENDPOINT,
    SOURCE_ENTITY,
)


@dataclass
class MeterConfig:
    """Настройки одного счётчика из YAML-конфигурации."""

    source_type: str  # entity | endpoint
    source_id: str  # entity_id либо meter_id
    account: str
    name: str
    meter_type: str
    tariffs: tuple = ()
    unit: str = ""

    @property
    def source(self) -> str:
        return f"{self.source_type}:{self.source_id}"


def _meter_has_source(config: dict) -> dict:
    has_entity = bool(config.get(CONF_ENTITY_ID))
    has_meter = bool(config.get(CONF_METER_ID))
    if has_entity == has_meter:
        raise vol.Invalid(
            "Meter entry must have exactly one of 'entity_id' or 'meter_id'"
        )
    return config


def _meter_tariffs(config: dict) -> dict:
    meter_type = config[CONF_TYPE]
    tariffs = config.get(CONF_TARIFFS)
    if meter_type == METER_TYPE_ELECTRICITY:
        if not tariffs:
            config[CONF_TARIFFS] = list(ELECTRICITY_TARIFFS)
    elif tariffs:
        raise vol.Invalid("'tariffs' are only allowed for electricity meters")
    return config


METER_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(CONF_ENTITY_ID): cv.entity_id,
            vol.Optional(CONF_METER_ID): cv.string,
            vol.Required(CONF_ACCOUNT): cv.string,
            vol.Required(CONF_NAME): cv.string,
            vol.Required(CONF_TYPE): vol.In(METER_TYPES),
            vol.Optional(CONF_TARIFFS): vol.All(
                cv.ensure_list, [vol.In(ELECTRICITY_TARIFFS)], vol.Unique()
            ),
        }
    ),
    _meter_has_source,
    _meter_tariffs,
)
