import html
from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import REPOSITORY_URL, ADMIN_TG_USERNAME, get_app_version_info
from keyboards import info_menu_kb, info_card_kb
from .common import safe_delete_message, render_panel

router = Router()


async def show_info_main(bot: Bot, user_id: int) -> None:
    text = (
        "ℹ️ <b>Раздел «Информация»</b>\n\n"
        "Выберите интересующий вас раздел ниже:"
    )
    await render_panel(
        bot=bot,
        user_id=user_id,
        text=text,
        reply_markup=info_menu_kb(),
    )


@router.message(Command("info", ignore_case=True))
async def cmd_info(message: Message, state: FSMContext, bot: Bot) -> None:
    await safe_delete_message(bot, message.chat.id, message.message_id)
    await state.clear()
    await show_info_main(bot, message.from_user.id)


@router.callback_query(F.data == "info:main")
async def cb_info_main(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await show_info_main(bot, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "info:reminders")
async def cb_info_reminders(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    text = (
        "📋 <b>Напоминания — как работать</b>\n\n"
        "• <b>Создание:</b> нажмите «Создать напоминание», просто напишите текст в чат или перешлите в бот сообщение из любого другого чата.\n\n"
        "• <b>Дата и время:</b> выберите одну из кнопок («Сегодня», «Завтра», «Через неделю», «Через месяц») или выберите любую дату через «Календарь». Укажите точное время или нажмите кнопку быстрого выбора времени (15:00).\n\n"
        "• <b>Периодичность:</b> можно создать разовое напоминание («Один раз») или повторяющееся («Каждый день», «Раз в неделю», «Каждые две недели», «Ежемесячно», «Ежегодно»).\n\n"
        "• <b>При срабатывании:</b> уведомление можно отложить («5 минут», «30 минут», «1 час», «1 день») или перезапустить кнопкой «Повторить».\n\n"
        "• <b>Редактирование:</b> в разделе /reminders показаны все активные напоминания по номерам — нажмите «Редактировать напоминания» и выберите нужное напоминание кнопкой (или введите его номер), чтобы изменить текст, дату, время или удалить запись."
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=info_card_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "info:settings")
async def cb_info_settings(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    text = (
        "⚙️ <b>Настройки — для чего задавать часовой пояс</b>\n\n"
        "Сервер бота работает в универсальном времени (UTC), а Telegram не передаёт боту часовой пояс вашего устройства автоматически.\n\n"
        "Задание часового пояса необходимо для того, чтобы:\n"
        "• текущее время на пульте и время всех напоминаний отображались точно по часам вашего смартфона или компьютера;\n"
        "• напоминания срабатывали строго в указанный вами час по вашему местному времени;\n"
        "• кнопки быстрого выбора даты и времени корректно определяли текущий день и час для вашего региона."
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=info_card_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "info:add_user")
async def cb_info_add_user(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    text = (
        "➕ <b>Добавление нового пользователя</b>\n\n"
        "Вы можете пригласить нового пользователя в бот по его числовому <b>Telegram ID</b>:\n\n"
        "1. <b>Как узнать Telegram ID:</b> откройте бот @userinfobot и перешлите в него любое сообщение от человека, которого хотите пригласить. Также в боте можно нажать кнопку User и выбрать имя пользователя из списка Ваших контактов. Либо попросите нового пользователя запустить @userinfobot и прислать вам число из строки <code>Id</code>.\n\n"
        "2. <b>Как добавить в бот:</b> откройте раздел /settings, нажмите кнопку «Добавить нового пользователя», отправьте полученный числовой Telegram ID и укажите имя пользователя.\n\n"
        "3. После добавления новому участнику придёт приглашение, и он сможет пользоваться ботом."
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=info_card_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "info:general")
async def cb_info_general(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    safe_repo = html.escape(REPOSITORY_URL)
    safe_admin = html.escape(ADMIN_TG_USERNAME)
    version_str, last_update_str = get_app_version_info()

    text = (
        "🌐 <b>О приложении</b>\n\n"
        "Этот бот — <b>open-source</b> приложение.\n"
        f"Репозиторий находится по адресу:\n{safe_repo}\n\n"
        "Предложения по улучшению дизайна и юзабилити направлять создателю и администратору бота "
        f"{safe_admin}\n\n"
        f"ver. {version_str} Last update - {last_update_str}"
    )
    await render_panel(
        bot=bot,
        user_id=callback.from_user.id,
        text=text,
        reply_markup=info_card_kb(),
    )
    await callback.answer()
