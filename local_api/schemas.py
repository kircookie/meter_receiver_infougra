from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

MeterType = Literal["cold_water", "hot_water", "electricity", "gas", "heat"]

METER_TYPE_UNITS = {
    "cold_water": "м³",
    "hot_water": "м³",
    "electricity": "кВт·ч",
    "gas": "м³",
    "heat": "Гкал",
}


class ReadingPayload(BaseModel):
    """Входящее показание от Home Assistant (forward) или внешнего отправителя."""

    account: str = Field(min_length=1)
    meter_id: str = Field(min_length=1)
    meter_name: str = ""
    meter_type: MeterType
    unit: Optional[str] = None
    measured_at: Optional[str] = None
    source: str = ""

    # Для воды/газа/отопления
    value: Optional[float] = Field(default=None, ge=0)
    # Для электросчётчика (день/ночь)
    day_kwh: Optional[float] = Field(default=None, ge=0)
    night_kwh: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_values(self) -> "ReadingPayload":
        if self.meter_type == "electricity":
            if self.value is not None:
                raise ValueError(
                    "'value' is not allowed for electricity, "
                    "use 'day_kwh'/'night_kwh'"
                )
            if self.day_kwh is None and self.night_kwh is None:
                raise ValueError(
                    "Electricity reading requires 'day_kwh' and/or 'night_kwh'"
                )
        else:
            if self.value is None:
                raise ValueError(f"'value' is required for {self.meter_type}")
            if self.day_kwh is not None or self.night_kwh is not None:
                raise ValueError(
                    "'day_kwh'/'night_kwh' are only allowed for electricity"
                )
        if not self.unit:
            self.unit = METER_TYPE_UNITS[self.meter_type]
        return self
