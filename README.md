# 🎛 Reminder Telegram Bot — «Напоминалкин» (Single-Message UI + Telegram Mini App)

Асинхронный Telegram-бот для управления персональными разовыми и повторяющимися напоминаниями с двуязычным интерфейсом (**RUS / ENG**), работающий в двух синхронизированных режимах поверх единой базы данных SQLite:

1. **Чат-режим (Single-Message UI — «Одноэкранный пульт»)** — работает как служба `systemd` (`reminder_bot.service`), не требует открытия входящих портов и поддерживает выход к Telegram API через локальный прокси (`TELEGRAM_PROXY`).
2. **Telegram Mini App** — адаптивный веб-интерфейс (FastAPI + нативный JS/CSS под тему Telegram), развёрнутый в Docker Compose и опубликованный по HTTPS через **Cloudflare Tunnel**.

---

## ⚙️ Технологический стек

* **Python 3.12+**
* **aiogram 3.x** (Telegram Bot API, FSM, Inline-клавиатуры, пакетное удаление сообщений, HTML-разметка, персональная кнопка `MenuButtonWebApp`)
* **aiohttp + aiohttp-socks** (асинхронные запросы к Telegram API в чат-боте и Mini App с независимой маршрутизацией через `TELEGRAM_PROXY` и `WEBAPP_TELEGRAM_PROXY`)
* **FastAPI + Uvicorn** (REST API, CSP-заголовки, автоверсионирование статики `?v=<hash>` и `/health`)
* **SQLAlchemy 2.0 (Async) + greenlet + aiosqlite** (единая SQLite БД, `NullPool`, `PRAGMA journal_mode = WAL`, `PRAGMA cache_size = -2000`, `PRAGMA busy_timeout = 5000`)
* **Docker Compose + `cloudflare/cloudflared`** (изолированный запуск Mini App и публикация по HTTPS без локального reverse proxy и SSL-сертификатов)
* **python-dotenv** (загрузка конфигурации из `.env`)

---

## 🧠 Ключевые возможности

### 1. Двуязычный интерфейс (RUS / ENG) и 24-часовой формат
* **Автоопределение языка:** при первом обращении нового пользователя в чат-бот или Mini App язык интерфейса определяется автоматически по его `language_code` в Telegram (`ru*` → Русский, остальные → English, при отсутствии кода → Русский) и сохраняется в таблице `user_settings.language`.
* **Переключение в настройках:** в разделе **«⚙️ Настройки»** (`/settings` → «🌐 Язык / Language») и на вкладке **«Настройки»** в Mini App можно в любой момент переключить язык (`🇷🇺 Русский` / `🇬🇧 English`). Смена языка мгновенно синхронизируется между чат-ботом, Mini App и описаниями slash-команд Telegram (`/start`, `/reminders`, `/notifications`, `/settings`, `/info`).
* **Единый 24-часовой формат времени (`ЧЧ:ММ` / `HH:MM`)** используется для обоих языков.

### 2. Архитектура Single-Message UI и очистка чата (`/clear`)
* В чат-режиме взаимодействие организовано внутри **одного главного сообщения-табло**, обновляемого на месте (`edit_message_text`).
* Любые текстовые сообщения пользователя считываются и удаляются ботом. При временных сбоях Telegram API неудалившиеся ID автоматически возвращаются в `tracked_messages` для повторной очистки.
* При переходе между крупными разделами и по командам `/start`, `/menu`, `/clear` старые сообщения удаляются пакетно (`delete_messages`) только после успешной отправки нового экрана.
* `AccessControlMiddleware` подключён как `outer_middleware`: проверяет доступ, автоопределяет язык нового пользователя, сериализует события per-user блокировкой `asyncio.Lock` и сбрасывает буфер отмены удаления при любом следующем действии в чате.

