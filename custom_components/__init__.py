from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .http import MeterReadingsView


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Meter Receiver integration."""

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["readings"] = {}

    hass.http.register_view(MeterReadingsView(hass))

    return True