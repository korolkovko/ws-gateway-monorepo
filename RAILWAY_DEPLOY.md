# Railway Deployment Guide

## Быстрый старт

### 1. Подготовка

Убедитесь что код запушен на GitHub:
```bash
git push origin main
```

### 2. Создание проекта на Railway

1. Перейди на [railway.app](https://railway.app/)
2. Login через GitHub
3. Click "New Project"
4. Choose "Deploy from GitHub repo"
5. Select `korolkovko/ws-gateway-monorepo`

### 3. Настройка проекта

После создания проекта:

1. **Выбери root directory:**
   - Settings → Root Directory: `server`
   - Это важно! Иначе Railway не найдет Procfile

2. **Добавь Redis:**
   - Click "New" → "Database" → "Add Redis"
   - Railway автоматически создаст `REDIS_URL` переменную

3. **Настрой переменные окружения:**
   - Settings → Variables
   - Add Variable:

```bash
# Telegram Bot (обязательно)
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_ADMIN_IDS=your_telegram_id

# JWT Secret (обязательно)
JWT_SECRET=your_random_secret_min_32_chars

# Optional
LOG_LEVEL=INFO
KIOSK_RESPONSE_TIMEOUT=45
ALLOW_DUPLICATE_CONNECTIONS=false

# Grafana Cloud (опционально)
GRAFANA_PROMETHEUS_URL=https://...
GRAFANA_PROMETHEUS_USERNAME=...
GRAFANA_PROMETHEUS_PASSWORD=...
```

### 4. Deploy!

Railway автоматически задеплоит при push в main.

Или вручную:
- Settings → Deployments → "Deploy Now"

### 5. Получи публичный URL

1. Settings → Networking
2. Click "Generate Domain"
3. Скопируй URL (например: `https://ws-gateway-production.up.railway.app`)

### 6. Проверка

```bash
# Health check
curl https://your-url.railway.app/health

# Dashboard
open https://your-url.railway.app/dashboard
```

## Переменные окружения

### Обязательные

| Переменная | Описание | Пример |
|------------|----------|--------|
| `TELEGRAM_BOT_TOKEN` | Токен от @BotFather | `123456:ABC-DEF...` |
| `TELEGRAM_ADMIN_IDS` | Telegram ID админов (через запятую) | `123456789,987654321` |
| `JWT_SECRET` | Секретный ключ для JWT (32+ символов) | `your_super_secret_key_here_min_32_chars` |
| `REDIS_URL` | Redis connection string | `redis://...` (автоматически от addon) |

### Опциональные

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `KIOSK_RESPONSE_TIMEOUT` | `45` | Таймаут ответа киоска (секунды) |
| `ALLOW_DUPLICATE_CONNECTIONS` | `false` | Разрешить дубликаты подключений |
| `WS_HOST` | `0.0.0.0` | WebSocket host |
| `PORT` | `8000` | Railway автоматически |

## Как получить Telegram Bot Token

1. Открой [@BotFather](https://t.me/botfather)
2. Отправь `/newbot`
3. Следуй инструкциям
4. Скопируй токен

## Как узнать свой Telegram ID

1. Открой [@userinfobot](https://t.me/userinfobot)
2. Отправь любое сообщение
3. Скопируй свой ID

## Мониторинг

### Логи

Railway Dashboard → Deployments → View Logs

### Метрики

```bash
curl https://your-url.railway.app/metrics
```

### Dashboard

```
https://your-url.railway.app/dashboard
```

## Auto-deploy при push

Railway автоматически деплоит при push в `main`:

```bash
git add .
git commit -m "Update server"
git push
# Railway автоматически задеплоит!
```

## Troubleshooting

### Build fails

Проверь:
- Root Directory = `server`
- `requirements.txt` существует
- Python version в `runtime.txt` (необязательно)

### Redis не подключается

Railway addon автоматически добавляет `REDIS_URL`.
Проверь в Settings → Variables

### Telegram бот не работает

1. Проверь `TELEGRAM_BOT_TOKEN`
2. Проверь `TELEGRAM_ADMIN_IDS`
3. Отправь `/start` боту

### Киоски не подключаются

1. Проверь что домен сгенерирован (Settings → Networking)
2. URL должен быть `wss://...` (с SSL)
3. Проверь JWT токен

## Стоимость

- Railway: ~$5/месяц с Redis addon
- Free tier: 500 часов/месяц (достаточно для тестирования)

## Следующие шаги

После успешного деплоя:

1. Открой бота в Telegram
2. Отправь `/start`
3. Создай киоск: `/add_kiosk kiosk_001 Test Kiosk`
4. Скопируй JWT токен
5. Настрой клиента на киоске
6. Проверь подключение: `/list_kiosks`

## Rollback

Если что-то пошло не так:

Railway Dashboard → Deployments → Previous Deployment → "Redeploy"

---

**Готово!** Сервер задеплоен и работает! 🚀
