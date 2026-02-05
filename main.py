import os
import logging
import sqlite3
import random
import time
import requests
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Animation, Gift
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ContextTypes
)
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import threading

class GiftFilter(filters.MessageFilter):
    def filter(self, message):
        """Фильтр для определения подарков"""
        # Проверяем наличие атрибута 'gift' в сообщении
        return hasattr(message, 'gift') and message.gift is not None

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '7933867695:AAFsxbHgD3ludRAfWq13gkYoQavylGJOCtI')
ADMIN_ID = 6059673725  # Ваш ID администратора
DB_NAME = 'nft_gift_bot.db'
WALLET_ADDRESS = "TVRAzpJQrzUy3wp1Kw4y2WNb8Y9TSqcuvM"  # USDT TRC20

# Конфигурация веб-панели
WEB_USERNAME = "admin"
WEB_PASSWORD = generate_password_hash("strong_password")
SECRET_KEY = "super_secret_key"

# После других констант
NFT_CATEGORIES = {
    "common": {"base": 30, "bonus_range": (5, 15)},
    "rare": {"base": 70, "bonus_range": (10, 25)},
    "epic": {"base": 150, "bonus_range": (20, 50)},
    "legendary": {"base": 300, "bonus_range": (50, 100)}
}

DAILY_GIFT_LIMIT = 3  # Максимум 3 NFT подарка в день

# regular_gift = Gift(id="reg123", title="Обычный подарок")

# Инициализация Flask
app = Flask(__name__)
app.secret_key = SECRET_KEY

# База данных NFT подарков (будет заполнена парсингом)
NFT_GIFTS = []
BONUS_MULTIPLIER = 1.0  # Множитель ежедневного бонуса

# Правила и уведомления
RULES_TEXT = (
    "📜 Правила платформы:\n\n"
    "1. Все цены на NFT основаны на данных из @Tonnel_Network_bot\n"
    "2. За каждую покупку NFT вы получаете звёзды\n"
    "3. Бонусные звёзды начисляются случайным образом\n"
    "4. Криптовалютные платежи обрабатываются в течение 24 часов\n\n"
    "⚠️ Платформа оставляет за право изменять условия начисления бонусов"
)

def is_verified_nft(gift_id: str) -> bool:
    """Проверяет NFT через API маркетплейса"""
    try:
        # В реальной системе заменить на настоящий API
        response = requests.get(
            f"https://api.nft-marketplace.com/verify/{gift_id}",
            timeout=5
        )
        return response.json().get('verified', False)
    except:
        return False
    
def detect_nft_category(gift) -> str:
    """Определяет категорию NFT подарка"""
    # Простая эмуляция - в реальной системе использовать анализ метаданных
    if "rare" in gift.title.lower():
        return "rare"
    elif "epic" in gift.title.lower():
        return "epic"
    elif "legendary" in gift.title.lower():
        return "legendary"
    return "common"

def calculate_nft_value(gift) -> int:
    """Рассчитывает стоимость с учетом категории NFT"""
    category = detect_nft_category(gift)
    config = NFT_CATEGORIES.get(category, NFT_CATEGORIES["common"])
    bonus = random.randint(*config["bonus_range"])
    return config["base"] + bonus

# Парсинг данных из @Tonnel_Network_bot
def parse_tonnel_bot():
    """Парсинг данных из Tonnel Network бота (имитация)"""
    # В реальной реализации используйте:
    # 1. Telethon для подключения к аккаунту Telegram
    # 2. Парсинг сообщений бота @Tonnel_Network_bot
    # 3. Извлечение данных о NFT
    
    # Имитация данных
    return [
        {"id": "TONNEL-001", "name": "Digital Art #1", "price": random.randint(1000, 5000), "bonus": random.randint(1, 10)},
        {"id": "TONNEL-002", "name": "CryptoPunk #999", "price": random.randint(5000, 15000), "bonus": random.randint(5, 15)},
        {"id": "TONNEL-003", "name": "Bored Ape #42", "price": random.randint(10000, 30000), "bonus": random.randint(10, 20)},
        {"id": "TONNEL-004", "name": "Metaverse Land", "price": random.randint(3000, 8000), "bonus": random.randint(3, 12)},
        {"id": "TONNEL-005", "name": "Rare Crypto Stamp", "price": random.randint(2000, 6000), "bonus": random.randint(2, 8)},
    ]

def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        stars INTEGER DEFAULT 0,
        referral_code TEXT UNIQUE,
        referred_by INTEGER DEFAULT 0,
        verified INTEGER DEFAULT 0,
        last_bonus_date TEXT
    )
    ''')
    
    # Таблица NFT
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS nfts (
        id TEXT PRIMARY KEY,
        name TEXT,
        market_price INTEGER,
        bonus_stars INTEGER,
        expiration_date TEXT
    )
    ''')
    
    # Таблица транзакций
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        nft_id TEXT,
        nft_name TEXT,
        market_price INTEGER,
        received_stars INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица крипто-платежей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS crypto_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        tx_hash TEXT,
        status TEXT DEFAULT 'pending',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица рефералов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        bonus_awarded INTEGER DEFAULT 0,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Таблица ограниченных предложений
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS limited_offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nft_id TEXT,
        bonus_multiplier REAL DEFAULT 1.5,
        start_time TEXT,
        end_time TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

