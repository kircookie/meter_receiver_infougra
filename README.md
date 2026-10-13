# Meter Receiver — Home Assistant + Local API

Приём показаний приборов учёта в Home Assistant и пересылка данных в промежуточную базу данных (SQLite) через локальный HTTP API.

```text
Прибор / шлюз / Postman                entity HA (сенсор)
        │ POST JSON                          │ изменение состояния
        ▼                                    ▼
Home Assistant custom component «meter_receiver»
        │  событие meter_receiver_reading_received → template sensors
        │  POST JSON (forward)
        ▼
Local Meter API (Flask)
        ├─ авторизация по X-API-Key
        ├─ только последнее показание на счётчик (+тариф)
        ├─ дедупликация (значение не изменилось → не пишем)
        ├─ флаг suspicious (показание меньше предыдущего)
        └─ SQLite: readings.db
        ▼
GET /api/v1/readings — выборка потребителями (например, ЛК)
```

Проект предназначен для работы в доверенной локальной сети. Не публикуйте endpoint Home Assistant или Local API в интернет без аутентификации, HTTPS и дополнительных мер защиты.

## Возможности

- Два типа источников показаний на выбор:
  - `entity_id` — существующий сенсор HA (значение берётся из состояния/атрибутов);
  - `meter_id` — внешний отправитель шлёт JSON на `POST /api/meter_receiver/readings`.
- Типы счётчиков: `cold_water` (ХВС, м³), `hot_water` (ГВС, м³), `electricity` (кВт·ч, тарифы день/ночь), `gas` (м³), `heat` (Гкал).
- Пользовательское название счётчика («ХВС», «Электроснабжение») и лицевой счёт задаются в YAML-конфигурации.
- Событие `meter_receiver_reading_received` в шине HA для template-сенсоров.
- Пересылка показаний во внешний API (`forward_url`) с заголовком `X-API-Key`.
- SQLite-хранилище: только последнее показание на пару счётчик+тариф, дедупликация, флаг `suspicious`.
- Эндпоинт выборки `GET /api/v1/readings` (фильтры: `account`, `meter_id`, `meter_type`, `tariff`).
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
│       ├── http.py              # endpoint /api/meter_receiver/readings
│       └── manifest.json
├── local_api/
│   ├── server.py                # Flask-приложение (create_app)
│   ├── storage.py               # SQLite: схема, store_reading, query_readings
│   ├── schemas.py               # Pydantic-схема входящего показания
│   ├── tests/test_api.py
│   └── requirements.txt
├── configuration.yaml           # пример конфигурации HA (методичка)
├── .env.example                 # шаблон настроек Local API
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

Авторизация: заголовок `X-API-Key`.

Вода / газ / отопление:

```json
{
  "account": "1234567890",
  "meter_id": "hvs_001",
  "meter_name": "ХВС",
  "meter_type": "cold_water",
  "unit": "м³",
  "measured_at": "2026-10-12T10:00:00+00:00",
  "source": "endpoint:hvs_001",
  "value": 12.3
}
```

Электроснабжение (день/ночь):

```json
{
  "account": "1234567890",
  "meter_id": "electricity_001",
  "meter_name": "Электроснабжение",
  "meter_type": "electricity",
  "unit": "кВт·ч",
  "measured_at": "2026-10-12T10:00:00+00:00",
  "source": "entity:sensor.electricity_meter",
  "day_kwh": 1284.73,
  "night_kwh": 512.4
}
```

Поля `unit`, `measured_at`, `source` необязательны; `unit` по умолчанию берётся из типа счётчика. Для электро допустимо передавать только один тариф. `value` запрещён для электро, `day_kwh`/`night_kwh` — для остальных типов.

Ответ `201`:

```json
{
  "status": "accepted",
  "meter_id": "electricity_001",
  "received_at": "2026-10-12T10:05:00.000000+00:00",
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
    {"account": "1234567890", "meter_id": "electricity_001", "meter_name": "Электроснабжение",
     "meter_type": "electricity", "tariff": "day", "value": 1284.73, "unit": "кВт·ч",
     "measured_at": "...", "received_at": "...", "source": "entity:sensor.electricity_meter",
     "status": "ok", "raw_payload": "{...}"},
    {"tariff": "night", ...}
  ]
}
```

### Формат хранения (SQLite)

Таблица `readings`, уникальность — `(account, meter_id, tariff)`; хранится только последнее показание:

