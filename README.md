# WebSocket Payment Gateway - Monorepo

Простой и надежный WebSocket транспорт для подключения локальных платежных шлюзов киосков к облачному бэкенду.

## Архитектура

```
Backend (FastAPI) → Server (Railway) ←WebSocket→ Client (Kiosk) → Payment Gateway
                         ↓                              ↓
                      Redis DB                    Local Hardware
```

### Компоненты

- **Server** ([server/](server/)) - WebSocket сервер на Railway с Telegram управлением
- **Client** ([client/](client/)) - Python клиент на киосках

⚠️ **Внимание:** Директории `proxy-client/` и `docs/` содержат устаревший код и документацию. Используйте актуальные `client/` и документацию в корне репозитория.

## Ключевые особенности v1.0.2

### Улучшения архитектуры

✅ **Request/Response Correlation**
- UUID для каждого запроса
- Поддержка параллельных запросов
- Точное сопоставление ответов

✅ **HTTP Method Flexibility**
- Поддержка GET и POST запросов
- Метод передается через `Header-Http-Method`
- Автоматическая конвертация body → query params для GET

✅ **Production Ready**
- Wheel packaging для легкой установки
- systemd service с автозапуском
- Health check endpoints с версией
- Настраиваемый порт health check (по умолчанию 9091)
- Ротация логов

✅ **Telegram Logging (Server)**
- HTML-форматирование с моноширинным JSON
- Отображение HTTP методов (GET/POST)
- Краткая сводка ключевых полей + полный JSON
- Автоматическая группировка запросов/ответов

### Упрощенная установка

- Установка одной командой через wheel
- Конфигурация через файлы (не в коде)
- Автозапуск при перезагрузке системы

## Быстрый старт

### Сервер (Railway)

```bash
cd server/
pip install -r requirements.txt
python main.py
```

См. [server/README.md](server/README.md) для деталей.

### Клиент (Kiosk)

#### Сборка wheel

```bash
cd client/
pip install build
python -m build
# Получаете: dist/ws_client-1.0.2-py3-none-any.whl
```

#### Установка на киоске

```bash
# Скопируйте wheel на киоск
scp dist/ws_client-1.0.2-py3-none-any.whl kiosk@kiosk-ip:/tmp/

# На киоске:
cd /tmp
sudo ./install.sh

# Настройте:
sudo nano /etc/ws-client/.env
sudo nano /etc/ws-client/routing_config.yaml

# Запустите:
sudo systemctl start ws-client
sudo systemctl enable ws-client
```

См. [client/README.md](client/README.md) для деталей.

## Формат сообщений

### Backend → Server

```http
POST /send
Header-Kiosk-Id: kiosk_001
Header-Operation-Type: payment
Header-Http-Method: POST  # или GET
{
  "order_id": 12345,
  "sum": 1000
}
```

### Server → Client (WebSocket)

```json
{
  "request_id": "uuid-here",
  "headers": {
    "header-kiosk-id": "kiosk_001",
    "header-operation-type": "payment",
    "header-http-method": "POST"
  },
  "body": {
    "order_id": 12345,
    "sum": 1000
  }
}
```

### Client → Gateway

**POST:**
```http
POST http://localhost:8011/api/v1/payment
{
  "order_id": 12345,
  "sum": 1000
}
```

**GET (автоматическая конвертация):**
```http
GET http://localhost:8011/api/v1/fiscal?check_id=123&status=pending
```

### Gateway → Client → Server → Backend

```json
{
  "request_id": "uuid-here",
  "status": "success",
  "transaction_id": "TXN123",
  ...
}
```

**Важно:** `request_id` НЕ передается в Gateway - только между Server ↔ Client.

## Конфигурация клиента

### .env

```bash
WS_SERVER_URL=wss://your-server.railway.app/ws
WS_TOKEN=your_jwt_token_here
LOG_LEVEL=INFO
HEALTH_CHECK_PORT=9091
```

### routing_config.yaml

```yaml
routes:
  payment:
    url: "http://127.0.0.1:8011/api/v1/payment"
    timeout: 35

  fiscal:
    url: "http://127.0.0.1:8011/api/v1/fiscal"
    timeout: 35
    # HTTP метод берется из Header-Http-Method

default:
  url: "http://127.0.0.1:8080"
  timeout: 30
```

## Мониторинг

### Health Checks

**Server:**
```bash
curl https://your-server.railway.app/health
```

