from aiogram.fsm.state import State, StatesGroup


class ReminderFSM(StatesGroup):
    # Создание напоминания
    waiting_for_text = State()
    waiting_for_date = State()
    waiting_for_custom_date = State()
    waiting_for_time = State()
    waiting_for_recurrence = State()
    # Настройка времени устройства (/settings)
    waiting_for_device_time = State()
    # Управление пользователями (/users и /user)
    waiting_for_new_user_id = State()
    waiting_for_new_user_name = State()
    waiting_for_edit_user_id = State()
    waiting_for_edit_user_name = State()
    waiting_for_del_user_id = State()
    waiting_for_my_edit_user_id = State()
    waiting_for_my_edit_user_name = State()
    waiting_for_my_del_user_id = State()
    # Выбор номера напоминания и его редактирование
    waiting_for_reminder_number = State()
    editing_text = State()
    editing_date = State()
    editing_time = State()
