# Telegram Reminder Bot & Web Mini App

Полнофункциональный Telegram-бот для напоминаний с встроенным интерфейсом Web Mini App. Проект построен на **Python 3.12**, **aiogram 3.x**, **FastAPI**, **SQLite (режим WAL)**, **Docker Compose** и **Cloudflare Tunnel**.

## 🌟 Ключевые возможности

### 🤖 Интерфейс Telegram-бота

* **Удобный пошаговый мастер (FSM)**: Создание однократных и повторяющихся напоминаний с автоматической валидацией прошедшего времени.

* **Настройка часовых поясов**: Готовые пресеты (включая Камчатку `UTC+12`, Москву `UTC+3` и др.) или ввод произвольного смещения / IANA-зоны.

* **Интерактивные кнопки в сообщениях**: Возможность отложить (`⏳ Отложить`), отметить выполненным (`✅ Прочитано`) или удалить напоминание прямо из чата.

* **Защита от случайного удаления (Undo)**: Однократная отмена удаления с ограничением по времени (TTL 60 секунд) как в боте, так и в Mini App.

### 📱 Web Mini App (FastAPI Backend)

* **Современный веб-интерфейс**: Просмотр, поиск, фильтрация и управление напоминаниями прямо внутри Telegram.

* **Быстрый выбор времени**: Кнопки в один клик: «+15 мин», «+1 час», «Сегодня вечером» (до 19:00) и «Завтра утром».

* **Синхронизация с чатом в реальном времени (`tg_sync`)**: Действия в Mini App автоматически обновляют или удаляют соответствующие сообщения-уведомления в чате Telegram.

* **Безопасность**: Строгая политика Content Security Policy (CSP), изоляция CORS и валидация подписи `initData`.

### 🛡️ Архитектура и надёжность

* **Идемпотентная доставка**: Атомарные блокировки в БД предотвращают дублирование отправки уведомлений при параллельных тиках шедулера.

* **Двойная схема проксирование (Dual Proxy)**:

  * Основной бот работает через локальный WARP SOCKS5 прокси (`TELEGRAM_PROXY`).

  * Mini App API поддерживает прямое подключение (`WEBAPP_TELEGRAM_PROXY=direct`) или работу через прокси.

* **Безопасный доступ без открытых портов**: Веб-приложение изолировано внутри контейнера и публикуется наружу исключительно через Cloudflare Tunnel.

## 📁 Структура проекта

```
reminder_bot/
├── bot.py                  # Главный файл запуска бота (aiogram 3 polling / события)
├── config.py               # Конфигурация и считывание переменных окружения
├── database.py             # Асинхронный SQLite: инициализация, миграции и запросы
├── scheduler.py            # Движок проверки и рассылки уведомлений по расписанию
├── middlewares.py          # Middleware для aiogram (логирование, контекст, лимиты)
├── keyboards.py            # Генераторы Inline и Reply клавиатур
├── handlers/               # Обработчики команд (/start, /settings, FSM шаги)
├── webapp/                 # Пакет веб-приложения FastAPI Mini App
│   ├── app.py              # Инициализация FastAPI, роуты, CSP и статика
│   ├── tg_sync.py          # Асинхронная синхронизация с Telegram API
│   └── static/             # HTML, JS и CSS ресурсы веб-интерфейса
├── tests/                  # Набор модульных и интеграционных тестов
│   └── test_review_fixes.py# Автотесты идемпотентности, FSM, отмены и FastAPI
├── docker-compose.yml      # Оркестрация контейнеров Mini App и Cloudflare Tunnel
├── reminder_bot.service    # Unit-файл systemd для фоновой службы бота
└── .env.example            # Шаблон переменных окружения
```

## ⚙️ Переменные окружения

Создайте или обновите файл `/opt/reminder_bot/.env` на основе шаблона `.env.example`:

```env
# Конфигурация Telegram Bot
BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ
WEBAPP_URL=https://reminder.litvinov.uk

# Пользователь и группы системных прав
APP_UID=1001
APP_GID=1001

# Сетевые настройки и прокси
TELEGRAM_PROXY=socks5://127.0.0.1:49000
WEBAPP_TELEGRAM_PROXY=direct

# Токен Cloudflare Tunnel
CLOUDFLARE_TUNNEL_TOKEN=eyJh...
```

## 🚀 Развёртывание и управление

Проект использует гибридную схему развёртывания:

1. **Основной процесс бота**: Запускается как служба Systemd (`reminder_bot.service`) на хосте.

2. **Mini App и Tunnel**: Запускаются в изоляции через Docker Compose (контейнеры `reminder_app` и `tunnel`).

### Управление службой Systemd (Основной бот)

```bash
# Проверка статуса службы
sudo systemctl status reminder_bot.service

# Перезапуск бота
sudo systemctl restart reminder_bot.service

# Просмотр логов в реальном времени
sudo journalctl -u reminder_bot.service -f -n 50
```

### Управление Docker Compose (Mini App и Cloudflare Tunnel)

```bash
cd /opt/reminder_bot

# Сборка и запуск контейнеров в фоновом режиме
sudo docker compose up -d --build

# Проверка статуса контейнеров
sudo docker compose ps

# Просмотр логов Mini App и Cloudflare Tunnel
sudo docker compose logs -f --tail=50 reminder_app tunnel
```

## 🧪 Тестирование и проверка

### Прогон автотестов бота (в окружении venv)

```bash
cd /opt/reminder_bot
sudo -u reminder_bot_user /opt/reminder_bot/venv/bin/python -m unittest discover -s tests -v
```

### Прогон автотестов WebApp / FastAPI (внутри Docker-контейнера)

```bash
cd /opt/reminder_bot
sudo docker compose exec reminder_app python -m unittest tests.test_review_fixes.ReviewFixesAsyncTests.test_p1_5_patch_invalid_text_does_not_mutate_datetime -v
```

### Проверка работоспособности эндпоинтов

```bash
# Проверка эндпоинта healthcheck Mini App
curl -i https://reminder.litvinov.uk/health

# Проверка прямого доступа к Telegram API из контейнера Mini App
sudo docker compose exec reminder_app python -c "import urllib.request; print(urllib.request.urlopen('https://api.telegram.org', timeout=5).status)"
```

## 📄 Лицензия

Внутренняя сервисная утилита. Все права защищены.