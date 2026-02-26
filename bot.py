import telebot
import requests
import os
import sqlite3
import threading
import time
import re
import urllib.parse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# Загружаем переменные из .env файла
load_dotenv()

# Получаем токены
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

# Создаём бота
bot = telebot.TeleBot(BOT_TOKEN)

# Информация о создателе
CREATOR_NAME = "Pavel"
CREATOR_NICKNAME = "@Gdrag182"
BOT_VERSION = "2.0"

# Словарь для хранения временных данных пользователей
user_data = {}

# Словарь для перевода погодных условий
weather_conditions = {
    'clear': 'Ясно ☀️',
    'clouds': 'Облачно ☁️',
    'rain': 'Дождь 🌧',
    'snow': 'Снег ❄️',
    'thunderstorm': 'Гроза ⛈',
    'mist': 'Туман 🌫',
    'fog': 'Туман 🌫',
    'drizzle': 'Морось 🌧'
}

# Дни недели
week_days = {
    'monday': 'Понедельник',
    'tuesday': 'Вторник',
    'wednesday': 'Среда',
    'thursday': 'Четверг',
    'friday': 'Пятница',
    'saturday': 'Суббота',
    'sunday': 'Воскресенье'
}

# Популярные города
popular_cities = ['Москва', 'Санкт-Петербург', 'Новосибирск', 'Екатеринбург',
                  'Кемерово', 'Прокопьевск']


# Создаём базу данных для напоминаний
def init_database():
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()

    # Проверяем, существует ли таблица
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reminders'")
    table_exists = cursor.fetchone()

    if table_exists:
        # Проверяем, есть ли колонка days
        cursor.execute("PRAGMA table_info(reminders)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]

        if 'days' not in column_names:
            # Создаём новую таблицу с правильной структурой
            cursor.execute('''
                CREATE TABLE reminders_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    chat_id INTEGER,
                    city TEXT,
                    reminder_time TEXT,
                    days TEXT DEFAULT 'everyday',
                    is_active BOOLEAN DEFAULT 1
                )
            ''')

            # Копируем данные из старой таблицы
            cursor.execute('''
                INSERT INTO reminders_new (id, user_id, chat_id, city, reminder_time, is_active)
                SELECT id, user_id, chat_id, city, reminder_time, is_active FROM reminders
            ''')

            # Удаляем старую таблицу и переименовываем новую
            cursor.execute("DROP TABLE reminders")
            cursor.execute("ALTER TABLE reminders_new RENAME TO reminders")
        else:
            # Обновляем все NULL значения в поле days
            cursor.execute("UPDATE reminders SET days = 'everyday' WHERE days IS NULL")
    else:
        # Создаём новую таблицу
        cursor.execute('''
            CREATE TABLE reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                city TEXT,
                reminder_time TEXT,
                days TEXT DEFAULT 'everyday',
                is_active BOOLEAN DEFAULT 1
            )
        ''')

    conn.commit()
    conn.close()


# Вызываем при запуске
init_database()


# Функция для добавления напоминания
def add_reminder(user_id, chat_id, city, reminder_time, days='everyday'):
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO reminders (user_id, chat_id, city, reminder_time, days)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, chat_id, city, reminder_time, days))
    conn.commit()
    conn.close()


# Функция для получения активных напоминаний
def get_active_reminders():
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, user_id, chat_id, city, reminder_time, days, is_active FROM reminders WHERE is_active = 1')
    reminders = cursor.fetchall()
    conn.close()
    return reminders


# Функция для удаления напоминания
def delete_reminder(reminder_id):
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE reminders SET is_active = 0 WHERE id = ?', (reminder_id,))
    conn.commit()
    conn.close()


# Функция для получения списка напоминаний пользователя
def get_user_reminders(user_id):
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, user_id, chat_id, city, reminder_time, days, is_active FROM reminders WHERE user_id = ? AND is_active = 1',
        (user_id,))
    reminders = cursor.fetchall()
    conn.close()
    return reminders


# Функция для проверки корректности времени
def is_valid_time(time_str):
    pattern = r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'
    return re.match(pattern, time_str) is not None


