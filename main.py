import os
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

# لیست آیدی ادمین‌ها
ADMIN_IDS = {x.strip() for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()}
ADMIN_PAGE_SIZE = 6
CHANNEL_POST_INTERVAL = 3600

CRYPTO_API_URL = 'https://api.abantether.com/api/v1/manager/otc/ticker'
FIAT_API_URL = 'https://cdn.jsdelivr.net/gh/HosseinOdd/Navasan-API@main/data/fiat.json'
GOLD_API_URL = 'https://cdn.jsdelivr.net/gh/HosseinOdd/Navasan-API@main/data/gold.json'

POPULAR_CRYPTOS = ["BTC", "ETH", "USDT", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "TON"]
POPULAR_FIATS = ["USD", "EUR", "AED", "TRY", "GBP", "IQD", "CNY", "JPY", "CAD", "AUD", "CHF", "SAR"]
POPULAR_GOLDS = ["gold_18", "coin_emami", "coin_half", "coin_quarter", "gold_miskal", "coin_bahar", "coin_gerami"]

FIAT_NAMES = {
    "USD": "دلار", "EUR": "یورو", "GBP": "پوند", "AED": "درهم", "TRY": "لیر",
    "CNY": "یوان", "JPY": "ین", "CAD": "دلار کانادا", "AUD": "دلار استرالیا", "CHF": "فرانک",
    "IQD": "دینار عراق", "SAR": "ریال عربستان"
}
GOLD_NAMES = {
    "gold_18": "طلای ۱۸", "gold_24": "طلای ۲۴", "gold_miskal": "مثقال", "coin_emami": "سکه امامی",
    "coin_bahar": "سکه بهار", "coin_half": "نیم سکه", "coin_quarter": "ربع سکه", "coin_gerami": "سکه گرمی"
}

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

# ==================== توابع قیمت ====================
def format_price(val):
    if val is None: return "نامشخص"
    try: return f"{float(val):,.0f}"
    except: return str(val)

def get_display_name(key): return GOLD_NAMES.get(key, FIAT_NAMES.get(key, key))

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

# ==================== کیبوردها ====================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪙 ارز دیجیتال", callback_data="MENU:CRYPTO"), InlineKeyboardButton("💵 ارزهای فیات", callback_data="MENU:FIAT")],
        [InlineKeyboardButton("🥇 طلا و سکه", callback_data="MENU:GOLD"), InlineKeyboardButton("🛢️ نفت برنت", callback_data="MENU:OIL")],
        [InlineKeyboardButton("📊 بازار امروز", callback_data="MENU:MARKET"), InlineKeyboardButton("🔄 مبدل ارز", callback_data="CONV:NEW")],
        [InlineKeyboardButton("🔔 هشدار قیمت", callback_data="ALERT:NEW"), InlineKeyboardButton("📋 هشدارهای من", callback_data="MENU:MYALERTS")],
        [InlineKeyboardButton("⭐ علاقه‌مندی‌ها", callback_data="FAV:VIEW"), InlineKeyboardButton("🎁 دعوت دوستان", callback_data="MENU:INVITE")],
        [InlineKeyboardButton("👤 پروفایل من", callback_data="MENU:PROFILE"), InlineKeyboardButton("ℹ️ راهنما", callback_data="MENU:HELP")],
        [InlineKeyboardButton("🏆 جدول قهرمانان", callback_data="MENU:LEADERBOARD")]
    ])

def back_kb(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="MENU:MAIN")]])

def get_assets_kb(prefix, assets_list, cancel_cb="MENU:MAIN"):
    kb = []
    for i in range(0, len(assets_list), 2):
        row = []
        for sym in assets_list[i:i+2]:
            name = GOLD_NAMES.get(sym, FIAT_NAMES.get(sym, sym))
            row.append(InlineKeyboardButton(name, callback_data=f"{prefix}:{sym}"))
        kb.append(row)
    kb.append([InlineKeyboardButton("❌ انصراف", callback_data=cancel_cb)])
    return InlineKeyboardMarkup(kb)

