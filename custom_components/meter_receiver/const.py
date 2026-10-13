DOMAIN = "meter_receiver"

EVENT_READING_RECEIVED = "meter_receiver_reading_received"

CONF_FORWARD_URL = "forward_url"
CONF_FORWARD_API_KEY = "forward_api_key"
CONF_METERS = "meters"
CONF_ENTITY_ID = "entity_id"
CONF_METER_ID = "meter_id"
CONF_ACCOUNT = "account"
CONF_NAME = "name"
CONF_TYPE = "meter_type"
CONF_TARIFFS = "tariffs"

SOURCE_ENTITY = "entity"
SOURCE_ENDPOINT = "endpoint"

METER_TYPE_COLD_WATER = "cold_water"
METER_TYPE_HOT_WATER = "hot_water"
METER_TYPE_ELECTRICITY = "electricity"
METER_TYPE_GAS = "gas"
METER_TYPE_HEAT = "heat"

METER_TYPES = (
    METER_TYPE_COLD_WATER,
    METER_TYPE_HOT_WATER,
    METER_TYPE_ELECTRICITY,
    METER_TYPE_GAS,
    METER_TYPE_HEAT,
)

TARIFF_DAY = "day"
TARIFF_NIGHT = "night"
ELECTRICITY_TARIFFS = (TARIFF_DAY, TARIFF_NIGHT)

DEFAULT_UNITS = {
    METER_TYPE_COLD_WATER: "м³",
    METER_TYPE_HOT_WATER: "м³",
    METER_TYPE_ELECTRICITY: "кВт·ч",
    METER_TYPE_GAS: "м³",
    METER_TYPE_HEAT: "Гкал",
}

# Атрибуты entity HA, откуда берутся зональные показания электросчётчика
ELECTRICITY_ATTRIBUTE_TARIFFS = {
    TARIFF_DAY: ("day_kwh", "t1"),
    TARIFF_NIGHT: ("night_kwh", "t2"),
}

READING_VALUE = "value"
