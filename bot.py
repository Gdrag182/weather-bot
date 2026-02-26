import telebot
import requests
import os
import sqlite3
import threading
import time
import re
import urllib.parse
from datetime import datetime
from dotenv import load_dotenv
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# Загружаем переменные из .env файла
load_dotenv()

# Получаем токены
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

print(f"🔑 Загружен токен бота: {BOT_TOKEN[:10]}...")
print(f"🔑 Загружен API ключ: {WEATHER_API_KEY[:10]}...")

# Создаём бота
bot = telebot.TeleBot(BOT_TOKEN)

# Информация о создателе
CREATOR_NAME = "Pavel"
CREATOR_NICKNAME = "@Gdrag182"
BOT_VERSION = "2.6"

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

# Популярные города
popular_cities = ['Москва', 'Санкт-Петербург', 'Новосибирск', 'Екатеринбург',
                  'Кемерово', 'Прокопьевск']


# Создаём базу данных для напоминаний
def init_database():
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
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
    print("💾 База данных инициализирована")


init_database()


# Функции для работы с БД
def add_reminder(user_id, chat_id, city, reminder_time, days='everyday'):
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO reminders (user_id, chat_id, city, reminder_time, days)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, chat_id, city, reminder_time, days))
    conn.commit()
    conn.close()


def get_active_reminders():
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM reminders WHERE is_active = 1')
    reminders = cursor.fetchall()
    conn.close()
    return reminders


def delete_reminder(reminder_id):
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE reminders SET is_active = 0 WHERE id = ?', (reminder_id,))
    conn.commit()
    conn.close()


def get_user_reminders(user_id):
    conn = sqlite3.connect('reminders.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM reminders WHERE user_id = ? AND is_active = 1', (user_id,))
    reminders = cursor.fetchall()
    conn.close()
    return reminders


def is_valid_time(time_str):
    pattern = r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'
    return re.match(pattern, time_str) is not None


def should_send_today(days_string):
    if days_string is None or days_string == "everyday":
        return True
    today = datetime.now().isoweekday()
    if days_string == "workdays":
        return today <= 5
    elif days_string == "weekend":
        return today >= 6
    else:
        days_list = days_string.split(',')
        return str(today) in days_list