**Client:**
```bash
curl http://localhost:9091/health
# Response includes client version:
# {
#   "status": "healthy",
#   "version": "1.0.2",
#   "ws_connected": true,
#   ...
# }
```

### Логи

**Server (Railway):**
```bash
# Railway Dashboard → Logs
```

**Client (systemd):**
```bash
# journalctl
sudo journalctl -u ws-client -f

# Файлы
sudo tail -f /var/log/ws-client/proxy_*.log
```

### Dashboard

```
https://your-server.railway.app/dashboard
```

## Разработка

### Требования

- Python 3.11+
- Redis (для сервера)
- Telegram Bot Token (для сервера)

### Структура

```
ws-monorepo/
├── server/              # WebSocket сервер
│   ├── src/
│   ├── main.py
│   ├── requirements.txt
│   └── README.md
│
├── client/              # Proxy клиент
│   ├── src/
│   │   └── ws_client/
│   ├── pyproject.toml
│   ├── install.sh
│   └── README.md
│
├── RAILWAY_DEPLOY.md    # Деплой на Railway
├── CLIENT_INSTALL.md    # Установка клиента
├── .github/
│   └── workflows/       # GitHub Actions
│
├── proxy-client/        # ⚠️ DEPRECATED - старый клиент
└── docs/                # ⚠️ DEPRECATED - старая документация
```

### Сборка клиента

```bash
cd client/
python -m build
# dist/ws_client-1.0.2-py3-none-any.whl
```

### Тестирование

```bash
# Установка в dev режиме
cd client/
pip install -e ".[dev]"

# Запуск
python -m ws_client
```

## Production Deployment

### Server (Railway)

1. Push to GitHub
2. Connect to Railway
3. Add Redis addon
4. Set environment variables
5. Deploy

См. [docs/railway_deployment.md](docs/railway_deployment.md)

### Client (Kiosks)

1. Собрать wheel
2. Скопировать на киоски
3. Запустить `install.sh`
4. Настроить конфиги
5. Включить service

См. [client/README.md](client/README.md)

## Обновление

### Server

```bash
git push  # Railway auto-deploy
```

### Client

```bash
# Собрать новый wheel
cd client/
python -m build

# На киоске:
pip install --upgrade ws_client-1.0.1-py3-none-any.whl
sudo systemctl restart ws-client
```

## Безопасность

- WSS (WebSocket Secure)
- JWT аутентификация
- Telegram admin-only управление
- Никаких секретов в коде

## Стабильность

- Автоматическое переподключение (exponential backoff)
- Offline queue (10 сообщений)
- Health checks
- Systemd auto-restart
- Connection pooling
- Ротация логов

## Простота

- Минимум логики (простой транспорт)
- Гибкий роутинг через YAML
- Wheel packaging
- Одна команда для установки

## Changelog

### v1.0.2 (2025-11-27)

**Features:**
- ✅ Версия клиента в health check endpoint
- ✅ Улучшенное Telegram логирование с HTML-форматированием
- ✅ Моноширинный JSON в Telegram сообщениях
- ✅ Отображение HTTP метода в Telegram логах

**Improvements:**
- 🚀 GitHub Actions автоматически собирает wheel при релизе

### v1.0.1 (2025-11-27)

**Features:**
- ✅ Настраиваемый порт health check через HEALTH_CHECK_PORT
- ✅ Изменен порт по умолчанию с 9090 на 9091

**Fixes:**
- 🐛 Исправлены права доступа для GitHub Actions

### v1.0.0 (2025-01-XX)

**Breaking Changes:**
- Новая структура монорепо
- Wheel packaging вместо git clone
- Request/response correlation через UUID

**Features:**
- ✅ Поддержка GET запросов
- ✅ Header-Http-Method для выбора метода
- ✅ Автоматическая конвертация body → query params
- ✅ Request ID для параллельных запросов
- ✅ Wheel packaging
- ✅ systemd service
- ✅ Install script

**Improvements:**
- 🚀 Правильный matching ответов
- 🚀 Поддержка параллельных запросов
- 🚀 Упрощенная установка
- 🚀 Профессиональный deployment

## Лицензия

Proprietary - All rights reserved

## Поддержка

При проблемах:
1. Проверьте логи
2. Health check endpoints
3. Конфигурацию
4. Связь с командой

---

**Сделано с ❤️ для стабильной работы киосков**
