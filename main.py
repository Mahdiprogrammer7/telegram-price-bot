import os
import re
import time
import asyncio
import threading
import certifi
from flask import Flask
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi
from oilpriceapi import OilPriceAPI

# ==================== تنظیمات ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
MONGO_URI = os.environ.get("MONGO_URI", "").strip()
OIL_PRICE_API_KEY = os.environ.get("OIL_PRICE_API_KEY", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/your_channel")
DEVELOPER_NAME = os.environ.get("DEVELOPER_NAME", "مهدی نجفی")
FEEDBACK_ID = os.environ.get("FEEDBACK_ID", "@mahdi8iiii")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "your_bot_username") # بدون @

ADMIN_IDS = {x.strip() for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()}
ADMIN_PAGE_SIZE = 8
PRO_INVITE_THRESHOLD = 5
CHANNEL_POST_INTERVAL = 3600

CRYPTO_API_URL = 'https://api.abantether.com/api/v1/manager/otc/ticker'
FIAT_API_URL = 'https://cdn.jsdelivr.net/gh/HosseinOdd/Navasan-API@main/data/fiat.json'
GOLD_API_URL = 'https://cdn.jsdelivr.net/gh/HosseinOdd/Navasan-API@main/data/gold.json'

# ==================== لیست دارایی‌ها ====================
POPULAR_CRYPTOS = ["BTC", "ETH", "USDT", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "TON"]
POPULAR_FIATS = ["USD", "EUR", "AED", "TRY", "GBP", "IQD", "CNY", "JPY", "CAD", "AUD", "CHF", "SAR"]
POPULAR_GOLDS = ["gold_18", "coin_emami", "coin_half", "coin_quarter", "gold_miskal", "coin_bahar", "coin_gerami"]

FIAT_NAMES = {
    "USD": "دلار آمریکا", "EUR": "یورو", "GBP": "پوند انگلیس",
    "AED": "درهم امارات", "TRY": "لیر ترکیه", "CNY": "یوان چین",
    "JPY": "ین ژاپن", "CAD": "دلار کانادا", "AUD": "دلار استرالیا",
    "CHF": "فرانک سوئیس", "IQD": "دینار عراق", "SAR": "ریال عربستان",
    "KWD": "دینار کویت", "QAR": "ریال قطر", "OMR": "ریال عمان",
    "BHD": "دینار بحرین", "JOD": "دینار اردن", "RUB": "روبل روسیه",
    "INR": "روپیه هند", "PKR": "روپیه پاکستان", "AFN": "افغانی",
}

GOLD_NAMES = {
    "gold_18": "طلای ۱۸ عیار", "gold_24": "طلای ۲۴ عیار", "gold_miskal": "مثقال طلا",
    "coin_emami": "سکه امامی", "coin_bahar": "سکه بهار آزادی", "coin_half": "نیم سکه",
    "coin_quarter": "ربع سکه", "coin_gerami": "سکه گرمی",
}

