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
BOT_USERNAME = os.environ.get("BOT_USERNAME", "your_bot_username")

ADMIN_IDS = {x.strip() for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()}
ADMIN_PAGE_SIZE = 8
CHANNEL_POST_INTERVAL = 3600

CRYPTO_API_URL = 'https://api.abantether.com/api/v1/manager/otc/ticker'
FIAT_API_URL = 'https://cdn.jsdelivr.net/gh/HosseinOdd/Navasan-API@main/data/fiat.json'
GOLD_API_URL = 'https://cdn.jsdelivr.net/gh/HosseinOdd/Navasan-API@main/data/gold.json'

# ==================== لیست دارایی‌ها ====================
POPULAR_CRYPTOS = ["BTC", "ETH", "USDT", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "TON"]
POPULAR_FIATS = ["USD", "EUR", "AED", "TRY", "GBP", "IQD", "CNY", "JPY", "CAD", "AUD", "CHF", "SAR"]
POPULAR_GOLDS = ["gold_18", "coin_emami", "coin_half", "coin_quarter", "gold_miskal", "coin_bahar", "coin_gerami"]

FIAT_NAMES = {
    "USD": "دلار آمریکا", "EUR": "یورو", "GBP": "پوند انگلیس", "AED": "درهم امارات", "TRY": "لیر ترکیه",
    "CNY": "یوان چین", "JPY": "ین ژاپن", "CAD": "دلار کانادا", "AUD": "دلار استرالیا", "CHF": "فرانک سوئیس",
    "IQD": "دینار عراق", "SAR": "ریال عربستان", "KWD": "دینار کویت", "QAR": "ریال قطر", "OMR": "ریال عمان",
    "BHD": "دینار بحرین", "JOD": "دینار اردن", "RUB": "روبل روسیه", "INR": "روپیه هند", "PKR": "روپیه پاکستان"
}
GOLD_NAMES = {
    "gold_18": "طلای ۱۸ عیار", "gold_24": "طلای ۲۴ عیار", "gold_miskal": "مثقال طلا", "coin_emami": "سکه امامی",
    "coin_bahar": "سکه بهار آزادی", "coin_half": "نیم سکه", "coin_quarter": "ربع سکه", "coin_gerami": "سکه گرمی"
}

# ==================== دیتابیس ====================
db_client = None
users_collection = None
alerts_collection = None
favorites_collection = None

async def init_db():
    global db_client, users_collection, alerts_collection, favorites_collection
    if not MONGO_URI: return
    try:
        db_client = AsyncIOMotorClient(MONGO_URI, server_api=ServerApi('1'), tlsCAFile=certifi.where())
        db = db_client["telegram_price_bot"]
        users_collection = db["users"]
        alerts_collection = db["alerts"]
        favorites_collection = db["favorites"]
        
        await users_collection.create_index("chat_id", unique=True)
        await alerts_collection.create_index([("chat_id", 1), ("asset", 1)], unique=True)
        await favorites_collection.create_index([("chat_id", 1), ("asset", 1)], unique=True)
        print("✅ دیتابیس متصل شد.")
    except Exception as e: print(f"❌ DB Error: {e}")

async def get_user(chat_id):
    if users_collection is None: return None
    return await users_collection.find_one({"chat_id": str(chat_id)})

async def get_lang(chat_id):
    user = await get_user(chat_id)
    return user.get("language", "fa") if user else "fa"

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

def get_crypto_kb():
    kb = [[InlineKeyboardButton(sym, callback_data=f"CRYPTO:{sym}") for sym in POPULAR_CRYPTOS[i:i+2]] for i in range(0, len(POPULAR_CRYPTOS), 2)]
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")])
    return InlineKeyboardMarkup(kb)

def get_fiat_kb():
    kb = [[InlineKeyboardButton(FIAT_NAMES.get(sym, sym), callback_data=f"FIAT:{sym}") for sym in POPULAR_FIATS[i:i+2]] for i in range(0, len(POPULAR_FIATS), 2)]
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")])
    return InlineKeyboardMarkup(kb)