def update_nft_gifts():
    """Обновление списка NFT подарков"""
    global NFT_GIFTS
    NFT_GIFTS = parse_tonnel_bot()
    
    # Обновление базы данных
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Удаляем устаревшие NFT
    cursor.execute("DELETE FROM nfts WHERE expiration_date < datetime('now')")
    
    # Добавляем новые
    for nft in NFT_GIFTS:
        # Случайная дата истечения (1-7 дней)
        expiration = (datetime.now() + timedelta(days=random.randint(1, 7))).strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('''
        INSERT OR REPLACE INTO nfts (id, name, market_price, bonus_stars, expiration_date)
        VALUES (?, ?, ?, ?, ?)
        ''', (nft['id'], nft['name'], nft['price'], nft['bonus'], expiration))
    
    conn.commit()
    conn.close()

def get_user(user_id: int):
    """Получение информации о пользователе"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user(user_id: int, username: str, first_name: str, last_name: str, verified=False):
    """Обновление данных пользователя"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if not get_user(user_id):
        # Генерация реферального кода
        ref_code = f"REF{user_id}{int(time.time()) % 10000}"
        cursor.execute('''
        INSERT INTO users (user_id, username, first_name, last_name, stars, referral_code, verified)
        VALUES (?, ?, ?, ?, 0, ?, ?)
        ''', (user_id, username, first_name, last_name, ref_code, int(verified)))
    else:
        cursor.execute('''
        UPDATE users 
        SET username = ?, first_name = ?, last_name = ?, verified = ?
        WHERE user_id = ?
        ''', (username, first_name, last_name, int(verified), user_id))
    
    conn.commit()
    conn.close()

def add_stars(user_id: int, amount: int):
    """Добавление звезд пользователю"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET stars = stars + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def record_nft_transaction(user_id: int, nft_id: str, nft_name: str, market_price: int, received_stars: int):
    """Запись транзакции NFT"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO transactions (user_id, nft_id, nft_name, market_price, received_stars)
    VALUES (?, ?, ?, ?, ?)
    ''', (user_id, nft_id, nft_name, market_price, received_stars))
    conn.commit()
    conn.close()

def get_referral_bonus(user_id: int):
    """Получение реферального бонуса"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Получаем количество рефералов
    cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND bonus_awarded = 0', (user_id,))
    new_referrals = cursor.fetchone()[0]
    
    if new_referrals > 0:
        # Начисляем 10 звезд за каждого нового реферала
        bonus = new_referrals * 10
        cursor.execute('UPDATE users SET stars = stars + ? WHERE user_id = ?', (bonus, user_id))
        cursor.execute('UPDATE referrals SET bonus_awarded = 1 WHERE referrer_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        return bonus
    
    conn.close()
    return 0

def get_daily_bonus(user_id: int):
    """Проверка и выдача ежедневного бонуса"""
    global BONUS_MULTIPLIER

    user = get_user(user_id)
    if not user:
        return 0
    
    today = datetime.now().strftime("%Y-%m-%d")
    last_bonus = user[8] if len(user) > 8 else None
    
    if last_bonus != today:
        # Бонус: 5-15 звезд + множитель
        base_bonus = random.randint(5, 15)
        bonus = int(base_bonus * BONUS_MULTIPLIER)
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET stars = stars + ?, last_bonus_date = ? WHERE user_id = ?', 
                      (bonus, today, user_id))
        conn.commit()
        conn.close()
        
        # Обновляем множитель на следующий день
        BONUS_MULTIPLIER = round(random.uniform(1.0, 2.0), 2)
        
        return bonus
    
    return 0

def get_active_offers():
    """Получение активных ограниченных предложений"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT nfts.id, nfts.name, nfts.market_price, nfts.bonus_stars, 
           limited_offers.bonus_multiplier, limited_offers.end_time
    FROM limited_offers
    JOIN nfts ON limited_offers.nft_id = nfts.id
    WHERE datetime(limited_offers.end_time) > datetime('now')
    ''')
    offers = cursor.fetchall()
    conn.close()
    
    return [{
        "id": o[0],
        "name": o[1],
        "market_price": o[2],
        "base_bonus": o[3],
        "bonus_multiplier": o[4],
        "end_time": o[5]
    } for o in offers]