# ==================== سیستم ترجمه ====================
TRANSLATIONS = {
    "fa": {
        "choose_language": "🌐 لطفاً زبان خود را انتخاب کنید:",
        "welcome_new": "سلام! 👋\n\nبه *ارز آنلاین* خوش آمدید.\n\nبرای شروع فقط *نام و نام خانوادگی* خود را وارد کنید:",
        "invalid_name": "❌ نام معتبر نیست (حداقل ۳ حرف). لطفاً دوباره وارد کنید:",
        "register_success": "✅ *ثبت‌نام با موفقیت انجام شد!*\n\n👤 نام: *{name}*\n🌐 زبان: {lang_name}\n\nخوش آمدی! از منوی زیر استفاده کن:",
        "welcome_back": "👋 سلام *{name}* عزیز! خوش برگشتی.\n\nاز منوی زیر استفاده کن:",
        "menu_title": "🏠 *منوی اصلی*\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        "menu_crypto": "🪙 ارز دیجیتال", "menu_fiat": "💵 ارزهای فیات", "menu_gold": "🥇 طلا و سکه",
        "menu_oil": "🛢️ نفت برنت", "menu_convert": "🔄 مبدل ارز", "menu_market": "📊 بازار امروز",
        "menu_fav": "⭐ علاقه‌مندی‌ها", "menu_alert": "🔔 هشدار قیمت", "menu_myalerts": "📋 هشدارهای من",
        "menu_list": "📊 لیست رمزارزها", "menu_profile": "👤 پروفایل من", "menu_invite": "🎁 دعوت دوستان",
        "menu_leaderboard": "🏆 جدول قهرمانان", "menu_help": "ℹ️ راهنما",
        "menu_main": "🏠 منوی اصلی", "menu_back": "🔙 بازگشت", "menu_cancel": "❌ انصراف",
        "profile_title": "👤 *پروفایل شما*", "profile_name": "📝 نام: *{name}*", "profile_lang": "🌐 زبان: {lang_name}",
        "profile_joined": "📅 تاریخ عضویت: {date}", "profile_invites": "🎁 تعداد دعوت‌شده‌ها: *{count}* نفر",
        "profile_user_type": "👑 نوع حساب: *{user_type}*", "user_type_special": "کاربر خاص ⭐", "user_type_normal": "کاربر عادی 👤",
        "pro_locked": "🔒 این قابلیت حرفه‌ای است.\n\nبرای فعال شدن دسترسی حرفه‌ای، حداقل *۵ نفر* را با لینک دعوت خودت به بات دعوت کن.",
        "profile_change_lang": "🌐 تغییر زبان", "profile_logout": "🚪 خروج از حساب",
        "logout_confirm": "⚠️ با خروج از حساب، پروفایل فعلی شما از حالت فعال خارج می‌شود و برای ورود بعدی باید دوباره ثبت‌نام کنید.\n\nآیا مطمئن هستید؟",
        "logout_done": "✅ از حساب خارج شدید.\n\nبرای ساخت پروفایل جدید، /start را بزنید.",
        "cancel": "✅ عملیات لغو شد.", "error": "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.", "not_found": "❌ یافت نشد.",
        "crypto_title": "🪙 *ارز دیجیتال*\n\nیکی از رمزارزها را انتخاب کنید:", "fiat_title": "💵 *ارزهای فیات*\n\nیکی از ارزها را انتخاب کنید:",
        "gold_title": "🥇 *طلا و سکه*\n\nیکی از گزینه‌ها را انتخاب کنید:", "market_title": "📊 *بازار امروز*",
        "footer": "\n\n━━━━━━━━━━━━━━━━━━\n👨‍💻 توسعه‌دهنده: *{dev}*\n📩 انتقادات: {feedback}",
        "force_join_title": "⚠️ *دسترسی محدود*", "force_join_text": "برای استفاده از ربات، لطفاً اول در کانال ما عضو شوید:\n\n📢 {channel}\n\nبعد از عضویت، روی دکمه زیر کلیک کنید:",
        "force_join_verify": "🔄 بررسی عضویت", "force_join_not_member": "❌ شما هنوز در کانال عضو نشده‌اید.\n\nلطفاً ابتدا در کانال عضو شوید و سپس دکمه بررسی را بزنید.",
        "invite_title": "🎁 *سیستم دعوت دوستان*", "invite_link": "🔗 لینک دعوت اختصاصی شما:", "invite_stats": "📊 *آمار شما:*",
        "invite_count": "• تعداد دعوت‌شده‌ها: *{count}* نفر", "invite_rank": "• رتبه شما: *#{rank}*",
        "invite_reward": "\n🎁 *پاداش:*\n• ۵ دعوت: 🔔 قابلیت هشدار قیمت حرفه‌ای برای شما باز می‌شود.",
        "invite_copy": "📋 کپی لینک دعوت", "leaderboard_title": "🏆 *جدول قهرمانان*",
        "leaderboard_you": "\n📍 رتبه شما: *#{rank}* با *{count}* دعوت", "leaderboard_empty": "هنوز هیچ کاربری کسی رو دعوت نکرده. اولین نفر باش!",
        "help_title": "ℹ️ *راهنمای ارز آنلاین*", "help_text": "به *ارز آنلاین* خوش آمدی! 👋\n\nاین بات برای دسترسی سریع به قیمت‌ها ساخته شده است."
    },
    "en": {
        "choose_language": "🌐 Please choose your language:",
        "welcome_new": "Hello! 👋\n\nWelcome to *Arz Online*.\n\nPlease enter your *full name* to get started:",
        "invalid_name": "❌ Invalid name (at least 3 characters). Please try again:",
        "register_success": "✅ *Registration successful!*\n\n👤 Name: *{name}*\n🌐 Language: {lang_name}\n\nWelcome! Use the menu below:",
        "welcome_back": "👋 Hello *{name}*! Welcome back.\n\nUse the menu below:",
        "menu_title": "🏠 *Main Menu*\n\nPlease choose one of the options below:",
        "menu_crypto": "🪙 Cryptocurrency", "menu_fiat": "💵 Fiat Currencies", "menu_gold": "🥇 Gold & Coins",
        "menu_oil": "🛢️ Brent Oil", "menu_convert": "🔄 Currency Converter", "menu_market": "📊 Today’s Market",
        "menu_fav": "⭐ Favorites", "menu_alert": "🔔 Price Alert", "menu_myalerts": "📋 My Alerts",
        "menu_list": "📊 Crypto List", "menu_profile": "👤 My Profile", "menu_invite": "🎁 Invite Friends",
        "menu_leaderboard": "🏆 Leaderboard", "menu_help": "ℹ️ Help",
        "menu_main": "🏠 Main Menu", "menu_back": "🔙 Back", "menu_cancel": "❌ Cancel",
        "profile_title": "👤 *Your Profile*", "profile_name": "📝 Name: *{name}*", "profile_lang": "🌐 Language: {lang_name}",
        "profile_joined": "📅 Joined: {date}", "profile_invites": "🎁 Invited: *{count}* users",
        "profile_user_type": "👑 Account type: *{user_type}*", "user_type_special": "Special User ⭐", "user_type_normal": "Normal User 👤",
        "pro_locked": "🔒 This is a professional feature.\n\nInvite at least *5 people* using your referral link to unlock professional access.",
        "profile_change_lang": "🌐 Change Language", "profile_logout": "🚪 Log out",
        "logout_confirm": "⚠️ Logging out deactivates your current profile. You can register again with /start.\n\nAre you sure?",
        "logout_done": "✅ You have logged out.\n\nUse /start to create/register your profile again.",
        "cancel": "✅ Operation cancelled.", "error": "❌ An error occurred. Please try again.", "not_found": "❌ Not found.",
        "crypto_title": "🪙 *Cryptocurrency*\n\nChoose a coin:", "fiat_title": "💵 *Fiat Currencies*\n\nChoose a currency:",
        "gold_title": "🥇 *Gold & Coins*\n\nChoose an option:", "market_title": "📊 *Today’s Market*",
        "footer": "\n\n━━━━━━━━━━━━━━━━━━\n👨‍💻 Developer: *{dev}*\n📩 Feedback: {feedback}",
        "force_join_title": "⚠️ *Access Restricted*", "force_join_text": "To use the bot, please join our channel first:\n\n📢 {channel}\n\nAfter joining, click the button below:",
        "force_join_verify": "🔄 Verify Membership", "force_join_not_member": "❌ You haven't joined the channel yet.\n\nPlease join first, then click verify.",
        "invite_title": "🎁 *Referral System*", "invite_link": "🔗 Your personal invite link:", "invite_stats": "📊 *Your Stats:*",
        "invite_count": "• Invited users: *{count}*", "invite_rank": "• Your rank: *#{rank}*",
        "invite_reward": "\n🎁 *Rewards:*\n• 5 invites: Free special alert",
        "invite_copy": "📋 Copy invite link", "leaderboard_title": "🏆 *Leaderboard*",
        "leaderboard_you": "\n📍 Your rank: *#{rank}* with *{count}* invites", "leaderboard_empty": "Nobody has invited anyone yet. Be the first!",
        "help_title": "ℹ️ *Arz Online Guide*", "help_text": "Welcome to *Arz Online*! 👋\n\nThis bot gives you quick access to prices."
    }
}
LANG_NAMES = {"fa": "فارسی", "en": "English"}