def get_gold_kb():
    kb = [[InlineKeyboardButton(GOLD_NAMES.get(sym, sym), callback_data=f"GOLD:{sym}") for sym in POPULAR_GOLDS[i:i+2]] for i in range(0, len(POPULAR_GOLDS), 2)]
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")])
    return InlineKeyboardMarkup(kb)

# ==================== پنل ادمین ====================
def is_admin(chat_id): return str(chat_id) in ADMIN_IDS

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 داشبورد", callback_data="ADMIN:STATS")],
        [InlineKeyboardButton("👥 کاربران", callback_data="ADMIN:USERS:0"), InlineKeyboardButton("🔎 جستجو", callback_data="ADMIN:SEARCH")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="ADMIN:BROADCAST")],
        [InlineKeyboardButton("🔙 بستن پنل", callback_data="MENU:MAIN")]
    ])

async def admin_stats_text():
    if users_collection is None: return "❌ دیتابیس متصل نیست."
    total = await users_collection.count_documents({})
    alerts = await alerts_collection.count_documents({}) if alerts_collection is not None else 0
    favs = await favorites_collection.count_documents({}) if favorites_collection is not None else 0
    return f"👨‍💻 **داشبورد مدیریت**\n\n👥 کل کاربران: **{total:,}**\n🔔 هشدارهای فعال: **{alerts:,}**\n⭐ علاقه‌مندی‌ها: **{favs:,}**"

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

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"🆔 Chat ID شما:\n`{chat_id}`\n\nاین شناسه را برای ADMIN_IDS در Render استفاده کن.", parse_mode='Markdown')

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    state = context.user_data.get('state')

    # ۱. ثبت‌نام
    if state == 'awaiting_name':
        if len(text) < 3:
            await update.message.reply_text("❌ نام معتبر نیست. دوباره وارد کنید:")
            return
        await users_collection.update_one({"chat_id": str(chat_id)}, {"$set": {"name": text, "language": "fa", "created_at": time.time(), "account_status": "active", "invite_count": 0}}, upsert=True)
        context.user_data['state'] = None
        await update.message.reply_text(f"✅ ثبت‌نام با موفقیت انجام شد!\n👤 نام: *{text}*\n\nاز منوی زیر استفاده کن:", reply_markup=main_menu(), parse_mode='Markdown')
        return

    # ۲. هشدار قیمت (مرحله ۱: نام دارایی)
    if state == 'alert_asset':
        asset = text.upper()
        context.user_data['alert_asset'] = asset
        context.user_data['state'] = 'alert_price'
        await update.message.reply_text(f"✅ دارایی: {get_display_name(asset)}\n\n🎯 حالا قیمت هدف را به تومان وارد کنید:")
        return

    # ۳. هشدار قیمت (مرحله ۲: قیمت)
    if state == 'alert_price':
        try:
            price = float(text.replace(",", ""))
            context.user_data['alert_price'] = price
            context.user_data['state'] = 'alert_dir'
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📈 بالاتر برود", callback_data="ALERT:DIR:above"), InlineKeyboardButton("📉 پایین‌تر بیاید", callback_data="ALERT:DIR:below")]])
            await update.message.reply_text(f"🎯 قیمت هدف: {format_price(price)} تومان\n\nحالا شرط را انتخاب کنید:", reply_markup=kb)
        except: await update.message.reply_text("❌ عدد معتبر وارد کنید.")
        return

    # ۴. افزودن به علاقه‌مندی‌ها
    if state == 'fav_add':
        asset = text.upper()
        context.user_data['state'] = None
        try:
            await favorites_collection.update_one({"chat_id": str(chat_id), "asset": asset}, {"$set": {"created_at": time.time()}}, upsert=True)
            await update.message.reply_text(f"⭐ *{get_display_name(asset)}* به علاقه‌مندی‌ها اضافه شد.", reply_markup=main_menu(), parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text("❌ خطا در ذخیره.", reply_markup=main_menu())
        return

    # ۵. مبدل ارز (پارس کردن متن مثل "100 USD TOMAN")
    conv_match = re.match(r'^(\d+(?:\.\d+)?)\s+([A-Za-z_]{2,10})\s+(?:به|to|in)\s+([A-Za-z_]{2,10})$', text, re.IGNORECASE)
    if conv_match:
        amount = float(conv_match.group(1))
        from_asset = conv_match.group(2).upper()
        to_asset = conv_match.group(3).upper()
        if from_asset == "IRT": from_asset = "TOMAN"
        if to_asset == "IRT": to_asset = "TOMAN"
        
        p_from = get_price(from_asset)
        p_to = get_price(to_asset)
        
        if not p_from or not p_to:
            await update.message.reply_text("❌ یکی از دارایی‌ها یافت نشد.")
            return
            
        result = amount * p_from / p_to
        txt = (
            f"🔄 **نتیجه تبدیل**\n━━━━━━━━━━━━━━━━━━\n"
            f"💱 {amount:,.2f} {get_display_name(from_asset)}\n⬇️⬇️⬇️\n"
            f"💰 **{result:,.2f} {get_display_name(to_asset)}**\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(txt, reply_markup=back_kb(), parse_mode='Markdown')
        return

    # جستجوی سریع قیمت
    sym = text.upper()
    price = get_price(sym)
    if price:
        await update.message.reply_text(f"💰 قیمت *{get_display_name(sym)}*: *{format_price(price)}*", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ یافت نشد. از منو استفاده کنید یا نام صحیح دارایی را وارد کنید.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id
    
    # --- ادمین ---
    if data.startswith("ADMIN:") and is_admin(chat_id):
        if data == "ADMIN:HOME": await query.edit_message_text(await admin_stats_text(), reply_markup=admin_keyboard(), parse_mode='Markdown')
        # (بقیه کدهای ادمین مثل قبل)
        return

    # --- منوی اصلی ---
    if data == "MENU:MAIN":
        await query.edit_message_text("🏠 *منوی اصلی*\nلطفا یک گزینه را انتخاب کنید:", reply_markup=main_menu(), parse_mode='Markdown')
    
    # --- منوها ---
    elif data == "MENU:CRYPTO": await query.edit_message_text("🪙 *ارز دیجیتال*", reply_markup=get_crypto_kb(), parse_mode='Markdown')
    elif data == "MENU:FIAT": await query.edit_message_text("💵 *ارزهای فیات*", reply_markup=get_fiat_kb(), parse_mode='Markdown')
    elif data == "MENU:GOLD": await query.edit_message_text("🥇 *طلا و سکه*", reply_markup=get_gold_kb(), parse_mode='Markdown')
    
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

    # --- هشدار قیمت ---
    elif data == "ALERT:NEW":
        context.user_data['state'] = 'alert_asset'
        await query.edit_message_text("🔔 **ثبت هشدار**\n\nنام دارایی را وارد کنید (مثال: BTC یا USD یا gold_18):", reply_markup=back_kb())
        
    elif data.startswith("ALERT:DIR:"):
        direction = data.split(":")[2]
        asset = context.user_data.get('alert_asset')
        price = context.user_data.get('alert_price')
        if not asset or not price:
            await query.edit_message_text("❌ خطا. دوباره شروع کنید.", reply_markup=main_menu())
            return
        try:
            await alerts_collection.update_one(
                {"chat_id": str(chat_id), "asset": asset},
                {"$set": {"target_price": price, "direction": direction, "created_at": time.time()}},
                upsert=True
            )
            dir_fa = "بالاتر برود 📈" if direction == "above" else "پایین‌تر بیاید 📉"
            await query.edit_message_text(f"✅ **هشدار ثبت شد!**\n\n🔔 {get_display_name(asset)}\n🎯 هدف: {format_price(price)} تومان\n📊 شرط: {dir_fa}", reply_markup=main_menu(), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text("❌ خطا در ثبت هشدار.", reply_markup=main_menu())
        context.user_data['state'] = None

    elif data == "MENU:MYALERTS":
        alerts = await alerts_collection.find({"chat_id": str(chat_id)}).to_list(length=20)
        if not alerts:
            await query.edit_message_text("📭 **هشدار فعالی ندارید.**", reply_markup=back_kb(), parse_mode='Markdown')
            return
        txt = "🔔 **هشدارهای فعال شما:**\n\n"
        for a in alerts:
            dir_fa = "بالاتر ⬆️" if a['direction'] == "above" else "پایین‌تر ⬇️"
            txt += f"🔸 {get_display_name(a['asset'])} | هدف: {format_price(a['target_price'])} ({dir_fa})\n"
        await query.edit_message_text(txt, reply_markup=back_kb(), parse_mode='Markdown')

    # --- مبدل ارز ---
    elif data == "CONV:NEW":
        await query.edit_message_text(
            "🔄 **مبدل ارز**\n\nلطفاً به این فرمت پیام دهید:\n"
            "`مقدار ارز_مبدا به ارز_مقصد`\n\n"
            "مثال:\n`100 USD به TOMAN`\n`0.5 BTC به USDT`",
            reply_markup=back_kb(),
            parse_mode='Markdown'
        )

    # --- علاقه‌مندی‌ها ---
    elif data == "FAV:VIEW":
        favs = await favorites_collection.find({"chat_id": str(chat_id)}).to_list(length=20)
        if not favs:
            await query.edit_message_text("⭐ لیست علاقه‌مندی‌های شما خالیه!\nبرای افزودن دکمه زیر را بزنید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ افزودن دارایی", callback_data="FAV:ADD")], [InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")]]), parse_mode='Markdown')
            return
        txt = "⭐ **لیست علاقه‌مندی‌های شما:**\n\n"
        for f in favs:
            price = get_price(f['asset'])
            txt += f"🔸 {get_display_name(f['asset'])}: {format_price(price)} تومان\n"
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ افزودن دارایی", callback_data="FAV:ADD")], [InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")]]), parse_mode='Markdown')

    elif data == "FAV:ADD":
        context.user_data['state'] = 'fav_add'
        await query.edit_message_text("⭐ نام دارایی را برای افزودن به علاقه‌مندی‌ها بفرستید (مثال: BTC):", reply_markup=back_kb())

    # --- پروفایل و راهنما ---
    elif data == "MENU:PROFILE":
        user = await get_user(chat_id)
        txt = f"👤 **پروفایل شما**\n\n📝 نام: {user['name']}\n🆔 Chat ID: `{chat_id}`"
        await query.edit_message_text(txt, reply_markup=back_kb(), parse_mode='Markdown')
    elif data == "MENU:HELP":
        await query.edit_message_text("ℹ️ **راهنما**\n\nاز دکمه‌های منو برای دریافت قیمت‌ها، ثبت هشدار و... استفاده کنید.\nبرای مبدل، دستور متنی ارسال کنید.", reply_markup=back_kb(), parse_mode='Markdown')

# ==================== تسک‌های پس‌زمینه ====================
async def alert_checker(app):
    while True:
        await asyncio.sleep(60) # هر 60 ثانیه
        if alerts_collection is None: continue
        alerts = await alerts_collection.find({}).to_list(length=None)
        for a in alerts:
            price = get_price(a["asset"])
            if not price: continue
            trig = (a["direction"] == "above" and price >= a["target_price"]) or (a["direction"] == "below" and price <= a["target_price"])
            if trig:
                try:
                    await app.bot.send_message(a["chat_id"], f"🔔 **هشدار فعال شد!**\n\n{a['asset']} به {format_price(price)} رسید.", parse_mode='Markdown')
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
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    print("🤖 Bot Started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