def create_payment(user_id: int, amount: int):
    """Создание записи о крипто-платеже"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO crypto_payments (user_id, amount)
    VALUES (?, ?)
    ''', (user_id, amount))
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return payment_id

def verify_payment(tx_hash: str):
    """Проверка крипто-платежа (имитация)"""
    # В реальной реализации: подключение к blockchain explorer API
    if tx_hash.startswith("TRX") and len(tx_hash) > 20:
        return True
    return False

# ================= Telegram Bot =================
async def start(update: Update, context: CallbackContext) -> None:
    """Обработка команды /start"""
    try:
        user = update.effective_user
        args = context.args if context.args else []
        
        # Проверка реферальной ссылки
        referred_by = 0
        if args and args[0].startswith("REF"):
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (args[0],))
                referrer = cursor.fetchone()
                if referrer:
                    referred_by = referrer[0]
                    # Записываем реферала
                    cursor.execute('''
                    INSERT OR IGNORE INTO referrals (referrer_id, referred_id)
                    VALUES (?, ?)
                    ''', (referred_by, user.id))
                    conn.commit()
            except Exception as e:
                logger.error(f"Referral error: {str(e)}")
            finally:
                conn.close()
        
        # Обработка None-значений
        username = user.username if user.username else ""
        first_name = user.first_name if user.first_name else "Пользователь"
        last_name = user.last_name if user.last_name else ""
        
        update_user(
            user.id, 
            username, 
            first_name, 
            last_name, 
            verified=False
        )
        
        # Ежедневный бонус
        daily_bonus = get_daily_bonus(user.id)
        bonus_msg = f"\n🎁 Вы получили ежедневный бонус: {daily_bonus} ⭐" if daily_bonus else ""
        
        # Реферальный бонус
        ref_bonus = get_referral_bonus(user.id)
        ref_msg = f"\n👥 Реферальный бонус: +{ref_bonus} ⭐" if ref_bonus else ""
        
        # Главное меню
        keyboard = [
            [InlineKeyboardButton("🎨 NFT Магазин", callback_data='nft_shop')],
            [InlineKeyboardButton("⭐ Мой баланс", callback_data='balance')],
            [InlineKeyboardButton("💰 Купить звёзды", callback_data='buy_stars')],
            [InlineKeyboardButton("🎁 Ограниченные предложения", callback_data='limited_offers')],
            [InlineKeyboardButton("📜 Правила платформы", callback_data='rules')]
        ]
        
        if referred_by:
            keyboard.append([InlineKeyboardButton("👥 Реферальная программа", callback_data='referral')])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Формирование приветствия
        greeting_name = first_name if first_name else username if username else "друг"
        greeting = f"👋 Привет, {greeting_name}!"
        
        await update.message.reply_text(
            f"{greeting}\n"
            "Добро пожаловать в эксклюзивный NFT магазин!\n\n"
            f"{bonus_msg}{ref_msg}\n"
            f"✨ Сегодняшний бонусный множитель: x{BONUS_MULTIPLIER}",
            reply_markup=reply_markup
        )
    
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}")
        if update.message:
            await update.message.reply_text("⚠️ Произошла ошибка при запуске бота. Пожалуйста, попробуйте позже.")

async def help_command(update: Update, context: CallbackContext) -> None:
    """Показывает справку по командам"""
    await update.message.reply_text(
        "💎 Помощь по боту:\n\n"
        "🎁 Отправьте NFT подарок, чтобы получить звёзды!\n"
        "⭐ 1 NFT подарок = 50-80 звёзд\n\n"
        "Основные команды:\n"
        "/start - Начать работу\n"
        "/balance - Проверить баланс\n"
        "/shop - Магазин NFT\n"
        "/gifts - Мои NFT подарки\n"
        "💡 Просто отправьте NFT подарок как обычное сообщение"
    )

async def show_rules(update: Update, context: CallbackContext) -> None:
    """Показать правила платформы"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        RULES_TEXT,
        reply_markup=reply_markup
    )

async def nft_shop(update: Update, context: CallbackContext) -> None:
    """Показать магазин NFT"""
    query = update.callback_query
    await query.answer()
    
    # Обновляем цены перед показом
    update_nft_gifts()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM nfts WHERE expiration_date > datetime('now')")
    nfts = cursor.fetchall()
    conn.close()
    
    if not nfts:
        await query.edit_message_text("⚠️ NFT подарки временно недоступны. Попробуйте позже.")
        return
    
    keyboard = []
    for nft in nfts:
        # Исправлен индекс: name = nft[1], bonus_stars = nft[3]
        # Добавлен ID NFT в кнопку
        random_bonus = random.randint(5, 20)
        keyboard.append([
            InlineKeyboardButton(
                f"{nft[1]} - {nft[3]} ⭐ (+{random_bonus}% бонус)", 
                callback_data=f'nft_{nft[0]}'  # ID NFT
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data='nft_shop')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎨 NFT Магазин:\n\n"
        "💎 Цены обновлены по данным @Tonnel_Network_bot\n"
        "✨ При покупке вы получаете звёзды с дополнительным бонусом",
        reply_markup=reply_markup
    )

async def nft_selected(update: Update, context: CallbackContext) -> None:
    """Обработка выбора NFT"""
    query = update.callback_query
    await query.answer()
    
    nft_id = query.data.split('_')[1]
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM nfts WHERE id = ?", (nft_id,))
    nft = cursor.fetchone()
    conn.close()
    
    if not nft:
        await query.edit_message_text("⚠️ NFT не найден или срок действия истёк!")
        return
    
    # Исправление индексов:
    # nft[0] - ID
    # nft[1] - name
    # nft[2] - market_price
    # nft[3] - bonus_stars
    # nft[4] - expiration_date
    
    # Случайный бонус (5-20% от цены)
    random_bonus = random.randint(5, 20)
    bonus_stars = nft[3] + int(nft[3] * random_bonus / 100)  # Исправлен индекс
    
    user_id = query.from_user.id
    add_stars(user_id, bonus_stars)
    record_nft_transaction(user_id, nft[0], nft[1], nft[2], bonus_stars)
    
    # Сообщение для пользователя
    await query.edit_message_text(
        f"🎉 Вы приобрели NFT: {nft[1]}\n"
        f"🏷️ Рыночная цена: {nft[2]} USDT\n"  # Исправлен индекс
        f"🎲 Случайный бонус: +{random_bonus}%\n\n"
        f"✨ Вы получили: {bonus_stars} ⭐\n\n"
        f"💎 Теперь у вас: {get_user(user_id)[4]} ⭐\n\n"
        f"🔍 NFT ID: {nft[0]}"
    )
    
    # Уведомление администратору
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"⚠️ Новая покупка NFT!\n"
             f"👤 Пользователь: @{query.from_user.username if query.from_user.username else 'N/A'}\n"
             f"🎨 NFT: {nft[1]}\n"
             f"🏷️ Цена: {nft[2]} USDT\n"  # Исправлен индекс
             f"🎁 Бонус: {random_bonus}%\n"
             f"💎 Начислено: {bonus_stars} ⭐"
    )