def t(key, lang="fa", **kwargs):
    text = TRANSLATIONS.get(lang, TRANSLATIONS["fa"]).get(key, TRANSLATIONS["fa"].get(key, key))
    if kwargs:
        try: text = text.format(**kwargs)
        except: pass
    return text

def footer_text(lang="fa"):
    return t("footer", lang, dev=DEVELOPER_NAME, feedback=FEEDBACK_ID)

# ==================== دیتابیس ====================
db_client = None
users_collection = None
alerts_collection = None
favorites_collection = None
referrals_collection = None

async def init_db():
    global db_client, users_collection, alerts_collection, favorites_collection, referrals_collection
    if not MONGO_URI: return
    try:
        db_client = AsyncIOMotorClient(MONGO_URI, server_api=ServerApi('1'), tlsCAFile=certifi.where())
        db = db_client["telegram_price_bot"]
        users_collection = db["users"]
        alerts_collection = db["alerts"]
        favorites_collection = db["favorites"]
        referrals_collection = db["referrals"]
        await users_collection.create_index("chat_id", unique=True)
        await alerts_collection.create_index([("chat_id", 1), ("asset", 1)], unique=True)
        await favorites_collection.create_index([("chat_id", 1), ("asset", 1)], unique=True)
        print("✅ دیتابیس متصل شد.")
    except Exception as e: print(f"❌ DB Error: {e}")

async def get_user(chat_id):
    if users_collection is None: return None
    return await users_collection.find_one({"chat_id": str(chat_id)})