# ОСНОВНАЯ ФУНКЦИЯ ПОЛУЧЕНИЯ ПОГОДЫ (С ОТЛАДКОЙ)
def get_weather_info(city):
    print(f"\n🔍 Поиск погоды для города: {city}")

    # СПОСОБ 1: Прямой запрос с кодом страны RU для русских городов
    try:
        # Проверяем, русский ли город
        if any('\u0400' <= c <= '\u04FF' for c in city):
            url = f'http://api.openweathermap.org/data/2.5/weather?q={city},RU&appid={WEATHER_API_KEY}&units=metric&lang=ru'
            print(f"📡 Запрос 1 (RU): {url.replace(WEATHER_API_KEY, 'HIDDEN')}")

            response = requests.get(url, timeout=10)
            print(f"📥 Статус ответа 1: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                return format_weather_message(data, city), None
    except Exception as e:
        print(f"❌ Ошибка способа 1: {e}")

    # СПОСОБ 2: Обычный запрос
    try:
        url = f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru'
        print(f"📡 Запрос 2: {url.replace(WEATHER_API_KEY, 'HIDDEN')}")

        response = requests.get(url, timeout=10)
        print(f"📥 Статус ответа 2: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            return format_weather_message(data, city), None
    except Exception as e:
        print(f"❌ Ошибка способа 2: {e}")

    # СПОСОБ 3: Без указания языка
    try:
        url = f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric'
        print(f"📡 Запрос 3: {url.replace(WEATHER_API_KEY, 'HIDDEN')}")

        response = requests.get(url, timeout=10)
        print(f"📥 Статус ответа 3: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            temp = data['main']['temp']
            return f"🌡 {city}: {temp:.1f}°C", None
    except Exception as e:
        print(f"❌ Ошибка способа 3: {e}")

    # СПОСОБ 4: Через геокодинг
    try:
        print("📍 Попытка геокодинга...")
        encoded_city = urllib.parse.quote(city)
        geo_url = f'http://api.openweathermap.org/geo/1.0/direct?q={encoded_city}&limit=1&appid={WEATHER_API_KEY}'

        geo_response = requests.get(geo_url, timeout=10)
        geo_data = geo_response.json()

        if geo_data and len(geo_data) > 0:
            lat = geo_data[0]['lat']
            lon = geo_data[0]['lon']
            found_city = geo_data[0].get('local_names', {}).get('ru', geo_data[0]['name'])
            country = geo_data[0].get('country', '')

            print(f"✅ Найдены координаты: {lat}, {lon}")

            weather_url = f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru'
            weather_response = requests.get(weather_url, timeout=10)

            if weather_response.status_code == 200:
                data = weather_response.json()
                return format_weather_message(data, found_city, country), None
    except Exception as e:
        print(f"❌ Ошибка геокодинга: {e}")

    # Если ничего не помогло
    error_msg = f"❌ Город '{city}' не найден.\n"
    error_msg += "Попробуй:\n"
    error_msg += "• Проверить название\n"
    error_msg += "• Написать на английском (Moscow, London)\n"
    error_msg += "• Добавить страну (Moscow, RU)"

    print(f"❌ Город не найден после всех попыток")
    return None, error_msg


def format_weather_message(data, city_name, country=None):
    temperature = data['main']['temp']
    feels_like = data['main']['feels_like']
    humidity = data['main']['humidity']
    pressure = data['main']['pressure']
    wind_speed = data['wind']['speed']
    weather_main = data['weather'][0]['main'].lower()
    weather_description = data['weather'][0]['description']

    if not country and 'sys' in data and 'country' in data['sys']:
        country = data['sys']['country']

    weather_emoji = weather_conditions.get(weather_main, '🌡')

    country_text = f", {country}" if country else ""

    weather_message = (
        f"🏙 *{city_name}{country_text}*\n\n"
        f"{weather_emoji} *{weather_description.capitalize()}*\n\n"
        f"🌡 *Температура:* {temperature:.1f}°C\n"
        f"🤔 *Ощущается как:* {feels_like:.1f}°C\n"
        f"💧 *Влажность:* {humidity}%\n"
        f"📊 *Давление:* {pressure} гПа\n"
        f"💨 *Ветер:* {wind_speed} м/с\n\n"
        f"✨ Хорошего дня!"
    )

    return weather_message


# Фоновая задача для проверки напоминаний
def check_reminders():
    print("⏰ Запущена система напоминаний")
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
                    print(f"Ошибка в напоминании: {e}")
                    continue

            time.sleep(60)
        except Exception as e:
            print(f"Ошибка в системе напоминаний: {e}")
            time.sleep(60)


reminder_thread = threading.Thread(target=check_reminders, daemon=True)
reminder_thread.start()


# Клавиатуры
def get_cities_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(city, callback_data=f"city_{city}") for city in popular_cities]
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton("🔍 Другой город", callback_data="other_city"))
    return keyboard


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
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data=f"back_to_time_{city}"))
    return keyboard


def get_time_keyboard(city):
    keyboard = InlineKeyboardMarkup(row_width=3)
    times = ["07:00", "09:00", "12:00", "15:00", "18:00", "20:00"]
    buttons = [InlineKeyboardButton(time, callback_data=f"time_{city}_{time}") for time in times]
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton("✏️ Своё время", callback_data=f"custom_time_{city}"))
    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
    return keyboard


def get_manage_reminders_keyboard(user_id):
    reminders = get_user_reminders(user_id)
    keyboard = InlineKeyboardMarkup(row_width=1)

    if not reminders:
        keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
        return keyboard

    for reminder in reminders:
        reminder_id, _, _, city, reminder_time, days, _ = reminder

        if days == "everyday":
            days_text = "ежедневно"
        elif days == "workdays":
            days_text = "будни"
        elif days == "weekend":
            days_text = "выходные"
        else:
            days_list = days.split(',')
            day_names = {"1": "Пн", "2": "Вт", "3": "Ср", "4": "Чт", "5": "Пт", "6": "Сб", "7": "Вс"}
            days_short = [day_names.get(d, "") for d in days_list if d in day_names]
            days_text = ", ".join(days_short)

        button_text = f"❌ {city} в {reminder_time} ({days_text})"
        keyboard.add(InlineKeyboardButton(button_text, callback_data=f"delete_{reminder_id}"))

    keyboard.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu"))
    return keyboard


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