async def show_balance(update: Update, context: CallbackContext) -> None:
    """Показать баланс пользователя"""
    query = update.callback_query
    await query.answer()
    
    user = get_user(query.from_user.id)
    if not user:
        await query.edit_message_text("❌ Ваш профиль не найден!")
        return
    
    keyboard = [
        [InlineKeyboardButton("🎨 NFT Магазин", callback_data='nft_shop')],
        [InlineKeyboardButton("💰 Купить звёзды", callback_data='buy_stars')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    verified = "✅" if user[7] else "❌"
    
    await query.edit_message_text(
        f"💎 Ваш баланс: {user[4]} звёзд\n"
        f"🛡️ Верификация: {verified}\n\n"
        f"✨ Сегодняшний бонусный множитель: x{BONUS_MULTIPLIER}\n"
        "⏳ Следующий ежедневный бонус через 24 часа",
        reply_markup=reply_markup
    )

async def show_balance(update: Update, context: CallbackContext) -> None:
    """Показать баланс пользователя"""
    query = update.callback_query
    await query.answer()
    
    user = get_user(query.from_user.id)
    if not user:
        await query.edit_message_text("❌ Ваш профиль не найден!")
        return
    
    keyboard = [
        [InlineKeyboardButton("🎨 NFT Магазин", callback_data='nft_shop')],
        [InlineKeyboardButton("💰 Купить звёзды", callback_data='buy_stars')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    verified = "✅" if user[7] else "❌"
    
    await query.edit_message_text(
        f"💎 Ваш баланс: {user[4]} звёзд\n"
        f"🛡️ Верификация: {verified}\n\n"
        "✨ Сегодняшний бонусный множитель: x{BONUS_MULTIPLIER}\n"
        "⏳ Следующий ежедневный бонус через 24 часа",
        reply_markup=reply_markup
    )

# В функции buy_stars_menu замените:
async def buy_stars_menu(update: Update, context: CallbackContext) -> None:
    """Меню покупки звезд"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("100 звёзд - 10 USDT", callback_data='buy_100')],
        [InlineKeyboardButton("500 звёзд - 50 USDT", callback_data='buy_500')],
        [InlineKeyboardButton("1000 звёзд - 100 USDT", callback_data='buy_1000')],
        [InlineKeyboardButton("5000 звёзд - 500 USDT", callback_data='buy_5000')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Экранируем адрес кошелька для Markdown
    escaped_wallet = WALLET_ADDRESS.replace("_", "\\_").replace("*", "\\*")
    
    await query.edit_message_text(
        "💰 Выберите пакет звёзд:\n\n"
        "💳 Оплата в USDT (TRC20)\n"
        f"📭 Кошелек: `{escaped_wallet}`\n\n"
        "⚠️ После оплаты отправьте хэш транзакции боту",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# В функции process_payment замените:
async def process_payment(update: Update, context: CallbackContext) -> None:
    """Обработка выбора пакета звезд"""
    query = update.callback_query
    await query.answer()
    
    amount = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    # Создаем запись о платеже
    payment_id = create_payment(user_id, amount)
    
    # Разбиваем сообщение на части
    message_parts = [
        f"💳 Вы выбрали пакет: {amount} звезд за {amount//10} USDT\n\n",
        f"📭 Отправьте {amount//10} USDT на кошелек:\n",
        f"`{WALLET_ADDRESS}`\n\n",
        "После оплаты отправьте хэш транзакции в формате:\n",
        f"`/pay {payment_id} TX_HASH`\n\n",
        "Пример:\n",
        f"`/pay {payment_id} TRX123...456`"
    ]
    
    # Собираем сообщение с правильным форматированием
    full_message = "".join(message_parts)
    
    await query.edit_message_text(
        full_message,
        parse_mode='Markdown'
    )

async def handle_payment(update: Update, context: CallbackContext) -> None:
    """Обработка платежной транзакции"""
    user_id = update.message.from_user.id
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("❌ Неверный формат. Используйте: /pay <ID_платежа> <TX_HASH>")
        return
    
    payment_id = args[0]
    tx_hash = args[1]
    
    # Проверяем платеж
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM crypto_payments WHERE id = ? AND user_id = ?', (payment_id, user_id))
    payment = cursor.fetchone()
    
    if not payment:
        await update.message.reply_text("❌ Платеж не найден!")
        return
    
    if payment[4] != 'pending':
        await update.message.reply_text(f"ℹ️ Этот платеж уже обработан. Статус: {payment[4]}")
        return
    
    # Верифицируем платеж (имитация)
    if verify_payment(tx_hash):
        # Обновляем статус
        cursor.execute('UPDATE crypto_payments SET status = "completed", tx_hash = ? WHERE id = ?', (tx_hash, payment_id))
        
        # Начисляем звезды
        add_stars(user_id, payment[2])
        
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ Платеж подтвержден!\n"
            f"💎 Ваш баланс пополнен на {payment[2]} звезд\n\n"
            f"💳 ID транзакции: {tx_hash}"
        )
        
        # Уведомление администратору
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💰 Новый крипто-платеж!\n"
                 f"👤 Пользователь: @{update.message.from_user.username}\n"
                 f"💎 Сумма: {payment[2]} звезд\n"
                 f"💳 TX Hash: {tx_hash}"
        )
    else:
        cursor.execute('UPDATE crypto_payments SET status = "failed", tx_hash = ? WHERE id = ?', (tx_hash, payment_id))
        conn.commit()
        conn.close()
        await update.message.reply_text("❌ Транзакция не найдена. Проверьте хэш и попробуйте снова.")

# Добавьте этот код в раздел функций оплаты

async def test_payment(update: Update, context: CallbackContext) -> None:
    """Инициировать тестовую оплату"""
    user_id = update.message.from_user.id
    
    # Создаем тестовый платеж на 100 звезд
    amount = 100
    payment_id = create_payment(user_id, amount)
    tx_hash = f"TEST_{payment_id}_{int(time.time())}"
    
    # Имитация успешной оплаты
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE crypto_payments SET status = "completed", tx_hash = ? WHERE id = ?',
        (tx_hash, payment_id))
    conn.commit()
    conn.close()
    
    # Начисляем звезды
    add_stars(user_id, amount)
    
    await update.message.reply_text(
        f"✅ Тестовый платеж успешно обработан!\n"
        f"💎 Ваш баланс пополнен на {amount} звезд\n"
        f"💳 ID транзакции: {tx_hash}\n\n"
        f"💡 Теперь у вас: {get_user(user_id)[4]} ⭐"
    )

# В функции main добавьте обработчик команды:


# Обновите функцию verify_payment для поддержки тестовых платежей:
def verify_payment(tx_hash: str):
    """Проверка крипто-платежа (с поддержкой тестовых)"""
    # Тестовые платежи
    if tx_hash.startswith("TEST_"):
        return True
        
    # В реальной реализации: подключение к blockchain explorer API
    if tx_hash.startswith("TRX") and len(tx_hash) > 20:
        return True
    return False

# В функции handle_payment добавьте специальное сообщение для тестовых платежей:
async def handle_payment(update: Update, context: CallbackContext) -> None:
    """Обработка платежной транзакции"""
    user_id = update.message.from_user.id
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("❌ Неверный формат. Используйте: /pay <ID_платежа> <TX_HASH>")
        return
    
    payment_id = args[0]
    tx_hash = args[1]
    
    # Проверяем платеж
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM crypto_payments WHERE id = ? AND user_id = ?', (payment_id, user_id))
    payment = cursor.fetchone()
    
    if not payment:
        await update.message.reply_text("❌ Платеж не найден!")
        return
    
    if payment[4] != 'pending':
        await update.message.reply_text(f"ℹ️ Этот платеж уже обработан. Статус: {payment[4]}")
        return
    
    # Верифицируем платеж
    if verify_payment(tx_hash):
        # Обновляем статус
        cursor.execute('UPDATE crypto_payments SET status = "completed", tx_hash = ? WHERE id = ?', (tx_hash, payment_id))
        
        # Начисляем звезды
        add_stars(user_id, payment[2])
        
        conn.commit()
        conn.close()
        
        # Специальное сообщение для тестовых платежей
        if tx_hash.startswith("TEST_"):
            message = (
                f"✅ Тестовый платеж подтвержден!\n"
                f"💎 Ваш баланс пополнен на {payment[2]} звезд (тест)\n\n"
                f"💳 ID транзакции: {tx_hash}"
            )
        else:
            message = (
                f"✅ Платеж подтвержден!\n"
                f"💎 Ваш баланс пополнен на {payment[2]} звезд\n\n"
                f"💳 ID транзакции: {tx_hash}"
            )
        
        await update.message.reply_text(message)
        
        # Уведомление администратору
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💰 {'ТЕСТОВЫЙ ' if tx_hash.startswith('TEST_') else ''}Крипто-платеж!\n"
                 f"👤 Пользователь: @{update.message.from_user.username}\n"
                 f"💎 Сумма: {payment[2]} звезд\n"
                 f"💳 TX Hash: {tx_hash}"
        )
    else:
        cursor.execute('UPDATE crypto_payments SET status = "failed", tx_hash = ? WHERE id = ?', (tx_hash, payment_id))
        conn.commit()
        conn.close()
        await update.message.reply_text("❌ Транзакция не найдена. Проверьте хэш и попробуйте снова.")

# Обновите функцию process_payment для тестовых инструкций
async def process_payment(update: Update, context: CallbackContext) -> None:
    """Обработка выбора пакета звезд"""
    query = update.callback_query
    await query.answer()
    
    amount = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    # Создаем запись о платеже
    payment_id = create_payment(user_id, amount)
    
    # Форматируем сообщение с тестовыми инструкциями
    message = (
        f"💳 Вы выбрали пакет: {amount} звезд за {amount//10} USDT\n\n"
        f"📭 Отправьте {amount//10} USDT на кошелек:\n"
        f"`{WALLET_ADDRESS}`\n\n"
        "После оплаты отправьте хэш транзакции в формате:\n"
        f"`/pay {payment_id} TX_HASH`\n\n"
        "Пример:\n"
        f"`/pay {payment_id} TRX123...456`\n\n"
        # "💡 Для тестирования без оплаты используйте:\n"
        # f"`/test_pay` - получить тестовые 100 звезд\n"
        # f"Или отправьте `/pay {payment_id} TEST_{payment_id}`"
    )
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown'
    )

# Добавьте эти функции в основной код

async def send_gift_handler(update: Update, context: CallbackContext) -> None:
    """Обработчик отправки подарков"""
    message = update.message
    user_id = message.from_user.id
    
    # Проверяем, является ли подарок NFT
    if not is_nft_gift(message.gift):
        await message.reply_text(
            "Извините, но мы не принимаем в качестве оплаты обычные подарки. "
            "Принимаются только NFT подарки."
        )
        return
    
    # Обрабатываем NFT подарок
    await process_nft_gift(update, context, message.gift)

def is_nft_gift(gift) -> bool:
    """Проверяет, является ли подарок NFT"""
    # Основной признак NFT подарка - наличие premium_animation
    return hasattr(gift, 'premium_animation') and gift.premium_animation is not None

async def process_nft_gift(update: Update, context: CallbackContext, gift) -> None:
    """Обрабатывает NFT подарок и начисляет звёзды"""
    user_id = update.message.from_user.id
    user = get_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ Ваш профиль не найден! Сначала запустите /start")
        return
    
    # Проверка лимита
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT COUNT(*) FROM gift_transactions 
    WHERE user_id = ? AND DATE(timestamp) = DATE('now')
    ''', (user_id,))
    gifts_today = cursor.fetchone()[0]
    
    if gifts_today >= DAILY_GIFT_LIMIT:
        await update.message.reply_text(
            "❌ Вы достигли дневного лимита NFT подарков! "
            f"Максимум {DAILY_GIFT_LIMIT} подарка в день."
        )
        conn.close()
        return
    
    # Получаем информацию о NFT подарке
    nft_value = calculate_nft_value(gift)
    
    # Начисляем звёзды
    add_stars(user_id, nft_value)
    
    # Записываем транзакцию
    cursor.execute('''
    INSERT INTO gift_transactions (user_id, gift_id, stars_received)
    VALUES (?, ?, ?)
    ''', (user_id, gift.id, nft_value))
    conn.commit()
    conn.close()
    
    # Формируем сообщение
    gift_type = gift.title if hasattr(gift, 'title') else "NFT Подарок"
    
    await update.message.reply_text(
        f"🎉 Спасибо за {gift_type}!\n"
        f"💎 Категория: {detect_nft_category(gift).capitalize()}\n"
        f"✨ Вы получили: {nft_value} ⭐\n"
        f"💳 Теперь ваш баланс: {get_user(user_id)[4]} ⭐\n\n"
        "💡 Вы можете проверить баланс командой /balance"
    )
    
    # Уведомление администратору
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🎁 Новый NFT подарок!\n"
             f"👤 Пользователь: @{update.message.from_user.username}\n"
             f"🎁 Тип: {gift_type} ({detect_nft_category(gift)})\n"
             f"💎 Начислено звёзд: {nft_value}"
    )

def calculate_nft_value(gift) -> int:
    """Рассчитывает стоимость NFT подарка в звёздах"""
    # В реальной реализации используйте API для оценки стоимости NFT
    # Базовая стоимость + случайный бонус
    base_value = 50
    bonus = random.randint(5, 30)
    return base_value + bonus

# В init_db() добавьте новую таблицу:
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # ... существующие таблицы ...
    
    # Таблица для учета NFT подарков
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS gift_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        gift_id TEXT,
        stars_received INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()


async def show_referral(update: Update, context: CallbackContext) -> None:
    """Показать реферальную программу"""
    query = update.callback_query
    await query.answer()
    
    user = get_user(query.from_user.id)
    if not user:
        await query.edit_message_text("❌ Ваш профиль не найден!")
        return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user[0],))
    referrals_count = cursor.fetchone()[0]
    conn.close()
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"👥 Реферальная программа\n\n"
        f"💎 Ваш реферальный код: `{user[5]}`\n"
        f"👥 Приглашено пользователей: {referrals_count}\n\n"
        "✨ За каждого приглашенного друга:\n"
        "- Вы получаете 10 звезд\n"
        "- Друг получает 5 звезд при первой покупке\n\n"
        "📢 Поделитесь ссылкой:\n"
        f"https://t.me/glftsrelayer_bot?start={user[5]}",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def show_limited_offers(update: Update, context: CallbackContext) -> None:
    """Показать ограниченные предложения"""
    query = update.callback_query
    await query.answer()
    
    offers = get_active_offers()
    if not offers:
        await query.edit_message_text("⏳ В данный момент нет активных предложений. Загляните позже!")
        return
    
    keyboard = []
    for offer in offers:
        time_left = datetime.fromisoformat(offer['end_time']) - datetime.now()
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        
        keyboard.append([
            InlineKeyboardButton(
                f"{offer['name']} - x{offer['bonus_multiplier']} бонус | Осталось: {hours}ч {minutes}мин", 
                callback_data=f'offer_{offer["id"]}'
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🔥 Ограниченные предложения:\n\n"
        "💎 Специальные NFT с увеличенным бонусом!\n"
        "⏱️ Предложение действует ограниченное время",
        reply_markup=reply_markup
    )

async def back_to_main(update: Update, context: CallbackContext) -> None:
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🎨 NFT Магазин", callback_data='nft_shop')],
        [InlineKeyboardButton("⭐ Мой баланс", callback_data='balance')],
        [InlineKeyboardButton("💰 Купить звёзды", callback_data='buy_stars')],
        [InlineKeyboardButton("🎁 Ограниченные предложения", callback_data='limited_offers')],
        [InlineKeyboardButton("📜 Правила платформы", callback_data='rules')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Главное меню NFT магазина:",
        reply_markup=reply_markup
    )

# ================= Web Panel =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == WEB_USERNAME and check_password_hash(WEB_PASSWORD, password):
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        
        return "Неверные учетные данные", 401
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Статистика пользователей
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE verified = 1')
    verified_users = cursor.fetchone()[0]
    
    # Статистика транзакций
    cursor.execute('SELECT SUM(received_stars) FROM transactions')
    total_stars = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM crypto_payments WHERE status = "completed"')
    completed_payments = cursor.fetchone()[0]
    
    # Последние транзакции
    cursor.execute('''
    SELECT users.user_id, users.username, transactions.nft_name, transactions.received_stars, transactions.timestamp
    FROM transactions
    JOIN users ON transactions.user_id = users.user_id
    ORDER BY transactions.timestamp DESC
    LIMIT 10
    ''')
    recent_transactions = cursor.fetchall()
    
    # Активные NFT
    cursor.execute('SELECT * FROM nfts WHERE expiration_date > datetime("now")')
    active_nfts = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard.html',
                           total_users=total_users,
                           verified_users=verified_users,
                           total_stars=total_stars,
                           completed_payments=completed_payments,
                           recent_transactions=recent_transactions,
                           active_nfts=active_nfts,
                           wallet_address=WALLET_ADDRESS)

@app.route('/users')
def users():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users ORDER BY stars DESC')
    users = cursor.fetchall()
    conn.close()
    
    return render_template('users.html', users=users)

@app.route('/verify_user/<int:user_id>')
def verify_user(user_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET verified = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('users'))

@app.route('/transactions')
def transactions():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT transactions.*, users.username 
    FROM transactions 
    JOIN users ON transactions.user_id = users.user_id
    ORDER BY timestamp DESC
    ''')
    transactions = cursor.fetchall()
    conn.close()
    
    return render_template('transactions.html', transactions=transactions)

@app.route('/telegram-auth', methods=['POST'])
def telegram_auth():
    """Обработка данных после авторизации через Telegram"""
    user_info = request.json.get('user_info')
    if user_info:
        user_data = json.loads(user_info)
        session['user_info'] = user_data  # Сохраняем данные пользователя в сессии
        return json.dumps({"status": "success", "message": "User authenticated successfully"})
    return json.dumps({"status": "error", "message": "Authorization failed"}), 400

@app.route('/payments')
def payments():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT crypto_payments.*, users.username 
    FROM crypto_payments 
    JOIN users ON crypto_payments.user_id = users.user_id
    ORDER BY timestamp DESC
    ''')
    payments = cursor.fetchall()
    conn.close()
    
    return render_template('payments.html', payments=payments)

# ================= Main =================
def run_flask():
    """Запуск Flask приложения"""
    app.run(host='0.0.0.0', port=5000)

# ================= Telegram Bot Handlers =================
async def nft_shop(update: Update, context: CallbackContext) -> None:
    """Показать магазин NFT"""
    query = update.callback_query
    await query.answer()
    
    # Обновляем цены перед показом
    update_nft_gifts()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM nfts WHERE expiration_date > datetime('now')")
    nfts = cursor.fetchall()
    conn.close()
    
    if not nfts:
        await query.edit_message_text("⚠️ NFT подарки временно недоступны. Попробуйте позже.")
        return
    
    keyboard = []
    for nft in nfts:
        # Исправлен индекс: name = nft[1], bonus_stars = nft[3]
        # Добавлен ID NFT в кнопку
        random_bonus = random.randint(5, 20)
        keyboard.append([
            InlineKeyboardButton(
                f"{nft[1]} - {nft[3]} ⭐ (+{random_bonus}% бонус)", 
                callback_data=f'nft_{nft[0]}'  # ID NFT
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data='nft_shop')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎨 NFT Магазин:\n\n"
        "💎 Цены обновлены по данным @Tonnel_Network_bot\n"
        "✨ При покупке вы получаете звёзды с дополнительным бонусом",
        reply_markup=reply_markup
    )

async def nft_selected(update: Update, context: CallbackContext) -> None:
    """Обработка выбора NFT"""
    query = update.callback_query
    await query.answer()
    
    nft_id = query.data.split('_')[1]
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM nfts WHERE id = ?", (nft_id,))
    nft = cursor.fetchone()
    conn.close()
    
    if not nft:
        await query.edit_message_text("⚠️ NFT не найден или срок действия истёк!")
        return
    
    # Исправление индексов:
    # nft[0] - ID
    # nft[1] - name
    # nft[2] - market_price
    # nft[3] - bonus_stars
    # nft[4] - expiration_date
    
    # Случайный бонус (5-20% от цены)
    random_bonus = random.randint(5, 20)
    bonus_stars = nft[3] + int(nft[3] * random_bonus / 100)  # Исправлен индекс
    
    user_id = query.from_user.id
    add_stars(user_id, bonus_stars)
    record_nft_transaction(user_id, nft[0], nft[1], nft[2], bonus_stars)
    
    # Сообщение для пользователя
    await query.edit_message_text(
        f"🎉 Вы приобрели NFT: {nft[1]}\n"
        f"🏷️ Рыночная цена: {nft[2]} USDT\n"  # Исправлен индекс
        f"🎲 Случайный бонус: +{random_bonus}%\n\n"
        f"✨ Вы получили: {bonus_stars} ⭐\n\n"
        f"💎 Теперь у вас: {get_user(user_id)[4]} ⭐\n\n"
        f"🔍 NFT ID: {nft[0]}"
    )
    
    # Уведомление администратору
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"⚠️ Новая покупка NFT!\n"
             f"👤 Пользователь: @{query.from_user.username if query.from_user.username else 'N/A'}\n"
             f"🎨 NFT: {nft[1]}\n"
             f"🏷️ Цена: {nft[2]} USDT\n"  # Исправлен индекс
             f"🎁 Бонус: {random_bonus}%\n"
             f"💎 Начислено: {bonus_stars} ⭐"
    )

async def show_balance(update: Update, context: CallbackContext) -> None:
    """Показать баланс пользователя"""
    query = update.callback_query
    await query.answer()
    
    user = get_user(query.from_user.id)
    if not user:
        await query.edit_message_text("❌ Ваш профиль не найден!")
        return
    
    keyboard = [
        [InlineKeyboardButton("🎨 NFT Магазин", callback_data='nft_shop')],
        [InlineKeyboardButton("💰 Купить звёзды", callback_data='buy_stars')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    verified = "✅" if user[7] else "❌"
    
    await query.edit_message_text(
        f"💎 Ваш баланс: {user[4]} звёзд\n"
        f"🛡️ Верификация: {verified}\n\n"
        f"✨ Сегодняшний бонусный множитель: x{BONUS_MULTIPLIER}\n"
        "⏳ Следующий ежедневный бонус через 24 часа",
        reply_markup=reply_markup
    )

# В функции main() обновляем обработчики:
def main() -> None:
    """Запуск бота"""
    init_db()
    update_nft_gifts()
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    gift_filter = GiftFilter()

    application = Application.builder().token(TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pay", handle_payment))
    application.add_handler(CommandHandler("test_pay", test_payment))

    # Обработчики callback-запросов (ИСПРАВЛЕНО)
    application.add_handler(CallbackQueryHandler(nft_shop, pattern='^nft_shop$'))
    application.add_handler(CallbackQueryHandler(show_balance, pattern='^balance$'))
    application.add_handler(CallbackQueryHandler(buy_stars_menu, pattern='^buy_stars$'))
    application.add_handler(CallbackQueryHandler(show_limited_offers, pattern='^limited_offers$'))
    application.add_handler(CallbackQueryHandler(show_rules, pattern='^rules$'))
    application.add_handler(CallbackQueryHandler(show_referral, pattern='^referral$'))
    application.add_handler(CallbackQueryHandler(back_to_main, pattern='^back$'))
    
    # Обработчики NFT (ИСПРАВЛЕНО)
    application.add_handler(CallbackQueryHandler(nft_selected, pattern='^nft_'))
    
    # Обработчики предложений
    application.add_handler(CallbackQueryHandler(nft_selected, pattern='^offer_'))

    # Обработчик NFT подарков
    application.add_handler(MessageHandler(gift_filter, send_gift_handler))
    
    # Обработчики покупки звезд
    for amount in [100, 500, 1000, 5000]:
        application.add_handler(
            CallbackQueryHandler(process_payment, pattern=f'^buy_{amount}$')
        )
    
    application.run_polling()

if __name__ == '__main__':
    main()