### 3. Telegram Mini App
* Доступен всем зарегистрированным пользователям через кнопку **Mini App** (`MenuButtonWebApp`) и кнопку **«📱 Открыть Mini App»** в главном меню.
* **Авторизация и безопасность:** каждый запрос к `/api/*` проверяет подпись Telegram `initData` (HMAC-SHA256, TTL 24 часа) и наличие пользователя в `bot_users`; ответы отдаются с заголовком `Content-Security-Policy` и отключённым кэшированием API; статика автоматически версионируется по SHA-256 хэшу (`?v=<hash>`).
* **Навигация:** **«👥 Люди»**, **«🔔 Уведомл.»** (со счётчиком непрочитанных), **«📋 Напоминания»**, **«⚙️ Настройки»**, **«ℹ️ Инфо»**.
* **Быстрый выбор времени и Rich-Text редактор:** в модальном окне создания/редактирования доступны кнопки **«⏱ Через 15 мин»**, **«⏱ Через час»**, **«🌆 Сегодня вечером»** (`19:00`, скрывается после 19:00) и **«🌅 Завтра утром»** (`09:00`), быстрые кнопки дат, форматирование (`B`, `I`, `U`, `S`, `code`, `spoiler`), защита от двойных кликов и устаревших ответов вкладок (`AbortController`).

### 4. Создание, редактирование, удаление и Undo напоминаний
* Поддерживаются разовые и повторяющиеся напоминания (`daily`, `weekly`, `biweekly`, `monthly`, `yearly`), пересылка сообщений любых типов, календарь, двухшаговый выбор часа и барабан минут. Перед финальным сохранением в FSM и API время повторно проверяется на актуальность.
* **Быстрое Reply-редактирование:** ответ (свайп влево) на любую карточку в `/reminders` обновляет текст на месте.
* **Мгновенное удаление и межпроцессный Undo:** удалённое напоминание сохраняется в таблице SQLite `deleted_reminders_undo` с серверным сроком жизни **60 секунд** (и сбрасывается в чат-боте при следующем действии) — отмена удаления работает и после перезапуска, и между ботом и Mini App.
* **Атомарный PATCH:** при редактировании напоминания через Mini App сначала валидируются все поля (включая `plain <= 1000` и `HTML <= 3500`), затем изменения применяются одной транзакцией.

### 5. Уведомления (`/notifications`) и надёжность доставки
* **Защита от дублей и потери:** планировщик резервирует срабатывание через lease (`reminders.processing_until`) и частичный уникальный индекс `uq_pending_rem_sched (reminder_id, scheduled_at)`, а фиксация `message_id` и перенос/закрытие напоминания выполняются единой транзакцией `finalize_triggered_delivery` с ретраями.
* **Атомарная обработка реакций между процессами:** кнопки **«🔁 Повторить»**, **«⏳ Отложить»** (`5m`, `30m`, `1h`, `1d`) и **«✅ Прочитано»** в чат-боте и Mini App работают через атомарный `DELETE ... RETURNING` в SQLite; при переносе («Отложить») удаление уведомления и перенос/клон напоминания выполняются в одной транзакции (при сбое уведомление сохраняется).

### 6. Пользователи (`/users`, `/user`) и часовые пояса (`/settings`)
* Все участники могут приглашать новых пользователей по Telegram ID; администратору приходит алерт на его языке интерфейса.
* При удалении пользователя транзакционно очищаются `bot_users`, `reminders`, `pending_notifications`, `tracked_messages`, `user_settings`, `user_panels`, `deleted_reminders_undo` и кэши в памяти, а приглашённые им участники и поле `invited_by` сохраняются для истории администратора.
* Часовые пояса используют фиксированный UTC-сдвиг (без сезонного DST): доступны пресеты от **London (UTC+1)** до **Камчатка (UTC+12)**, синхронизация с устройством и ручной ввод времени `ЧЧ:ММ`.

---

## 📂 Структура проекта

