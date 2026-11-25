from datetime import date, datetime, timedelta

SUPPORTED_LANGS: tuple[str, ...] = ("ru", "en")
DEFAULT_LANG = "ru"


def normalize_lang(lang: str | None) -> str:
    val = (lang or "").strip().lower()
    if val in SUPPORTED_LANGS:
        return val
    return DEFAULT_LANG


def detect_language_from_code(language_code: str | None) -> str:
    """Автоопределение языка нового пользователя по Telegram language_code."""
    code = (language_code or "").strip().lower()
    if not code:
        return DEFAULT_LANG
    if code.startswith("ru"):
        return "ru"
    return "en"


MONTHS_NOMINATIVE: dict[str, dict[int, str]] = {
    "ru": {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
    },
    "en": {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December",
    },
}

MONTHS_GENITIVE: dict[str, dict[int, str]] = {
    "ru": {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
    },
    "en": {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December",
    },
}

MONTHS_SHORT: dict[str, dict[int, str]] = {
    "ru": {
        1: "Янв", 2: "Фев", 3: "Мар", 4: "Апр",
        5: "Май", 6: "Июн", 7: "Июл", 8: "Авг",
        9: "Сен", 10: "Окт", 11: "Ноя", 12: "Дек",
    },
    "en": {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
        5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
        9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    },
}

WEEKDAYS: dict[str, dict[int, str]] = {
    "ru": {
        0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг",
        4: "пятница", 5: "суббота", 6: "воскресенье",
    },
    "en": {
        0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
        4: "Friday", 5: "Saturday", 6: "Sunday",
    },
}

WEEKDAYS_ON_DAY: dict[str, dict[int, str]] = {
    "ru": {
        0: "в понедельник", 1: "во вторник", 2: "в среду", 3: "в четверг",
        4: "в пятницу", 5: "в субботу", 6: "в воскресенье",
    },
    "en": {
        0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
        4: "Friday", 5: "Saturday", 6: "Sunday",
    },
}

WEEKDAY_HEADERS: dict[str, list[str]] = {
    "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "𝐂б", "𝐁𝐜"],
    "en": ["Mo", "Tu", "We", "Th", "Fr", "𝐒𝐚", "𝐒𝐮"],
}

RECURRENCE_LABELS_BY_LANG: dict[str, dict[str, str]] = {
    "ru": {
        "once": "Один раз",
        "daily": "🔁 Каждый день",
        "weekly": "🔁 Раз в неделю",
        "biweekly": "🔁 Каждые две недели",
        "monthly": "🔁 Ежемесячно",
        "yearly": "🔁 Ежегодно",
    },
    "en": {
        "once": "Once",
        "daily": "🔁 Daily",
        "weekly": "🔁 Weekly",
        "biweekly": "🔁 Every 2 weeks",
        "monthly": "🔁 Monthly",
        "yearly": "🔁 Yearly",
    },
}

TZ_ABBR_MAPS: dict[str, dict[int, str]] = {
    "ru": {
        60: "London (UTC+1)",
        120: "Калининград (UTC+2)",
        180: "Москва (UTC+3)",
        240: "Самара (UTC+4)",
        300: "Магнитогорск (UTC+5)",
        360: "Омск (UTC+6)",
        420: "Красноярск (UTC+7)",
        480: "Иркутск (UTC+8)",
        540: "Якутск (UTC+9)",
        600: "Хабаровск (UTC+10)",
        660: "Магадан (UTC+11)",
        720: "Камчатка (UTC+12)",
    },
    "en": {
        60: "London (UTC+1)",
        120: "Kaliningrad (UTC+2)",
        180: "Moscow (UTC+3)",
        240: "Samara (UTC+4)",
        300: "Magnitogorsk (UTC+5)",
        360: "Omsk (UTC+6)",
        420: "Krasnoyarsk (UTC+7)",
        480: "Irkutsk (UTC+8)",
        540: "Yakutsk (UTC+9)",
        600: "Khabarovsk (UTC+10)",
        660: "Magadan (UTC+11)",
        720: "Kamchatka (UTC+12)",
    },
}

SNOOZE_LABELS_BY_LANG: dict[str, dict[str, str]] = {
    "ru": {"5m": "5 минут", "30m": "30 минут", "1h": "1 час", "1d": "1 день"},
    "en": {"5m": "5 min", "30m": "30 min", "1h": "1 hour", "1d": "1 day"},
}

