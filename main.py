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
from oilpriceapi import OilPriceAPI

# ==================== تنظیمات ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8825337126:AAGo-ZLEzFGhQpDN-qbw4ufkazZ0w3OrgNQ")
MONGO_URI = os.environ.get("MONGO_URI", "")
OIL_PRICE_API_KEY = os.environ.get("OIL_PRICE_API_KEY", "")

CRYPTO_API_URL = 'https://api.abantether.com/api/v1/manager/otc/ticker'
FIAT_API_URL = 'https://cdn.jsdelivr.net/gh/HosseinOdd/Navasan-API@main/data/fiat.json'
GOLD_API_URL = 'https://cdn.jsdelivr.net/gh/HosseinOdd/Navasan-API@main/data/gold.json'

CHANNEL_ID = os.environ.get("CHANNEL_ID", "") 
CHANNEL_POST_INTERVAL = 3600 

# ==================== دیتابیس ====================
db_client = None
users_collection = None

async def init_db():
    global db_client, users_collection
    if not MONGO_URI:
        print("⚠️ MONGO_URI set نشده است. دیتابیس کار نمیکند.")
        return
    try:
        db_client = AsyncIOMotorClient(MONGO_URI, server_api='1', tlsCAFile=certifi.where())
        db = db_client["telegram_price_bot"]
        users_collection = db["users"]
        await users_collection.create_index("chat_id", unique=True)
        print("✅ اتصال به دیتابیس برقرار شد.")
    except Exception as e:
        print(f"❌ خطا در دیتابیس: {e}")

# ==================== دریافت قیمت‌ها ====================
FIAT_NAMES = {"USD": "دلار", "EUR": "یورو", "AED": "درهم", "TRY": "لیر"}
GOLD_NAMES = {"gold_18": "طلای ۱۸ عیار", "coin_emami": "سکه امامی", "coin_half": "نیم سکه"}

def format_price(price_val):
    if price_val is None: return "نامشخص"
    try:
        return f"{float(price_val):,.0f}"
    except: return str(price_val)

def fetch_oil():
    try:
        if not OIL_PRICE_API_KEY: return None
        client = OilPriceAPI(api_key=OIL_PRICE_API_KEY)
        res = client.prices.get("BRENT_CRUDE_USD")
        return {"price": res.value, "currency": res.currency}
    except: return None

def fetch_fiat(symbol):
    try:
        res = requests.get(FIAT_API_URL, timeout=10).json()
        if symbol.lower() in res:
            p = res[symbol.lower()].get("value") if isinstance(res[symbol.lower()], dict) else res[symbol.lower()]
            p = float(str(p).replace(",", ""))
            return p / 10 if p > 10_000_000 else p
    except: pass
    return None

def fetch_gold(asset):
    try:
        res = requests.get(GOLD_API_URL, timeout=10).json()
        key_map = {"gold_18": "18ayar", "coin_emami": "sekkeh", "coin_half": "nim"}
        if asset in key_map and key_map[asset] in res:
            return float(res[key_map[asset]]["value"])
    except: pass
    return None

def fetch_crypto(symbol):
    try:
        res = requests.get(CRYPTO_API_URL, timeout=10).json()
        market = res.get("data", {}).get("markets", {})
        if symbol in market: return float(market[symbol]["buy_price"])
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
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="MENU:HELP")]
    ])

def crypto_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("BTC", callback_data="CRYPTO:BTC"), InlineKeyboardButton("ETH", callback_data="CRYPTO:ETH")],
        [InlineKeyboardButton("USDT", callback_data="CRYPTO:USDT"), InlineKeyboardButton("SOL", callback_data="CRYPTO:SOL")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")]
    ])

def fiat_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("دلار 🇺🇸", callback_data="FIAT:USD"), InlineKeyboardButton("یورو 🇪🇺", callback_data="FIAT:EUR")],
        [InlineKeyboardButton("درهم 🇦🇪", callback_data="FIAT:AED"), InlineKeyboardButton("لیر 🇹🇷", callback_data="FIAT:TRY")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")]
    ])

def gold_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("طلای ۱۸", callback_data="GOLD:gold_18"), InlineKeyboardButton("سکه امامی", callback_data="GOLD:coin_emami")],
        [InlineKeyboardButton("نیم سکه", callback_data="GOLD:coin_half")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")]
    ])