async def create_user(chat_id, name, lang="fa", referred_by=None):
    if users_collection is None: return False
    chat_id = str(chat_id)
    existing = await users_collection.find_one({"chat_id": chat_id})
    if existing:
        await users_collection.update_one({"chat_id": chat_id}, {"$set": {"name": name, "language": lang, "account_status": "active"}})
        return True
    doc = {"chat_id": chat_id, "name": name, "language": lang, "created_at": time.time(), "account_status": "active", "invite_count": 0, "special_user": False, "blocked": False, "referred_by": referred_by}
    await users_collection.insert_one(doc)
    if referred_by and str(referred_by) != chat_id:
        res = await referrals_collection.update_one({"referrer": str(referred_by), "referred": chat_id}, {"$setOnInsert": {"referrer": str(referred_by), "referred": chat_id, "created_at": time.time()}}, upsert=True)
        if res.upserted_id:
            await users_collection.update_one({"chat_id": str(referred_by)}, {"$inc": {"invite_count": 1}})
    return True

async def get_lang(chat_id):
    user = await get_user(chat_id)
    return user.get("language", "fa") if user else "fa"

# ==================== قیمت‌ها ====================
def format_price(val):
    if val is None: return "نامشخص"
    try: return f"{float(val):,.0f}"
    except: return str(val)

def fetch_oil():
    try:
        if not OIL_PRICE_API_KEY: return None
        res = OilPriceAPI(api_key=OIL_PRICE_API_KEY).prices.get("BRENT_CRUDE_USD")
        return {"price": res.value, "currency": res.currency}
    except: return None

def fetch_fiat(sym):
    try:
        res = requests.get(FIAT_API_URL, timeout=10).json()
        if sym.lower() in res:
            p = float(str(res[sym.lower()].get("value") if isinstance(res[sym.lower()], dict) else res[sym.lower()]).replace(",", ""))
            return p / 10 if p > 10_000_000 else p
    except: pass
    return None

def fetch_gold(asset):
    try:
        res = requests.get(GOLD_API_URL, timeout=10).json()
        key_map = {
            "gold_18": "18ayar", "gold_24": "18ayar", "gold_miskal": "18ayar",
            "coin_emami": "sekkeh", "coin_bahar": "bahar", "coin_half": "nim",
            "coin_quarter": "rob", "coin_gerami": "gerami"
        }
        if asset in key_map and key_map[asset] in res:
            base_price = float(res[key_map[asset]]["value"])
            if asset == "gold_24": return base_price * (24 / 18)
            if asset == "gold_miskal": return base_price * 4.608
            return base_price
    except: pass
    return None

def fetch_crypto(sym):
    try:
        res = requests.get(CRYPTO_API_URL, timeout=10).json()
        if sym in res.get("data", {}).get("markets", {}): return float(res["data"]["markets"][sym]["buy_price"])
    except: pass
    return None

def get_price(asset):
    if asset == "TOMAN": return 1.0
    if asset in GOLD_NAMES: return fetch_gold(asset)
    if asset in FIAT_NAMES: return fetch_fiat(asset)
    return fetch_crypto(asset)

def get_display_name(key): return GOLD_NAMES.get(key, FIAT_NAMES.get(key, key))

# ==================== چک عضویت ====================
async def check_membership(bot, user_id):
    if not CHANNEL_ID: return True
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=int(user_id))
        return m.status in ['member', 'administrator', 'creator']
    except: return False

# ==================== کیبوردها ====================
def lang_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🇮🇷 فارسی", callback_data="LANG:fa"), InlineKeyboardButton("🇬🇧 English", callback_data="LANG:en")]])

def main_menu(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("menu_crypto", lang), callback_data="MENU:CRYPTO"), InlineKeyboardButton(t("menu_fiat", lang), callback_data="MENU:FIAT")],
        [InlineKeyboardButton(t("menu_gold", lang), callback_data="MENU:GOLD"), InlineKeyboardButton(t("menu_oil", lang), callback_data="MENU:OIL")],
        [InlineKeyboardButton(t("menu_market", lang), callback_data="MENU:MARKET"), InlineKeyboardButton(t("menu_convert", lang), callback_data="CONV:NEW")],
        [InlineKeyboardButton(t("menu_alert", lang), callback_data="ALERT:NEW"), InlineKeyboardButton(t("menu_myalerts", lang), callback_data="MENU:MYALERTS")],
        [InlineKeyboardButton(t("menu_fav", lang), callback_data="FAV:VIEW"), InlineKeyboardButton(t("menu_invite", lang), callback_data="MENU:INVITE")],
        [InlineKeyboardButton(t("menu_profile", lang), callback_data="MENU:PROFILE"), InlineKeyboardButton(t("menu_help", lang), callback_data="MENU:HELP")],
        [InlineKeyboardButton(t("menu_leaderboard", lang), callback_data="MENU:LEADERBOARD")]
    ])