def get_alert_cat_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪙 رمزارز", callback_data="ALERT:CAT:crypto"), InlineKeyboardButton("💵 فیات", callback_data="ALERT:CAT:fiat")],
        [InlineKeyboardButton("🥇 طلا و سکه", callback_data="ALERT:CAT:gold")],
        [InlineKeyboardButton("❌ انصراف", callback_data="MENU:MAIN")]
    ])

def get_dir_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 بالاتر برود", callback_data="ALERT:DIR:above"), InlineKeyboardButton("📉 پایین‌تر بیاید", callback_data="ALERT:DIR:below")],
        [InlineKeyboardButton("❌ انصراف", callback_data="MENU:MAIN")]
    ])

# ==================== پنل ادمین ====================
def is_admin(chat_id): return str(chat_id) in ADMIN_IDS

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 داشبورد", callback_data="ADMIN:STATS"), InlineKeyboardButton("👥 کاربران", callback_data="ADMIN:USERS:0")],
        [InlineKeyboardButton("🔎 جستجوی کاربر", callback_data="ADMIN:SEARCH"), InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="ADMIN:BROADCAST")],
        [InlineKeyboardButton("🔔 هشدارها", callback_data="ADMIN:ALERTS"), InlineKeyboardButton("⭐ افراد خاص", callback_data="ADMIN:SPECIAL")],
        [InlineKeyboardButton("⭐ علاقه‌مندی‌ها", callback_data="ADMIN:FAVS"), InlineKeyboardButton("🩺 وضعیت سیستم", callback_data="ADMIN:HEALTH")],
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="ADMIN:HOME")]
    ])

def admin_back_keyboard(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="ADMIN:HOME")]])

async def admin_stats_text():
    if users_collection is None: return "❌ دیتابیس متصل نیست."
    now = time.time()
    total = await users_collection.count_documents({})
    active = await users_collection.count_documents({"account_status": {"$ne": "logged_out"}, "blocked": {"$ne": True}})
    logged_out = await users_collection.count_documents({"account_status": "logged_out"})
    blocked = await users_collection.count_documents({"blocked": True})
    active_24h = await users_collection.count_documents({"last_seen_at": {"$gte": now - 86400}, "account_status": {"$ne": "logged_out"}})
    active_7d = await users_collection.count_documents({"last_seen_at": {"$gte": now - 7*86400}, "account_status": {"$ne": "logged_out"}})
    active_30d = await users_collection.count_documents({"last_seen_at": {"$gte": now - 30*86400}, "account_status": {"$ne": "logged_out"}})
    new_24h = await users_collection.count_documents({"created_at": {"$gte": now - 86400}})
    new_7d = await users_collection.count_documents({"created_at": {"$gte": now - 7*86400}})
    alerts = await alerts_collection.count_documents({}) if alerts_collection is not None else 0
    favs = await favorites_collection.count_documents({}) if favorites_collection is not None else 0
    refs = await referrals_collection.count_documents({}) if referrals_collection is not None else 0
    specials = await users_collection.count_documents({"special_user": True})
    
    return (
        "👨‍💻 **داشبورد مدیریت ارز آنلاین**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 کل پروفایل‌ها: **{total:,}**\n"
        f"🟢 حساب‌های فعال: **{active:,}**\n"
        f"🚪 خارج‌شده‌ها: **{logged_out:,}**\n"
        f"🚫 مسدودشده‌ها: **{blocked:,}**\n"
        f"🟢 فعال ۲۴ ساعت: **{active_24h:,}**\n"
        f"📅 فعال ۷ روز: **{active_7d:,}** | فعال ۳۰ روز: **{active_30d:,}**\n"
        f"🆕 ثبت‌نام ۲۴ ساعت: **{new_24h:,}** | ۷ روز: **{new_7d:,}**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔔 هشدارهای فعال: **{alerts:,}**\n"
        f"⭐ علاقه‌مندی‌ها: **{favs:,}**\n"
        f"🎁 Referralها: **{refs:,}**\n"
        f"⭐ افراد خاص: **{specials:,}**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🕐 بروزرسانی: {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

async def admin_users_page(page=0):
    page = max(0, int(page))
    if users_collection is None: return "❌ دیتابیس متصل نیست.", admin_back_keyboard()
    total = await users_collection.count_documents({})
    skip = page * ADMIN_PAGE_SIZE
    docs = await users_collection.find({}).sort("created_at", -1).skip(skip).limit(ADMIN_PAGE_SIZE).to_list(length=ADMIN_PAGE_SIZE)
    
    lines = [f"👥 **کاربران (صفحه {page + 1})**", "━━━━━━━━━━━━━━━━━━"]
    kb = []
    for i, u in enumerate(docs):
        name = str(u.get("name", "بدون نام"))[:20]
        uid = str(u.get("chat_id", "-"))
        status = "🚫" if u.get("blocked") else ("🚪" if u.get("account_status") == "logged_out" else "🟢")
        if u.get("special_user"): status += "⭐"
        lines.append(f"{skip+i+1}. {status} {name} | `{uid}`")
        kb.append([InlineKeyboardButton(f"{status} {name}", callback_data=f"ADMIN:USER:{uid}")])
    
    total_pages = max(1, (total + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE)
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"ADMIN:USERS:{page-1}"))
    if page + 1 < total_pages: nav.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"ADMIN:USERS:{page+1}"))
    if nav: kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 پنل مدیریت", callback_data="ADMIN:HOME")])
    return "\n".join(lines), InlineKeyboardMarkup(kb)