# ==================== هندلرها ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "سلام! 👋\n\nبه *ارز آنلاین* خوش آمدید.\n\nاز منوی زیر برای دریافت قیمت‌ها استفاده کنید:"
    await update.message.reply_text(text, reply_markup=main_menu(), parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "ℹ️ *راهنمای ربات*\n\n- برای دریافت قیمت‌ها از منو استفاده کنید.\n- دستور /start برای شروع مجدد."
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")]]), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "MENU:MAIN":
        await query.edit_message_text("🏠 *منوی اصلی*\nلطفا یک گزینه را انتخاب کنید:", reply_markup=main_menu(), parse_mode='Markdown')
    
    elif data == "MENU:CRYPTO":
        await query.edit_message_text("🪙 *ارز دیجیتال*\nیکی از رمزارزها را انتخاب کنید:", reply_markup=crypto_menu(), parse_mode='Markdown')
    
    elif data == "MENU:FIAT":
        await query.edit_message_text("💵 *ارزهای فیات*\nیکی از ارزها را انتخاب کنید:", reply_markup=fiat_menu(), parse_mode='Markdown')
    
    elif data == "MENU:GOLD":
        await query.edit_message_text("🥇 *طلا و سکه*\nیکی از گزینه‌ها را انتخاب کنید:", reply_markup=gold_menu(), parse_mode='Markdown')
    
    elif data == "MENU:OIL":
        oil = fetch_oil()
        if oil:
            text = f"🛢️ *نفت برنت*\n💰 قیمت: *{format_price(oil['price'])} {oil['currency']}*\n🕐 زمان: {time.strftime('%Y-%m-%d %H:%M')}"
        else:
            text = "❌ در حال حاضر امکان دریافت قیمت نفت وجود ندارد."
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")]]), parse_mode='Markdown')
    
    elif data == "MENU:MARKET":
        btc = get_price("BTC") or 0
        usd = get_price("USD") or 0
        gold = get_price("gold_18") or 0
        oil = fetch_oil()
        oil_price = f"{format_price(oil['price'])} {oil['currency']}" if oil else "نامشخص"
        
        text = (
            "📊 *بازار امروز*\n━━━━━━━━━━━━━━━━━━\n"
            f"🪙 بیت‌کوین: *{format_price(btc)}* دلار\n"
            f"💵 دلار: *{format_price(usd)}* تومان\n"
            f"🥇 طلای ۱۸: *{format_price(gold)}* تومان\n"
            f"🛢️ نفت برنت: *{oil_price}*\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🕐 {time.strftime('%Y-%m-%d %H:%M')}"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 بروزرسانی", callback_data="MENU:MARKET"), InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:MAIN")]]), parse_mode='Markdown')
        
    elif data == "MENU:HELP":
        await help_command(update, context)
        
    elif data.startswith("CRYPTO:"):
        sym = data.split(":")[1]
        price = get_price(sym)
        text = f"📊 *{sym}*\n💰 قیمت: *{format_price(price)} تومان*" if price else f"❌ قیمت {sym} در دسترس نیست."
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:CRYPTO")]]), parse_mode='Markdown')
        
    elif data.startswith("FIAT:"):
        sym = data.split(":")[1]
        price = get_price(sym)
        name = FIAT_NAMES.get(sym, sym)
        text = f"💵 *{name}*\n💰 قیمت: *{format_price(price)} تومان*" if price else f"❌ قیمت {name} در دسترس نیست."
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:FIAT")]]), parse_mode='Markdown')
        
    elif data.startswith("GOLD:"):
        sym = data.split(":")[1]
        price = get_price(sym)
        name = GOLD_NAMES.get(sym, sym)
        text = f"🥇 *{name}*\n💰 قیمت: *{format_price(price)} تومان*" if price else f"❌ قیمت {name} در دسترس نیست."
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="MENU:GOLD")]]), parse_mode='Markdown')

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    sym = text.strip().upper()
    if sym in ["BTC", "ETH", "USDT"] or sym in FIAT_NAMES:
        price = get_price(sym)
        if price:
            await update.message.reply_text(f"💰 قیمت *{sym}*: *{format_price(price)}*", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ یافت نشد.")

# ==================== کانال و سرور ====================
async def channel_poster(app: Application):
    while True:
        await asyncio.sleep(CHANNEL_POST_INTERVAL)
        if not CHANNEL_ID: continue
        try:
            btc = get_price("BTC") or 0
            usd = get_price("USD") or 0
            gold = get_price("gold_18") or 0
            oil = fetch_oil()
            oil_price = f"{format_price(oil['price'])} {oil['currency']}" if oil else "نامشخص"
            
            text = (
                "📊 *نرخ لحظه‌ای بازار*\n━━━━━━━━━━━━━━━━━━\n"
                f"🪙 BTC: *{format_price(btc)}*\n"
                f"💵 دلار: *{format_price(usd)}* تومان\n"
                f"🥇 طلای ۱۸: *{format_price(gold)}* تومان\n"
                f"🛢️ نفت برنت: *{oil_price}*\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"🕐 {time.strftime('%Y-%m-%d %H:%M')}"
            )
            await app.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode='Markdown')
            print("✅ پست کانال ارسال شد.")
        except Exception as e:
            print(f"❌ خطا در ارسال پست کانال: {e}")

# ==================== اجرای اصلی ====================
app_flask = Flask(__name__)

@app_flask.route('/')
def home(): return "Telegram Bot is Running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def main():
    # 1. اجرای Flask در یک ترد جداگانه برای پاسخ به Health Check رندر
    threading.Thread(target=run_flask, daemon=True).start()
    
    # 2. اجرای ربات تلگرام در حلقه اصلی
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # راه‌اندازی تسک پس‌زمینه برای کانال
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db()) # دیتابیس رو یکبار مقداردهی اولیه میکنیم
    loop.create_task(channel_poster(application))

    print("🤖 ربات تلگرام روشن شد...")
    # نکته کلیدی: استفاده از close_loop=False برای جلوگیری از تداخل
    application.run_polling(close_loop=False, drop_pending_updates=True)

if __name__ == '__main__':
    main()