def get_crypto_kb(lang):
    markup = InlineKeyboardMarkup([])
    pairs = [POPULAR_CRYPTOS[i:i+2] for i in range(0, len(POPULAR_CRYPTOS), 2)]
    for pair in pairs:
        row = [InlineKeyboardButton(sym, callback_data=f"CRYPTO:{sym}") for sym in pair]
        markup.inline_keyboard.append(row)
    markup.inline_keyboard.append([InlineKeyboardButton(t("menu_back", lang), callback_data="MENU:MAIN")])
    return markup

def get_fiat_kb(lang):
    markup = InlineKeyboardMarkup([])
    pairs = [POPULAR_FIATS[i:i+2] for i in range(0, len(POPULAR_FIATS), 2)]
    for pair in pairs:
        row = [InlineKeyboardButton(FIAT_NAMES.get(sym, sym), callback_data=f"FIAT:{sym}") for sym in pair]
        markup.inline_keyboard.append(row)
    markup.inline_keyboard.append([InlineKeyboardButton(t("menu_back", lang), callback_data="MENU:MAIN")])
    return markup

def get_gold_kb(lang):
    markup = InlineKeyboardMarkup([])
    pairs = [POPULAR_GOLDS[i:i+2] for i in range(0, len(POPULAR_GOLDS), 2)]
    for pair in pairs:
        row = [InlineKeyboardButton(GOLD_NAMES.get(sym, sym), callback_data=f"GOLD:{sym}") for sym in pair]
        markup.inline_keyboard.append(row)
    markup.inline_keyboard.append([InlineKeyboardButton(t("menu_back", lang), callback_data="MENU:MAIN")])
    return markup

def force_join_kb(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 کانال", url=CHANNEL_LINK)],
        [InlineKeyboardButton(t("force_join_verify", lang), callback_data="FORCEJOIN:VERIFY")]
    ])

# ==================== پنل ادمین ====================
def is_admin(chat_id): return str(chat_id) in ADMIN_IDS

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 داشبورد", callback_data="ADMIN:STATS")],
        [InlineKeyboardButton("👥 کاربران", callback_data="ADMIN:USERS:0"), InlineKeyboardButton("🔎 جستجوی کاربر", callback_data="ADMIN:SEARCH")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="ADMIN:BROADCAST")],
        [InlineKeyboardButton("⭐ افراد خاص", callback_data="ADMIN:SPECIAL")],
        [InlineKeyboardButton("🩺 وضعیت سیستم", callback_data="ADMIN:HEALTH")],
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="ADMIN:HOME")]
    ])

def admin_back_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="ADMIN:HOME")]])

async def admin_stats_text():
    if users_collection is None: return "❌ دیتابیس متصل نیست."
    now = time.time()
    total = await users_collection.count_documents({})
    active = await users_collection.count_documents({"account_status": {"$ne": "logged_out"}, "blocked": {"$ne": True}})
    blocked = await users_collection.count_documents({"blocked": True})
    active_24h = await users_collection.count_documents({"last_seen_at": {"$gte": now - 86400}, "account_status": {"$ne": "logged_out"}})
    alerts = await alerts_collection.count_documents({}) if alerts_collection is not None else 0
    favs = await favorites_collection.count_documents({}) if favorites_collection is not None else 0
    return (
        "👨‍💻 **داشبورد مدیریت**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 کل پروفایل‌ها: **{total:,}**\n"
        f"🟢 حساب‌های فعال: **{active:,}**\n"
        f"🚫 مسدودشده‌ها: **{blocked:,}**\n"
        f"🟢 فعال ۲۴ ساعت: **{active_24h:,}**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔔 هشدارهای فعال: **{alerts:,}**\n"
        f"⭐ علاقه‌مندی‌ها: **{favs:,}**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {time.strftime('%Y-%m-%d %H:%M')}"
    )

async def admin_users_page(page=0):
    page = max(0, int(page))
    if users_collection is None: return "❌ دیتابیس متصل نیست.", admin_back_keyboard()
    total = await users_collection.count_documents({})
    skip = page * ADMIN_PAGE_SIZE
    docs = await users_collection.find({}).sort("created_at", -1).skip(skip).limit(ADMIN_PAGE_SIZE).to_list(length=ADMIN_PAGE_SIZE)
    lines = [f"👥 **کاربران (صفحه {page + 1})**", "━━━━━━━━━━━━━━━━━━"]
    markup_buttons = []
    for i, u in enumerate(docs):
        name = str(u.get("name", "بدون نام"))[:20]
        uid = str(u.get("chat_id", "-"))
        status = "🚫" if u.get("blocked") else "🟢"
        lines.append(f"{skip+i+1}. {status} {name} | `{uid}`")
        markup_buttons.append([InlineKeyboardButton(text=f"👤 {name}", callback_data=f"ADMIN:USER:{uid}")])
    
    total_pages = max(1, (total + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"ADMIN:USERS:{page-1}"))
    if page + 1 < total_pages: nav.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"ADMIN:USERS:{page+1}"))
    if nav: markup_buttons.append(nav)
    markup_buttons.append([InlineKeyboardButton("🔙 پنل مدیریت", callback_data="ADMIN:HOME")])
    return "\n".join(lines), InlineKeyboardMarkup(markup_buttons)

