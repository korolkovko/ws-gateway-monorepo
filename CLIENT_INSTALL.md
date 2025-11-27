# Установка WebSocket клиента на Linux

## Вариант 1: Тестовая установка (без автозапуска)

Для быстрого тестирования и разработки.

### Шаг 1: Установка зависимостей

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip python3-venv

# CentOS/RHEL
sudo yum install python3 python3-pip
```

### Шаг 2: Создание виртуального окружения

```bash
# Создай директорию для проекта
mkdir -p ~/ws-client-test
cd ~/ws-client-test

# Создай виртуальное окружение
python3 -m venv venv
source venv/bin/activate
```

### Шаг 3: Установка wheel

**Вариант A: Из GitHub Release**
```bash
# Скачай wheel из релиза
wget https://github.com/korolkovko/ws-gateway-monorepo/releases/download/v1.0.2/ws_client-1.0.2-py3-none-any.whl

# Установи
pip install ws_client-1.0.2-py3-none-any.whl
```

**Вариант B: Из локального файла**
```bash
# Скопируй wheel на сервер и установи
pip install /path/to/ws_client-1.0.2-py3-none-any.whl
```

### Шаг 4: Настройка конфигурации

```bash
# Создай .env файл
cat > .env << 'EOF'
WS_SERVER_URL=wss://your-server.railway.app/ws
WS_TOKEN=your_jwt_token_here
LOG_LEVEL=INFO
HEALTH_CHECK_PORT=9091
EOF

# Создай routing_config.yaml
cat > routing_config.yaml << 'EOF'
routes:
  payment:
    url: "http://127.0.0.1:8011/api/v1/dcpayment/payment"
    timeout: 35
  fiscal:
    url: "http://127.0.0.1:8011/api/v1/fiscal"
    timeout: 35
  kds:
    url: "http://127.0.0.1:8012/api/v1/kds"
    timeout: 30
  print:
    url: "http://127.0.0.1:8013/api/v1/print"
    timeout: 20
EOF
```

### Шаг 5: Запуск

```bash
# Убедись что venv активирован
source venv/bin/activate

# Запусти клиента
python -m ws_client

# Или используй прямую команду
ws-client
```

### Остановка

```bash
# Нажми Ctrl+C в терминале где запущен клиент
```

---

## Вариант 2: Продакшн установка (с автозапуском)

Для production-окружения с systemd service.

### Шаг 1: Установка зависимостей

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip

# CentOS/RHEL
sudo yum install python3 python3-pip
```

### Шаг 2: Создание пользователя для сервиса

```bash
# Создай системного пользователя
sudo useradd -r -s /bin/false -M -d /opt/ws-client kiosk
```

### Шаг 3: Установка wheel глобально

```bash
# Скачай wheel
cd /tmp
wget https://github.com/korolkovko/ws-gateway-monorepo/releases/download/v1.0.2/ws_client-1.0.2-py3-none-any.whl

# Установи глобально (для всех пользователей)
sudo pip3 install ws_client-1.0.2-py3-none-any.whl
```

### Шаг 4: Создание директорий

```bash
# Директории для конфигов и логов
sudo mkdir -p /etc/ws-client
sudo mkdir -p /var/log/ws-client
sudo mkdir -p /opt/ws-client

# Установи владельца
sudo chown kiosk:kiosk /var/log/ws-client
sudo chown kiosk:kiosk /opt/ws-client
```

### Шаг 5: Настройка конфигурации

```bash
# Создай .env файл
sudo tee /etc/ws-client/.env > /dev/null << 'EOF'
WS_SERVER_URL=wss://your-server.railway.app/ws
WS_TOKEN=your_jwt_token_here
LOG_LEVEL=INFO
HEALTH_CHECK_PORT=9091
EOF

# Создай routing_config.yaml
sudo tee /etc/ws-client/routing_config.yaml > /dev/null << 'EOF'
routes:
  payment:
    url: "http://127.0.0.1:8011/api/v1/dcpayment/payment"
    timeout: 35
  fiscal:
    url: "http://127.0.0.1:8011/api/v1/fiscal"
    timeout: 35
  kds:
    url: "http://127.0.0.1:8012/api/v1/kds"
    timeout: 30
  print:
    url: "http://127.0.0.1:8013/api/v1/print"
    timeout: 20
EOF

# Установи права доступа
sudo chmod 600 /etc/ws-client/.env
sudo chown kiosk:kiosk /etc/ws-client/.env
```

### Шаг 6: Создание systemd service

```bash
# Создай service файл
sudo tee /etc/systemd/system/ws-client.service > /dev/null << 'EOF'
[Unit]
Description=WebSocket Payment Gateway Client
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=kiosk
Group=kiosk
WorkingDirectory=/opt/ws-client

# Environment files
EnvironmentFile=/etc/ws-client/.env

# Start command
ExecStart=/usr/local/bin/ws-client

# Restart policy
Restart=always
RestartSec=10
StartLimitInterval=0

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/ws-client

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ws-client

[Install]
WantedBy=multi-user.target
EOF
```

### Шаг 7: Запуск сервиса

```bash
# Перезагрузи systemd
sudo systemctl daemon-reload

# Включи автозапуск
sudo systemctl enable ws-client

# Запусти сервис
sudo systemctl start ws-client

# Проверь статус
sudo systemctl status ws-client
```

### Управление сервисом

```bash
# Проверить статус
sudo systemctl status ws-client

# Посмотреть логи
sudo journalctl -u ws-client -f

# Посмотреть последние 100 строк
sudo journalctl -u ws-client -n 100

# Перезапустить
sudo systemctl restart ws-client

# Остановить
sudo systemctl stop ws-client

# Отключить автозапуск
sudo systemctl disable ws-client
```