| Колонка | Описание |
|---|---|
| `account` | Лицевой счёт |
| `meter_id` | Идентификатор счётчика |
| `meter_name` | Пользовательское название |
| `meter_type` | `cold_water` / `hot_water` / `electricity` / `gas` / `heat` |
| `tariff` | `NULL` или `day` / `night` (электро) |
| `value` | Показание |
| `unit` | `м³` / `кВт·ч` / `Гкал` |
| `measured_at` | Время измерения (от прибора, если есть) |
| `received_at` | Время приёма сервером (UTC) |
| `source` | `entity:<entity_id>` / `endpoint:<meter_id>` |
| `status` | `ok` / `suspicious` |
| `raw_payload` | Исходный JSON |

### Тесты

```bash
cd local_api
.venv/bin/python -m pytest tests/ -q
```

## Home Assistant component

### Установка

Скопируйте каталог в конфигурационную папку HA:

```text
custom_components/meter_receiver/  →  /config/custom_components/meter_receiver/
```

### Конфигурация

Пример полностью — в [`configuration.yaml`](configuration.yaml) репозитория. Кратко:

```yaml
meter_receiver:
  forward_url: "http://192.168.1.50:5001/api/v1/readings"
  forward_api_key: "тот-же-ключ-что-в-.env"
  meters:
    - entity_id: sensor.hvs_counter        # источник: сенсор HA
      account: "1234567890"                # лицевой счёт (задаётся вручную)
      name: "ХВС"
      meter_type: cold_water
    - meter_id: electricity_001            # источник: endpoint
      account: "1234567890"
      name: "Электроснабжение"
      meter_type: electricity
      tariffs: [day, night]                # по умолчанию оба тарифа
```

Правила:

- У счётчика ровно один источник: `entity_id` **или** `meter_id`.
- `tariffs` допустимы только для `electricity`; если не указаны — `[day, night]`.
- Для entity-источника электросчётчика показания тарифов читаются из атрибутов сенсора: `day_kwh`/`t1` (день) и `night_kwh`/`t2` (ночь); для остальных типов — из состояния сенсора.
- Если `forward_url` не задан — показание принимается, сенсоры обновляются, пересылка со статусом `skipped`.

После изменения `configuration.yaml`: **Developer Tools → YAML → Check configuration → Restart**.

### Endpoint /api/meter_receiver/readings

Без авторизации (рассчитан на доверенную LAN). Принимает только настроенные `meter_id`:

```bash
curl -X POST http://IP_HA:8123/api/meter_receiver/readings \
  -H "Content-Type: application/json" \
  -d '{"meter_id": "electricity_001", "day_kwh": 1284.73, "night_kwh": 512.4}'
```

Для воды/газа: `{"meter_id": "hvs_001", "value": 12.3}`. Опционально `measured_at` (ISO-8601).

Успешный ответ содержит `received` (нормализованное показание) и `forward` (`sent`/`failed`/`skipped`).

## Диагностика

| Симптом | Причина | Решение |
|---|---|---|
| `404` на `/api/meter_receiver/readings` | Компонент не загрузился | Проверьте `/config/custom_components/meter_receiver/`, блок `meter_receiver:` и перезапустите HA |
| `400 Unknown meter_id` | Счётчик не описан в конфиге | Добавьте запись с `meter_id:` под `meters:` |
| `400` про тарифы | Неверные поля для типа счётчика | Электро — `day_kwh`/`night_kwh`, остальные — `value` |
| `401` от Local API | Неверный/пустой `X-API-Key` | Сверьте `API_KEY` в `.env` и `forward_api_key` в HA |
| `500 API_KEY is not configured` | Ключ не задан в `.env` | Задайте `API_KEY` и перезапустите API |
| `forward.status: failed` | API недоступен / firewall / неверный URL | Проверьте `/health` с хоста HA, IP/порт |
| Показания не пишутся в БД | Дедупликация (`duplicate`) | Значение совпадает с текущим — это нормально |
| Запись `status: suspicious` | Показание меньше предыдущего | Проверьте прибор/отправителя |

## Следующие шаги

- Входная аутентификация endpoint Home Assistant (токен в заголовке).
- **Config Flow**: мастер добавления счётчиков в UI Home Assistant вместо YAML (выбор entity из выпадающего списка, создание отдельных entity на каждый счётчик).
- Хранение секретов в `secrets.yaml` / Config Entry.
- Очередь с retry и журналирование ошибок пересылки.
- PostgreSQL/TimescaleDB вместо SQLite при росте числа счётчиков.
- Push-модель доставки в ЛК (webhook) вместо поллинга `GET /api/v1/readings`.