async def admin_user_detail(chat_id):
    user = await get_user(chat_id)
    if not user: return "❌ کاربر پیدا نشد.", admin_back_keyboard()
    text = (
        "👤 **جزئیات کاربر**\n━━━━━━━━━━━━━━━━━━\n"
        f"📝 نام: **{user.get('name', 'بدون نام')}**\n"
        f"🆔 Chat ID: `{user.get('chat_id')}`\n"
        f"🌐 زبان: **{LANG_NAMES.get(user.get('language', 'fa'), user.get('language', 'fa'))}**\n"
        f"🎁 دعوت‌ها: **{user.get('invite_count', 0)}**\n"
        f"👑 نوع: **{'خاص ⭐' if user.get('special_user') else 'عادی 👤'}**\n"
        f"📌 وضعیت: **{'مسدود 🚫' if user.get('blocked') else 'فعال 🟢'}**"
    )
    kb = []
    if user.get("blocked"): kb.append([InlineKeyboardButton("🟢 رفع مسدودی", callback_data=f"ADMIN:UNBLOCK:{chat_id}")])
    else: kb.append([InlineKeyboardButton("🚫 مسدود کردن", callback_data=f"ADMIN:BLOCK:{chat_id}")])
    
    if user.get("special_user"): kb.append([InlineKeyboardButton("⭐ حذف از خاص‌ها", callback_data=f"ADMIN:UNSPECIAL:{chat_id}")])
    else: kb.append([InlineKeyboardButton("⭐ افزودن به خاص‌ها", callback_data=f"ADMIN:SPECIAL:{chat_id}")])
    
    kb.append([InlineKeyboardButton("🔙 کاربران", callback_data="ADMIN:USERS:0")])
    return text, InlineKeyboardMarkup(kb)