LANG_NAMES: dict[str, str] = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        "access_denied": "У Вас нет доступа к боту",
        "admin_only": "⛔ Доступно только администратору",
        "admin_only_users_cmd": "⛔ <b>Доступ к разделу /users есть только у администратора.</b>",
        "user_sec_hint": "ℹ️ <b>Раздел /user появится после того, как вы добавите хотя бы одного нового пользователя в Настройках (/settings).</b>",
        "user_sec_alert": "Сначала добавьте пользователя через Настройки",
        "no_name": "Без имени",
        "no_name_html": "<i>Без имени</i>",
        "role_admin": "👑 Админ",
        "role_admin_full": "👑 Администратор",
        "role_user": "👤 Пользователь",
        "welcome_invite": (
            "Привет. Вы приглашены в бот Напоминалкин.\n\n"
            "Нажмите Menu или Start.\n\n"
            "Ознакомиться с тем, как работает бот можно в Меню в разделе Информация.\n\n"
            "Перед началом работы задайте в Настройках свой текущий часовой пояс, чтобы время бота и Вашего устройства совпадало"
        ),
        "user_removed_notice": "⛔ <b>Вы удалены из списка пользователей, доступ к боту прекращён.</b>",
        "admin_new_user_alert": (
            "👤 <b>Добавлен новый пользователь</b>\n\n"
            "👤 <b>Имя:</b> {new_name}\n"
            "🆔 <b>Telegram ID:</b> <code>{new_user_id}</code>\n"
            "➕ <b>Пригласил:</b> {inviter_label}"
        ),
        "cmd_start": "🧭 Главное меню",
        "cmd_notifications": "🔔 Уведомления",
        "cmd_reminders": "📋 Напоминания",
        "cmd_users": "👥 Пользователи",
        "cmd_settings": "⚙️ Настройки",
        "cmd_info": "ℹ️ Информация",
        "home_now": "Сейчас {time}, {date}",
        "home_footer": "Выберите действие кнопками ниже, напишите текст или <b>перешлите сюда сообщение</b> из любого чата.",
        "btn_create_rem": "➕ Создать напоминание",
        "btn_create_more_rem": "➕ Создать ещё напоминание",
        "btn_reminders": "📋 Напоминания",
        "btn_notifications": "🔔 Уведомления",
        "btn_users": "👥 Пользователи",
        "btn_settings": "⚙️ Настройки",
        "btn_info": "ℹ️ Информация",
        "btn_open_webapp": "📱 Открыть Mini App",
        "btn_home": "🏠 В главное меню",
        "btn_back": "⬅️ Назад",
        "btn_back_plain": "Назад",
        "btn_back_to_reminders": "⬅️ Назад к напоминаниям",
        "btn_back_to_settings": "⬅️ Назад в настройки",
        "btn_back_to_hours": "⬅️ К выбору часа",
        "btn_back_to_rem": "⬅️ Назад к напоминанию",
        "btn_back_to_user": "⬅️ Назад к пользователю",
        "btn_back_to_user_select": "⬅️ К выбору пользователя",
        "btn_to_users_section": "👥 В раздел «Пользователи»",
        "btn_change_date": "📅 Изменить дату",
        "btn_change_date_short": "⬅️ Изменить дату",
        "btn_change_time_short": "⬅️ Изменить время",
        "btn_yes_delete": "✅ Да, удалить",
        "btn_ok": "Ok",
        "settings_title": "⚙️ <b>Раздел «Настройки»</b>",
        "settings_current_time": "🕒 Текущее время: <code>{dt} — {tz}</code>",
        "settings_current_lang": "🌐 Язык интерфейса: <b>{lang_name}</b>",
        "settings_choose": "Выберите нужный пункт настроек:",
        "btn_set_time": "🕒 Настроить время бота",
        "btn_set_lang": "🌐 Язык / Language",
        "btn_add_user": "➕ Добавить нового пользователя",
        "tz_title": "🕒 <b>Настроить время бота</b>",
        "tz_current": "Сейчас установлено: <code>{time} — {tz}</code>",
        "tz_prompt": (
            "Выберите часовой пояс кнопкой ниже <b>ИЛИ отправьте в чат текущее время на вашем устройстве</b> "
            "в формате <code>ЧЧ:ММ</code> (например, <code>21:30</code>):"
        ),
        "tz_updated_cb": "Время обновлено!",
        "tz_synced_notice": "✅ Время синхронизировано: <code>{dt} — {tz}</code>",
        "tz_synced_device_notice": "✅ Время синхронизировано с устройством: <code>{dt} — {tz}</code>",
        "tz_bad_format": (
            "⚠️ <b>Неверный формат!</b>\n"
            "Введите текущее время с вашего устройства в формате <code>ЧЧ:ММ</code> (например, <code>19:45</code>) "
            "или нажмите одну из кнопок ниже:"
        ),
        "lang_title": "🌐 <b>Язык интерфейса / Language</b>",
        "lang_current": "Текущий язык: <b>{lang_name}</b>",
        "lang_prompt": "Выберите язык интерфейса бота и Mini App:",
        "lang_updated_cb": "Язык обновлён!",
        "lang_updated_notice": "✅ Язык интерфейса изменён: <b>{lang_name}</b>",
        "info_title": "ℹ️ <b>Раздел «Информация»</b>\n\nВыберите интересующий вас раздел ниже:",
        "info_btn_reminders": "📋 Как создать напоминание",
        "info_btn_notifications": "🔔 Работа с уведомлениями",
        "info_btn_settings": "🕒 Выбор часового пояса",
        "info_btn_add_user": "👤 Как добавить нового пользователя",
        "info_btn_app_mode": "📱 Вид приложения",
        "info_btn_general": "🌐 О приложении",
        "info_chat_reminders": (
            "📋 <b>Напоминания — как работать</b>\n\n"
            "• <b>Создание:</b> нажмите «Создать напоминание», просто напишите текст в чат или перешлите в бот сообщение из любого другого чата.\n\n"
            "• <b>Дата и время:</b> выберите одну из кнопок («Сегодня», «Завтра», «Через неделю», «Через месяц») или выберите любую дату через «Календарь». Укажите точное время или нажмите кнопку быстрого выбора времени (15:00).\n\n"
            "• <b>Периодичность:</b> можно создать разовое напоминание («Один раз») или повторяющееся («Каждый день», «Раз в неделю», «Каждые две недели», «Ежемесячно», «Ежегодно»).\n\n"
            "• <b>При срабатывании:</b> уведомление можно отложить («5 минут», «30 минут», «1 час», «1 день») или перезапустить кнопкой «Повторить».\n\n"
            "• <b>Редактирование</b>: в разделе «Напоминания» показаны все активные напоминания по номерам — нажмите «Редактировать напоминания» и выберите нужное напоминание кнопкой (или введите его номер), чтобы изменить текст, дату, время или удалить запись.\n\n"
            "• <b>Быстрое редактирование</b>: для быстрого редактирования текста напоминания сделайте свайп влево, долгое нажатие (или правая кнопка мыши) и кнопка «Ответить»."
        ),
        "info_chat_notifications": (
            "🔔 <b>Уведомления</b>\n\n"
            "Если у Вас есть хотя бы одно уведомление, на которое не последовала реакция "
            "(кнопка «Прочитано», «Повтор» или «Отложить»), то появляется раздел «Уведомления», "
            "в котором выводятся все напоминания, которые ожидают реакции пользователя."
        ),
        "info_chat_settings": (
            "⚙️ <b>Настройки — для чего задавать часовой пояс</b>\n\n"
            "Сервер бота работает в универсальном времени (UTC), а Telegram не передаёт боту часовой пояс вашего устройства автоматически.\n\n"
            "Задание часового пояса необходимо для того, чтобы:\n"
            "• текущее время на пульте и время всех напоминаний отображались точно по часам вашего смартфона или компьютера;\n"
            "• напоминания срабатывали строго в указанный вами час по вашему местному времени;\n"
            "• кнопки быстрого выбора даты и времени корректно определяли текущий день и час для вашего региона.\n\n"
            "Например, Вы планируете поездку Магадан -&gt; Москва -&gt; Уфа. Необходимо сделать себе напоминание о регистрации на рейс за сутки до вылета. Сейчас вы находитесь дома в Уфе.\n\n"
            "Чтобы при формировании напоминания не пересчитывать сдвиг по времени Уфа-Москва и Уфа-Магадан, ещё в месте своего пребывания в разделе Настройки (/settings) выставляете часовой пояс «Магадан» (UTC+11) и делаете напоминание «Регистрация на рейс Магадан-Москва в 09:30». Далее выставляете часовой пояс «Москва» (UTC+3) и делаете напоминание «Регистрация на рейс Москва-Уфа в 19:15». После этого возвращаете свой пояс (UTC+5).\n\n"
            "В итоге, в Магадане, напоминание сработает в заданный день в 9:30 утра по местному времени, а не по уфимскому, когда самолёт уже на подлёте к Москве"
        ),
        "info_chat_add_user": (
            "➕ <b>Добавление нового пользователя</b>\n\n"
            "Вы можете пригласить нового пользователя в бот по его числовому <b>Telegram ID</b>:\n\n"
            "1. <b>Как узнать Telegram ID:</b> откройте бот @userinfobot и перешлите в него любое сообщение от человека, которого хотите пригласить. Также в боте можно нажать кнопку User и выбрать имя пользователя из списка Ваших контактов. Либо попросите нового пользователя запустить @userinfobot и прислать вам число из строки <code>Id</code>.\n\n"
            "2. <b>Как добавить в бот:</b> откройте раздел /settings, нажмите кнопку «Добавить нового пользователя», отправьте полученный числовой Telegram ID и укажите имя пользователя.\n\n"
            "3. После добавления новому участнику придёт приглашение, и он сможет пользоваться ботом."
        ),
        "info_chat_app_mode": (
            "📱 <b>Вид приложения</b>\n\n"
            "Приложение можно использовать в двух вариантах - как чат в Телеграм или как мини-приложение."
        ),
        "info_chat_general": (
            "🌐 <b>О приложении</b>\n\n"
            "Этот бот — <b>open-source</b> приложение.\n"
            "Репозиторий находится по адресу:\n{repo}\n\n"
            "Предложения по улучшению дизайна и юзабилити направлять создателю и администратору бота "
            "{admin}\n\n"
            "ver. {ver} Last update - {date}"
        ),
        "cal_year_ahead": "⏩ На год вперёд: {month} {year}",
        "cal_year_lbl": "Год: {year}",
        "cal_past_date": "Эта дата уже в прошлом",
        "cal_past_month": "Нельзя выбрать прошедший месяц",
        "cal_past_year": "Нельзя выбрать прошедший год",
        "cal_past_time": "Это время сегодня уже прошло",
        "drum_hour_up": "▲ {h:02d} ч",
        "drum_hour_down": "▼ {h:02d} ч",
        "drum_min_up": "▲ {m:02d} мин",
        "drum_min_down": "▼ {m:02d} мин",
        "drum_pick": "✅ Выбрать {h:02d}:{m:02d}",
        "btn_today": "Сегодня",
        "btn_tomorrow": "Завтра",
        "btn_in_week": "Через неделю",
        "btn_in_month": "Через месяц",
        "btn_in_year": "Через год",
        "btn_calendar": "📅 Календарь",
        "btn_once": "Один раз",
        "btn_once_ico": "1️⃣ Один раз",
        "btn_recurring": "🔁 Повторяющееся",
        "btn_rec_daily": "Каждый день",
        "btn_rec_weekly": "Раз в неделю",
        "btn_rec_biweekly": "Каждые две недели",
        "btn_rec_monthly": "Ежемесячно",
        "btn_rec_yearly": "Ежегодно",
        "btn_rec_daily_ico": "📅 Каждый день",
        "btn_rec_weekly_ico": "🗓 Раз в неделю",
        "btn_rec_biweekly_ico": "📆 Каждые две недели",
        "btn_rec_monthly_ico": "🌙 Ежемесячно",
        "btn_rec_yearly_ico": "🎉 Ежегодно",
        "btn_set_1500": "⏰ Установить 15:00",
        "skip_today_15": "Сегодня в 15:00",
        "skip_today_at": "Сегодня в {time}",
        "skip_tomorrow_15": "Завтра в 15:00",
        "skip_tomorrow_at": "Завтра в {time}",
        "skip_week_15": "Через неделю в 15:00",
        "skip_month_15": "Через месяц в 15:00",
        "skip_year_15": "Через год в 15:00",
        "skip_date_at": "{date} в {time}",
        "create_step1_title": "✍️ <b>Создание напоминания – Шаг 1 из 4</b>",
        "create_step1_prompt": "Введите текст сообщения или перешлите в бот сообщение из любого чата",
        "create_step2_header": "📅 <b>Создание напоминания - Шаг 2 из 4</b>",
        "create_step2_body": "{header}\nВыберите желаемую дату\n\n💬 <b>Сообщение:</b>\n{text}",
        "create_expired_cb": "Сессия создания устарела. Начните заново.",
        "create_expired_notice": "ℹ️ <b>Сессия создания напоминания устарела.</b> Нажмите «➕ Создать напоминание» или отправьте текст заново.",
        "create_stale_btn": "Кнопка устарела. Начните заново или откройте главное меню.",
        "create_hour_prompt": (
            "⏰ <b>Создание напоминания — Выбор часа</b>\n\n"
            "💬 <b>Сообщение:</b>\n{text}\n\n"
            "📅 <b>Дата:</b> <code>{date}</code>\n\n"
            "{err_block}"
            "Нажмите <b>«{skip}»</b>, выберите <b>час</b> в сетке ниже "
            "или напишите время в чат (например, <code>09:30</code>):"
        ),
        "create_min_prompt": (
            "⏰ <b>Создание напоминания — Выбор минут</b>\n\n"
            "💬 <b>Сообщение:</b>\n{text}\n\n"
            "📅 <b>Дата:</b> <code>{date}</code>\n"
            "🕒 <b>Выбранное время:</b> <code>{h:02d}:{m:02d}</code>\n\n"
            "{err_block}"
            "Нажмите на готовое время в сетке ниже или подкрутите <b>барабан</b> (▲/▼) до нужной минуты:"
        ),
        "create_cal_prompt": (
            "📅 <b>Календарь — Выбор даты</b>\n\n"
            "💬 <b>Сообщение:</b>\n{text}\n\n"
            "{err_block}"
            "Выберите день в календаре, нажмите на <b>месяц и год</b> в шапке для быстрого переключения года "
            "или отправьте дату в чат (<code>ДД.ММ.ГГГГ</code>):"
        ),
        "create_ym_prompt": (
            "📅 <b>Быстрый выбор года и месяца</b>\n\n"
            "💬 <b>Сообщение:</b>\n{text}\n\n"
            "Нажмите <b>«На год вперёд»</b>, переключите год стрелками <code>&lt;</code> <code>&gt;</code> "
            "или выберите нужный месяц:"
        ),
        "create_rec_type_prompt": (
            "🔁 <b>Создание напоминания — Периодичность</b>\n\n"
            "💬 <b>Сообщение:</b>\n{text}\n\n"
            "📅 <b>Дата:</b> <code>{date}</code>\n"
            "⏰ <b>Время:</b> <code>{time}</code>\n\n"
            "Выберите тип напоминания:"
        ),
        "create_rec_period_prompt": (
            "🔁 <b>Выбор периодичности напоминания</b>\n\n"
            "💬 <b>Сообщение:</b>\n{text}\n\n"
            "📅 <b>Первый запуск:</b> <code>{date} в {time}</code>\n\n"
            "С какой периодичностью присылать напоминание?"
        ),
        "err_bad_date_create": "Неверный формат даты! Выберите день в календаре или введите ДД.ММ.ГГГГ.",
        "err_past_date_create": "Указанная дата уже в прошлом! Выберите актуальную дату.",
        "err_past_time": "Выбранное время уже прошло. Укажите более позднее время",
        "err_bad_time_create": "Неверный формат времени! Выберите час кнопкой или введите ЧЧ:ММ.",
        "msg_doc": "📎 Документ: {name}",
        "msg_doc_fallback": "файл",
        "msg_photo": "🖼 Фотография",
        "msg_video": "🎬 Видео",
        "msg_voice": "🎤 Голосовое сообщение",
        "msg_audio": "🎵 Аудио: {title}",
        "msg_audio_fallback": "аудиозапись",
        "msg_video_note": "📹 Видеосообщение",
        "msg_contact": "👤 Контакт: {name} ({phone})",
        "msg_location": "📍 Геолокация: {lat}, {lon}",
        "msg_poll": "📊 Опрос: {question}",
        "msg_forwarded": "📌 Пересланное сообщение",
        "grp_today": "Сегодня, {day} ⏰",
        "grp_tomorrow": "Завтра, {day} 🕰",
        "grp_day_after": "Послезавтра, {day} 🕑",
        "grp_very_soon": "Совсем скоро ⌛️",
        "grp_in_week": "Через неделю 📅",
        "grp_in_year": "Через год",
        "grp_in_half_year": "Через полгода",
        "grp_in_month": "Через месяц",
        "grp_near_future": "В скором будущем ⏳",
        "rem_at_time": "В {time}",
        "rem_date_at_time": "{date}, в {time}",
        "rem_num_prefix": "№{idx} - ",
        "rem_empty": "У вас пока нет активных напоминаний.",
        "rem_inactive": "Напоминание уже не активно.",
        "rem_not_found_or_sent": "Напоминание не найдено или уже отправлено.",
        "btn_undo_delete": "↩️ Отменить удаление",
        "btn_edit_rems": "✏️ Редактировать напоминания",
        "btn_del_rem": "🗑 Удалить напоминание",
        "btn_edit_text": "✏️ Изменить текст",
        "btn_edit_date": "📅 Изменить дату",
        "btn_edit_time": "⏰ Изменить время",
        "btn_edit_rec": "🔁 Изменить периодичность",
        "cb_pick_num_edit": "Выберите номер для редактирования",
        "cb_pick_num_del": "Выберите номер для удаления",
        "rem_deleted_num": "Напоминание №{num} удалено.",
        "rem_deleted": "Напоминание удалено.",
        "undo_unavailable": "Отмена удаления больше недоступна",
        "undo_done": "Удаление отменено",
        "rem_num_not_found": "Напоминание с номером «{num}» не найдено.",
        "rem_manage_card": (
            "Управление напоминанием{title_num}\n"
            "{notice_block}"
            "{dt_str}"
            "{rec_line}\n"
            "{text}\n\n"
            "Выберите нужное действие:"
        ),
        "rem_text_updated": "Текст напоминания обновлён.",
        "edit_cal_prompt": (
            "Календарь — Выбор новой даты\n"
            "{text}\n\n"
            "{err_block}"
            "Выберите дату в календаре, нажмите на месяц и год в шапке для переключения года "
            "или отправьте дату в чат (ДД.ММ.ГГГГ):"
        ),
        "edit_ym_prompt": (
            "Быстрый выбор года и месяца\n"
            "{text}\n\n"
            "Нажмите «На год вперёд», переключите год стрелками < > или выберите нужный месяц:"
        ),
        "edit_date_prompt": (
            "Изменение даты напоминания\n"
            "{dt_str}\n"
            "{text}\n\n"
            "Выберите новую дату кнопкой ниже или откройте Календарь:"
        ),
        "edit_hour_prompt": (
            "Изменение времени напоминания — Выбор часа\n"
            "Дата: {date}\n"
            "{text}\n\n"
            "{err_block}"
            "Нажмите «{skip}», выберите час в сетке ниже или отправьте время в чат:"
        ),
        "edit_min_prompt": (
            "Изменение времени напоминания — Выбор минут\n"
            "Дата: {date}\n"
            "Выбранное время: {h:02d}:{m:02d}\n"
            "{text}\n\n"
            "Выберите время в сетке ниже или подкрутите барабан (▲/▼):"
        ),
        "edit_old_time_passed": "Прежнее время ({time}) сегодня уже прошло.",
        "edit_date_changed": "Дата изменена на {date}.",
        "edit_bad_date": "Неверный формат даты. Выберите дату в календаре или введите ДД.ММ.ГГГГ.",
        "edit_past_date": "Указанная дата уже в прошлом. Выберите актуальную дату.",
        "edit_time_changed": "Время напоминания изменено на {dt_str} ({tz}).",
        "edit_bad_time": "Неверный формат времени. Выберите час кнопкой или введите ЧЧ:ММ.",
        "edit_rec_prompt": (
            "Изменение периодичности напоминания\n"
            "Повтор: {rec}\n"
            "{text}\n\n"
            "Выберите режим срабатывания:"
        ),
        "edit_rec_period_prompt": (
            "Выбор периодичности повторения\n"
            "{text}\n\n"
            "Выберите, с какой периодичностью присылать напоминание:"
        ),
        "edit_rec_once_done": "Установлен режим: Один раз.",
        "edit_rec_changed": "Периодичность изменена: {rec}.",
        "notif_section_panel": (
            "🔔 <b>Раздел «Уведомления»</b>\n\n"
            "Непрочитанных уведомлений: <b>{count}</b>\n"
            "Выберите действие под нужным уведомлением выше:"
        ),
        "btn_notif_repeat": "🔁 Повторить",
        "btn_notif_snooze": "⏳ Отложить",
        "btn_notif_ack": "✅ Прочитано",
        "notif_already_done": "Уведомление уже обработано",
        "notif_acked_cb": "Прочитано",
        "notif_rem_not_found": "Напоминание не найдено",
        "notif_pick_snooze": "Выберите, на сколько отложить",
        "notif_snooze_missing_rem": "Исходное напоминание не найдено. Уведомление сохранено.",
        "notif_snoozed_cb": "Отложено на {label}",
        "users_title": "👥 <b>Раздел «Пользователи»</b>",
        "users_empty": "Список пользователей пуст.",
        "users_total": "Всего пользователей с доступом: <b>{count}</b>",
        "users_my_empty": "Список добавленных вами пользователей пуст.",
        "users_my_total": "Добавленные вами пользователи (<b>{count}</b>):",
        "users_empty_notice": "ℹ️ Список пользователей пуст.",
        "users_no_removable": "ℹ️ Нет пользователей для удаления.",
        "my_users_no_del": "ℹ️ У вас нет добавленных пользователей для удаления.",
        "my_users_no_edit": "ℹ️ У вас пока нет добавленных пользователей для редактирования.",
        "users_cannot_del_admin": "⚠️ Нельзя удалить администратора бота.",
        "users_not_found_del": "⚠️ Пользователь <code>{uid}</code> не найден или недоступен для удаления.",
        "users_not_found_my": "⚠️ Пользователь <code>{uid}</code> не найден среди добавленных вами.",
        "users_not_found": "⚠️ Пользователь <code>{uid}</code> не найден.",
        "users_not_found_short": "⚠️ Пользователь не найден.",
        "users_not_found_my_short": "⚠️ Пользователь не найден среди добавленных вами.",
        "users_not_found_db": "⚠️ Пользователь <code>{uid}</code> не найден в базе.",
        "users_del_failed": "⚠️ Не удалось удалить пользователя <code>{uid}</code>.",
        "users_del_confirm": (
            "🗑 <b>Удаление пользователя</b>\n\n"
            "👤 <b>Имя:</b> {name}\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n\n"
            "Вы действительно хотите удалить этого пользователя и прекратить ему доступ к боту?"
        ),
        "users_admin_my_title": "👥 <b>Мои пользователи (добавленные администратором)</b>",
        "users_admin_my_empty": "Список пользователей, добавленных администратором, пуст.",
        "users_admin_my_total": "Всего добавлено вами: <b>{count}</b>",
        "users_admin_all_title": "👥 <b>Все пользователи (добавленные другими пользователями)</b>",
        "users_admin_all_empty": "Пока нет пользователей, добавленных другими участниками.",
        "users_admin_all_total": "Всего добавлено другими пользователями: <b>{count}</b>",
        "users_added_date": "📅 Дата добавления: <code>{dt}</code>",
        "users_added_by": "➕ Добавил: {inviter}",
        "btn_my_users": "Мои пользователи",
        "btn_all_users": "Все пользователи",
        "btn_edit_user": "✏️ Редактировать пользователя",
        "btn_del_user": "🗑 Удалить пользователя",
        "btn_edit_user_name": "✏️ Изменить имя",
        "add_user_prompt": (
            "➕ <b>Добавление нового пользователя</b>\n\n"
            "Отправьте в чат <b>Telegram ID нового пользователя</b> (только цифры, например: 123456789).\n"
            "Telegram ID того, кого Вы хотите добавить можно узнать в боте @userinfobot"
        ),
        "add_user_bad_id": "⚠️ <b>Некорректный Telegram ID!</b> Пожалуйста, отправьте только цифры:",
        "add_user_title": "➕ <b>Добавление нового пользователя</b>",
        "add_user_dup_admin": (
            "⚠️ <b>Такой пользователь уже существует!</b>\n"
            "👤 Имя: <b>{name}</b>\n"
            "🆔 Telegram ID: <code>{uid}</code> ({role})"
        ),
        "add_user_dup_user": "⚠️ <b>Такой пользователь (<code>{uid}</code>) уже существует!</b>",
        "add_user_dup_retry": "Введите другой <b>Telegram ID нового пользователя</b> или вернитесь назад:",
        "add_user_dup_short": "⚠️ <b>Такой пользователь уже существует!</b> (<code>{uid}</code>)",
        "add_user_ask_name": (
            "➕ <b>Добавление нового пользователя</b>\n\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n\n"
            "Теперь отправьте в чат <b>имя пользователя</b> (например: <code>Иван</code> или <code>Мария</code>):"
        ),
        "add_user_bad_name": (
            "➕ <b>Добавление нового пользователя</b>\n\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n\n"
            "⚠️ <b>Некорректное имя!</b>\n"
            "Введите имя пользователя (до 100 символов):"
        ),
        "add_user_invite_sent": "приглашение отправлено",
        "add_user_invite_pending": "получит доступ сразу после запуска бота (/start)",
        "add_user_success": "✅ <b>Пользователь {name} (<code>{uid}</code>) добавлен</b> ({status}).",
        "user_card_my": (
            "✏️ <b>Карточка пользователя</b>\n\n"
            "{notice_block}"
            "👤 <b>Имя:</b> {name}\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n\n"
            "Выберите действие:"
        ),
        "user_card_admin": (
            "✏️ <b>Карточка пользователя</b>\n\n"
            "{notice_block}"
            "👤 <b>Имя:</b> {name}\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n"
            "🔑 <b>Роль:</b> {role}\n\n"
            "Выберите действие:"
        ),
        "user_bad_num_or_id": "⚠️ <b>Некорректный номер или Telegram ID!</b> Выберите номер кнопкой ниже:",
        "user_edit_name_prompt": (
            "✏️ <b>Изменение имени пользователя</b>\n\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n"
            "👤 <b>Текущее имя:</b> {name}\n\n"
            "Отправьте в чат <b>новое имя</b> для этого пользователя:"
        ),
        "user_edit_name_bad": (
            "✏️ <b>Изменение имени пользователя</b>\n\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n\n"
            "⚠️ <b>Некорректное имя!</b>\n"
            "Введите новое имя пользователя (от 1 до 100 символов):"
        ),
        "user_name_updated": "✅ <b>Имя успешно изменено на «{name}»!</b>",
        "user_deleted_cb": "Пользователь удалён",
        "user_del_notified": "уведомление отправлено",
        "user_del_closed": "доступ закрыт",
        "user_del_success": "✅ <b>Пользователь {label} удалён</b> ({status}).",
        "api_missing_init_data": "Отсутствует подпись Telegram initData",
        "api_bad_init_data": "Некорректная подпись initData",
        "api_invalid_sig": "Подпись Telegram initData не прошла проверку",
        "api_bad_auth_date": "Некорректная дата авторизации",
        "api_session_expired": "Сессия Mini App устарела, откройте заново",
        "api_missing_user": "В initData отсутствуют данные пользователя",
        "api_bad_user": "Некорректные данные пользователя",
        "api_enter_text": "Введите текст напоминания",
        "api_text_too_long": "Текст напоминания не должен превышать 1000 символов",
        "api_html_too_long": "Текст с форматированием слишком длинный",
        "api_bad_datetime": "Неверный формат даты или времени",
        "api_rem_not_found": "Напоминание не найдено или уже отправлено",
        "api_rem_inactive": "Напоминание уже не активно",
        "api_rem_already_deleted": "Напоминание уже удалено",
        "api_undo_unavailable": "Отмена удаления больше недоступна",
        "api_notif_not_found": "Исходное напоминание не найдено",
        "api_notif_text_not_found": "Текст напоминания не найден",
        "api_bad_time_hhmm": "Введите время в формате ЧЧ:ММ",
        "api_bad_time_range": "Некорректное время (00:00–23:59)",
        "api_tz_payload_missing": "Укажите offset_minutes или device_time",
        "api_user_exists": "Пользователь {uid} уже существует",
        "api_user_exists_short": "Такой пользователь уже существует",
        "api_user_not_found": "Пользователь не найден",
        "api_cannot_del_admin": "Нельзя удалить администратора бота",
    },
    "en": {
        "access_denied": "You do not have access to this bot",
        "admin_only": "⛔ Admin access only",
        "admin_only_users_cmd": "⛔ <b>Only the administrator can access /users.</b>",
        "user_sec_hint": "ℹ️ <b>The /user section will appear after you invite at least one user in Settings (/settings).</b>",
        "user_sec_alert": "Invite a user in Settings first",
        "no_name": "No name",
        "no_name_html": "<i>No name</i>",
        "role_admin": "👑 Admin",
        "role_admin_full": "👑 Administrator",
        "role_user": "👤 User",
        "welcome_invite": (
            "Hello! You have been invited to Reminder Bot.\n\n"
            "Press Menu or Start.\n\n"
            "You can learn how the bot works in Menu → Info.\n\n"
            "Before getting started, please set your local timezone in Settings so the bot's clock matches your device."
        ),
        "user_removed_notice": "⛔ <b>You have been removed from the users list. Access to the bot has been revoked.</b>",
        "admin_new_user_alert": (
            "👤 <b>New user added</b>\n\n"
            "👤 <b>Name:</b> {new_name}\n"
            "🆔 <b>Telegram ID:</b> <code>{new_user_id}</code>\n"
            "➕ <b>Invited by:</b> {inviter_label}"
        ),
        "cmd_start": "🧭 Main Menu",
        "cmd_notifications": "🔔 Notifications",
        "cmd_reminders": "📋 Reminders",
        "cmd_users": "👥 Users",
        "cmd_settings": "⚙️ Settings",
        "cmd_info": "ℹ️ Info",
        "home_now": "Now {time}, {date}",
        "home_footer": "Choose an action below, type a message, or <b>forward any message here</b> from another chat.",
        "btn_create_rem": "➕ Create reminder",
        "btn_create_more_rem": "➕ Create another reminder",
        "btn_reminders": "📋 Reminders",
        "btn_notifications": "🔔 Notifications",
        "btn_users": "👥 Users",
        "btn_settings": "⚙️ Settings",
        "btn_info": "ℹ️ Info",
        "btn_open_webapp": "📱 Open Mini App",
        "btn_home": "🏠 Main Menu",
        "btn_back": "⬅️ Back",
        "btn_back_plain": "Back",
        "btn_back_to_reminders": "⬅️ Back to reminders",
        "btn_back_to_settings": "⬅️ Back to settings",
        "btn_back_to_hours": "⬅️ Back to hours",
        "btn_back_to_rem": "⬅️ Back to reminder",
        "btn_back_to_user": "⬅️ Back to user",
        "btn_back_to_user_select": "⬅️ Select user",
        "btn_to_users_section": "👥 Users section",
        "btn_change_date": "📅 Change date",
        "btn_change_date_short": "⬅️ Change date",
        "btn_change_time_short": "⬅️ Change time",
        "btn_yes_delete": "✅ Yes, delete",
        "btn_ok": "Ok",
        "settings_title": "⚙️ <b>Settings</b>",
        "settings_current_time": "🕒 Current time: <code>{dt} — {tz}</code>",
        "settings_current_lang": "🌐 Interface language: <b>{lang_name}</b>",
        "settings_choose": "Choose a setting below:",
        "btn_set_time": "🕒 Set bot time",
        "btn_set_lang": "🌐 Язык / Language",
        "btn_add_user": "➕ Add new user",
        "tz_title": "🕒 <b>Set bot time</b>",
        "tz_current": "Currently set: <code>{time} — {tz}</code>",
        "tz_prompt": (
            "Choose a timezone below <b>OR send your device's current time</b> "
            "in 24-hour <code>HH:MM</code> format (e.g., <code>21:30</code>):"
        ),
        "tz_updated_cb": "Time updated!",
        "tz_synced_notice": "✅ Time synced: <code>{dt} — {tz}</code>",
        "tz_synced_device_notice": "✅ Time synced with device: <code>{dt} — {tz}</code>",
        "tz_bad_format": (
            "⚠️ <b>Invalid format!</b>\n"
            "Enter your device's current time in <code>HH:MM</code> format (e.g., <code>19:45</code>) "
            "or choose a button below:"
        ),
        "lang_title": "🌐 <b>Interface Language / Язык</b>",
        "lang_current": "Current language: <b>{lang_name}</b>",
        "lang_prompt": "Choose interface language for the bot and Mini App:",
        "lang_updated_cb": "Language updated!",
        "lang_updated_notice": "✅ Interface language changed to: <b>{lang_name}</b>",
        "info_title": "ℹ️ <b>Info</b>\n\nSelect a topic below:",
        "info_btn_reminders": "📋 How to create a reminder",
        "info_btn_notifications": "🔔 Working with notifications",
        "info_btn_settings": "🕒 Choosing a timezone",
        "info_btn_add_user": "👤 How to add a new user",
        "info_btn_app_mode": "📱 App modes",
        "info_btn_general": "🌐 About",
        "info_chat_reminders": (
            "📋 <b>Reminders — How it works</b>\n\n"
            "• <b>Create:</b> tap «Create reminder», send text directly to the chat, or forward a message from any other chat.\n\n"
            "• <b>Date &amp; time:</b> pick a quick button («Today», «Tomorrow», «In a week», «In a month») or any date in the «Calendar». Pick an exact 24-hour time or tap the quick time button (15:00).\n\n"
            "• <b>Recurrence:</b> create a one-time reminder («Once») or a recurring one («Daily», «Weekly», «Every 2 weeks», «Monthly», «Yearly»).\n\n"
            "• <b>When triggered:</b> you can snooze a notification («5 min», «30 min», «1 hour», «1 day») or reschedule it with «Repeat».\n\n"
            "• <b>Editing:</b> in «Reminders», tap «Edit reminders» and choose the reminder number (or type it) to change its text, date, time, recurrence, or delete it.\n\n"
            "• <b>Quick edit:</b> swipe left / reply to any reminder card to instantly update its text."
        ),
        "info_chat_notifications": (
            "🔔 <b>Notifications</b>\n\n"
            "Whenever you have at least one triggered reminder awaiting your action "
            "(«Mark read», «Repeat», or «Snooze»), the «Notifications» section appears "
            "listing all unread notifications."
        ),
        "info_chat_settings": (
            "⚙️ <b>Settings — Why set a timezone</b>\n\n"
            "The server runs in UTC and Telegram does not automatically share your device timezone with bots.\n\n"
            "Setting your timezone ensures that:\n"
            "• the clock and all reminder times match your phone or computer;\n"
            "• reminders trigger at the exact local time you selected;\n"
            "• quick date and time buttons calculate today and the current hour accurately.\n\n"
            "Tip for travel: if you plan a trip across timezones, you can temporarily switch to the destination timezone in /settings, schedule a flight check-in reminder in local time, and then switch back to your home timezone — the reminder will fire at the exact destination local time."
        ),
        "info_chat_add_user": (
            "➕ <b>Adding a new user</b>\n\n"
            "You can invite a new user by their numeric <b>Telegram ID</b>:\n\n"
            "1. <b>How to find a Telegram ID:</b> open @userinfobot and forward any message from the person, or ask them to start @userinfobot and send you the number from the <code>Id</code> line.\n\n"
            "2. <b>How to add:</b> open /settings, tap «Add new user», send the numeric Telegram ID, and enter a display name.\n\n"
            "3. Once added, the invited user receives an invite message and gains immediate access."
        ),
        "info_chat_app_mode": (
            "📱 <b>App modes</b>\n\n"
            "You can use this app in two synchronized modes — as a Telegram chat bot or as a Telegram Mini App."
        ),
        "info_chat_general": (
            "🌐 <b>About</b>\n\n"
            "This bot is an <b>open-source</b> application.\n"
            "Repository:\n{repo}\n\n"
            "Send design and usability feedback to the developer and administrator: "
            "{admin}\n\n"
            "ver. {ver} Last update - {date}"
        ),
        "cal_year_ahead": "⏩ Next year: {month} {year}",
        "cal_year_lbl": "Year: {year}",
        "cal_past_date": "This date is in the past",
        "cal_past_month": "Cannot select a past month",
        "cal_past_year": "Cannot select a past year",
        "cal_past_time": "This time has already passed today",
        "drum_hour_up": "▲ {h:02d} h",
        "drum_hour_down": "▼ {h:02d} h",
        "drum_min_up": "▲ {m:02d} min",
        "drum_min_down": "▼ {m:02d} min",
        "drum_pick": "✅ Select {h:02d}:{m:02d}",
        "btn_today": "Today",
        "btn_tomorrow": "Tomorrow",
        "btn_in_week": "In a week",
        "btn_in_month": "In a month",
        "btn_in_year": "In a year",
        "btn_calendar": "📅 Calendar",
        "btn_once": "Once",
        "btn_once_ico": "1️⃣ Once",
        "btn_recurring": "🔁 Recurring",
        "btn_rec_daily": "Daily",
        "btn_rec_weekly": "Weekly",
        "btn_rec_biweekly": "Every 2 weeks",
        "btn_rec_monthly": "Monthly",
        "btn_rec_yearly": "Yearly",
        "btn_rec_daily_ico": "📅 Daily",
        "btn_rec_weekly_ico": "🗓 Weekly",
        "btn_rec_biweekly_ico": "📆 Every 2 weeks",
        "btn_rec_monthly_ico": "🌙 Monthly",
        "btn_rec_yearly_ico": "🎉 Yearly",
        "btn_set_1500": "⏰ Set 15:00",
        "skip_today_15": "Today at 15:00",
        "skip_today_at": "Today at {time}",
        "skip_tomorrow_15": "Tomorrow at 15:00",
        "skip_tomorrow_at": "Tomorrow at {time}",
        "skip_week_15": "In a week at 15:00",
        "skip_month_15": "In a month at 15:00",
        "skip_year_15": "In a year at 15:00",
        "skip_date_at": "{date} at {time}",
        "create_step1_title": "✍️ <b>Create reminder – Step 1 of 4</b>",
        "create_step1_prompt": "Enter reminder text or forward a message from any chat",
        "create_step2_header": "📅 <b>Create reminder – Step 2 of 4</b>",
        "create_step2_body": "{header}\nSelect a date\n\n💬 <b>Message:</b>\n{text}",
        "create_expired_cb": "Session expired. Please start again.",
        "create_expired_notice": "ℹ️ <b>Reminder creation session expired.</b> Tap «➕ Create reminder» or send text again.",
        "create_stale_btn": "Button expired. Start again or open the main menu.",
        "create_hour_prompt": (
            "⏰ <b>Create reminder — Pick hour</b>\n\n"
            "💬 <b>Message:</b>\n{text}\n\n"
            "📅 <b>Date:</b> <code>{date}</code>\n\n"
            "{err_block}"
            "Tap <b>«{skip}»</b>, pick an <b>hour</b> below, "
            "or type time in 24-hour format (e.g., <code>09:30</code>):"
        ),
        "create_min_prompt": (
            "⏰ <b>Create reminder — Pick minutes</b>\n\n"
            "💬 <b>Message:</b>\n{text}\n\n"
            "📅 <b>Date:</b> <code>{date}</code>\n"
            "🕒 <b>Selected time:</b> <code>{h:02d}:{m:02d}</code>\n\n"
            "{err_block}"
            "Pick a preset below or spin the <b>wheel</b> (▲/▼) to the exact minute:"
        ),
        "create_cal_prompt": (
            "📅 <b>Calendar — Pick date</b>\n\n"
            "💬 <b>Message:</b>\n{text}\n\n"
            "{err_block}"
            "Pick a day in the calendar, tap the <b>month &amp; year</b> header to switch years, "
            "or send a date (<code>DD.MM.YYYY</code>):"
        ),
        "create_ym_prompt": (
            "📅 <b>Quick year &amp; month picker</b>\n\n"
            "💬 <b>Message:</b>\n{text}\n\n"
            "Tap <b>«Next year»</b>, use <code>&lt;</code> <code>&gt;</code> to change year, "
            "or choose a month:"
        ),
        "create_rec_type_prompt": (
            "🔁 <b>Create reminder — Recurrence</b>\n\n"
            "💬 <b>Message:</b>\n{text}\n\n"
            "📅 <b>Date:</b> <code>{date}</code>\n"
            "⏰ <b>Time:</b> <code>{time}</code>\n\n"
            "Select reminder type:"
        ),
        "create_rec_period_prompt": (
            "🔁 <b>Select recurrence interval</b>\n\n"
            "💬 <b>Message:</b>\n{text}\n\n"
            "📅 <b>First trigger:</b> <code>{date} at {time}</code>\n\n"
            "How often should this reminder repeat?"
        ),
        "err_bad_date_create": "Invalid date format! Pick a day in the calendar or enter DD.MM.YYYY.",
        "err_past_date_create": "That date is in the past! Please choose a future date.",
        "err_past_time": "Selected time has already passed. Please choose a later time",
        "err_bad_time_create": "Invalid time format! Pick an hour or enter HH:MM (24h).",
        "msg_doc": "📎 Document: {name}",
        "msg_doc_fallback": "file",
        "msg_photo": "🖼 Photo",
        "msg_video": "🎬 Video",
        "msg_voice": "🎤 Voice message",
        "msg_audio": "🎵 Audio: {title}",
        "msg_audio_fallback": "audio file",
        "msg_video_note": "📹 Video note",
        "msg_contact": "👤 Contact: {name} ({phone})",
        "msg_location": "📍 Location: {lat}, {lon}",
        "msg_poll": "📊 Poll: {question}",
        "msg_forwarded": "📌 Forwarded message",
        "grp_today": "Today, {day} ⏰",
        "grp_tomorrow": "Tomorrow, {day} 🕰",
        "grp_day_after": "Day after tomorrow, {day} 🕑",
        "grp_very_soon": "Very soon ⌛️",
        "grp_in_week": "In a week 📅",
        "grp_in_year": "In a year",
        "grp_in_half_year": "In 6 months",
        "grp_in_month": "In a month",
        "grp_near_future": "Coming up ⏳",
        "rem_at_time": "At {time}",
        "rem_date_at_time": "{date}, at {time}",
        "rem_num_prefix": "#{idx} - ",
        "rem_empty": "You have no active reminders yet.",
        "rem_inactive": "Reminder is no longer active.",
        "rem_not_found_or_sent": "Reminder not found or already triggered.",
        "btn_undo_delete": "↩️ Undo delete",
        "btn_edit_rems": "✏️ Edit reminders",
        "btn_del_rem": "🗑 Delete reminder",
        "btn_edit_text": "✏️ Edit text",
        "btn_edit_date": "📅 Change date",
        "btn_edit_time": "⏰ Change time",
        "btn_edit_rec": "🔁 Change recurrence",
        "cb_pick_num_edit": "Pick a number to edit",
        "cb_pick_num_del": "Pick a number to delete",
        "rem_deleted_num": "Reminder #{num} deleted.",
        "rem_deleted": "Reminder deleted.",
        "undo_unavailable": "Undo is no longer available",
        "undo_done": "Deletion undone",
        "rem_num_not_found": "Reminder #{num} not found.",
        "rem_manage_card": (
            "Manage reminder{title_num}\n"
            "{notice_block}"
            "{dt_str}"
            "{rec_line}\n"
            "{text}\n\n"
            "Choose an action:"
        ),
        "rem_text_updated": "Reminder text updated.",
        "edit_cal_prompt": (
            "Calendar — Pick a new date\n"
            "{text}\n\n"
            "{err_block}"
            "Pick a date in the calendar, tap the month & year header to change year, "
            "or send a date (DD.MM.YYYY):"
        ),
        "edit_ym_prompt": (
            "Quick year & month picker\n"
            "{text}\n\n"
            "Tap «Next year», use < > arrows to change year, or select a month:"
        ),
        "edit_date_prompt": (
            "Change reminder date\n"
            "{dt_str}\n"
            "{text}\n\n"
            "Choose a new date below or open Calendar:"
        ),
        "edit_hour_prompt": (
            "Change reminder time — Pick hour\n"
            "Date: {date}\n"
            "{text}\n\n"
            "{err_block}"
            "Tap «{skip}», pick an hour below, or send time (HH:MM):"
        ),
        "edit_min_prompt": (
            "Change reminder time — Pick minutes\n"
            "Date: {date}\n"
            "Selected time: {h:02d}:{m:02d}\n"
            "{text}\n\n"
            "Pick a time below or spin the wheel (▲/▼):"
        ),
        "edit_old_time_passed": "Previous time ({time}) has already passed today.",
        "edit_date_changed": "Date changed to {date}.",
        "edit_bad_date": "Invalid date format. Pick a date in the calendar or enter DD.MM.YYYY.",
        "edit_past_date": "That date is in the past. Please choose a valid date.",
        "edit_time_changed": "Reminder time changed to {dt_str} ({tz}).",
        "edit_bad_time": "Invalid time format. Pick an hour or enter HH:MM (24h).",
        "edit_rec_prompt": (
            "Change reminder recurrence\n"
            "Current: {rec}\n"
            "{text}\n\n"
            "Choose trigger mode:"
        ),
        "edit_rec_period_prompt": (
            "Choose recurrence interval\n"
            "{text}\n\n"
            "How often should this reminder repeat?"
        ),
        "edit_rec_once_done": "Mode set to: Once.",
        "edit_rec_changed": "Recurrence changed to: {rec}.",
        "notif_section_panel": (
            "🔔 <b>Notifications</b>\n\n"
            "Unread notifications: <b>{count}</b>\n"
            "Choose an action under any notification above:"
        ),
        "btn_notif_repeat": "🔁 Repeat",
        "btn_notif_snooze": "⏳ Snooze",
        "btn_notif_ack": "✅ Read",
        "notif_already_done": "Notification already handled",
        "notif_acked_cb": "Marked as read",
        "notif_rem_not_found": "Reminder not found",
        "notif_pick_snooze": "Choose snooze duration",
        "notif_snooze_missing_rem": "Original reminder not found. Notification was kept.",
        "notif_snoozed_cb": "Snoozed for {label}",
        "users_title": "👥 <b>Users</b>",
        "users_empty": "User list is empty.",
        "users_total": "Total users with access: <b>{count}</b>",
        "users_my_empty": "You haven't invited any users yet.",
        "users_my_total": "Users invited by you (<b>{count}</b>):",
        "users_empty_notice": "ℹ️ User list is empty.",
        "users_no_removable": "ℹ️ No removable users.",
        "my_users_no_del": "ℹ️ You have no invited users to delete.",
        "my_users_no_edit": "ℹ️ You have no invited users to edit.",
        "users_cannot_del_admin": "⚠️ Cannot delete the bot administrator.",
        "users_not_found_del": "⚠️ User <code>{uid}</code> not found or cannot be deleted.",
        "users_not_found_my": "⚠️ User <code>{uid}</code> not found among your invited users.",
        "users_not_found": "⚠️ User <code>{uid}</code> not found.",
        "users_not_found_short": "⚠️ User not found.",
        "users_not_found_my_short": "⚠️ User not found among your invited users.",
        "users_not_found_db": "⚠️ User <code>{uid}</code> not found in database.",
        "users_del_failed": "⚠️ Failed to delete user <code>{uid}</code>.",
        "users_del_confirm": (
            "🗑 <b>Delete user</b>\n\n"
            "👤 <b>Name:</b> {name}\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n\n"
            "Are you sure you want to delete this user and revoke their access?"
        ),
        "users_admin_my_title": "👥 <b>My users (added by administrator)</b>",
        "users_admin_my_empty": "No users added by administrator yet.",
        "users_admin_my_total": "Added by you: <b>{count}</b>",
        "users_admin_all_title": "👥 <b>All users (invited by other users)</b>",
        "users_admin_all_empty": "No users invited by other members yet.",
        "users_admin_all_total": "Invited by other users: <b>{count}</b>",
        "users_added_date": "📅 Added on: <code>{dt}</code>",
        "users_added_by": "➕ Invited by: {inviter}",
        "btn_my_users": "My users",
        "btn_all_users": "All users",
        "btn_edit_user": "✏️ Edit user",
        "btn_del_user": "🗑 Delete user",
        "btn_edit_user_name": "✏️ Rename",
        "add_user_prompt": (
            "➕ <b>Add new user</b>\n\n"
            "Send the new user's <b>numeric Telegram ID</b> (digits only, e.g.: 123456789).\n"
            "You can find any Telegram ID via @userinfobot"
        ),
        "add_user_bad_id": "⚠️ <b>Invalid Telegram ID!</b> Please send digits only:",
        "add_user_title": "➕ <b>Add new user</b>",
        "add_user_dup_admin": (
            "⚠️ <b>This user already exists!</b>\n"
            "👤 Name: <b>{name}</b>\n"
            "🆔 Telegram ID: <code>{uid}</code> ({role})"
        ),
        "add_user_dup_user": "⚠️ <b>User <code>{uid}</code> already exists!</b>",
        "add_user_dup_retry": "Enter another <b>Telegram ID</b> or go back:",
        "add_user_dup_short": "⚠️ <b>This user already exists!</b> (<code>{uid}</code>)",
        "add_user_ask_name": (
            "➕ <b>Add new user</b>\n\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n\n"
            "Now send the <b>user's name</b> (e.g.: <code>Alex</code> or <code>Maria</code>):"
        ),
        "add_user_bad_name": (
            "➕ <b>Add new user</b>\n\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n\n"
            "⚠️ <b>Invalid name!</b>\n"
            "Enter a name (up to 100 characters):"
        ),
        "add_user_invite_sent": "invitation sent",
        "add_user_invite_pending": "will get access as soon as they start the bot (/start)",
        "add_user_success": "✅ <b>User {name} (<code>{uid}</code>) added</b> ({status}).",
        "user_card_my": (
            "✏️ <b>User card</b>\n\n"
            "{notice_block}"
            "👤 <b>Name:</b> {name}\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n\n"
            "Choose an action:"
        ),
        "user_card_admin": (
            "✏️ <b>User card</b>\n\n"
            "{notice_block}"
            "👤 <b>Name:</b> {name}\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n"
            "🔑 <b>Role:</b> {role}\n\n"
            "Choose an action:"
        ),
        "user_bad_num_or_id": "⚠️ <b>Invalid number or Telegram ID!</b> Pick a number below:",
        "user_edit_name_prompt": (
            "✏️ <b>Rename user</b>\n\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n"
            "👤 <b>Current name:</b> {name}\n\n"
            "Send the <b>new name</b> for this user:"
        ),
        "user_edit_name_bad": (
            "✏️ <b>Rename user</b>\n\n"
            "🆔 <b>Telegram ID:</b> <code>{uid}</code>\n\n"
            "⚠️ <b>Invalid name!</b>\n"
            "Enter a new name (1 to 100 characters):"
        ),
        "user_name_updated": "✅ <b>Name changed to «{name}»!</b>",
        "user_deleted_cb": "User deleted",
        "user_del_notified": "notification sent",
        "user_del_closed": "access revoked",
        "user_del_success": "✅ <b>User {label} deleted</b> ({status}).",
        "api_missing_init_data": "Missing Telegram initData signature",
        "api_bad_init_data": "Invalid initData signature",
        "api_invalid_sig": "Telegram initData verification failed",
        "api_bad_auth_date": "Invalid auth date",
        "api_session_expired": "Mini App session expired, please reopen",
        "api_missing_user": "Missing user data in initData",
        "api_bad_user": "Invalid user data",
        "api_enter_text": "Enter reminder text",
        "api_text_too_long": "Reminder text must not exceed 1000 characters",
        "api_html_too_long": "Formatted text is too long",
        "api_bad_datetime": "Invalid date or time format",
        "api_rem_not_found": "Reminder not found or already triggered",
        "api_rem_inactive": "Reminder is no longer active",
        "api_rem_already_deleted": "Reminder already deleted",
        "api_undo_unavailable": "Undo is no longer available",
        "api_notif_not_found": "Original reminder not found",
        "api_notif_text_not_found": "Reminder text not found",
        "api_bad_time_hhmm": "Enter time in HH:MM format (24h)",
        "api_bad_time_range": "Invalid time (00:00–23:59)",
        "api_tz_payload_missing": "Provide offset_minutes or device_time",
        "api_user_exists": "User {uid} already exists",
        "api_user_exists_short": "This user already exists",
        "api_user_not_found": "User not found",
        "api_cannot_del_admin": "Cannot delete the bot administrator",
    },
}


