# Meter Receiver — Home Assistant + Local API

Локальный тестовый проект для приёма показаний приборов учёта в Home Assistant и пересылки данных в отдельный HTTP API.

```text
Postman / прибор / шлюз
        │
        │ POST JSON
        ▼
Home Assistant custom component
meter_receiver
        │
        ├─ отправляет событие Home Assistant
        ├─ обновляет template sensors
        │
        └─ POST JSON
                ▼
Local Meter API
        │
        ├─ выводит запрос в консоль
        └─ записывает данные в JSONL-файл
```

Проект предназначен для разработки и тестов в доверенной локальной сети. Не публикуйте endpoint Home Assistant или локальный API в интернет без аутентификации, HTTPS и дополнительных мер защиты.

## Возможности

- Приём JSON-показаний в Home Assistant через `POST /api/meter_receiver/readings`.
- Проверка обязательного поля `meter_id` и приведение числовых значений.
- Отправка события `meter_receiver_reading_received` в Home Assistant.
- Обновление template-сенсоров энергии и мощности.
- Пересылка показаний на внешний API, указанный в `forward_url`.
- Локальный Flask API для тестирования.
- Сохранение всех успешно принятых показаний в `received_readings.jsonl`.
- Настройка API через переменные окружения из `.env`.

## Структура репозитория (ДОРАБОТАТЬ КАК РЕПОЗИТОРИЙ В HOME ASSISTANT ДЛЯ ЗАГРУЗКИ ПОЛЬЗОВАТЕЛЯМИ)

```text
.
├── custom_components/
│   └── meter_receiver/
│       ├── __init__.py
│       ├── const.py
│       ├── http.py
│       └── manifest.json
├── local_api/
│   ├── server.py
│   ├── requirements.txt
│   ├── .env.example
│   └── .gitignore
├── home_assistant/
│   └── configuration.example.yaml
├── .gitignore
└── README.md
```

При установке в Home Assistant содержимое `custom_components/meter_receiver/` копируется в:

```text
/config/custom_components/meter_receiver/
```

Файл `home_assistant/configuration.example.yaml` содержит фрагменты, которые нужно добавить в основной файл:

```text
/config/configuration.yaml
```

## Формат показаний

Входной endpoint Home Assistant ожидает JSON:

```json
{
  "meter_id": "electricity_001",
  "name": "Квартира — электросчётчик",
  "energy_kwh": 1284.73,
  "power_w": 842
}
```

| Поле | Тип | Обязательное | Описание |
|---|---:|---:|---|
| `meter_id` | string | Да | Стабильный идентификатор прибора учёта |
| `name` | string | Нет | Отображаемое имя счётчика |
| `energy_kwh` | number | Нет | Накопленное потребление электроэнергии, кВт·ч |
| `power_w` | number | Нет | Текущая мощность, Вт |

Для `energy_kwh` следует передавать именно накопительное значение счётчика. Такое значение подходит для сенсора Home Assistant с `device_class: energy` и `state_class: total_increasing`.

## Local Meter API

Локальный API запускается на компьютере и принимает данные, которые custom component Home Assistant отправляет после получения показания.

### Требования

- Python 3.10 или выше.
- Home Assistant и компьютер с API находятся в одной локальной сети.
- Локальный TCP-порт API, по умолчанию `5001`, доступен из сети Home Assistant.

Проверка версии Python:

```bash
python3 --version
```

### Установка зависимостей

Перейдите в каталог API:

```bash
cd local_api
```

Создайте и активируйте виртуальное окружение.

**macOS / Linux (`zsh`, `bash`):**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell:**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Установите зависимости из файла проекта:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Настройка `.env`

Создайте локальный файл конфигурации на основе шаблона:

```bash
cp .env.example .env
```

На Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Откройте `.env` в редакторе и укажите нужные значения:

```dotenv
API_HOST=0.0.0.0
API_PORT=5001
DATA_FILE=received_readings.jsonl
API_KEY=replace-with-a-long-random-secret
```

Описание переменных:

| Переменная | Значение по умолчанию | Назначение |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Адрес, на котором слушает API. `0.0.0.0` нужен для доступа Home Assistant по LAN |
| `API_PORT` | `5001` | TCP-порт API |
| `DATA_FILE` | `received_readings.jsonl` | Путь к файлу с принятыми данными; относительный путь отсчитывается от `local_api` |
| `API_KEY` | Нет | Общий секрет для заголовка `X-API-Key` |

`.env` содержит секрет и не должен попадать в Git. В репозиторий добавляется только `.env.example` без настоящего ключа.

Сгенерировать случайный ключ на macOS/Linux:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

На Windows PowerShell:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Запуск

Из папки `local_api`, с активированным виртуальным окружением:

```bash
python server.py
```

Пример запуска:

```text
 * Serving Flask app 'server'
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5001
 * Running on http://...:5001
```

Используйте адрес вида `http://...:5001` в настройке компонента Home Assistant. Не используйте `127.0.0.1` или `localhost`: для Home Assistant это адрес самого HA, а не вашего компьютера.

Остановка API:

```text
Ctrl + C
```

### Health check

Пока API запущен, проверьте его с компьютера:

```bash
curl http://127.0.0.1:5001/health
```

Ожидаемый ответ:

```json
{
  "service": "local-meter-api",
  "status": "ok"
}
```

Проверьте также LAN-адрес компьютера:

```bash
curl http://...:5001/health
```

Если запрос к LAN-адресу не проходит, проверьте firewall и убедитесь, что используется фактический IP компьютера.

## Home Assistant component

### Установка

Скопируйте каталог компонента в конфигурационную папку Home Assistant:

```text
custom_components/meter_receiver/
```

→

```text
/config/custom_components/meter_receiver/
```

После копирования в целевой папке должна быть структура:

```text
/config/custom_components/meter_receiver/
├── __init__.py
├── const.py
├── http.py
└── manifest.json
```

### Конфигурация

Добавьте в `/config/configuration.yaml`:

```yaml
meter_receiver:
  forward_url: "http://...:5001/api/v1/readings"
  forward_api_key: "replace-with-the-same-api-key-from-local-api-env"
```

- Замените `...` на IPv4-адрес компьютера, где запущен Local Meter API.
- `forward_api_key` должен совпадать с `API_KEY` в `local_api/.env`.
- Если `forward_url` не задан, компонент примет показание и обновит сенсоры, но не будет выполнять пересылку.

Добавьте template sensors. Если ключ `template:` уже присутствует в `configuration.yaml`, добавьте только элемент списка ниже, не дублируйте ключ `template:`.

```yaml
template:
  - trigger:
      - platform: event
        event_type: meter_receiver_reading_received
    sensor:
      - name: "Электросчётчик — энергия"
        unique_id: meter_receiver_energy
        state: "{{ trigger.event.data.energy_kwh }}"
        unit_of_measurement: "kWh"
        device_class: energy
        state_class: total_increasing
        attributes:
          meter_id: "{{ trigger.event.data.meter_id }}"
          source_name: "{{ trigger.event.data.name }}"

      - name: "Электросчётчик — мощность"
        unique_id: meter_receiver_power
        state: "{{ trigger.event.data.power_w }}"
        unit_of_measurement: "W"
        device_class: power
        state_class: measurement
        attributes:
          meter_id: "{{ trigger.event.data.meter_id }}"
          source_name: "{{ trigger.event.data.name }}"
```

После изменения файлов:

1. В Home Assistant откройте **Developer Tools → YAML**.
2. Нажмите **Check configuration**.
3. Если проверка успешна, выполните **Restart Home Assistant**.

## Postman: полный тест

Перед тестом убедитесь, что:

- Local Meter API запущен на компьютере;
- Home Assistant перезапущен после установки компонента;
- `forward_url` и `forward_api_key` настроены;
- Home Assistant и API видят друг друга в LAN.

Создайте в Postman запрос:

| Поле | Значение |
|---|---|
| Method | `POST` |
| URL | `http://IP_HOME_ASSISTANT:PORT/api/meter_receiver/readings` |
| Header | `Content-Type: application/json` |