# Функция для проверки, нужно ли отправить напоминание сегодня
def should_send_today(days_string):
    if days_string is None:
        return True

    if days_string == "everyday":
        return True

    today = datetime.now().isoweekday()

    if days_string == "workdays":
        return today <= 5
    elif days_string == "weekend":
        return today >= 6
    else:
        days_list = days_string.split(',')
        return str(today) in days_list


# Функция для получения координат города (геокодинг)
def get_city_coordinates(city_name):
    try:
        encoded_city = urllib.parse.quote(city_name)
        url = f'http://api.openweathermap.org/geo/1.0/direct?q={encoded_city}&limit=1&appid={WEATHER_API_KEY}'
        response = requests.get(url)
        data = response.json()

        if data and len(data) > 0:
            lat = data[0]['lat']
            lon = data[0]['lon']
            found_city = data[0].get('local_names', {}).get('ru', data[0]['name'])
            country = data[0].get('country', '')
            return lat, lon, found_city, country
        return None, None, None, None
    except Exception as e:
        print(f"Ошибка геокодинга: {e}")
        return None, None, None, None


# Функция для получения погоды по координатам
def get_weather_by_coords(lat, lon, city_name, country):
    try:
        url = f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru'
        response = requests.get(url)
        data = response.json()

        if response.status_code == 200:
            temperature = data['main']['temp']
            feels_like = data['main']['feels_like']
            humidity = data['main']['humidity']
            pressure = data['main']['pressure']
            wind_speed = data['wind']['speed']
            weather_main = data['weather'][0]['main'].lower()
            weather_description = data['weather'][0]['description']

            weather_emoji = weather_conditions.get(weather_main, '🌡')

            weather_message = (
                f"🏙 *{city_name}, {country}*\n\n"
                f"{weather_emoji} *{weather_description.capitalize()}*\n\n"
                f"🌡 *Температура:* {temperature:.1f}°C\n"
                f"🤔 *Ощущается как:* {feels_like:.1f}°C\n"
                f"💧 *Влажность:* {humidity}%\n"
                f"📊 *Давление:* {pressure} гПа\n"
                f"💨 *Ветер:* {wind_speed} м/с\n\n"
                f"✨ Хорошего дня!"
            )

            return weather_message, None
        else:
            return None, f"❌ Не удалось получить погоду для города {city_name}"

    except Exception as e:
        return None, f"😕 Произошла ошибка. Попробуй позже!"


# Функция для получения погоды (основная, с геокодингом)
def get_weather_info(city):
    try:
        lat, lon, found_city, country = get_city_coordinates(city)

        if lat and lon:
            return get_weather_by_coords(lat, lon, found_city, country)
        else:
            return None, f"❌ Город '{city}' не найден. Проверь название или попробуй написать на английском!"

    except Exception as e:
        print(f"Ошибка: {e}")
        return None, f"😕 Произошла ошибка. Попробуй позже!"


# Фоновая задача для проверки напоминаний
def check_reminders():
    while True:
        try:
            current_time = datetime.now().strftime("%H:%M")
            reminders = get_active_reminders()

            for reminder in reminders:
                try:
                    reminder_id, user_id, chat_id, city, reminder_time, days, is_active = reminder

                    if reminder_time == current_time and should_send_today(days):
                        weather_msg, error_msg = get_weather_info(city)
                        if weather_msg:
                            today_num = datetime.now().isoweekday()
                            day_names = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
                            today_name = day_names.get(today_num, "")

                            bot.send_message(chat_id,
                                             f"🔔 *Напоминание о погоде в {city}!*\n"
                                             f"📅 *{today_name}*\n\n"
                                             f"{weather_msg}",
                                             parse_mode='Markdown')
                except Exception as e:
                    print(f"Ошибка при обработке напоминания: {e}")
                    continue

            time.sleep(60)
        except Exception as e:
            print(f"Ошибка в проверке напоминаний: {e}")
            time.sleep(60)


# Запускаем проверку напоминаний в отдельном потоке
reminder_thread = threading.Thread(target=check_reminders, daemon=True)
reminder_thread.start()


