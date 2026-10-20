# Meter Receiver — Home Assistant + Local API

Приём показаний приборов учёта из Home Assistant (только entity-источники) и пересылка в промежуточную базу данных (SQLite) через локальный HTTP API.

```text
entity HA (сенсор счётчика, напр. интеграция Элехант)
        │ изменение состояния
        ▼
Home Assistant custom component «meter_receiver»
        │  событие meter_receiver_reading_received → template sensors
        │  POST JSON (forward): счётчик + код ЛС + показания
        ▼
Local Meter API (Flask)
        ├─ авторизация по X-API-Key
        ├─ только последнее показание на счётчик (+тариф)
        ├─ дедупликация (значение не изменилось → не пишем)
        ├─ флаг suspicious (показание меньше предыдущего)
        └─ SQLite: readings.db
        ▼
GET /api/v1/readings — выборка потребителями (ЛК проверяет код ЛС при заборе)
```

Проект предназначен для работы в доверенной локальной сети. Не публикуйте Local API в интернет без аутентификации, HTTPS и дополнительных мер защиты.

## Возможности

- Источник показаний — сенсоры Home Assistant (`entity_id`), например интеграция Элехант.
- Типы счётчиков: `cold_water` (ХВС, м³), `hot_water` (ГВС, м³), `electricity` (кВт·ч, тарифы день/ночь), `gas` (м³), `heat` (Гкал).
- Для каждого счётчика задаются: лицевой счёт (`account`), номер счётчика (`meter_number`), код лицевого счёта из ЛК (`code`) — код пока принимается и хранится, верификацию выполняет ЛК при заборе данных.
- Событие `meter_receiver_reading_received` в шине HA для template-сенсоров.
- Пересылка показаний во внешний API (`forward_url`) с заголовком `X-API-Key`.
- SQLite-хранилище: только последнее показание на пару счётчик+тариф, дедупликация, флаг `suspicious`.
- Эндпоинт выборки `GET /api/v1/readings` (фильтры: `account`, `meter_number`, `meter_type`, `tariff`).
- pytest-набор для Local API.

## Структура репозитория

```text
.
├── custom_components/
│   └── meter_receiver/          # компонент для /config/custom_components/
│       ├── __init__.py          # сетап, CONFIG_SCHEMA, отслеживание entity
│       ├── const.py
│       ├── meters.py            # MeterConfig + YAML-схема счётчиков
│       ├── processing.py        # пайплайн: событие + forward
│       └── manifest.json
├── local_api/
│   ├── server.py                # Flask-приложение (create_app)
│   ├── storage.py               # SQLite: схема, store_reading, query_readings
│   ├── schemas.py               # Pydantic-схема входящего показания
│   ├── tests/test_api.py
│   └── requirements.txt
├── configuration.yaml           # пример конфигурации HA (методичка)
├── .env.example                 # шаблон настроек Local API
├── hacs.json                    # метаданные для HACS
└── README.md
```

## Local Meter API

### Установка и запуск

```bash
cd local_api
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp ../.env.example .env          # задать API_KEY
python server.py
```

Переменные окружения (`.env`):

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Адрес прослушивания |
| `API_PORT` | `5001` | TCP-порт |
| `DB_PATH` | `readings.db` | Путь к файлу SQLite (создаётся автоматически) |
| `API_KEY` | — | Секрет для заголовка `X-API-Key` (обязателен для записи/выборки) |

Health check: `curl http://127.0.0.1:5001/health` → `{"status": "ok", "service": "local-meter-api"}`.

### POST /api/v1/readings — приём показания

Авторизация: заголовок `X-API-Key`. Показания присылает Home Assistant (forward).

Вода / газ / отопление:

```json
{
  "account": "1234567890",
  "code": "код-лицевого-счёта-из-ЛК",
  "meter_number": "126439",
  "meter_name": "ХВС",
  "meter_type": "cold_water",
  "unit": "м³",
  "measured_at": "2026-10-20T10:00:00+00:00",
  "source": "entity:sensor.svd_15_126439_water",
  "value": 12.3
}
```

Электроснабжение (день/ночь):

```json
{
  "account": "1234567890",
  "code": "код-лицевого-счёта-из-ЛК",
  "meter_number": "7701234567",
  "meter_name": "Электроснабжение",
  "meter_type": "electricity",
  "unit": "кВт·ч",
  "measured_at": "2026-10-20T10:00:00+00:00",
  "source": "entity:sensor.electricity_meter",
  "day_kwh": 1284.73,
  "night_kwh": 512.4
}
```

Обязательные поля: `account`, `code`, `meter_number`, `meter_type` и показание (`value` или `day_kwh`/`night_kwh`). `unit` по умолчанию берётся из типа счётчика. Для электро допустимо передавать только один тариф. `value` запрещён для электро, `day_kwh`/`night_kwh` — для остальных типов.

Ответ `201`:

```json
{
  "status": "accepted",
  "meter_number": "7701234567",
  "received_at": "2026-10-20T10:05:00.000000+00:00",
  "stored": 2,
  "results": [
    {"tariff": "day", "value": 1284.73, "status": "ok", "result": "accepted"},
    {"tariff": "night", "value": 512.4, "status": "ok", "result": "accepted"}
  ]
}
```

`status: "duplicate"` и `stored: 0` — показание не изменилось, запись не обновлялась. `status: "suspicious"` в `results` — значение меньше предыдущего (записано, но помечено).

### GET /api/v1/readings — выборка