```text
/opt/reminder_bot/
├── bot.py                      # Точка входа чат-бота: БД, прокси с маскировкой секретов, команды, планировщик
├── config.py                   # Конфигурация из .env, WEBAPP_TELEGRAM_PROXY, маскировка секретов, автоверсия
├── i18n.py                     # Единый модуль локализации RUS/ENG (строки, даты, часовые пояса, справка)
├── database.py                 # Асинхронные модели SQLAlchemy (SQLite WAL, NullPool), идемпотентный init_db()
├── middlewares.py              # outer_middleware: доступ, автоопределение языка, per-user Lock, сброс Undo
├── keyboards.py                # Двуязычные Inline-клавиатуры, календарь, барабан времени, сетки 1–15
├── scheduler.py                # Фоновый планировщик с lease, ретраями финализации, backoff и RetryAfter
├── handlers/                   # Обработчики чат-бота
│   ├── __init__.py
│   ├── states.py
│   ├── common.py               # Парсеры callback, очистка с requeue, sync_user_commands, render_panel
│   ├── menu.py
│   ├── info.py
│   ├── settings.py             # Часовые пояса и переключатель языка RUS/ENG
│   ├── users.py
│   ├── notifications.py
│   ├── reminders_edit.py
│   └── reminders_create.py
├── webapp/                     # Бэкенд и фронтенд Telegram Mini App
│   ├── app.py                  # FastAPI, CSP, автоверсионирование статики, /health
│   ├── auth.py                 # Проверка initData (HMAC-SHA256) и автоопределение языка
│   ├── schemas.py              # Pydantic-схемы (включая нормализацию имени и LangUpdateRequest)
│   ├── grouping.py             # Двуязычная группировка напоминаний по горизонтам
│   ├── html_sanitizer.py       # Санитизация Telegram HTML
│   ├── tg_sync.py              # Асинхронный aiohttp/aiohttp-socks клиент синхронизации с Telegram API
│   ├── routes_reminders.py
│   ├── routes_notifications.py
│   ├── routes_users.py
│   ├── routes_settings.py      # /api/settings, /api/settings/tz, /api/settings/lang, /api/info
│   └── static/                 # index.html, styles.css, i18n.js, api.js, editor.js, app.js
├── tests/
│   └── test_review_fixes.py    # Автотесты (unittest) БД, конкурентных гонок, Undo, валидации и i18n
├── Dockerfile
├── docker-compose.yml          # Сервисы reminder_app (порт 8000 внутри сети) и tunnel (cloudflared)
├── requirements.txt            # Зависимости чат-бота (venv / systemd)
├── requirements-webapp.txt     # Зависимости Mini App (FastAPI, Uvicorn, aiohttp, aiohttp-socks, SQLAlchemy)
├── reminder_bot.service        # Конфигурация службы systemd
├── .env.example
└── README.md
```

---

## 🚀 Настройка `.env` и управление на VPS (`/opt/reminder_bot`)

### Переменные окружения (`.env`)
```ini
TELEGRAM_BOT_TOKEN=1234567890:AAH_your_bot_token_here
ADMIN_TELEGRAM_ID=123456789
USER_TELEGRAM_ID=987654321,112233445
TZ_OFFSET_HOURS=5
APP_VERSION_PREFIX=1.4
REPOSITORY=https://github.com/romualdomgn/Reminder-bot
TgUserName=@YourTelegramUsername

# Прокси для чат-бота (например, локальный Cloudflare WARP)
TELEGRAM_PROXY=socks5://127.0.0.1:49000

# Прокси для Mini App: direct — прямой выход (если WARP слушает только 127.0.0.1 на хосте),
# либо URL прокси, доступного из контейнера
WEBAPP_TELEGRAM_PROXY=direct

# Cloudflare Tunnel и URL Mini App
CLOUDFLARE_TUNNEL_TOKEN=eyJ...
WEBAPP_URL=https://reminder.example.com
APP_UID=990
APP_GID=985
```

### Полезные команды на VPS
* **Чат-бот (`systemd`):**
  ```bash
  sudo systemctl status reminder_bot.service --no-pager
  sudo journalctl -u reminder_bot.service -n 50 -f
  sudo chown -R reminder_bot_user:reminder_bot_user /opt/reminder_bot && sudo systemctl restart reminder_bot.service
  ```
* **Mini App и туннель (`docker compose`):**
  ```bash
  cd /opt/reminder_bot
  sudo docker compose ps
  sudo docker compose logs -f reminder_app tunnel
  sudo docker compose up -d --force-recreate reminder_app   # после правки .env
  sudo docker compose up -d --build reminder_app            # после правки requirements-webapp.txt / Dockerfile
  ```
* **Проверка синтаксиса и запуск автотестов (работают во временной БД):**
  ```bash
  cd /opt/reminder_bot
  sudo -u reminder_bot_user /opt/reminder_bot/venv/bin/python -m py_compile     bot.py config.py i18n.py database.py scheduler.py middlewares.py keyboards.py     handlers/*.py webapp/*.py tests/test_review_fixes.py
  sudo -u reminder_bot_user /opt/reminder_bot/venv/bin/python -m unittest discover -s tests -v
  sudo docker compose exec reminder_app python -m unittest     tests.test_review_fixes.ReviewFixesAsyncTests.test_p1_5_patch_invalid_text_does_not_mutate_datetime     tests.test_review_fixes.ReviewFixesAsyncTests.test_i18n_webapp_lang_endpoint -v
  ```