async def admin_user_detail(chat_id):
    user = await get_user(chat_id)
    if not user: return "❌ کاربر پیدا نشد.", admin_back_keyboard()
    status = 'مسدود 🚫' if user.get('blocked') else ('خارج‌شده 🚪' if user.get('account_status') == 'logged_out' else 'فعال 🟢')
    text = (
        "👤 **جزئیات کاربر**\n━━━━━━━━━━━━━━━━━━\n"
        f"📝 نام: **{user.get('name', 'بدون نام')}**\n"
        f"🆔 Chat ID: `{user.get('chat_id')}`\n"
        f"🎁 دعوت‌ها: **{user.get('invite_count', 0)}**\n"
        f"👑 نوع: **{'خاص ⭐' if user.get('special_user') else 'عادی 👤'}**\n"
        f"📌 وضعیت: **{status}**"
    )
    kb = []
    if user.get("blocked"): kb.append([InlineKeyboardButton("🟢 رفع مسدودی", callback_data=f"ADMIN:UNBLOCK:{chat_id}")])
    else: kb.append([InlineKeyboardButton("🚫 مسدود کردن", callback_data=f"ADMIN:BLOCK:{chat_id}")])
    
    if user.get("special_user"): kb.append([InlineKeyboardButton("⭐ حذف از خاص‌ها", callback_data=f"ADMIN:UNSPECIAL:{chat_id}")])
    else: kb.append([InlineKeyboardButton("⭐ افزودن به خاص‌ها", callback_data=f"ADMIN:SPECIAL:{chat_id}")])
    
    kb.append([InlineKeyboardButton("🔙 کاربران", callback_data="ADMIN:USERS:0")])
    return text, InlineKeyboardMarkup(kb)

