from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import CONF_METER_ID, DOMAIN
from .processing import async_process_reading, endpoint_values, parse_measured_at

_LOGGER = logging.getLogger(__name__)


class MeterReadingsView(HomeAssistantView):
    """Accept meter readings through HTTP POST."""

    url = "/api/meter_receiver/readings"
    name = "api:meter_receiver:readings"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def post(self, request: web.Request) -> web.Response:
        """Receive a reading from a local sender (gateway, device, Postman)."""

        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("expected a JSON object")

            meter_id = str(payload[CONF_METER_ID]).strip()
            if not meter_id:
                raise ValueError("meter_id cannot be empty")
        except (ValueError, TypeError, KeyError) as err:
            return web.json_response(
                {
                    "status": "error",
                    "message": f"Invalid JSON payload: {err}",
                },
                status=400,
            )

        meters_by_id = self.hass.data[DOMAIN]["meters_by_meter_id"]
        meter = meters_by_id.get(meter_id)
        if meter is None:
            return web.json_response(
                {
                    "status": "error",
                    "message": (
                        f"Unknown meter_id '{meter_id}'. "
                        "Configure it under 'meter_receiver: meters:' with 'meter_id:'"
                    ),
                },
                status=400,
            )

        try:
            values = endpoint_values(meter, payload)
            measured_at = parse_measured_at(payload.get("measured_at"))
        except ValueError as err:
            return web.json_response(
                {"status": "error", "message": str(err)},
                status=400,
            )

        record = await async_process_reading(
            self.hass,
            meter,
            values,
            measured_at=measured_at,
            raw=payload,
        )

        _LOGGER.debug("Received meter reading: %s", record)

        return web.json_response(
            {
                "status": "ok",
                "meter_id": meter_id,
                "received": {
                    key: record[key]
                    for key in (
                        "account",
                        "meter_name",
                        "meter_type",
                        "unit",
                        "measured_at",
                        "received_at",
                        "source",
                        "values",
                    )
                },
                "forward": record["forward"],
            },
            status=200,
        )