Авторизация: заголовок `X-API-Key`. Возвращает последние показания с фильтрами:

```bash
curl -H "X-API-Key: $API_KEY" \
  "http://127.0.0.1:5001/api/v1/readings?account=1234567890&meter_type=electricity"
```

```json
{
  "count": 2,
  "results": [
    {"account": "1234567890", "code": "код-ЛК", "meter_number": "7701234567",
     "meter_name": "Электроснабжение", "meter_type": "electricity", "tariff": "day",
     "value": 1284.73, "unit": "кВт·ч", "measured_at": "...",
     "received_at": "...", "source": "entity:sensor.electricity_meter",
     "status": "ok", "raw_payload": "{...}"},
    {"tariff": "night", ...}
  ]
}
```

### Формат хранения (SQLite)

Таблица `readings`, уникальность — `(account, meter_number, tariff)`; хранится только последнее показание:

| Колонка | Описание |
|---|---|
| `account` | Лицевой счёт |
| `code` | Код лицевого счёта из ЛК (верификацию выполняет ЛК при заборе) |
| `meter_number` | Номер счётчика |
| `meter_name` | Пользовательское название |
| `meter_type` | `cold_water` / `hot_water` / `electricity` / `gas` / `heat` |
| `tariff` | `NULL` или `day` / `night` (электро) |
| `value` | Показание |
| `unit` | `м³` / `кВт·ч` / `Гкал` |
| `measured_at` | Время измерения (от прибора, если есть) |
| `received_at` | Время приёма сервером (UTC) |
| `source` | `entity:<entity_id>` |
| `status` | `ok` / `suspicious` |
| `raw_payload` | Исходный JSON |

### Тесты

```bash
cd local_api
.venv/bin/python -m pytest tests/ -q
```

## Home Assistant component

### Установка

Через HACS: Custom repositories → `https://github.com/kircookie/meter_receiver_infougra` → категория Integration → Download → перезапуск HA. Либо вручную — скопировать каталог в `/config/custom_components/meter_receiver/`.

### Конфигурация

Пример полностью — в [`configuration.yaml`](configuration.yaml) репозитория. Кратко:

```yaml
meter_receiver:
  forward_url: "http://192.168.1.50:5001/api/v1/readings"
  forward_api_key: "тот-же-ключ-что-в-.env"
  meters:
    - entity_id: sensor.svd_15_126439_water   # сенсор счётчика в HA
      account: "1234567890"                   # лицевой счёт
      code: "код-из-личного-кабинета"         # код ЛС, уходит в forward
      meter_number: "126439"                  # номер счётчика (как в ЛК)
      name: "ХВС"
      meter_type: cold_water
    - entity_id: sensor.electricity_meter
      account: "1234567890"
      code: "код-из-личного-кабинета"
      meter_number: "7701234567"
      name: "Электроснабжение"
      meter_type: electricity
      tariffs: [day, night]                   # по умолчанию оба тарифа
```

Правила:

- Источник только один — `entity_id` (показания принимаются только со счётчиков, отображённых в HA).
- Все поля обязательны: `entity_id`, `account`, `code`, `meter_number`, `name`, `meter_type`.
- `tariffs` допустимы только для `electricity`; если не указаны — `[day, night]`.
- Для электросчётчика показания тарифов читаются из атрибутов сенсора: `day_kwh`/`t1` (день) и `night_kwh`/`t2` (ночь); для остальных типов — из состояния сенсора.
- Если `forward_url` не задан — показание принимается, сенсоры обновляются, пересылка со статусом `skipped`.

После изменения `configuration.yaml`: перезапуск HA (Настройки → Система → Перезапустить), в логах ищите `Meter Receiver set up: N meters (entity sources), forward_url=...`.

## Диагностика

| Симптом | Причина | Решение |
|---|---|---|
| Ошибка валидации конфига про `meter_receiver` | Не заполнены обязательные поля счётчика | Все поля: `entity_id`, `account`, `code`, `meter_number`, `name`, `meter_type` |
| `Skipping reading from sensor... state is not a number` | Состояние сенсора не число | Проверьте сенсор в Средства разработчика → Состояния |
| `... has no tariff attributes` | У электро-сенсора нет атрибутов `day_kwh`/`night_kwh` | Добавьте template-сенсор с этими атрибутами или оставьте один тариф |
| `401` от Local API | Неверный/пустой `X-API-Key` | Сверьте `API_KEY` в `.env` и `forward_api_key` в HA |
| `500 API_KEY is not configured` | Ключ не задан в `.env` | Задайте `API_KEY` и перезапустите API |
| `forward.status: failed` | API недоступен / firewall / неверный URL | Проверьте `/health` с хоста HA, IP/порт |
| Показания не пишутся в БД | Дедупликация (`duplicate`) | Значение совпадает с текущим — это нормально |
| Запись `status: suspicious` | Показание меньше предыдущего | Проверьте прибор/сенсор |

## Следующие шаги

- **Верификация кода ЛК**: справочник пар (счётчик, код) и отказ при несовпадении на стороне API (сейчас код принимается и хранится, проверяет ЛК при заборе).
- **Config Flow**: мастер добавления счётчиков в UI Home Assistant вместо YAML.
- Очередь с retry и журналирование ошибок пересылки.
- PostgreSQL/TimescaleDB вместо SQLite при росте числа счётчиков.
- Push-модель доставки в ЛК (webhook) вместо поллинга `GET /api/v1/readings`.