def t(lang: str | None, key: str, **kwargs) -> str:
    norm = normalize_lang(lang)
    table = TRANSLATIONS.get(norm, TRANSLATIONS[DEFAULT_LANG])
    template = table.get(key)
    if template is None:
        template = TRANSLATIONS[DEFAULT_LANG].get(key, key)
    if kwargs:
        return template.format(**kwargs)
    return template


def get_lang_display_name(lang: str | None) -> str:
    return LANG_NAMES.get(normalize_lang(lang), LANG_NAMES[DEFAULT_LANG])


def format_recurrence_label(recurrence: str, lang: str = DEFAULT_LANG) -> str:
    table = RECURRENCE_LABELS_BY_LANG.get(normalize_lang(lang), RECURRENCE_LABELS_BY_LANG[DEFAULT_LANG])
    return table.get(recurrence, "")


def format_tz_label(offset_minutes: int, lang: str = DEFAULT_LANG) -> str:
    tz_map = TZ_ABBR_MAPS.get(normalize_lang(lang), TZ_ABBR_MAPS[DEFAULT_LANG])
    if offset_minutes in tz_map:
        return tz_map[offset_minutes]
    sign = "+" if offset_minutes >= 0 else "-"
    total = abs(offset_minutes)
    hours, mins = divmod(total, 60)
    if mins:
        return f"UTC{sign}{hours}:{mins:02d}"
    return f"UTC{sign}{hours}"


