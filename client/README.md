# WebSocket Proxy Client

WebSocket клиент для подключения локальных платежных шлюзов к облачному серверу.

## Установка

### Из wheel файла

```bash
pip install ws_client-1.0.0-py3-none-any.whl
```

### Из исходников (для разработки)

```bash
cd client
pip install -e .
```

## Использование

### Запуск

```bash
# Как команда (после установки wheel):
ws-client

# Как Python модуль:
python -m ws_client
```

### Конфигурация

Создайте файл `.env`:

```bash
# WebSocket сервер
WS_SERVER_URL=wss://your-server.railway.app/ws
WS_TOKEN=your_jwt_token_here

# Логирование
LOG_LEVEL=INFO
```

Создайте файл `routing_config.yaml`:

```yaml
routes:
  payment:
    url: "http://127.0.0.1:8011/api/v1/payment"
    method: POST
    timeout: 35

  fiscal:
    url: "http://127.0.0.1:8011/api/v1/fiscal"
    timeout: 35  # метод берется из Header-Http-Method

default:
  url: "http://127.0.0.1:8080"
  timeout: 30
```

## Установка как systemd service

```bash
# 1. Установить wheel
sudo pip install ws_client-1.0.0-py3-none-any.whl

# 2. Создать конфигурационные директории
sudo mkdir -p /etc/ws-client
sudo mkdir -p /var/log/ws-client

# 3. Скопировать конфиги
sudo cp .env /etc/ws-client/
sudo cp routing_config.yaml /etc/ws-client/

# 4. Создать systemd service
sudo cp ws-client.service /etc/systemd/system/

# 5. Запустить
sudo systemctl daemon-reload
sudo systemctl enable ws-client
sudo systemctl start ws-client

# 6. Проверить статус
sudo systemctl status ws-client

# 7. Просмотр логов
sudo journalctl -u ws-client -f
```

## Сборка wheel

```bash
cd client
pip install build
python -m build

# Wheel файл будет в dist/
ls dist/
# ws_client-1.0.0-py3-none-any.whl
```

## Health Check

Клиент запускает HTTP сервер на `localhost:9090`:

```bash
curl http://localhost:9090/health
```

Ответ:
```json
{
  "status": "healthy",
  "ws_connected": true,
  "uptime_seconds": 12345.67,
  "stats": {
    "messages_received": 100,
    "messages_sent": 100,
    "errors": 0,
    "reconnections": 1
  },
  "queue_size": 0,
  "routes_configured": 4
}
```

## Разработка

```bash
# Установка в dev режиме
cd client
pip install -e ".[dev]"

# Тесты
pytest

# Форматирование
black src/
ruff check src/
```