# ==================== هندلرهای اصلی ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = await get_user(chat_id)
    
    if is_admin(chat_id):
        await update.message.reply_text("👨‍💻 پنل مدیریت:", reply_markup=admin_keyboard())
    
    if user:
        lang = user.get("language", "fa")
        if not await check_membership(context.bot, chat_id):
            await update.message.reply_text(t("force_join_title", lang) + "\n\n" + t("force_join_text", lang, channel=CHANNEL_ID), reply_markup=force_join_kb(lang))
            return
        await update.message.reply_text(t("welcome_back", lang, name=user["name"]) + footer_text(lang), reply_markup=main_menu(lang), parse_mode='Markdown')
    else:
        context.user_data['state'] = 'awaiting_lang'
        await update.message.reply_text(t("choose_language", "fa"), reply_markup=lang_kb())

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_chat.id):
        await update.message.reply_text("👨‍💻 پنل مدیریت:", reply_markup=admin_keyboard())

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"🆔 Chat ID شما:\n`{chat_id}`\n\nاین شناسه را برای ADMIN_IDS در Render استفاده کن.",
        parse_mode='Markdown'
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    state = context.user_data.get('state')
    lang = await get_lang(chat_id)

    # ثبت‌نام
    if state == 'awaiting_name':
        if len(text) < 3:
            await update.message.reply_text(t("invalid_name", lang))
            return
        ref = context.user_data.get('referral')
        await create_user(chat_id, text, context.user_data.get('lang', 'fa'), ref)
        context.user_data['state'] = None
        user = await get_user(chat_id)
        await update.message.reply_text(t("register_success", lang, name=text, lang_name=LANG_NAMES[lang]) + footer_text(lang), reply_markup=main_menu(lang), parse_mode='Markdown')
        return

    # پنل ادمین (جستجو و پیام همگانی)
    if is_admin(chat_id):
        if state == 'admin_search':
            context.user_data['state'] = None
            query = text
            docs = await users_collection.find({"$or": [{"chat_id": query}, {"name": {"$regex": query, "$options": "i"}}]}).limit(10).to_list(length=10)
            if not docs:
                await update.message.reply_text("❌ کاربری یافت نشد.", reply_markup=admin_back_keyboard())
                return
            kb = [[InlineKeyboardButton(f"👤 {u['name']}", callback_data=f"ADMIN:USER:{u['chat_id']}")] for u in docs]
            kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="ADMIN:HOME")])
            await update.message.reply_text("🔎 نتایج جستجو:", reply_markup=InlineKeyboardMarkup(kb))
            return
            
        if state == 'admin_broadcast':
            context.user_data['state'] = None
            sent, failed = 0, 0
            async for u in users_collection.find({"account_status": {"$ne": "logged_out"}, "blocked": {"$ne": True}}):
                try:
                    await context.bot.send_message(u["chat_id"], text)
                    sent += 1
                except: failed += 1
            await update.message.reply_text(f"✅ ارسال شد.\nموفق: {sent}\nناموفق: {failed}", reply_markup=admin_keyboard())
            return

    # هشدار قیمت
    if state == 'alert_price':
        try:
            price = float(text.replace(",", ""))
            context.user_data['alert_price'] = price
            context.user_data['state'] = 'alert_dir'
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📈 بالا", callback_data="ALERT:DIR:above"), InlineKeyboardButton("📉 پایین", callback_data="ALERT:DIR:below")]])
            await update.message.reply_text(f"🎯 قیمت هدف: {format_price(price)}\nشرط را انتخاب کنید:", reply_markup=kb)
        except: await update.message.reply_text("❌ عدد معتبر وارد کنید.")
        return

    # جستجوی سریع با تایپ کردن
    sym = text.upper()
    if sym in POPULAR_CRYPTOS or sym in FIAT_NAMES or sym in GOLD_NAMES or sym == "TOMAN":
        price = get_price(sym)
        if price:
            await update.message.reply_text(f"💰 قیمت *{get_display_name(sym)}*: *{format_price(price)}*", parse_mode='Markdown')
            return
    await update.message.reply_text("❌ یافت نشد. از منو استفاده کنید.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id
    lang = await get_lang(chat_id)

    # --- ادمین ---
    if data.startswith("ADMIN:") and is_admin(chat_id):
        if data == "ADMIN:HOME": await query.edit_message_text(await admin_stats_text(), reply_markup=admin_keyboard())
        elif data == "ADMIN:USERS:0":
            txt, kb = await admin_users_page(0)
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
        elif data.startswith("ADMIN:USERS:"):
            page = int(data.split(":")[2])
            txt, kb = await admin_users_page(page)
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
        elif data.startswith("ADMIN:USER:"):
            uid = data.split(":")[2]
            txt, kb = await admin_user_detail(uid)
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
        elif data.startswith("ADMIN:BLOCK:"):
            await users_collection.update_one({"chat_id": data.split(":")[2]}, {"$set": {"blocked": True}})
            txt, kb = await admin_user_detail(data.split(":")[2])
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
        elif data.startswith("ADMIN:UNBLOCK:"):
            await users_collection.update_one({"chat_id": data.split(":")[2]}, {"$set": {"blocked": False}})
            txt, kb = await admin_user_detail(data.split(":")[2])
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
        elif data.startswith("ADMIN:SPECIAL:"):
            await users_collection.update_one({"chat_id": data.split(":")[2]}, {"$set": {"special_user": True}})
            txt, kb = await admin_user_detail(data.split(":")[2])
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
        elif data.startswith("ADMIN:UNSPECIAL:"):
            await users_collection.update_one({"chat_id": data.split(":")[2]}, {"$set": {"special_user": False}})
            txt, kb = await admin_user_detail(data.split(":")[2])
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
        elif data == "ADMIN:SEARCH":
            context.user_data['state'] = 'admin_search'
            await query.edit_message_text("🔎 نام یا Chat ID کاربر را ارسال کنید:", reply_markup=admin_back_keyboard())
        elif data == "ADMIN:BROADCAST":
            context.user_data['state'] = 'admin_broadcast'
            await query.edit_message_text("📢 متن پیام همگانی را ارسال کنید:", reply_markup=admin_back_keyboard())
        elif data == "ADMIN:HEALTH":
            await query.edit_message_text("🩺 سیستم فعال است.\nربات: @onlineArzmonyBot", reply_markup=admin_back_keyboard())
        return

    # --- کاربر ---
    if data == "FORCEJOIN:VERIFY":
        if await check_membership(context.bot, chat_id):
            context.user_data['state'] = 'awaiting_lang'
            await query.edit_message_text(t("choose_language", "fa"), reply_markup=lang_kb())
        else:
            await query.edit_message_text(t("force_join_not_member", lang), reply_markup=force_join_kb(lang))
        return

    if data.startswith("LANG:"):
        context.user_data['lang'] = data.split(":")[1]
        context.user_data['state'] = 'awaiting_name'
        await query.edit_message_text(t("welcome_new", context.user_data['lang']), parse_mode='Markdown')
        return

    user = await get_user(chat_id)
    if user and user.get("blocked"): return

    if data == "MENU:MAIN": await query.edit_message_text(t("menu_title", lang), reply_markup=main_menu(lang), parse_mode='Markdown')
    elif data == "MENU:CRYPTO": await query.edit_message_text(t("crypto_title", lang), reply_markup=get_crypto_kb(lang), parse_mode='Markdown')
    elif data == "MENU:FIAT": await query.edit_message_text(t("fiat_title", lang), reply_markup=get_fiat_kb(lang), parse_mode='Markdown')
    elif data == "MENU:GOLD": await query.edit_message_text(t("gold_title", lang), reply_markup=get_gold_kb(lang), parse_mode='Markdown')
    elif data == "MENU:OIL":
        oil = fetch_oil()
        txt = f"🛢️ *نفت برنت*\n💰 {format_price(oil['price'])} {oil['currency']}" if oil else "❌ در دسترس نیست."
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("menu_back", lang), callback_data="MENU:MAIN")]]), parse_mode='Markdown')
    elif data == "MENU:MARKET":
        txt = f"📊 *بازار امروز*\n🪙 BTC: {format_price(get_price('BTC'))}\n💵 دلار: {format_price(get_price('USD'))}\n🥇 طلا: {format_price(get_price('gold_18'))}\n🛢️ نفت: {format_price(fetch_oil()['price'] if fetch_oil() else 0)}"
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("menu_back", lang), callback_data="MENU:MAIN")]]), parse_mode='Markdown')
    
    elif data.startswith(("CRYPTO:", "FIAT:", "GOLD:")):
        parts = data.split(":")
        price = get_price(parts[1])
        await query.edit_message_text(f"💰 قیمت *{get_display_name(parts[1])}*: *{format_price(price)}*", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("menu_back", lang), callback_data="MENU:MAIN")]]), parse_mode='Markdown')

    elif data == "MENU:PROFILE":
        user = await get_user(chat_id)
        txt = f"{t('profile_title', lang)}\n{t('profile_name', lang, name=user['name'])}\n{t('profile_invites', lang, count=user.get('invite_count', 0))}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t("profile_logout", lang), callback_data="PROFILE:LOGOUT")], [InlineKeyboardButton(t("menu_back", lang), callback_data="MENU:MAIN")]])
        await query.edit_message_text(txt + footer_text(lang), reply_markup=kb, parse_mode='Markdown')
    elif data == "PROFILE:LOGOUT":
        await users_collection.update_one({"chat_id": str(chat_id)}, {"$set": {"account_status": "logged_out"}})
        await query.edit_message_text(t("logout_done", lang))
    elif data == "MENU:INVITE":
        user = await get_user(chat_id)
        link = f"https://t.me/{BOT_USERNAME}?start={chat_id}"
        txt = f"{t('invite_title', lang)}\n{t('invite_link', lang)}\n`{link}`\n{t('invite_count', lang, count=user.get('invite_count',0))}"
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("invite_copy", lang), url=f"https://t.me/share/url?url={link}")], [InlineKeyboardButton(t("menu_back", lang), callback_data="MENU:MAIN")]]), parse_mode='Markdown')
    elif data == "MENU:HELP":
        await query.edit_message_text(t("help_text", lang), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("menu_back", lang), callback_data="MENU:MAIN")]]), parse_mode='Markdown')