---

## Автоматическая установка (Production)

Используй готовый скрипт установки:

```bash
# Скачай wheel и install.sh из репозитория
cd /tmp
wget https://github.com/korolkovko/ws-gateway-monorepo/releases/download/v1.0.2/ws_client-1.0.2-py3-none-any.whl
wget https://raw.githubusercontent.com/korolkovko/ws-gateway-monorepo/main/client/install.sh

# Сделай скрипт исполняемым
chmod +x install.sh

# Запусти установку
sudo ./install.sh

# Настрой конфигурацию
sudo nano /etc/ws-client/.env
sudo nano /etc/ws-client/routing_config.yaml

# Запусти сервис
sudo systemctl start ws-client
sudo systemctl enable ws-client
```

---

## Получение JWT токена

После деплоя сервера на Railway:

1. **Открой Telegram бота**
2. **Отправь `/start`**
3. **Создай киоск:**
   ```
   /add_kiosk kiosk_001 Тестовый киоск
   ```
4. **Скопируй JWT токен** из ответа бота
5. **Добавь токен в `.env`:**
   ```bash
   WS_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```

---

## Проверка работы

### 1. Проверка подключения

```bash
# Проверь логи клиента
sudo journalctl -u ws-client -f

# Должен увидеть:
# "websocket_connected"
# "kiosk_authenticated"
```

### 2. Проверка в Telegram боте

```
/list_kiosks
```

Киоск должен быть в статусе `connected`.

### 3. Тестовый запрос

```bash
# С сервера отправь тестовый запрос
curl -X POST https://your-server.railway.app/send \
  -H "Header-Kiosk-Id: kiosk_001" \
  -H "Header-Operation-Type: payment" \
  -H "Content-Type: application/json" \
  -d '{"order_id": 123, "sum": 1000}'
```

---

## Обновление клиента

### Тестовая установка

```bash
cd ~/ws-client-test
source venv/bin/activate

# Скачай новую версию
wget https://github.com/korolkovko/ws-gateway-monorepo/releases/download/v1.0.3/ws_client-1.0.3-py3-none-any.whl

# Обнови
pip install --upgrade ws_client-1.0.3-py3-none-any.whl

# Перезапусти (Ctrl+C и снова python -m ws_client)
```

### Production установка

```bash
# Скачай новую версию
cd /tmp
wget https://github.com/korolkovko/ws-gateway-monorepo/releases/download/v1.0.3/ws_client-1.0.3-py3-none-any.whl

# Обнови
sudo pip3 install --upgrade ws_client-1.0.3-py3-none-any.whl

# Перезапусти сервис
sudo systemctl restart ws-client

# Проверь статус
sudo systemctl status ws-client
```

---

## Удаление

### Тестовая установка

```bash
cd ~/ws-client-test
source venv/bin/activate
pip uninstall ws-client -y
cd ..
rm -rf ws-client-test
```

### Production установка

```bash
# Останови и отключи сервис
sudo systemctl stop ws-client
sudo systemctl disable ws-client

# Удали service файл
sudo rm /etc/systemd/system/ws-client.service
sudo systemctl daemon-reload

# Удали конфиги и логи
sudo rm -rf /etc/ws-client
sudo rm -rf /var/log/ws-client
sudo rm -rf /opt/ws-client

# Удали wheel
sudo pip3 uninstall ws-client -y

# Удали пользователя (опционально)
sudo userdel kiosk
```

---

## Troubleshooting

### Клиент не подключается

1. **Проверь URL сервера:**
   ```bash
   grep WS_SERVER_URL /etc/ws-client/.env
   # Должно быть wss:// (не ws://)
   ```

2. **Проверь токен:**
   ```bash
   grep WS_TOKEN /etc/ws-client/.env
   # Токен должен быть валидным JWT
   ```

3. **Проверь сеть:**
   ```bash
   ping your-server.railway.app
   curl https://your-server.railway.app/health
   ```

### Ошибка "Operation not found in routing config"

Добавь отсутствующий route в `/etc/ws-client/routing_config.yaml`:

```yaml
routes:
  new_operation:
    url: "http://127.0.0.1:8080/api/endpoint"
    timeout: 30
```

Перезапусти:
```bash
sudo systemctl restart ws-client
```

### Высокое потребление CPU/памяти

Проверь метрики:
```bash
systemctl status ws-client
top -p $(pgrep -f ws-client)
```

Проверь логи на ошибки:
```bash
sudo journalctl -u ws-client --since "1 hour ago"
```

---

## Логирование

### Уровни логирования

В `.env` можно установить:
```bash
LOG_LEVEL=DEBUG   # Подробные логи (разработка)
LOG_LEVEL=INFO    # Нормальные логи (по умолчанию)
LOG_LEVEL=WARNING # Только предупреждения
LOG_LEVEL=ERROR   # Только ошибки
```

### Просмотр логов

```bash
# Все логи
sudo journalctl -u ws-client

# С фильтром по времени
sudo journalctl -u ws-client --since today
sudo journalctl -u ws-client --since "2024-01-15 10:00"

# Follow mode (в реальном времени)
sudo journalctl -u ws-client -f

# Последние N строк
sudo journalctl -u ws-client -n 50

# Экспорт логов
sudo journalctl -u ws-client > ws-client.log
```

---

**Готово!** Клиент установлен и работает! 🚀

Для получения помощи: https://github.com/korolkovko/ws-gateway-monorepo/issues