# Обработчики команд
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_name = message.from_user.first_name
    welcome_text = (
        f"🌟 *Привет, {user_name}!*\n\n"
        f"Я *WeatherBot* — твой помощник по погоде! 🌤\n\n"
        f"📌 *Что я умею:*\n"
        f"• Показывать погоду в любом городе\n"
        f"• Напоминания о погоде ⏰\n"
        f"• Красивые кнопки\n\n"
        f"👇 *Нажми кнопку ниже!*"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode='Markdown', reply_markup=get_main_keyboard())


@bot.message_handler(func=lambda message: True)
def handle_main_keyboard(message):
    if message.text == "🌤 Узнать погоду":
        bot.send_message(message.chat.id,
                         "🏙 *Введите название города*\n\n"
                         "Например: Москва, London, Париж",
                         parse_mode='Markdown',
                         reply_markup=get_cities_keyboard())

    elif message.text == "🌟 Популярные города":
        bot.send_message(message.chat.id,
                         "🌆 *Выберите город:*",
                         parse_mode='Markdown',
                         reply_markup=get_cities_keyboard())

    elif message.text == "⏰ Напомнить о погоде":
        bot.send_message(message.chat.id,
                         "⏰ *Выберите город:*",
                         parse_mode='Markdown',
                         reply_markup=get_cities_keyboard())

    elif message.text == "📋 Мои напоминания":
        user_id = message.from_user.id
        reminders = get_user_reminders(user_id)

        if reminders:
            bot.send_message(message.chat.id,
                             "📋 *Ваши напоминания:*\nНажмите для удаления",
                             parse_mode='Markdown',
                             reply_markup=get_manage_reminders_keyboard(user_id))
        else:
            bot.send_message(message.chat.id,
                             "📋 *У вас нет активных напоминаний*",
                             parse_mode='Markdown',
                             reply_markup=get_main_keyboard())

    elif message.text == "ℹ️ О боте":
        about_text = (
            "🤖 *WeatherBot*\n\n"
            f"Версия: {BOT_VERSION}\n"
            f"Создатель: {CREATOR_NAME}\n\n"
            "📊 Функции:\n"
            "• Погода в реальном времени\n"
            "• Напоминания с выбором дней\n"
            "• Удобные кнопки"
        )
        bot.send_message(message.chat.id, about_text, parse_mode='Markdown', reply_markup=get_main_keyboard())

    elif message.text == "👨‍💻 О разработчике":
        creator_text = (
            "👨‍💻 *О разработчике*\n\n"
            f"Создал: {CREATOR_NAME}\n"
            f"Контакты: {CREATOR_NICKNAME}\n\n"
            "Сделано с ❤️ на Python"
        )
        bot.send_message(message.chat.id, creator_text, parse_mode='Markdown', reply_markup=get_main_keyboard())

    elif message.text == "📞 Помощь":
        help_text = (
            "🔍 *Помощь*\n\n"
            "1️⃣ Нажми «Узнать погоду»\n"
            "2️⃣ Введи город\n"
            "3️⃣ Получи прогноз\n\n"
            "❓ Вопросы: @Gdrag182"
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
                                 f"⏰ *Выберите дни для {city} в {time_str}:*",
                                 parse_mode='Markdown',
                                 reply_markup=get_days_keyboard(city, time_str))
            else:
                bot.send_message(message.chat.id,
                                 "❌ Неверный формат. Используйте ЧЧ:ММ (например, 14:30)")
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
                bot.send_message(message.chat.id, "👇 *Что дальше?*",
                                 parse_mode='Markdown', reply_markup=keyboard)
            else:
                bot.send_message(message.chat.id, error_msg)


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data.startswith("city_"):
        city = call.data.replace("city_", "")
        bot.answer_callback_query(call.id, f"Ищем {city}...")

        weather_msg, error_msg = get_weather_info(city)

        if weather_msg:
            bot.send_message(call.message.chat.id, weather_msg, parse_mode='Markdown')

            keyboard = InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                InlineKeyboardButton("🔄 Другой город", callback_data="other_city"),
                InlineKeyboardButton("🌟 Популярные", callback_data="show_popular"),
                InlineKeyboardButton("⏰ Напомнить", callback_data=f"set_reminder_{city}")
            )
            bot.send_message(call.message.chat.id, "👇 *Что дальше?*",
                             parse_mode='Markdown', reply_markup=keyboard)
        else:
            bot.send_message(call.message.chat.id, error_msg)

    elif call.data.startswith("set_reminder_"):
        city = call.data.replace("set_reminder_", "")
        bot.send_message(call.message.chat.id,
                         f"⏰ *Выберите время для {city}:*",
                         parse_mode='Markdown',
                         reply_markup=get_time_keyboard(city))

    elif call.data.startswith("time_"):
        parts = call.data.split("_")
        city = parts[1]
        reminder_time = parts[2]
        user_id = call.from_user.id

        user_data[user_id] = {'city': city, 'time': reminder_time, 'awaiting_days': True}
        bot.edit_message_text(f"⏰ *Выберите дни для {city} в {reminder_time}:*",
                              call.message.chat.id,
                              call.message.message_id,
                              parse_mode='Markdown',
                              reply_markup=get_days_keyboard(city, reminder_time))

    elif call.data.startswith("custom_time_"):
        city = call.data.replace("custom_time_", "")
        user_id = call.from_user.id

        user_data[user_id] = {'city': city, 'awaiting_time': True}

        bot.edit_message_text(f"✏️ *Введите время для {city}*\n\n"
                              "Формат: ЧЧ:ММ (например, 14:30)",
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
            days_text = "будни"
        elif days_option == "weekend":
            days_string = "weekend"
            days_text = "выходные"
        else:
            days_string = days_option
            day_names = {"1": "Пн", "2": "Вт", "3": "Ср", "4": "Чт", "5": "Пт", "6": "Сб", "7": "Вс"}
            days_text = day_names.get(days_option, "")

        add_reminder(user_id, chat_id, city, reminder_time, days_string)

        success_text = (
            f"✅ *Напоминание создано!*\n\n"
            f"📍 Город: {city}\n"
            f"⏰ Время: {reminder_time}\n"
            f"📅 Дни: {days_text}"
        )

        bot.edit_message_text(success_text,
                              chat_id,
                              call.message.message_id,
                              parse_mode='Markdown')

        bot.send_message(chat_id, "👇 *Что дальше?*",
                         parse_mode='Markdown', reply_markup=get_main_keyboard())

        if user_id in user_data:
            del user_data[user_id]

    elif call.data.startswith("delete_"):
        reminder_id = call.data.replace("delete_", "")
        delete_reminder(reminder_id)

        bot.answer_callback_query(call.id, "✅ Удалено!")

        user_id = call.from_user.id
        reminders = get_user_reminders(user_id)

        if reminders:
            bot.edit_message_text("📋 *Ваши напоминания:*",
                                  call.message.chat.id,
                                  call.message.message_id,
                                  parse_mode='Markdown',
                                  reply_markup=get_manage_reminders_keyboard(user_id))
        else:
            bot.edit_message_text("📋 *Напоминаний больше нет*",
                                  call.message.chat.id,
                                  call.message.message_id,
                                  parse_mode='Markdown')

    elif call.data.startswith("back_to_time_"):
        city = call.data.replace("back_to_time_", "")
        bot.edit_message_text(f"⏰ *Выберите время для {city}:*",
                              call.message.chat.id,
                              call.message.message_id,
                              parse_mode='Markdown',
                              reply_markup=get_time_keyboard(city))

    elif call.data == "other_city":
        bot.send_message(call.message.chat.id, "🏙 *Введите название города:*", parse_mode='Markdown')

    elif call.data == "show_popular":
        bot.send_message(call.message.chat.id,
                         "🌆 *Популярные города:*",
                         parse_mode='Markdown',
                         reply_markup=get_cities_keyboard())

    elif call.data == "back_to_menu":
        bot.send_message(call.message.chat.id,
                         "🏠 *Главное меню*",
                         parse_mode='Markdown',
                         reply_markup=get_main_keyboard())

    bot.answer_callback_query(call.id)


# Запуск
if __name__ == '__main__':
    print("=" * 50)
    print("✨ БОТ ПОГОДЫ ЗАПУЩЕН")
    print("=" * 50)
    print(f"👨‍💻 Разработчик: {CREATOR_NAME} ({CREATOR_NICKNAME})")
    print(f"📱 Версия: {BOT_VERSION}")
    print(f"🔑 API ключ загружен: {WEATHER_API_KEY[:5]}...{WEATHER_API_KEY[-5:]}")
    print(f"🤖 Токен бота: {BOT_TOKEN[:5]}...{BOT_TOKEN[-5:]}")
    print("⏰ Система напоминаний активна")
    print("📡 Режим отладки ВКЛЮЧЕН")
    print("=" * 50)

    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")
            time.sleep(5)
            print("🔄 Перезапуск...")
            continue