# ==================== تسک‌های پس‌زمینه ====================
async def channel_poster(app):
    while True:
        await asyncio.sleep(CHANNEL_POST_INTERVAL)
        if not CHANNEL_ID: continue
        try:
            text = f"📊 *نرخ لحظه‌ای بازار*\n🪙 BTC: *{format_price(get_price('BTC'))}*\n💵 دلار: *{format_price(get_price('USD'))}*\n🥇 طلا: *{format_price(get_price('gold_18'))}*\n🛢️ نفت: *{format_price(fetch_oil()['price'] if fetch_oil() else 0)}*\n🕐 {time.strftime('%H:%M')}"
            await app.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode='Markdown')
        except Exception as e: print(f"Post error: {e}")

async def alert_checker(app):
    while True:
        await asyncio.sleep(60)
        if alerts_collection is None: continue
        alerts = await alerts_collection.find({}).to_list(length=None)
        for a in alerts:
            price = get_price(a["asset"])
            if not price: continue
            trig = (a["direction"] == "above" and price >= a["target_price"]) or (a["direction"] == "below" and price <= a["target_price"])
            if trig:
                try:
                    await app.bot.send_message(a["chat_id"], f"🔔 هشدار فعال شد!\n{a['asset']} به {format_price(price)} رسید.")
                    await alerts_collection.delete_one({"_id": a["_id"]})
                except: pass

# ==================== اجرا ====================
flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Telegram Bot is Running!"
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

async def post_init(application: Application) -> None:
    await init_db()
    asyncio.create_task(channel_poster(application))
    asyncio.create_task(alert_checker(application))

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("🤖 Bot Started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