Пример URL для HA на стандартном порту:

```text
http://192.168.1.50:8123/api/meter_receiver/readings
```

Если пользовательский интерфейс HA открывается без `:8123`, используйте тот же адрес и порт, что в браузере.

В Postman: **Body → raw → JSON**:

```json
{
  "meter_id": "electricity_001",
  "name": "Квартира — электросчётчик",
  "energy_kwh": 1284.73,
  "power_w": 842
}
```

Успешный ответ от Home Assistant:

```json
{
  "status": "ok",
  "meter_id": "electricity_001",
  "received": {
    "meter_id": "electricity_001",
    "name": "Квартира — электросчётчик",
    "energy_kwh": 1284.73,
    "power_w": 842
  },
  "forward": {
    "status": "sent",
    "http_status": 201,
    "response": "{...}"
  }
}
```

## Проверка полученных данных

Успешная доставка подтверждается в трёх местах.

### Ответ Home Assistant в Postman

Проверьте:

```json
"forward": {
  "status": "sent",
  "http_status": 201
}
```

### Терминал Local Meter API

В окне, где запущен `python server.py`, появятся JSON и access log:

```text
"POST /api/v1/readings HTTP/1.1" 201 -
```

### Файл истории

Файл создаётся рядом с `server.py` либо в пути `DATA_FILE` из `.env`:

```text
local_api/received_readings.jsonl
```

Посмотреть последнюю запись:

```bash
tail -n 1 received_readings.jsonl
```

Файл использует JSON Lines: одна строка соответствует одному принятому показанию.

### Сущности Home Assistant

Откройте **Developer Tools → States** и найдите:

```text
Электросчётчик — энергия
Электросчётчик — мощность
```

Entity IDs обычно похожи на:

```text
sensor.elektroschetchik_energiya
sensor.elektroschetchik_moshchnost
```

## Диагностика

| Симптом | Возможная причина | Решение |
|---|---|---|
| `404 Not Found` при запросе в HA | Компонент не загрузился или endpoint не зарегистрирован | Проверьте путь `/config/custom_components/meter_receiver/`, блок `meter_receiver:` и перезапустите Home Assistant |
| `400 Invalid JSON payload` от HA | Нет `meter_id`, ID пустой, либо числовые поля не приводятся к числу | Передайте непустой строковый `meter_id`; используйте корректные числовые значения |
| `forward.status: skipped` | В YAML не указан `forward_url` | Добавьте `forward_url` и перезапустите HA |
| `forward.status: failed` | API не доступен, URL неверный, firewall блокирует порт или API key не совпадает | Убедитесь, что API запущен, проверьте `/health`, IP/порт и ключ |
| `401 Unauthorized` от local API | Неверный либо отсутствующий `X-API-Key` | Сверьте `API_KEY` в `.env` и `forward_api_key` в конфигурации HA |
| `zsh: command not found: .venv\\Scripts\\Activate.ps1` | Использована Windows-команда в macOS/Linux | Используйте `source .venv/bin/activate` |
| `ModuleNotFoundError: No module named 'flask'` | Flask не установлен в активном venv | Активируйте `.venv` и выполните `python -m pip install -r requirements.txt` |
| `Address already in use` | Порт API уже занят | Остановите процесс на этом порту или измените `API_PORT` и `forward_url` |
| Не создаётся `received_readings.jsonl` | Запрос не дошёл до API или API вернул ошибку | Проверьте ответ HA: ожидается `forward.status: sent` и `http_status: 201` |

## Следующие шаги

- Реализовать входную аутентификацию endpoint Home Assistant.
- Хранить секреты Home Assistant не в YAML, а в `secrets.yaml` или Config Entry.
- Добавить схему данных и валидацию полей через Pydantic.
- Перейти с JSONL на SQLite/PostgreSQL/TimescaleDB.
- Добавить очередь, retry и журналирование ошибок пересылки.
- Перевести integration на Config Flow и создавать отдельные entity для каждого `meter_id`.
