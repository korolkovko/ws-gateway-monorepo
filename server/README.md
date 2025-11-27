# WebSocket Payment Gateway Server

FastAPI WebSocket сервер для подключения киосков к облачному бэкенду через Railway.

## Особенности

- WebSocket сервер с автоматическим переподключением
- JWT аутентификация
- Redis для хранения состояния киосков
- Telegram бот для управления
- Prometheus метрики + Grafana Cloud
- Structured logging (JSON)

## Требования

- Python 3.11+
- Redis
- Telegram Bot Token

## Локальная разработка

```bash
# Установка зависимостей
pip install -r requirements.txt

# Настройка .env
cp .env.example .env
nano .env

# Запуск Redis (если локально)
docker run -d -p 6379:6379 redis:7-alpine

# Запуск сервера
python main.py
```

Сервер запустится на `http://localhost:8000`

## Deployment на Railway

### Быстрый старт

1. Fork этот репозиторий
2. Создай проект на [Railway](https://railway.app)
3. Подключи GitHub репозиторий
4. Добавь Redis addon
5. Настрой переменные окружения
6. Deploy!

### Переменные окружения

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_IDS=123456789,987654321

# JWT
JWT_SECRET=your_secret_key_here

# Redis (автоматически от Railway addon)
REDIS_URL=redis://...

# Optional
LOG_LEVEL=INFO
KIOSK_RESPONSE_TIMEOUT=45
```

### Railway Config

Railway автоматически определит:
- `Procfile` - команду запуска
- `requirements.txt` - зависимости
- `runtime.txt` - версию Python

## API Endpoints

### POST /send
Отправить сообщение киоску

**Headers:**
```
Header-Kiosk-Id: kiosk_001
Header-Operation-Type: payment
Header-Http-Method: POST  # optional, default POST
```

**Body:**
```json
{
  "order_id": 12345,
  "sum": 1000
}
```

**Response:**
```json
{
  "status": "success",
  "transaction_id": "TXN123"
}
```

### GET /health
Health check

```json
{
  "status": "healthy",
  "redis": "connected",
  "active_kiosks": 3,
  "total_kiosks": 10
}
```

### GET /metrics
Prometheus метрики

### GET /dashboard
Web dashboard с real-time метриками

### WebSocket /ws?token=JWT
WebSocket endpoint для клиентов

## Telegram Bot Commands

- `/start` - Приветствие
- `/add_kiosk <id> [name]` - Добавить киоск
- `/list_kiosks` - Список киосков
- `/status` - Статус сервера
- `/regenerate_token <id>` - Новый токен
- `/enable_kiosk <id>` - Включить киоск
- `/disable_kiosk <id>` - Выключить киоск
- `/remove_kiosk <id>` - Удалить киоск

## Мониторинг

### Grafana Cloud

1. Создай аккаунт на [grafana.com](https://grafana.com/)
2. Настрой Prometheus data source
3. Добавь переменные:
   ```
   GRAFANA_PROMETHEUS_URL=...
   GRAFANA_PROMETHEUS_USERNAME=...
   GRAFANA_PROMETHEUS_PASSWORD=...
   ```

### UptimeRobot

1. Создай монитор для `/health`
2. Настрой уведомления

## Структура

```
server/
├── src/
│   ├── api/              # HTTP endpoints
│   ├── auth/             # JWT handling
│   ├── config/           # Settings
│   ├── monitoring/       # Metrics
│   ├── redis_client/     # Redis ops
│   ├── telegram_bot/     # Telegram
│   └── websocket/        # WebSocket server
├── main.py              # Entry point
├── requirements.txt
├── .env.example
└── Procfile
```

## Changelog

### v1.0.0
- ✅ UUID request_id для correlation
- ✅ Поддержка параллельных запросов
- ✅ Улучшенный matching ответов
- ✅ Structured logging

## Troubleshooting

### Redis не подключается

Проверь `REDIS_URL` в переменных окружения

### Telegram бот не отвечает

1. Проверь `TELEGRAM_BOT_TOKEN`
2. Проверь `TELEGRAM_ADMIN_IDS`
3. Убедись что бот запущен

### Киоск не подключается

1. Проверь JWT токен
2. Убедись что киоск enabled
3. Проверь WebSocket URL

## License

Proprietary
