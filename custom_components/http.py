from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, EVENT_READING_RECEIVED

_LOGGER = logging.getLogger(__name__)


class MeterReadingsView(HomeAssistantView):
    """Accept meter readings through HTTP POST."""

    url = "/api/meter_receiver/readings"
    name = "api:meter_receiver:readings"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Receive a reading from a local sender."""

        try:
            payload = await request.json()

            meter_id = str(payload["meter_id"]).strip()
            name = str(payload.get("name", meter_id)).strip()

            if not meter_id:
                raise ValueError("meter_id cannot be empty")

            reading = {
                "meter_id": meter_id,
                "name": name,
                "energy_kwh": self._to_float(payload.get("energy_kwh")),
                "power_w": self._to_float(payload.get("power_w")),
            }

        except (ValueError, TypeError, KeyError) as err:
            return web.json_response(
                {
                    "status": "error",
                    "message": f"Invalid JSON payload: {err}",
                },
                status=400,
            )

        self.hass.data[DOMAIN]["readings"][meter_id] = reading

        self.hass.bus.async_fire(
            EVENT_READING_RECEIVED,
            reading,
        )

        _LOGGER.debug("Received meter reading: %s", reading)

        return web.json_response(
            {
                "status": "ok",
                "meter_id": meter_id,
                "received": reading,
            },
            status=200,
        )

    @staticmethod
    def _to_float(value):
        """Convert optional value to float."""
        if value is None:
            return None

        return float(value)