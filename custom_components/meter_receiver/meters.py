from __future__ import annotations

from dataclasses import dataclass

import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ACCOUNT,
    CONF_CODE,
    CONF_ENTITY_ID,
    CONF_METER_NUMBER,
    CONF_NAME,
    CONF_TARIFFS,
    CONF_TYPE,
    ELECTRICITY_TARIFFS,
    METER_TYPE_ELECTRICITY,
    METER_TYPES,
)


@dataclass
class MeterConfig:
    """Настройки одного счётчика из YAML-конфигурации."""

    entity_id: str
    account: str
    code: str  # код лицевого счёта из ЛК (верификацию выполняет ЛК при заборе)
    meter_number: str  # номер счётчика (как в ЛК)
    name: str
    meter_type: str
    tariffs: tuple = ()
    unit: str = ""

    @property
    def source(self) -> str:
        return f"entity:{self.entity_id}"


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
            vol.Required(CONF_ENTITY_ID): cv.entity_id,
            vol.Required(CONF_ACCOUNT): cv.string,
            vol.Required(CONF_CODE): cv.string,
            vol.Required(CONF_METER_NUMBER): cv.string,
            vol.Required(CONF_NAME): cv.string,
            vol.Required(CONF_TYPE): vol.In(METER_TYPES),
            vol.Optional(CONF_TARIFFS): vol.All(
                cv.ensure_list, [vol.In(ELECTRICITY_TARIFFS)], vol.Unique()
            ),
        }
    ),
    _meter_tariffs,
)