async def admin_special_users():
    docs = await users_collection.find({"special_user": True}).to_list(length=50)
    if not docs: return "⭐ هنوز کاربر خاصی وجود ندارد.", admin_back_keyboard()
    txt = "⭐ **لیست افراد خاص:**\n\n"
    kb = []
    for u in docs:
        txt += f"- {u['name']} | `{u['chat_id']}`\n"
        kb.append([InlineKeyboardButton(f"👤 {u['name']}", callback_data=f"ADMIN:USER:{u['chat_id']}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="ADMIN:HOME")])
    return txt, InlineKeyboardMarkup(kb)

# ==================== هندلرهای اصلی ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = await get_user(chat_id)
    
    if is_admin(chat_id):
        await update.message.reply_text("👨‍💻 پنل مدیریت:", reply_markup=admin_keyboard())
    
    if user:
        await update.message.reply_text(f"👋 سلام *{user['name']}* عزیز! خوش برگشتی.\n\nاز منوی زیر استفاده کن:", reply_markup=main_menu(), parse_mode='Markdown')
    else:
        context.user_data['state'] = 'awaiting_name'
        await update.message.reply_text("سلام! 👋\n\nبه *ارز آنلاین* خوش آمدید.\n\nبرای شروع فقط *نام و نام خانوادگی* خود را وارد کنید:", parse_mode='Markdown')

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_chat.id):
        await update.message.reply_text("👨‍💻 پنل مدیریت:", reply_markup=admin_keyboard())

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    state = context.user_data.get('state')

    # ۱. ثبت‌نام
    if state == 'awaiting_name':
        if len(text) < 3:
            await update.message.reply_text("❌ نام معتبر نیست. دوباره وارد کنید:")
            return
        await users_collection.update_one({"chat_id": str(chat_id)}, {"$set": {"name": text, "language": "fa", "created_at": time.time(), "account_status": "active", "last_seen_at": time.time(), "invite_count": 0}}, upsert=True)
        context.user_data['state'] = None
        await update.message.reply_text(f"✅ ثبت‌نام با موفقیت انجام شد!\n👤 نام: *{text}*\n\nاز منوی زیر استفاده کن:", reply_markup=main_menu(), parse_mode='Markdown')
        return

    # پنل ادمین (جستجو)
    if is_admin(chat_id) and state == 'admin_search':
        context.user_data['state'] = None
        docs = await users_collection.find({"$or": [{"chat_id": text}, {"name": {"$regex": text, "$options": "i"}}]}).limit(10).to_list(length=10)
        if not docs:
            await update.message.reply_text("❌ کاربری یافت نشد.", reply_markup=admin_back_keyboard())
            return
        kb = [[InlineKeyboardButton(f"👤 {u['name']}", callback_data=f"ADMIN:USER:{u['chat_id']}")] for u in docs]
        kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="ADMIN:HOME")])
        await update.message.reply_text("🔎 نتایج:", reply_markup=InlineKeyboardMarkup(kb))
        return

    # پنل ادمین (پیام همگانی)
    if is_admin(chat_id) and state == 'admin_broadcast':
        context.user_data['state'] = None
        sent, failed = 0, 0
        async for u in users_collection.find({"account_status": {"$ne": "logged_out"}, "blocked": {"$ne": True}}):
            try:
                await context.bot.send_message(u["chat_id"], text)
                sent += 1
            except: failed += 1
        await update.message.reply_text(f"✅ ارسال شد.\nموفق: {sent}\nناموفق: {failed}", reply_markup=admin_keyboard())
        return

    # ۲. مبدل ارز
    if state == 'awaiting_conv_amount':
        try:
            amount = float(text.replace(",", ""))
            from_asset, to_asset = context.user_data.get('conv_from'), context.user_data.get('conv_to')
            if not from_asset or not to_asset: return
            p_from, p_to = get_price(from_asset), get_price(to_asset)
            if not p_from or not p_to: return await update.message.reply_text("❌ قیمت در دسترس نیست.")
            result = amount * p_from / p_to
            context.user_data['state'] = None
            await update.message.reply_text(f"🔄 **نتیجه تبدیل**\n{amount:,.2f} {get_display_name(from_asset)} = **{result:,.4f} {get_display_name(to_asset)}**", reply_markup=main_menu(), parse_mode='Markdown')
        except ValueError: await update.message.reply_text("❌ عدد معتبر وارد کنید.")
        return

    # ۳. هشدار قیمت
    if state == 'awaiting_alert_price':
        try:
            price = float(text.replace(",", ""))
            context.user_data['alert_price'] = price
            context.user_data['state'] = 'awaiting_alert_dir'
            await update.message.reply_text(f"🎯 قیمت هدف: {format_price(price)}\nشرط را انتخاب کنید:", reply_markup=get_dir_kb())
        except ValueError: await update.message.reply_text("❌ عدد معتبر وارد کنید.")
        return

    # جستجوی سریع قیمت
    price = get_price(text.upper())
    if price: await update.message.reply_text(f"💰 قیمت *{get_display_name(text.upper())}*: *{format_price(price)}*", parse_mode='Markdown')
    else: await update.message.reply_text("❌ یافت نشد.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id
    
    # ================== بخش ادمین ==================
    if data.startswith("ADMIN:") and is_admin(chat_id):
        if data in ("ADMIN:HOME", "ADMIN:STATS"):
            await query.edit_message_text(await admin_stats_text(), reply_markup=admin_keyboard(), parse_mode='Markdown')
        
        elif data.startswith("ADMIN:USERS:"):
            page = int(data.split(":")[2])
            txt, kb = await admin_users_page(page)
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
            
        elif data.startswith("ADMIN:USER:"):
            uid = data.split(":")[2]
            txt, kb = await admin_user_detail(uid)
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
            
        elif data.startswith("ADMIN:BLOCK:"):
            uid = data.split(":")[2]
            await users_collection.update_one({"chat_id": uid}, {"$set": {"blocked": True}})
            txt, kb = await admin_user_detail(uid)
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
            
        elif data.startswith("ADMIN:UNBLOCK:"):
            uid = data.split(":")[2]
            await users_collection.update_one({"chat_id": uid}, {"$set": {"blocked": False}})
            txt, kb = await admin_user_detail(uid)
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
            
        elif data.startswith("ADMIN:SPECIAL:"):
            uid = data.split(":")[2]
            await users_collection.update_one({"chat_id": uid}, {"$set": {"special_user": True}})
            txt, kb = await admin_user_detail(uid)
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
            
        elif data.startswith("ADMIN:UNSPECIAL:"):
            uid = data.split(":")[2]
            await users_collection.update_one({"chat_id": uid}, {"$set": {"special_user": False}})
            txt, kb = await admin_user_detail(uid)
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
            
        elif data == "ADMIN:SEARCH":
            context.user_data['state'] = 'admin_search'
            await query.edit_message_text("🔎 نام یا Chat ID را بفرستید:", reply_markup=admin_back_keyboard())
            
        elif data == "ADMIN:BROADCAST":
            context.user_data['state'] = 'admin_broadcast'
            await query.edit_message_text("📢 متن پیام همگانی را بفرستید:", reply_markup=admin_back_keyboard())
            
        elif data == "ADMIN:SPECIAL":
            txt, kb = await admin_special_users()
            await query.edit_message_text(txt, reply_markup=kb, parse_mode='Markdown')
            
        elif data == "ADMIN:HEALTH":
            await query.edit_message_text("🩺 سیستم کاملاً فعال است.", reply_markup=admin_back_keyboard())
        return

    # ================== بخش کاربر ==================
    if data == "MENU:MAIN":
        context.user_data['state'] = None
        await query.edit_message_text("🏠 *منوی اصلی*\nلطفا یک گزینه را انتخاب کنید:", reply_markup=main_menu(), parse_mode='Markdown')
    
    elif data == "MENU:CRYPTO": await query.edit_message_text("🪙 *ارز دیجیتال*", reply_markup=get_assets_kb("CRYPTO", POPULAR_CRYPTOS), parse_mode='Markdown')
    elif data == "MENU:FIAT": await query.edit_message_text("💵 *ارزهای فیات*", reply_markup=get_assets_kb("FIAT", POPULAR_FIATS), parse_mode='Markdown')
    elif data == "MENU:GOLD": await query.edit_message_text("🥇 *طلا و سکه*", reply_markup=get_assets_kb("GOLD", POPULAR_GOLDS), parse_mode='Markdown')
    
    elif data == "MENU:OIL":
        oil = fetch_oil()
        txt = f"🛢️ *نفت برنت*\n💰 {format_price(oil['price'])} {oil['currency']}" if oil else "❌ در دسترس نیست."
        await query.edit_message_text(txt, reply_markup=back_kb(), parse_mode='Markdown')
    elif data == "MENU:MARKET":
        txt = f"📊 *بازار امروز*\n🪙 BTC: {format_price(get_price('BTC'))}\n💵 دلار: {format_price(get_price('USD'))}\n🥇 طلا: {format_price(get_price('gold_18'))}\n🛢️ نفت: {format_price(fetch_oil()['price'] if fetch_oil() else 0)}"
        await query.edit_message_text(txt, reply_markup=back_kb(), parse_mode='Markdown')
    elif data.startswith(("CRYPTO:", "FIAT:", "GOLD:")):
        parts = data.split(":")
        price = get_price(parts[1])
        await query.edit_message_text(f"💰 قیمت *{get_display_name(parts[1])}*: *{format_price(price)}*", reply_markup=back_kb(), parse_mode='Markdown')

    # مبدل
    elif data == "CONV:NEW":
        context.user_data['state'] = None
        kb = get_assets_kb("CONV:FROM", ["TOMAN", "USD", "EUR", "BTC", "ETH", "USDT", "gold_18", "coin_emami"], "MENU:MAIN")
        await query.edit_message_text("🔄 **مبدل ارز**\nمرحله ۱: ارز مبدا؟", reply_markup=kb, parse_mode='Markdown')
    elif data.startswith("CONV:FROM:"):
        context.user_data['conv_from'] = data.split(":")[2]
        kb = get_assets_kb("CONV:TO", ["TOMAN", "USD", "EUR", "BTC", "ETH", "USDT", "gold_18", "coin_emami"], "MENU:MAIN")
        await query.edit_message_text(f"✅ مبدا: {get_display_name(context.user_data['conv_from'])}\nمرحله ۲: ارز مقصد؟", reply_markup=kb, parse_mode='Markdown')
    elif data.startswith("CONV:TO:"):
        context.user_data['conv_to'] = data.split(":")[2]
        context.user_data['state'] = 'awaiting_conv_amount'
        await query.edit_message_text(f"✅ مبدا: {get_display_name(context.user_data['conv_from'])}\n✅ مقصد: {get_display_name(context.user_data['conv_to'])}\n\nمرحله ۳: مقدار را تایپ کنید:", reply_markup=back_kb(), parse_mode='Markdown')

    # هشدار
    elif data == "ALERT:NEW":
        context.user_data['state'] = None
        await query.edit_message_text("🔔 **ثبت هشدار**\nدسته‌بندی؟", reply_markup=get_alert_cat_kb(), parse_mode='Markdown')
    elif data.startswith("ALERT:CAT:"):
        cat = data.split(":")[2]
        assets = POPULAR_CRYPTOS if cat == "crypto" else POPULAR_FIATS if cat == "fiat" else POPULAR_GOLDS
        kb = get_assets_kb("ALERT:SET", assets, "ALERT:NEW")
        await query.edit_message_text("🔔 **انتخاب دارایی**", reply_markup=kb, parse_mode='Markdown')
    elif data.startswith("ALERT:SET:"):
        context.user_data['alert_asset'] = data.split(":")[2]
        context.user_data['state'] = 'awaiting_alert_price'
        await query.edit_message_text(f"✅ دارایی: {get_display_name(context.user_data['alert_asset'])}\n\n🎯 قیمت هدف را تایپ کنید:", reply_markup=back_kb(), parse_mode='Markdown')
    elif data.startswith("ALERT:DIR:"):
        direction = data.split(":")[2]
        asset = context.user_data.get('alert_asset')
        price = context.user_data.get('alert_price')
        if asset and price:
            await alerts_collection.update_one({"chat_id": str(chat_id), "asset": asset}, {"$set": {"target_price": price, "direction": direction, "created_at": time.time()}}, upsert=True)
            dir_fa = "بالاتر برود 📈" if direction == "above" else "پایین‌تر بیاید 📉"
            context.user_data['state'] = None
            await query.edit_message_text(f"✅ **هشدار ثبت شد!**\n🔔 {get_display_name(asset)}\n🎯 هدف: {format_price(price)} ({dir_fa})", reply_markup=main_menu(), parse_mode='Markdown')

    elif data == "MENU:MYALERTS":
        alerts = await alerts_collection.find({"chat_id": str(chat_id)}).to_list(length=20)
        if not alerts: return await query.edit_message_text("📭 **هشدار فعالی ندارید.**", reply_markup=back_kb(), parse_mode='Markdown')
        txt = "🔔 **هشدارهای شما:**\n\n"
        for a in alerts:
            txt += f"🔸 {get_display_name(a['asset'])} | هدف: {format_price(a['target_price'])} ({a['direction']})\n"
        await query.edit_message_text(txt, reply_markup=back_kb(), parse_mode='Markdown')

    # علاقه‌مندی
    elif data == "FAV:VIEW":
        favs = await favorites_collection.find({"chat_id": str(chat_id)}).to_list(length=20)
        if not favs: return await query.edit_message_text("⭐ لیست خالیه!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ افزودن", callback_data="FAV:ADD")], [InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")]]))
        txt = "⭐ **علاقه‌مندی‌های شما:**\n\n"
        for f in favs:
            txt += f"🔸 {get_display_name(f['asset'])}: {format_price(get_price(f['asset']))} تومان\n"
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ افزودن", callback_data="FAV:ADD")], [InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")]]), parse_mode='Markdown')
    elif data == "FAV:ADD":
        assets = ["BTC", "ETH", "USDT", "USD", "EUR", "gold_18", "coin_emami"]
        kb = get_assets_kb("FAV:SET", assets, "FAV:VIEW")
        await query.edit_message_text("⭐ **افزودن به علاقه‌مندی‌ها**\nکدام دارایی؟", reply_markup=kb, parse_mode='Markdown')
    elif data.startswith("FAV:SET:"):
        asset = data.split(":")[2]
        await favorites_collection.update_one({"chat_id": str(chat_id), "asset": asset}, {"$set": {"created_at": time.time()}}, upsert=True)
        await query.edit_message_text(f"✅ {get_display_name(asset)} اضافه شد.", reply_markup=back_kb(), parse_mode='Markdown')

    # پروفایل
    elif data == "MENU:PROFILE":
        user = await get_user(chat_id)
        await query.edit_message_text(f"👤 **پروفایل**\n📝 نام: {user['name']}\n🆔 ID: `{chat_id}`", reply_markup=back_kb(), parse_mode='Markdown')
    elif data == "MENU:HELP":
        await query.edit_message_text("ℹ️ **راهنما**\nاز دکمه‌های منو استفاده کنید.", reply_markup=back_kb(), parse_mode='Markdown')

# ==================== تسک‌های پس‌زمینه ====================
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
                    await app.bot.send_message(a["chat_id"], f"🔔 **هشدار فعال شد!**\n\n{get_display_name(a['asset'])} به {format_price(price)} رسید.", parse_mode='Markdown')
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
    asyncio.create_task(alert_checker(application))

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("🤖 Bot Started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
