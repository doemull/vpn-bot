import telebot
import logging
import sqlite3
from datetime import datetime, timedelta
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import aiohttp
import qrcode
from transliterate import translit
import wg_easy_api_wrapper
from wg_easy_api_wrapper import Server
import threading
from telebot import types
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#credentials
ADMIN_ID = os.getenv('ADMIN_ID')
server_url = os.getenv('server_url')
password = os.getenv('password')
TOKEN = os.getenv('TOKEN')
bot = telebot.TeleBot(TOKEN)
user_device_map = {}
user_devices = {}
user_periods = {}

# Подключение к базе данных
def init_db():
    conn = sqlite3.connect("data/vpn_subscriptions.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS clients (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        tg_id INTEGER UNIQUE,
                        created_at TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        client_id INTEGER,
                        device_name TEXT,
                        subscription_period INTEGER,
                        start_date TEXT,
                        end_date TEXT,
                        payment_proof TEXT,
                        confirmed INTEGER DEFAULT 0,
                        file_name TEXT,
                        FOREIGN KEY (client_id) REFERENCES clients(id))''')
    conn.commit()
    conn.close()


init_db()

# Главная клавиатура
def main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Тарифы"))
    markup.add(KeyboardButton("О нас"))
    markup.add(KeyboardButton("Мой профиль"))
    return markup


# Способ получения файла
def metod_choice():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Файл"))
    markup.add(KeyboardButton("QR-код"))
    markup.add(KeyboardButton("Мой профиль"))
    return markup


# Клавиатура тарифов
def tariffs_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("1 месяц - 150₽"))
    markup.add(KeyboardButton("3 месяца - 400₽"))
    markup.add(KeyboardButton("6 месяцев - 750₽"))
    return markup


def metod_choice_country():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Phone"))
    markup.add(KeyboardButton("Computer"))
    markup.add(KeyboardButton("TV"))
    return markup


# Клавиатура после оплаты
def after_payment_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Мой профиль"))
    markup.add(KeyboardButton("Подключить еще одно устройство"))
    markup.add(KeyboardButton("Отменить подписку"))
    markup.add(KeyboardButton("Тех.поддержка"))
    return markup

def subsribe_renew():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("Отменить подписку"))
    markup.add(KeyboardButton("Мой профиль"))
    return markup

def info_button():
    markup = types.InlineKeyboardMarkup()
    button1 = types.InlineKeyboardButton(text='📝 Оферта', url='https://telegra.ph/Oferta-na-obsluzhivanie-SHifrovannogo-kanala-04-23')
    button2 = types.InlineKeyboardButton(text='📖 Правила', url='https://telegra.ph/Pravila-polzovaniya-Telegram-botom-VPN-04-24')
    button3 = types.InlineKeyboardButton(text='🌐 Наш канал', url='https://t.me/virtual_privat_network')
    markup.row(button1, button2)
    markup.add (button3)
    return markup

@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(message.chat.id, """🌍 Свободный интернет – всего за 150 рублей в месяц! 🚀

Твои любимые сайты заблокированы? 😡
Instagram, YouTube, ChatGPT, X (Twitter) и другие ресурсы недоступны?

🔑 Решение есть! Наш VPN откроет доступ ко всему интернету!""", reply_markup=main_keyboard())
    
    bot.send_message(message.chat.id, "📋 Перед началом работы с ботом, необходимо ознакомиться с документациями", reply_markup=info_button())


@bot.message_handler(func=lambda message: message.text == "Тарифы")
def show_tariffs(message):
    bot.send_message(message.chat.id, "Выберите тариф:", reply_markup=tariffs_keyboard())


@bot.message_handler(content_types=['photo'])
def handle_payment_proof(message, period):
    user_id = message.chat.id
    name = message.from_user.first_name
    
    if period is not None:
        user_periods[user_id] = period

    if message.photo is None:  # Проверяем, отправил ли пользователь фото
        msg = bot.send_message(user_id, "❌ Пожалуйста, отправьте СКРИНШОТ оплаты!")
        bot.register_next_step_handler(msg, lambda m: handle_payment_proof(m, period))  # Перезапускаем функцию
        return

    file_id = message.photo[-1].file_id

    msg = bot.send_message(user_id, 'Выберите устройство, для которого нужен VPN', reply_markup=metod_choice_country())
    bot.register_next_step_handler(msg, lambda m: save_subscription(m, user_id, name, file_id, user_periods.get(user_id)))


def save_subscription(message, user_id, name, file_id, period):
    device_name = message.text
    user_device_map[user_id] = device_name

    conn = sqlite3.connect("data/vpn_subscriptions.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM clients WHERE tg_id = ?", (user_id,))
    client = cursor.fetchone()

    if not client:
        cursor.execute("INSERT INTO clients (name, tg_id, created_at) VALUES (?, ?, ?)",
                       (name, user_id, datetime.now().strftime("%d.%m.%Y")))
        conn.commit()
        client_id = cursor.lastrowid
    else:
        client_id = client[0]
###
    cursor.execute(
        "INSERT INTO subscriptions (client_id, device_name, subscription_period, payment_proof) VALUES (?, ?, ?, ?)",
        (client_id, device_name, period, file_id))

    cursor.execute("""
        UPDATE subscriptions
        SET name = (SELECT clients.name FROM clients WHERE clients.id = subscriptions.client_id)
        WHERE client_id IN (SELECT id FROM clients)
    """)
    conn.commit()
    conn.close()

    bot.send_message(user_id, "📩 Ваш платеж отправлен на проверку администратору.")

    # Уведомление админа
    markup = InlineKeyboardMarkup()
    confirm_btn = InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{user_id}_{device_name}_{period}")
    reject_btn = InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}_{device_name}")
    markup.add(confirm_btn, reject_btn)
    tg = message.from_user.username

    bot.send_photo(ADMIN_ID, file_id, caption=f"💰 Новый платёж от {name}: @{tg} (ID: {user_id}) на устройство {device_name}",
                   reply_markup=markup)



@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_"))
def confirm_payment(call):
    try:
        _, tg_id, device_name, period = call.data.split("_", 3)
        tg_id = int(tg_id)
        period_int = int(period)

        now = datetime.now()
        start_date_var = now.strftime("%d.%m.%Y")
        end_date_var = (now + timedelta(days=int(period_int))).strftime("%d.%m.%Y")

        conn = sqlite3.connect("data/vpn_subscriptions.db")
        cursor = conn.cursor()

        # Получаем client_id по tg_id
        cursor.execute("SELECT id FROM clients WHERE tg_id = ?", (tg_id,))
        client = cursor.fetchone()
        if not client:
            bot.send_message(ADMIN_ID, f"Ошибка: клиент с TG_ID {tg_id} не найден в базе.")
            return

        client_id = client[0]
        # Обновляем подписку
        cursor.execute('''
            UPDATE subscriptions 
            SET start_date = ?, end_date = ?, confirmed = 1
            WHERE client_id = ? AND device_name = ?''',(start_date_var, end_date_var, client_id, device_name))
        conn.commit()

        cursor.execute("SELECT * FROM subscriptions WHERE client_id = ? AND device_name = ?", (client_id, device_name))
        updated_subscription = cursor.fetchone()
        logger.info(f"Обновленная запись: {updated_subscription}")
        conn.close()

        bot.send_message(tg_id, f"✅ Оплата подтверждена! Ваше устройство {device_name} активировано на {period} дней")
        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=f"✅ Оплата от подтверждена!")

        if device_name == 'Phone':
            bot.send_message(tg_id,
                             f"Ссылка на инструкцию для установки {device_name}: https://telegra.ph/Instrukciya-dlya-podklyucheniya-Telefona-04-24 \n\nС помощью кнопок ниже, выберите способ получения конфигурации⚙️",
                             reply_markup=metod_choice())
        elif device_name == 'Computer':
            bot.send_message(tg_id,
                             f"Ссылка на инструкцию для установки {device_name}: https://telegra.ph/Instrukciya-dlya-podklyucheniya-PK-04-24 \n\nС помощью кнопок ниже, выберите способ получения конфигурации⚙️",
                             reply_markup=metod_choice())
        elif device_name == 'TV':
            bot.send_message(tg_id,
                             f"Ссылка на инструкцию для установки {device_name}: https://telegra.ph/Instrukciya-dlya-podklyucheniya-TV-04-24 \n\nС помощью кнопок ниже, выберите способ получения конфигурации⚙️",
                             reply_markup=metod_choice())
        else:
            bot.send_message(tg_id, f"Ошибка при выборе устройства, обратитесь в тех.поддержку: @doemull")
    except Exception as e:
        logger.error(f"Ошибка при подтверждении оплаты: {e}")
        bot.send_message(ADMIN_ID, f"❌ Ошибка при подтверждении оплаты: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_"))
def reject_payment(call):
    _, tg_id, device_name = call.data.split("_")

    bot.send_message(tg_id, "❌ Оплата отклонена. Для уточнения причины можете обратиться к @doemull")
    bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id,
                             caption="❌ Оплата отклонена.")
    
    period = user_periods.get(tg_id)

    msg = bot.send_message(tg_id, "📸 Отправьте СКРИНШОТ оплаты повторно.")
    bot.register_next_step_handler(msg, lambda m:handle_payment_proof(m, period))

def transliterate_name(client_name):
    """Транслитерирует русские имена в английские"""
    return translit(client_name, 'ru', reversed=True) if client_name else "client"


@bot.message_handler(func=lambda message: message.text in ["1 месяц - 150₽", "3 месяца - 400₽", "6 месяцев - 750₽"])
def process_tariff_choice(message):
    periods = {"1 месяц - 150₽": 30, "3 месяца - 400₽": 90, "6 месяцев - 750₽": 180}
    amount = {"1 месяц - 150₽": 150, "3 месяца - 400₽": 400, "6 месяцев - 750₽": 750}
    period = periods[message.text]
    price = amount[message.text]

    pay_links = {
        "1 месяц - 150₽": "Номер: +7913-585-25-60 (Даниил Сергеевич Ф.)\nБанк: Райффайзен ‼️",
        "3 месяца - 400₽": "Номер: +7913-585-25-60 (Даниил Сергеевич Ф.)\nБанк: Райффайзен ‼️",
        "6 месяцев - 750₽": "Номер: +7913-585-25-60 (Даниил Сергеевич Ф.)\nБанк: Райффайзен ‼️"
    }

    bot.send_message(message.chat.id, f"Вы выбрали {message.text}\n\nОплатите через банковский перевод:\n{pay_links[message.text]}")

    bot.send_message(message.chat.id, f"Для подтверждения оплаты отправьте скриншот оплаты:")
    bot.register_next_step_handler(message, lambda m: handle_payment_proof(m, period))


# Функция получения конфигурации клиента
async def get_client_config(client_name):
    english_name = transliterate_name(client_name)
    """Получает конфигурацию клиента, если он существует"""
    await asyncio.sleep(2)  # Даем серверу время обновить список
    async with aiohttp.ClientSession() as session:
        server = Server(server_url, password, session)
        await server.login()
        clients = await server.get_clients()
        for client in clients:
            if client.name == english_name:
                return await client.get_configuration()
    return None  # Если клиент не найден


# Функция создания нового клиента
async def create_client(client_name):
    english_name = transliterate_name(client_name)
    """Создает клиента в WireGuard, если его нет"""
    async with aiohttp.ClientSession() as session:
        server = Server(server_url, password, session)
        await server.login()
        await server.create_client(english_name)


async def process_and_send_config(user_id, client_names):
    english_name = transliterate_name(client_names)
    """Создаёт клиента (если нужно), получает конфиг и отправляет его"""
    config = await get_client_config(english_name)

    if config is None:  # Если клиента нет, создаём его
        await create_client(english_name)
        await asyncio.sleep(5)  # Даём серверу время на генерацию конфига
        config = await get_client_config(english_name)  # Пробуем получить снова

    if config:
        filename = f"{english_name}.conf"
        with open(filename, "w") as file:
            file.write(config)

        with open(filename, "rb") as file:
            bot.send_document(user_id, file, caption=f"✅ Вот ваш конфигурационный файл {filename}",
                              reply_markup=after_payment_keyboard())

    else:
        bot.send_message(user_id, "❌ Ошибка при получении конфигурации.", reply_markup=after_payment_keyboard())


async def process_and_send_config_QR(user_id, client_names):
    english_name = transliterate_name(client_names)
    """Создаёт клиента (если нужно), получает конфиг и отправляет его"""
    config = await get_client_config(english_name)

    if config is None:  # Если клиента нет, создаём его
        await create_client(english_name)
        await asyncio.sleep(5)  # Даём серверу время на генерацию конфига
        config = await get_client_config(english_name)  # Пробуем получить снова

    if config:
        qr_filename = f"{english_name}.png"
        qr = qrcode.make(config)
        qr.save(qr_filename)
        with open(qr_filename, "rb") as qr_file:
            bot.send_photo(user_id, qr_file, caption="📡 Вот ваш QR-код для быстрого подключения!",
                           reply_markup=after_payment_keyboard())
    else:
        bot.send_message(user_id, "❌ Ошибка при получении конфигурации.", reply_markup=after_payment_keyboard())

async def check_subscriptions(bot: telebot):
    while True:
        try:
            conn = sqlite3.connect("data/vpn_subscriptions.db")
            cursor = conn.cursor()

            today = datetime.now().strftime("%d.%m.%Y")
            today_date = datetime.now().date()

            cursor.execute("""
                            SELECT client_id, device_name, end_date 
                            FROM subscriptions 
                            WHERE end_date = ? AND confirmed = 1
                           """, (today,))
            subscriptions = cursor.fetchall()

            user_subscriptions = {}
            for client_id, device_name, end_date in subscriptions:
                if client_id not in user_subscriptions:
                    user_subscriptions[client_id] = []
                user_subscriptions[client_id].append(f"🔹{device_name} до {end_date}‼️")


            for client_id, devices in user_subscriptions.items():
                cursor.execute('''
                SELECT  tg_id, name 
                FROM clients 
                WHERE id = ?''', (client_id,))
                client = cursor.fetchone()
                if client:
                    tg_id, name = client
                    device_list = "\n".join(devices)
                    message = (f"{name}, ваша подписка истекает сегодня ⏰ \n\n{device_list}\n\nПродлите ее, чтобы избежать отключения!")

                    keyboard = InlineKeyboardMarkup()
                    for device_name in devices:
                        keyboard.add(InlineKeyboardButton(
                        text = f"Продлить для: {device_name}",
                        callback_data = f"renew_{client_id}_{device_name}"))    
                    bot.send_message(tg_id, message, reply_markup=keyboard)
            
            #просрочка подписки на два дня
            cursor.execute("""
                           SELECT client_id, device_name, end_date
                           FROM subscriptions 
                           WHERE confirmed = 1
                           """)
            all_subscriptions = cursor.fetchall()

            expired_subs = {}

            for client_id, device_name, end_date in all_subscriptions: 
                try:
                    end_date_obj = datetime.strptime(end_date, "%d.%m.%Y").date()
                except ValueError:
                    print (f"Ошибка преобразования даты: {end_date}")
                    continue

                if today_date >=end_date_obj + timedelta(days=2):
                    if client_id not in expired_subs:
                        expired_subs[client_id] = []
                    expired_subs[client_id].append(device_name)

            for client_id, devices in expired_subs.items():
                cursor.execute("""
                            SELECT tg_id, name
                                FROM clients
                                WHERE id = ?
                               """, (client_id,))
                client = cursor.fetchone()

                if client:
                    tg_id, name = client
                    device_lister = "\n".join ([f"🔹 {device_name}" for device_name in devices])
                    bot.send_message(tg_id, f"{name}, у вас просрочены более 2-х дней следующие устройства ⚠️\n\n{device_lister}\n\nПродлите подписку, используя сообщения выше, чтобы избежать отключения сервиса 📵")
                    user = client
                    #print (user, devices)
                    await (dis_client(user, devices))
            conn.close()
        except Exception as e:
            print(f"Ошибка при проверке подписок:{e}")
        await asyncio.sleep(43200)

async def dis_client (user, devices):
    tg_id, name = user
    async with aiohttp.ClientSession() as session:
        server = Server(server_url, password, session)
        await server.login()

        clients = await server.get_clients()
        
        for device in devices:
            file_name = f"{name}_{tg_id}_{device}"
            #print (file_name)
            target_client = None
            

            for client in clients:
                if client.name == file_name:
                    target_client = client
                    break
        

            if target_client:       
                #print(f"✅ Найден клиент: {target_client.name}")
                #print(f"UID: {target_client.uid}")
                #отключение
                await target_client.disable()
                bot.send_message(tg_id, f"❌ Конфигурация '{target_client.name}' отключена.\n\nДля включения необходимо внести оплату, используя сообщения выше 💳")
                bot.send_message(ADMIN_ID, f"❌ Конфигурация '{target_client.name}' отключена. ")
            else:
                print("❌ Клиент не найден.")




def del_sub(message):
    conn = sqlite3.connect("data/vpn_subscriptions.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, device_name, start_date, end_date FROM subscriptions WHERE client_id = (SELECT id FROM clients WHERE tg_id = ?) ", (message.chat.id,))
    del_device = cursor.fetchall()

    if not del_device:
        bot.send_message(message.chat.id, "У вас нет активных подписок.")
        return

    keyboard = InlineKeyboardMarkup()
    for sub_id, device_name, start_date, end_date in del_device:
        button_text = f"🔹{device_name} с {start_date} по {end_date}"
        keyboard.add(InlineKeyboardButton(text=button_text, callback_data=f"delete_{sub_id}"))
    bot.send_message(message.chat.id, "Выберите подписку для удаления", reply_markup=keyboard)

    conn.close()

async def delete_from_wg(file_name, sub_id):
    async with aiohttp.ClientSession() as session:
        server = Server(server_url, password, session)
        await server.login()

        clients = await server.get_clients()
        target_client = None

        for client in clients:
            if client.name == file_name:
                target_client = client
                break

        if target_client:
            print(f"✅ Найден клиент: {target_client.name}")
            print(f"UID: {target_client.uid}")
            # Пример: удалить
            await server.remove_client(target_client.uid)
            print(f"Клиент '{client.name}' успешно удалён.")

        else:
            print("❌ Клиент не найден.")

        conn = sqlite3.connect("data/vpn_subscriptions.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
        conn.commit()
        conn.close()


def handle_delete_callback(call):
    if call.data.startswith("delete_"):
        sub_id = call.data.split("_")[1]
        conn = sqlite3.connect("data/vpn_subscriptions.db")
        cursor = conn.cursor()

        cursor.execute("SELECT file_name FROM subscriptions WHERE id = ?", (sub_id,))
        file_name = cursor.fetchone()[0]
        print (file_name)
        
        bot.send_message(call.message.chat.id, "Подписка успешно удалена!", reply_markup=after_payment_keyboard())
        asyncio.run(delete_from_wg(file_name,sub_id))


def keyboard_renew():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("1 месяц - 150₽", callback_data="sub_1m"))
    keyboard.add(InlineKeyboardButton("3 месяца - 400₽", callback_data="sub_3m"))
    keyboard.add(InlineKeyboardButton("6 месяцев - 750₽", callback_data="sub_6m"))
    return keyboard

def handle_renew_subscriprions(call):
    if call.data.startswith("renew_"):
        tg_id = call.message.chat.id

        conn = sqlite3.connect("data/vpn_subscriptions.db")
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM clients WHERE tg_id = ?", (tg_id,))
        user_str = cursor.fetchone()
        today_end = datetime.now()

        if user_str:
            client_id = user_str[0]
            cursor.execute("SELECT * FROM subscriptions WHERE client_id = ?", (client_id,))
            user_exists = cursor.fetchone()
            cursor.execute("SELECT device_name FROM subscriptions WHERE client_id = ? AND end_date <= ?", (client_id, today_end.strftime("%d.%m.%Y")))
            user_device = cursor.fetchone()[0]

            user_devices[tg_id] = user_device
        else:
            bot.send_message(tg_id, "Устройство не найдено.")
            conn.close()
            return
        conn.close()

        bot.send_message(call.message.chat.id, "Выберите тариф", reply_markup=keyboard_renew())


@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
def callback_handler(call):
    handle_delete_callback(call)


@bot.callback_query_handler(func=lambda call: call.data.startswith("renew_"))
def callback_renew(call):
    handle_renew_subscriprions(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith("sub_"))
def handler_renew_subscriptions(call):
    tg_id = call.message.chat.id
    user_device = user_devices.get(tg_id)

    if not user_device:
        bot.send_message(tg_id, "Ошибка, устройства нет")
        return

    subscription_data = {
        "sub_1m": {
            "link":"Номер: +7913-585-25-60 (Даниил Сергеевич Ф.\nБанк: Райффайзен ‼️)",
            "days": 30,
            "label": "1 месяц - 150₽"
        },
        "sub_3m": {
            "link": "Номер: +7913-585-25-60 (Даниил Сергеевич Ф.\nБанк: Райффайзен ‼️",
            "days": 90,
            "label": "3 месяца - 400₽"
        },
        "sub_6m": {
            "link": "Номер: +7913-585-25-60 (Даниил Сергеевич Ф.\nБанк: Райффайзен ‼️",
            "days": 180,
            "label": "6 месяцев - 750₽"
        }
    }

    selected = subscription_data.get(call.data)

    if selected:
        bot.send_message(tg_id, f"Вы выбрали подписку на: {selected['label']}\n"
                                  f"Срок действия: {selected['days']} дней\n\n"
                                  f"Оплатите через банковский перевод:\n{selected['link']}")
    else:
        bot.send_message(tg_id, "Ошибка: выбранный тариф не найден.")


    conn = sqlite3.connect('data/vpn_subscriptions.db')
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM clients where tg_id = ?', (tg_id,))
    result = cursor.fetchone()

    if not result:
        bot.send_message(tg_id, "Клиент не найден в базе.")
        conn.close()
        return
    client_id = result[0]

    start_date = datetime.now()
    end_date = start_date + timedelta(days=selected["days"])

    cursor.execute('''UPDATE subscriptions
    SET subscription_period = ?, start_date = ?, end_date = ?
    WHERE client_id = ? AND device_name = ?''', (selected["days"], start_date.strftime("%d.%m.%Y"), end_date.strftime("%d.%m.%Y"), client_id, user_device))

    conn.commit()
    conn.close()
    ask_for_screenshot(call.message, user_device)

def ask_for_screenshot(message,user_device):
    msg = bot.send_message(message.chat.id, "Пожалуйста отправьте скриншот для оплаты устройства: "+user_device)
    bot.register_next_step_handler(msg, lambda m: handle_payment_screenshot(m, user_device))


def handle_payment_screenshot(message, user_device):
    if message.photo:
        file_id = message.photo[-1].file_id
        name = message.from_user.username
        caption = f"Скриншот оплаты от @{name}\nУстройство: {user_device}"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirmed_{message.chat.id}_{user_device}"))
        markup.add(InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_{message.chat.id}_{user_device}"))

        bot.send_photo(ADMIN_ID, file_id, caption=caption, reply_markup=markup)
        bot.send_message(message.chat.id, "📩 Ваш платеж отправлен на проверку администратору.")
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте СКРИНШОТ оплаты")

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirmed_") or call.data.startswith("decline_"))
def process_payment_decision(call):
    data_parts = call.data.split("_")
    action = data_parts[0]
    user_id = int(data_parts[1])
    user_device = "_".join(data_parts[2:])

    if action == "confirmed":
        bot.send_message(user_id, f"Подписка для устройства {user_device} успешно продлена ✅")
        asyncio.run(process_enable(data_parts))

    elif action == "decline":
        bot.send_message(user_id, f"Подписка для устройства {user_device} не была подтверждена ❌")
    bot.answer_callback_query(call.id)

def process_enable(data_parts):
    tg_id = data_parts[1]
    device = data_parts[2]

    conn = sqlite3.connect("data/vpn_subscriptions.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM clients WHERE tg_id = ?", (tg_id,))
    client_id = cursor.fetchone()
    cursor.execute("SELECT file_name FROM subscriptions WHERE client_id=? AND device_name=?", (client_id, device))
    file_name = cursor.fetchone()
    print (file_name)



@bot.message_handler(func=lambda message: message.text == "Файл")
def config_file(message):
    """Обработчик команды 'Файл'"""
    teleg_id = str(message.chat.id)
    device_name = user_device_map.get(message.chat.id, "UnknownDevice")
    client_name = str(message.from_user.first_name + "_" + teleg_id + "_" + device_name) # название подключения
    
    
    conn = sqlite3.connect("data/vpn_subscriptions.db") #запись названия подключения в таблицу 
    cursor = conn.cursor()

    cursor.execute("SELECT id from clients WHERE tg_id = ?", (message.chat.id,))
    line = cursor.fetchone()[0] #содержит id устройства 
    print ("client id:", line)

    cursor.execute("SELECT file_name FROM subscriptions WHERE client_id=? AND file_name LIKE ?", (line, f"{client_name}%"))
    
    existing_names = [row[0] for row in cursor.fetchall()]
    print ("уже существующие имена:", existing_names)

    if client_name not in existing_names:
        client_names = client_name
    else:
        i = 1
        while f"{client_name}{i}" in existing_names:
            i += 1
        client_names = f"{client_name}{i}"
    print ("сгенерировано имя:", client_names)

    cursor.execute("""UPDATE subscriptions SET file_name =? 
                    WHERE id = (
                    SELECT id FROM subscriptions
                    WHERE client_id = ? AND device_name = ? AND file_name IS NULL
                    ORDER BY id ASC LIMIT 1)
                    """, (client_names, line, device_name))
    conn.commit()
    conn.close()

    bot.send_message(message.chat.id, "⏳ Генерация конфигурации, подождите...")
    asyncio.run(process_and_send_config(message.chat.id, client_names))


@bot.message_handler(func=lambda message: message.text == "QR-код")
def config_QR(message):
    teleg_id = str(message.chat.id)
    device_name = user_device_map.get(message.chat.id, "UnknownDevice")

    client_name = str(message.from_user.first_name + "_" + teleg_id + "_" + device_name)
    

    conn = sqlite3.connect("data/vpn_subscriptions.db") #запись названия подключения в таблицу 
    cursor = conn.cursor()

    cursor.execute("SELECT id from clients WHERE tg_id = ?", (message.chat.id,))
    line = cursor.fetchone()[0] #содержит id устройства 
    print ("client id:", line)

    cursor.execute("SELECT file_name FROM subscriptions WHERE client_id=? AND file_name LIKE ?", (line, f"{client_name}%"))
    
    existing_names = [row[0] for row in cursor.fetchall()]
    print ("уже существующие имена:", existing_names)

    if client_name not in existing_names:
        client_names = client_name
    else:
        i = 1
        while f"{client_name}{i}" in existing_names:
            i += 1
        client_names = f"{client_name}{i}"
    print ("сгенерировано имя:", client_names)

    cursor.execute("""UPDATE subscriptions SET file_name =? 
                    WHERE id = (
                    SELECT id FROM subscriptions
                    WHERE client_id = ? AND device_name = ? AND file_name IS NULL
                    ORDER BY id ASC LIMIT 1)
                    """, (client_names, line, device_name))
    conn.commit()
    conn.close()

    bot.send_message(message.chat.id, "⏳ Генерация конфигурации, подождите...")    
    asyncio.run(process_and_send_config_QR(message.chat.id, client_names))


@bot.message_handler(func=lambda message: message.text == "Мой профиль")
def show_profile(message):
    conn = sqlite3.connect("data/vpn_subscriptions.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, name FROM clients WHERE tg_id = ?", (message.chat.id,))
    client = cursor.fetchone()

    if client:
        client_id, name = client
        cursor.execute("SELECT device_name, start_date, end_date, confirmed FROM subscriptions WHERE client_id = ?",
                       (client_id,))
        subscriptions = cursor.fetchall()
        conn.close()

        profile_text = f"👤 Ваш профиль:\nИмя: {name}\n\n📱 Подключенные устройства:\n"

        for sub in subscriptions:
            device, start_date_var, end_date_var, confirmed = sub
            status = "✅ Активно" if confirmed else "⏳ Ожидает подтверждения"
            profile_text += f"🔹 {device}: {status}\n⏳ {start_date_var} - {end_date_var}\n\n"

        bot.send_message(message.chat.id, profile_text)
    else:
        bot.send_message(message.chat.id, "Вы еще не оформляли подписку.")

@bot.message_handler(func=lambda message: message.text == "Тех.поддержка")
def support(message):
    support_profile = 'https://t.me/doemull'
    bot.send_message(message.chat.id,
                     f"Если у вас появились проблемы с подключением, вы можете написать в поддержку: {support_profile}")

@bot.message_handler(func=lambda message: message.text == "Подключить еще одно устройство")
def new_device(message):
    show_tariffs(message)

@bot.message_handler(func=lambda message: message.text == "Отменить подписку")
def delete_sub(message):
    del_sub(message)

@bot.message_handler(func=lambda message: message.text == "О нас")
def information(message):
    bot.send_message(message.chat.id, f''' 🌐 Наше подключение - это: 

✔️ Обход блокировок – без ограничений и запретов
✔️ Полная анонимность – никто не узнает, что ты смотришь
✔️ Защита данных – надежное шифрование твоего трафика 
✔️ Отличная скорость – никаких лагов и буферизации
✔️ Возможность выбора локации для подключения
✔️ Доступный способ оплаты

Локации для подключения:
🇳🇱 Нидерланды 
🇸🇰 Словакия 

🔹 Работает на iOS, Android, Windows, macOS''')

def run_bot():
    bot.infinity_polling()
async def main():
    loop = asyncio.get_running_loop()
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    await check_subscriptions(bot)

if __name__ == "__main__":
    asyncio.run(main())