def get_tz_presets(lang: str = DEFAULT_LANG) -> list[dict]:
    tz_map = TZ_ABBR_MAPS.get(normalize_lang(lang), TZ_ABBR_MAPS[DEFAULT_LANG])
    return [{"offset_minutes": mins, "label": label} for mins, label in sorted(tz_map.items())]


def get_snooze_label(interval_code: str, lang: str = DEFAULT_LANG) -> str:
    table = SNOOZE_LABELS_BY_LANG.get(normalize_lang(lang), SNOOZE_LABELS_BY_LANG[DEFAULT_LANG])
    return table.get(interval_code, table["1d"])


def format_date_human(target_date: date, current_year: int, lang: str = DEFAULT_LANG) -> str:
    norm = normalize_lang(lang)
    month_str = MONTHS_GENITIVE[norm][target_date.month]
    if target_date.year == current_year:
        return f"{target_date.day} {month_str}"
    return f"{target_date.day} {month_str} {target_date.year}"


def format_full_date_human(target_date: date, lang: str = DEFAULT_LANG) -> str:
    norm = normalize_lang(lang)
    return f"{target_date.day} {MONTHS_GENITIVE[norm][target_date.month]} {target_date.year}"


def format_date_with_weekday(target_date: date, lang: str = DEFAULT_LANG) -> str:
    norm = normalize_lang(lang)
    return f"{target_date.strftime('%d.%m.%Y')}, {WEEKDAYS[norm][target_date.weekday()]}"