# Создаём клавиатуру с популярными городами
def get_cities_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for city in popular_cities:
        buttons.append(InlineKeyboardButton(city, callback_data=f"city_{city}"))
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton("🔍 Другой город", callback_data="other_city"))
    return keyboard


# Клавиатура для выбора дней недели
def get_days_keyboard(city, time):
    keyboard = InlineKeyboardMarkup(row_width=3)

    days_buttons = [
        InlineKeyboardButton("Пн", callback_data=f"day_{city}_{time}_1"),
        InlineKeyboardButton("Вт", callback_data=f"day_{city}_{time}_2"),
        InlineKeyboardButton("Ср", callback_data=f"day_{city}_{time}_3"),
        InlineKeyboardButton("Чт", callback_data=f"day_{city}_{time}_4"),
        InlineKeyboardButton("Пт", callback_data=f"day_{city}_{time}_5"),
        InlineKeyboardButton("Сб", callback_data=f"day_{city}_{time}_6"),
        InlineKeyboardButton("Вс", callback_data=f"day_{city}_{time}_7")
    ]
    keyboard.add(*days_buttons)

    keyboard.add(
        InlineKeyboardButton("📅 Ежедневно", callback_data=f"day_{city}_{time}_everyday"),
        InlineKeyboardButton("💼 Будни", callback_data=f"day_{city}_{time}_workdays"),
        InlineKeyboardButton("🎉 Выходные", callback_data=f"day_{city}_{time}_weekend")
    )

    keyboard.add(InlineKeyboardButton("🔙 Назад к выбору времени", callback_data=f"back_to_time_{city}"))
    return keyboard


# Клавиатура для выбора времени напоминания
def get_time_keyboard(city):
    keyboard = InlineKeyboardMarkup(row_width=3)
    times = ["07:00", "09:00", "12:00", "15:00", "18:00", "20:00"]
    buttons = []
    for time in times:
        buttons.append(InlineKeyboardButton(time, callback_data=f"time_{city}_{time}"))
    keyboard.add(*buttons)

    keyboard.add(InlineKeyboardButton("✏️ Своё время", callback_data=f"custom_time_{city}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu"))
    return keyboard


# Клавиатура для управления напоминаниями
def get_manage_reminders_keyboard(user_id):
    reminders = get_user_reminders(user_id)
    keyboard = InlineKeyboardMarkup(row_width=1)

    if not reminders:
        keyboard.add(InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu"))
        return keyboard

    for reminder in reminders:
        reminder_id, _, _, city, reminder_time, days, _ = reminder

        if days is None:
            days = "everyday"

        if days == "everyday":
            days_text = "ежедневно"
        elif days == "workdays":
            days_text = "будни"
        elif days == "weekend":
            days_text = "выходные"
        else:
            days_list = days.split(',')
            days_short = []
            day_names = {"1": "Пн", "2": "Вт", "3": "Ср", "4": "Чт",
                         "5": "Пт", "6": "Сб", "7": "Вс"}
            for d in days_list:
                if d in day_names:
                    days_short.append(day_names[d])
            days_text = ", ".join(days_short)

        button_text = f"❌ {city} в {reminder_time} ({days_text})"
        keyboard.add(InlineKeyboardButton(button_text, callback_data=f"delete_{reminder_id}"))

    keyboard.add(InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu"))
    return keyboard


# Создаём главную клавиатуру (ReplyKeyboard)
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("🌤 Узнать погоду"),
        KeyboardButton("🌟 Популярные города"),
        KeyboardButton("⏰ Напомнить о погоде"),
        KeyboardButton("📋 Мои напоминания"),
        KeyboardButton("ℹ️ О боте"),
        KeyboardButton("📞 Помощь"),
        KeyboardButton("👨‍💻 О разработчике")
    ]
    keyboard.add(*buttons)
    return keyboard


# Команда /start с красивым приветствием
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_name = message.from_user.first_name

    welcome_text = (
        f"🌟 *Привет, {user_name}!*\n\n"
        f"Я *WeatherBot* — твой персональный помощник по погоде! 🌤\n\n"
        f"📌 *Что я умею:*\n"
        f"• Показывать текущую погоду в любом городе\n"
        f"• Быстрый просмотр погоды в популярных городах\n"
        f"• Устанавливать напоминания о погоде на выбранные дни ⏰\n"
        f"• Красивое оформление с эмодзи\n\n"
        f"👇 *Нажми на кнопку ниже, чтобы начать!*"
    )

    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown', reply_markup=get_main_keyboard())


# Обработка кнопок главного меню
@bot.message_handler(func=lambda message: True)
def handle_main_keyboard(message):
    if message.text == "🌤 Узнать погоду":
        bot.send_message(message.chat.id,
                         "🏙 *Введите название города* (например: Москва, Лондон, Париж):\n\n"
                         "Или выберите город из списка 👇",
                         parse_mode='Markdown',
                         reply_markup=get_cities_keyboard())

    elif message.text == "🌟 Популярные города":
        bot.send_message(message.chat.id,
                         "🌆 *Популярные города:*\nВыберите город из списка ниже:",
                         parse_mode='Markdown',
                         reply_markup=get_cities_keyboard())

    elif message.text == "⏰ Напомнить о погоде":
        bot.send_message(message.chat.id,
                         "⏰ *Настройка напоминания*\n\n"
                         "Сначала выбери город:",
                         parse_mode='Markdown',
                         reply_markup=get_cities_keyboard())

    elif message.text == "📋 Мои напоминания":
        user_id = message.from_user.id
        reminders = get_user_reminders(user_id)

        if reminders:
            bot.send_message(message.chat.id,
                             "📋 *Твои активные напоминания:*\n\n"
                             "Нажми на напоминание, чтобы удалить его:",
                             parse_mode='Markdown',
                             reply_markup=get_manage_reminders_keyboard(user_id))
        else:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu"))

            bot.send_message(message.chat.id,
                             "📋 *У тебя пока нет активных напоминаний*\n\n"
                             "Нажми «⏰ Напомнить о погоде», чтобы создать новое! 🌤",
                             parse_mode='Markdown',
                             reply_markup=keyboard)

    elif message.text == "ℹ️ О боте":
        about_text = (
            "🤖 *WeatherBot*\n\n"
            f"Версия: {BOT_VERSION}\n"
            "Создан с ❤️ на Python\n\n"
            "📊 *Возможности:*\n"
            "• Текущая погода в реальном времени\n"
            "• Температура, влажность, давление\n"
            "• Скорость ветра\n"
            "• Популярные города для быстрого выбора\n"
            "• Напоминания о погоде с выбором дней ⏰\n"
        )
        bot.send_message(message.chat.id, about_text, parse_mode='Markdown', reply_markup=get_main_keyboard())

    elif message.text == "👨‍💻 О разработчике":
        creator_text = (
            "👨‍💻 *О разработчике*\n\n"
            f"Меня создал *{CREATOR_NAME}* — талантливый разработчик и просто хороший человек! 🌟\n\n"
            f"📱 Связаться с разработчиком: {CREATOR_NICKNAME}\n\n"
            "💡 *Интересные факты:*\n"
            "• Этот бот написан на Python\n"
            "• Код полностью открыт для изучения\n"
            "• Создан с любовью к погоде и технологиям\n\n"
            "🌤 *Пользуйся с удовольствием!*"
        )
        bot.send_message(message.chat.id, creator_text, parse_mode='Markdown', reply_markup=get_main_keyboard())

    elif message.text == "📞 Помощь":
        help_text = (
            "🔍 *Как пользоваться ботом:*\n\n"
            "1️⃣ Нажми *«Узнать погоду»* — узнать погоду сейчас\n"
            "2️⃣ Нажми *«Напомнить о погоде»* — установить напоминание\n"
            "3️⃣ Выбери город, время и дни недели\n"
            "4️⃣ Нажми *«Мои напоминания»* — управлять активными напоминаниями\n\n"
            "✨ *Советы:*\n"
            "• Города можно писать на русском или английском\n"
            "• Можно выбрать несколько дней для напоминания\n"
            "• Есть быстрый выбор: будни, выходные, ежедневно\n"
            "• Можно указать своё время (например, 14:30)\n\n"
            "📝 *Примеры:* Москва, Лондон, Париж\n\n"
            "❓ *Есть вопросы?* Напиши разработчику!"
        )
        bot.send_message(message.chat.id, help_text, parse_mode='Markdown', reply_markup=get_main_keyboard())

    else:
        user_id = message.from_user.id
        if user_id in user_data and user_data[user_id].get('awaiting_time'):
            city = user_data[user_id]['city']
            time_str = message.text.strip()

            if is_valid_time(time_str):
                user_data[user_id] = {'city': city, 'time': time_str, 'awaiting_days': True}
                bot.send_message(message.chat.id,
                                 f"⏰ *Выбери дни для напоминания*\n\n"
                                 f"📍 Город: {city}\n"
                                 f"⏱ Время: {time_str}\n\n"
                                 f"В какие дни присылать прогноз?",
                                 parse_mode='Markdown',
                                 reply_markup=get_days_keyboard(city, time_str))
            else:
                bot.send_message(message.chat.id,
                                 "❌ *Некорректное время!*\n\n"
                                 "Пожалуйста, введи время в формате *ЧЧ:ММ* (например, 14:30 или 09:15)",
                                 parse_mode='Markdown')
        else:
            bot.send_chat_action(message.chat.id, 'typing')
            city = message.text
            weather_msg, error_msg = get_weather_info(city)

            if weather_msg:
                bot.send_message(message.chat.id, weather_msg, parse_mode='Markdown')

                keyboard = InlineKeyboardMarkup(row_width=2)
                keyboard.add(
                    InlineKeyboardButton("🔄 Другой город", callback_data="other_city"),
                    InlineKeyboardButton("🌟 Популярные", callback_data="show_popular"),
                    InlineKeyboardButton("⏰ Напомнить", callback_data=f"set_reminder_{city}")
                )
                bot.send_message(message.chat.id, "👇 *Что делаем дальше?*",
                                 parse_mode='Markdown', reply_markup=keyboard)
            else:
                bot.send_message(message.chat.id, error_msg)


# Обработка нажатий на инлайн-кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data.startswith("city_"):
        city = call.data.replace("city_", "")
        bot.answer_callback_query(call.id, f"Ищем погоду в {city}...")

        weather_msg, error_msg = get_weather_info(city)

        if weather_msg:
            bot.send_message(call.message.chat.id, weather_msg, parse_mode='Markdown')

            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton("🔄 Другой город", callback_data="other_city"),
                InlineKeyboardButton("🌟 Популярные", callback_data="show_popular"),
                InlineKeyboardButton("⏰ Напомнить", callback_data=f"set_reminder_{city}")
            )
            bot.send_message(call.message.chat.id, "👇 *Что делаем дальше?*",
                             parse_mode='Markdown', reply_markup=keyboard)
        else:
            bot.send_message(call.message.chat.id, error_msg)

    elif call.data.startswith("set_reminder_"):
        city = call.data.replace("set_reminder_", "")
        bot.send_message(call.message.chat.id,
                         f"⏰ *Выбери время для напоминания о погоде в {city}:*",
                         parse_mode='Markdown',
                         reply_markup=get_time_keyboard(city))

    elif call.data.startswith("time_"):
        parts = call.data.split("_")
        city = parts[1]
        reminder_time = parts[2]
        user_id = call.from_user.id

        user_data[user_id] = {'city': city, 'time': reminder_time, 'awaiting_days': True}
        bot.edit_message_text(f"⏰ *Выбери дни для напоминания*\n\n"
                              f"📍 Город: {city}\n"
                              f"⏱ Время: {reminder_time}\n\n"
                              f"В какие дни присылать прогноз?",
                              call.message.chat.id,
                              call.message.message_id,
                              parse_mode='Markdown',
                              reply_markup=get_days_keyboard(city, reminder_time))

    elif call.data.startswith("custom_time_"):
        city = call.data.replace("custom_time_", "")
        user_id = call.from_user.id

        user_data[user_id] = {'city': city, 'awaiting_time': True}

        bot.edit_message_text(f"✏️ *Введи своё время*\n\n"
                              f"Город: {city}\n\n"
                              f"Напиши время в формате *ЧЧ:ММ*\n"
                              f"Например: 14:30, 09:15, 23:45\n\n"
                              f"❗️Время должно быть от 00:00 до 23:59",
                              call.message.chat.id,
                              call.message.message_id,
                              parse_mode='Markdown')

    elif call.data.startswith("day_"):
        parts = call.data.split("_")
        city = parts[1]
        reminder_time = parts[2]
        days_option = parts[3]
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        if days_option == "everyday":
            days_string = "everyday"
            days_text = "ежедневно"
        elif days_option == "workdays":
            days_string = "workdays"
            days_text = "будни (Пн-Пт)"
        elif days_option == "weekend":
            days_string = "weekend"
            days_text = "выходные (Сб, Вс)"
        else:
            days_string = days_option
            day_names = {"1": "Пн", "2": "Вт", "3": "Ср", "4": "Чт",
                         "5": "Пт", "6": "Сб", "7": "Вс"}
            days_text = day_names.get(days_option, "")

        add_reminder(user_id, chat_id, city, reminder_time, days_string)

        success_text = (
            f"✅ *Напоминание установлено!*\n\n"
            f"📍 Город: {city}\n"
            f"⏰ Время: {reminder_time}\n"
            f"📅 Дни: {days_text}\n\n"
            f"Я буду присылать тебе погоду в выбранные дни! 🌤"
        )

        bot.edit_message_text(success_text,
                              chat_id,
                              call.message.message_id,
                              parse_mode='Markdown')

        bot.send_message(chat_id, "👇 *Что делаем дальше?*",
                         parse_mode='Markdown', reply_markup=get_main_keyboard())

        if user_id in user_data:
            del user_data[user_id]

    elif call.data.startswith("delete_"):
        reminder_id = call.data.replace("delete_", "")
        delete_reminder(reminder_id)

        bot.answer_callback_query(call.id, "✅ Напоминание удалено!")

        user_id = call.from_user.id
        reminders = get_user_reminders(user_id)

        if reminders:
            bot.edit_message_text("📋 *Твои активные напоминания:*\n\n"
                                  "Нажми на напоминание, чтобы удалить его:",
                                  call.message.chat.id,
                                  call.message.message_id,
                                  parse_mode='Markdown',
                                  reply_markup=get_manage_reminders_keyboard(user_id))
        else:
            bot.edit_message_text("📋 *У тебя больше нет активных напоминаний*",
                                  call.message.chat.id,
                                  call.message.message_id,
                                  parse_mode='Markdown')
            bot.send_message(call.message.chat.id,
                             "Хочешь создать новое? Нажми «⏰ Напомнить о погоде»! 🌤",
                             reply_markup=get_main_keyboard())

    elif call.data.startswith("back_to_time_"):
        city = call.data.replace("back_to_time_", "")
        bot.edit_message_text(f"⏰ *Выбери время для напоминания о погоде в {city}:*",
                              call.message.chat.id,
                              call.message.message_id,
                              parse_mode='Markdown',
                              reply_markup=get_time_keyboard(city))

    elif call.data == "other_city":
        bot.send_message(call.message.chat.id,
                         "🏙 *Введите название города:*",
                         parse_mode='Markdown')

    elif call.data == "show_popular":
        bot.send_message(call.message.chat.id,
                         "🌆 *Популярные города:*\nВыберите город из списка:",
                         parse_mode='Markdown',
                         reply_markup=get_cities_keyboard())

    elif call.data == "back_to_menu":
        bot.send_message(call.message.chat.id,
                         "🏠 *Главное меню*",
                         parse_mode='Markdown',
                         reply_markup=get_main_keyboard())

    bot.answer_callback_query(call.id)


# Запускаем бота
if __name__ == '__main__':
    print("✨ Бот погоды запущен...")
    print(f"👨‍💻 Разработчик: {CREATOR_NAME} ({CREATOR_NICKNAME})")
    print(f"📱 Версия: {BOT_VERSION}")
    print("⏰ Система напоминаний активна (с поддержкой дней недели)")
    print("📱 Нажми Ctrl+C для остановки")

    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)
            continue