def format_header_day(target_date: date, lang: str = DEFAULT_LANG) -> str:
    norm = normalize_lang(lang)
    return f"{WEEKDAYS[norm][target_date.weekday()]}, {target_date.day} {MONTHS_GENITIVE[norm][target_date.month]}"


def format_created_reminder_dt(local_dt: datetime, today: date, lang: str = DEFAULT_LANG) -> str:
    norm = normalize_lang(lang)
    target_date = local_dt.date()
    time_str = local_dt.strftime("%H:%M")
    if target_date == today:
        prefix = "Сегодня" if norm == "ru" else "Today"
        return f"{prefix}, {WEEKDAYS_ON_DAY[norm][target_date.weekday()]}, {time_str}"
    if target_date == today + timedelta(days=1):
        prefix = "Завтра" if norm == "ru" else "Tomorrow"
        return f"{prefix}, {WEEKDAYS_ON_DAY[norm][target_date.weekday()]}, {time_str}"
    return f"{format_date_with_weekday(target_date, norm)}, {time_str}"


def get_webapp_info_cards(
    lang: str, repo_url: str, admin_username: str, version_str: str, last_update: str,
) -> list[dict[str, str]]:
    if normalize_lang(lang) == "en":
        return [
            {
                "title": "📋 How to create a reminder",
                "body": (
                    "Tap «Create reminder», enter text, choose a quick time or date (or any date in the calendar), "
                    "exact 24-hour time, and recurrence (once, daily, weekly, every 2 weeks, monthly, or yearly). "
                    "Active reminders can be edited or deleted with instant undo."
                ),
            },
            {
                "title": "🔔 Working with notifications",
                "body": (
                    "All triggered reminders awaiting action appear in «Notifications». "
                    "Each notification can be marked as read, snoozed (5 min, 30 min, 1 hour, 1 day), "
                    "or rescheduled with «Repeat»."
                ),
            },
            {
                "title": "🕒 Choosing a timezone",
                "body": (
                    "The server stores reminders in UTC. Set your timezone in «Settings» "
                    "by syncing with your device, picking a city, or entering your local HH:MM time (24h), "
                    "so notifications arrive strictly on time."
                ),
            },
            {
                "title": "👤 How to add a new user",
                "body": (
                    "Get the person's numeric Telegram ID via @userinfobot, open «People» → «Add new user», "
                    "and enter their ID and name. They will immediately gain access to the bot."
                ),
            },
            {
                "title": "📱 App modes",
                "body": "You can use this app in two synchronized modes — as a Telegram chat bot or as a Telegram Mini App.",
            },
            {
                "title": "🌐 About",
                "body": (
                    f"Open-source app «Reminder Bot».\n"
                    f"Repository: {repo_url}\n"
                    f"Developer: {admin_username}\n"
                    f"ver. {version_str} Last update - {last_update}"
                ),
            },
        ]

    return [
        {
            "title": "📋 Как создать напоминание",
            "body": (
                "Нажмите «Создать напоминание», укажите текст, выберите быстрое время или дату (либо любую дату "
                "в календаре), точное время и периодичность (разовое, ежедневно, раз в неделю, "
                "раз в две недели, ежемесячно или ежегодно). Активные напоминания можно редактировать "
                "и удалять с возможностью мгновенной отмены."
            ),
        },
        {
            "title": "🔔 Работа с уведомлениями",
            "body": (
                "Все сработавшие напоминания без реакции попадают в раздел «Уведомления». "
                "Каждое уведомление можно отметить прочитанным, отложить (5 мин, 30 мин, 1 час, 1 день) "
                "или перезапустить кнопкой «Повторить»."
            ),
        },
        {
            "title": "🕒 Выбор часового пояса",
            "body": (
                "Сервер хранит напоминания в UTC. Настройте свой часовой пояс в «Настройках» "
                "кнопкой автосинхронизации с устройством, выбором города или вводом времени ЧЧ:ММ, "
                "чтобы уведомления приходили строго по местному времени."
            ),
        },
        {
            "title": "👤 Как добавить нового пользователя",
            "body": (
                "Узнайте числовой Telegram ID участника через @userinfobot, откройте раздел "
                "«Пользователи» → «Добавить пользователя», введите ID и имя. После этого участник "
                "сразу получит доступ к боту."
            ),
        },
        {
            "title": "📱 Вид приложения",
            "body": "Приложение можно использовать в двух вариантах - как чат в Телеграм или как мини-приложение.",
        },
        {
            "title": "🌐 О приложении",
            "body": (
                f"Open-source приложение «Напоминалкин».\n"
                f"Репозиторий: {repo_url}\n"
                f"Разработчик: {admin_username}\n"
                f"ver. {version_str} Last update - {last_update}"
            ),
        },
    ]
