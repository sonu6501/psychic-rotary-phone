from flask import Flask, request, jsonify
import requests
import os
import json
from datetime import datetime
import threading
import time
import pandas as pd
import numpy as np
import yfinance as yf
import pytz

app = Flask(__name__)

# ==========================================
# ⚙️ ENVIRONMENT VARIABLES & CONFIGURATION
# ==========================================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# आपकी एडमिन आईडी स्क्रीनशॉट से ली गई है
ADMIN_IDS = [7278927637] 

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("⚠️ WARNING: Telegram Token या Chat ID ठीक से सेट नहीं है! कृपया चेक करें।")

# ==========================================
# 📊 GLOBAL DATA STRUCTURES
# ==========================================
alerts_today = []
stocks_data = {}
user_states = {}  # मल्टी-स्टेप कमांड्स (जैसे ब्रॉडकास्ट) के लिए स्टेट मैनेज करेगा
bot_settings = {
    'is_paused': False  # एडमिन स्कैनिंग को रोक या चालू कर सकता है
}

USERS_DB_FILE = 'users_db.json'

# ==========================================
# 🗄️ DATABASE MANAGEMENT FUNCTIONS
# ==========================================
def load_users():
    """यूज़र्स का डेटा JSON फाइल से मेमोरी में लोड करता है।"""
    if os.path.exists(USERS_DB_FILE):
        try:
            with open(USERS_DB_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading users DB: {e}")
            return {}
    return {}

def save_users(users_data):
    """मेमोरी के डेटा को वापस JSON फाइल में सुरक्षित रूप से सेव करता है।"""
    try:
        with open(USERS_DB_FILE, 'w') as f:
            json.dump(users_data, f, indent=4)
    except Exception as e:
        print(f"Error saving users DB: {e}")

bot_users = load_users()

# ==========================================
# 📈 STOCK & CRYPTO LISTS
# ==========================================
NSE_STOCKS = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","SBIN",
    "BHARTIARTL","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI","SUNPHARMA",
    "TITAN","BAJFINANCE","WIPRO","ONGC","NTPC","POWERGRID","ULTRACEMCO","HCLTECH",
    "NESTLEIND","TATAMOTORS","ADANIENT","ADANIPORTS","BAJAJFINSV","JSWSTEEL",
    "TATASTEEL","TECHM","DRREDDY","CIPLA","DIVISLAB","COALINDIA","GRASIM",
    "BPCL","EICHERMOT","HINDALCO","INDUSINDBK","SBILIFE","HDFCLIFE","APOLLOHOSP",
    "BAJAJ-AUTO","TATACONSUM","BRITANNIA","HEROMOTOCO","UPL","DMART","ADANIGREEN",
    "ADANITRANS","SIEMENS","PIDILITIND","HAVELLS","MARICO","BERGEPAINT","COLPAL",
    "DABUR","GODREJCP","TATAPOWER","CANBK","PNB","BANKBARODA","FEDERALBNK",
    "IDFCFIRSTB","BANDHANBNK","MUTHOOTFIN","CHOLAFIN","BAJAJHLDNG","SBICARD",
    "MANAPPURAM","LICHSGFIN","M&M","MOTHERSON","BOSCHLTD","EXIDEIND","AMARAJABAT",
    "BALKRISIND","MRF","CEATLTD","APOLLOTYRE","TIINDIA","SCHAEFFLER","SUNDRMFAST",
    "ZOMATO","NYKAA","PAYTM","POLICYBZR","DELHIVERY","IRCTC","INDIGO","SPICEJET",
    "TRENT","VEDL","NMDC","SAIL","HINDZINC","NATIONALUM","MOIL","GMRINFRA",
    "IRB","ASHOKA","KNRCON","NCC","HCC","PNCINFRA","AHLUCONT","PATELENG",
    "INOXWIND","SUZLON","TATAELXSI","LTTS","PERSISTENT","COFORGE","MPHASIS",
    "HEXAWARE","KPITTECH","CYIENT","ZENSAR","NIITTECH","RAMSARUP","MASTEK",
    "SONACOMS","RVNL","IRFC","HUDCO","REC","PFC","SJVN","NHPC","TORNTPOWER",
    "CESC","JSWENERGY","RENUKA","TRIVENI","DWARIKESH","BALRAMCHIN","EID",
    "GODREJPROP","LODHA","DLF","OBEROIRLTY","PHOENIXLTD","PRESTIGE","BRIGADE",
    "SOBHA","MAHINDCIE","SWARAJENG","ESCORTS","FORCEMOT","VSTIND","MAHLOG",
    "GESHIP","SCI","CONCOR","BLUEDART","GATI","MAHINDRA","MINDTREE","LTIM",
    "OFSS","NIIT","RATEGAIN","NAUKRI","JUSTDIAL","INDIAMART","MATRIMONY","MAKEMYTRIP",
    "TANLA","ROUTE","HFCL","STLTECH","TATACOMM","RAILTEL","NBCC","BEML",
    "BEL","HAL","MIDHANI","MTAR","PARAS","LAXMIMACH","GRINDWELL","ELGIEQUIP",
    "THERMAX","BHEL","ABB","VOLTAS","BLUESTARCO","WHIRLPOOL","SYMPHONY","CROMPTON"
]

CRYPTO_PAIRS = [
    "BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD",
    "ADA-USD","AVAX-USD","DOGE-USD","DOT-USD","MATIC-USD"
]

# ==========================================
# 📡 TELEGRAM API UTILITIES
# ==========================================
def send_message(chat_id, message, reply_markup=None):
    """टेलीग्राम पर मैसेज भेजने का मुख्य फंक्शन"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Telegram send_message error: {e}")
        return None

def send_document(chat_id, document_path, caption=""):
    """टेलीग्राम पर फाइल भेजने का फंक्शन (बैकअप के लिए)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    try:
        with open(document_path, 'rb') as doc:
            files = {'document': doc}
            data = {'chat_id': chat_id, 'caption': caption}
            response = requests.post(url, data=data, files=files, timeout=20)
            return response.json()
    except Exception as e:
        print(f"Telegram send_document error: {e}")
        return None

# ==========================================
# 🔐 AUTHENTICATION & KEYBOARDS
# ==========================================
def is_admin(chat_id):
    return chat_id in ADMIN_IDS

def is_banned(chat_id):
    chat_id_str = str(chat_id)
    if chat_id_str in bot_users:
        return bot_users[chat_id_str].get('is_banned', False)
    return False

def get_user_keyboard():
    """नॉर्मल यूज़र्स के लिए सुरक्षित कीबोर्ड"""
    return {
        'keyboard': [
            [{'text': '📊 Price Check'},    {'text': '🔥 All Active Stocks'}],
            [{'text': '📈 All BUY Stocks'}, {'text': '📉 All SELL Stocks'}],
            [{'text': '📋 Aaj Ke Alerts'},  {'text': '⏮ Last Alert'}],
            [{'text': '🏆 Top Gainers'},     {'text': '💀 Top Losers'}],
            [{'text': '❓ Help'}]
        ],
        'resize_keyboard': True,
        'persistent': True
    }

def get_admin_keyboard():
    """एडमिन के लिए सुपर पावर कीबोर्ड"""
    return {
        'keyboard': [
            [{'text': '🛠 Admin Panel'},    {'text': '🔍 Force Scan'}],
            [{'text': '📢 Broadcast'},      {'text': '💾 Backup DB'}],
            [{'text': '⏸ Pause Bot'},       {'text': '▶️ Resume Bot'}],
            [{'text': '👥 All Users'},       {'text': '✅ Bot Status'}],
            [{'text': '📊 Price Check'},    {'text': '🔥 Active Stocks'}],
        ],
        'resize_keyboard': True,
        'persistent': True
    }

def register_user(chat_id, first_name, username):
    """नये यूजर को डेटाबेस में सेव करना और इंटरैक्शन ट्रैक करना"""
    chat_id_str = str(chat_id)
    if chat_id_str not in bot_users:
        now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%d-%m-%Y %H:%M:%S")
        bot_users[chat_id_str] = {
            'first_name': first_name,
            'username': username,
            'join_date': now,
            'interactions': 1,
            'is_banned': False
        }
        save_users(bot_users)
        for admin in ADMIN_IDS:
            send_message(admin, f"🚨 <b>New User Registered!</b>\n\n👤 Name: {first_name}\n🔗 Username: @{username}\n🆔 ID: <code>{chat_id}</code>")
    else:
        bot_users[chat_id_str]['interactions'] = bot_users[chat_id_str].get('interactions', 0) + 1
        save_users(bot_users)

# ==========================================
# 🧮 MARKET ANALYSIS ALGORITHMS
# ==========================================
def calculate_ema(prices, period):
    prices = np.array(prices, dtype=float)
    k = 2.0 / (period + 1)
    ema = [prices[0]]
    for p in prices[1:]:
        ema.append(p * k + ema[-1] * (1 - k))
    return ema

def calculate_rsi(prices, period=14):
    prices = np.array(prices, dtype=float)
    deltas = np.diff(prices)
    gains  = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100
    rs  = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)

def check_stock(symbol, is_crypto=False):
    """स्टॉक या क्रिप्टो की लाइव एनालिसिस करता है"""
    try:
        ticker_sym = symbol if is_crypto else symbol + ".NS"
        ticker     = yf.Ticker(ticker_sym)
        hist       = ticker.history(period="3mo", interval="1d")

        if hist.empty or len(hist) < 25:
            return None

        closes = hist['Close'].tolist()

        ema9  = calculate_ema(closes, 9)
        ema21 = calculate_ema(closes, 21)
        rsi   = calculate_rsi(closes[-15:])

        prev_ema9_gt  = ema9[-2]  > ema21[-2]
        curr_ema9_gt  = ema9[-1]  > ema21[-1]

        buy_signal  = (not prev_ema9_gt) and curr_ema9_gt  and rsi < 70
        sell_signal = prev_ema9_gt       and (not curr_ema9_gt) and rsi > 30

        current_price = round(closes[-1], 2)

        if buy_signal:
            return {'ticker': symbol, 'price': str(current_price), 'action': 'BUY',  'timeframe': '1D', 'rsi': str(rsi), 'strategy': 'EMA9x21+RSI'}
        elif sell_signal:
            return {'ticker': symbol, 'price': str(current_price), 'action': 'SELL', 'timeframe': '1D', 'rsi': str(rsi), 'strategy': 'EMA9x21+RSI'}

        return None

    except Exception as e:
        print(f"Error checking {symbol}: {e}")
        return None

def format_alert_message(data):
    now    = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%d-%m-%Y %H:%M:%S")
    action = data.get('action', '').upper()
    if action == 'BUY':
        emoji       = '🟢'
        action_text = '📈 BUY SIGNAL'
    elif action == 'SELL':
        emoji       = '🔴'
        action_text = '📉 SELL SIGNAL'
    else:
        emoji       = '🔔'
        action_text = '⚡ ALERT'
    return (
        f"{emoji} <b>{action_text}</b> {emoji}\n\n"
        f"📊 <b>Stock:</b>     {data.get('ticker', 'N/A')}\n"
        f"💰 <b>Price:</b>     ₹{data.get('price', 'N/A')}\n"
        f"⚡ <b>Action:</b>    {action}\n"
        f"📊 <b>RSI:</b>       {data.get('rsi', 'N/A')}\n"
        f"⏰ <b>Timeframe:</b> {data.get('timeframe', 'N/A')}\n"
        f"📝 <b>Strategy:</b>  {data.get('strategy', 'N/A')}\n"
        f"🕐 <b>Time:</b>      {now}"
    )

def scan_all_stocks(triggered_by=None):
    if bot_settings['is_paused'] and not triggered_by:
        print("Bot is paused. Auto-scan skipped.")
        return

    print("🔍 Scanning started...")
    notify_chat = triggered_by if triggered_by else TELEGRAM_CHAT_ID
    if triggered_by:
        send_message(notify_chat, "🔍 <b>Force Scanning shuru hua...</b>\nसभी मार्केट्स चेक हो रहे हैं।")

    buy_signals  = []
    sell_signals = []
    total        = len(NSE_STOCKS) + len(CRYPTO_PAIRS)
    done         = 0

    # NSE Stocks scan
    for symbol in NSE_STOCKS:
        result = check_stock(symbol, is_crypto=False)
        if result:
            result['time'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')
            alerts_today.append(result)
            stocks_data[symbol] = result
            if result['action'] == 'BUY':
                buy_signals.append(result)
            else:
                sell_signals.append(result)
        done += 1
        time.sleep(0.2)  

    # Crypto scan
    for symbol in CRYPTO_PAIRS:
        result = check_stock(symbol, is_crypto=True)
        if result:
            result['time'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')
            alerts_today.append(result)
            stocks_data[symbol] = result
            if result['action'] == 'BUY':
                buy_signals.append(result)
            else:
                sell_signals.append(result)
        done += 1
        time.sleep(0.2)

    # Summary Generation
    summary = (
        f"✅ <b>Scan Complete!</b>\n\n"
        f"📊 Total Checked: {total}\n"
        f"📈 BUY Signals:  {len(buy_signals)}\n"
        f"📉 SELL Signals: {len(sell_signals)}\n"
        f"🕐 Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M')}\n\n"
    )

    if buy_signals:
        summary += "🟢 <b>BUY Stocks:</b>\n"
        for s in buy_signals:
            summary += f"📈 <b>{s['ticker']}</b> @ ₹{s['price']} | RSI: {s['rsi']}\n"
        summary += "\n"

    if sell_signals:
        summary += "🔴 <b>SELL Stocks:</b>\n"
        for s in sell_signals:
            summary += f"📉 <b>{s['ticker']}</b> @ ₹{s['price']} | RSI: {s['rsi']}\n"

    if not buy_signals and not sell_signals:
        summary += "😴 कोई नया सिग्नल नहीं मिला।"

    if len(summary) > 4000:
        chunks = [summary[i:i+4000] for i in range(0, len(summary), 4000)]
        for chunk in chunks:
            send_message(notify_chat, chunk)
    else:
        send_message(notify_chat, summary)

def auto_scan_loop():
    IST = pytz.timezone('Asia/Kolkata')
    while True:
        try:
            if not bot_settings['is_paused']:
                now = datetime.now(IST)
                # Weekdays 9am-4pm
                if now.weekday() < 5 and 9 <= now.hour <= 16:
                    scan_all_stocks()
                else:
                    # Crypto scans 24/7
                    scan_all_stocks()
            time.sleep(3600)  # 1 Hour delay
        except Exception as e:
            print(f"Auto scan error: {e}")
            time.sleep(60)

# ==========================================
# 👑 SUPER ADMIN COMMAND HANDLERS
# ==========================================

def handle_admin_panel(chat_id):
    total_users = len(bot_users)
    banned_users = sum(1 for u in bot_users.values() if u.get('is_banned', False))
    status_emoji = "⏸ PAUSED" if bot_settings['is_paused'] else "▶️ RUNNING"
    
    message = (
        f"👑 <b>SUPER ADMIN PANEL</b> 👑\n\n"
        f"🤖 <b>Bot Status:</b> {status_emoji}\n"
        f"👥 <b>Total Users:</b> {total_users}\n"
        f"🚫 <b>Banned Users:</b> {banned_users}\n"
        f"🔥 <b>Active Stocks:</b> {len(stocks_data)}\n"
        f"🔔 <b>Today Alerts:</b> {len(alerts_today)}\n\n"
        f"<b>🛠️ Manual Admin Commands:</b>\n"
        f"<code>/ban [user_id]</code> - किसी को बैन करें\n"
        f"<code>/unban [user_id]</code> - किसी को अनबैन करें\n"
    )
    send_message(chat_id, message)

def handle_broadcast_init(chat_id):
    user_states[chat_id] = 'WAITING_FOR_BROADCAST'
    send_message(chat_id, "📢 <b>Broadcast Mode Active:</b>\n\nकृपया वह मैसेज टाइप करें जो आप सभी यूज़र्स को भेजना चाहते हैं।\n\n(इसे कैंसिल करने के लिए 'cancel' टाइप करें)")

def execute_broadcast(admin_chat_id, text):
    if text.lower() == 'cancel':
        user_states.pop(admin_chat_id, None)
        send_message(admin_chat_id, "✅ ब्रॉडकास्ट कैंसिल कर दिया गया है।")
        return

    send_message(admin_chat_id, "⏳ ब्रॉडकास्ट शुरू हो रहा है... कृपया प्रतीक्षा करें।")
    success = 0
    failed = 0
    
    broadcast_msg = f"🔔 <b>Admin Update:</b>\n\n{text}"
    
    for uid, data in bot_users.items():
        if not data.get('is_banned', False):
            res = send_message(uid, broadcast_msg)
            if res and res.get('ok'):
                success += 1
            else:
                failed += 1
            time.sleep(0.05) # Rate limit protection

    user_states.pop(admin_chat_id, None)
    send_message(admin_chat_id, f"✅ <b>Broadcast Complete!</b>\n\n📨 Successfully sent: {success}\n❌ Failed: {failed}")

def handle_ban_unban(chat_id, text, action):
    parts = text.split()
    if len(parts) < 2:
        send_message(chat_id, f"⚠️ सही फॉर्मेट का उपयोग करें: <code>/{action} 123456789</code>")
        return
    
    target_id = parts[1]
    if target_id not in bot_users:
        send_message(chat_id, "❌ यह यूज़र डेटाबेस में नहीं मिला।")
        return
        
    if action == 'ban':
        bot_users[target_id]['is_banned'] = True
        send_message(chat_id, f"🚫 यूज़र <code>{target_id}</code> को सफलतापूर्ण बैन कर दिया गया है।")
        send_message(target_id, "🚫 <b>ACCOUNT BANNED</b>\n\nआपको एडमिन द्वारा बैन कर दिया गया है। आप अब इस बॉट का इस्तेमाल नहीं कर सकते।", reply_markup={"remove_keyboard": True})
    else:
        bot_users[target_id]['is_banned'] = False
        send_message(chat_id, f"✅ यूज़र <code>{target_id}</code> को सफलतापूर्ण अनबैन कर दिया गया है।")
        send_message(target_id, "✅ आपका अकाउंट एडमिन द्वारा अनबैन कर दिया गया है। आप फिर से बॉट का इस्तेमाल कर सकते हैं।", reply_markup=get_user_keyboard())
    
    save_users(bot_users)

# ==========================================
# 👤 GENERAL COMMAND HANDLERS
# ==========================================

def handle_start(chat_id, first_name, username):
    register_user(chat_id, first_name, username)
    admin_status = "👑 <b>Super Admin Access Granted</b>" if is_admin(chat_id) else "👤 <b>User Mode Active</b>"
    
    message = (
        f"🤖 <b>नमस्ते {first_name}! Black Devil Trading Bot में आपका स्वागत है।</b>\n\n"
        f"{admin_status}\n\n"
        f"मैं लाइव मार्केट में NSE + Crypto स्कैन करता हूँ!\n\n"
        f"<b>Commands:</b>\n"
        f"/price RELIANCE — लाइव प्राइस चेक करें\n"
        f"/allstocks — एक्टिव स्टॉक्स की लिस्ट\n"
        f"/buy — BUY सिग्नल्स देखें\n"
        f"/sell — SELL सिग्नल्स देखें\n"
        f"/gainers — टॉप गेनर्स\n"
        f"/alerts — आज के सभी अलर्ट्स\n\n"
        f"<i>👇 नीचे दिए गए बटन्स का उपयोग करें!</i>"
    )
    
    keyboard = get_admin_keyboard() if is_admin(chat_id) else get_user_keyboard()
    send_message(chat_id, message, reply_markup=keyboard)

def handle_users_list(chat_id):
    if not bot_users:
        send_message(chat_id, "👥 अभी तक कोई यूज़र रजिस्टर नहीं हुआ है।")
        return
        
    message = f"👥 <b>Registered Users ({len(bot_users)}):</b>\n\n"
    for uid, data in bot_users.items():
        name = data.get('first_name', 'Unknown')
        uname = data.get('username', 'None')
        banned = "🚫 BANNED" if data.get('is_banned', False) else "✅ ACTIVE"
        message += f"👤 <b>{name}</b> (@{uname})\n🆔 <code>{uid}</code>\nСтатус: {banned}\n\n"
        
    if len(message) > 4000:
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            send_message(chat_id, chunk)
    else:
        send_message(chat_id, message)

def handle_price(chat_id, text):
    parts = text.strip().split()
    if len(parts) < 2:
        send_message(chat_id, "⚠️ स्टॉक का सिंबल बताएं!\n\nExample: <code>/price RELIANCE</code>")
        return
    symbol = parts[1].upper()
    send_message(chat_id, f"🔍 <b>{symbol}</b> का प्राइस फेच हो रहा है...")
    try:
        ticker = yf.Ticker(symbol + ".NS")
        info   = ticker.history(period="5d", interval="1m")
        if info.empty:
            ticker = yf.Ticker(symbol)
            info   = ticker.history(period="5d", interval="1m")
        
        if not info.empty and len(info) >= 2:
            price      = round(info['Close'].iloc[-1], 2)
            prev_close = round(info['Close'].iloc[-2],  2)
            change     = round(price - prev_close, 2)
            change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
            trend      = "📈" if change >= 0 else "📉"
            sign       = "+" if change >= 0 else ""
            msg = (
                f"{trend} <b>{symbol}</b>\n\n"
                f"💰 <b>Price:</b>  ₹{price}\n"
                f"📊 <b>Change:</b> {sign}{change} ({sign}{change_pct}%)\n"
                f"🕐 <b>Time:</b>   {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M')}"
            )
            send_message(chat_id, msg)
        else:
            send_message(chat_id, f"❌ <b>{symbol}</b> का डेटा नहीं मिला!")
    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

def handle_allstocks(chat_id, filter_action=None):
    if not stocks_data:
        send_message(chat_id, "🔥 कोई एक्टिव स्टॉक नहीं है। मार्केट कंडीशन न्यूट्रल हैं।")
        return
    if filter_action:
        filtered = {k: v for k, v in stocks_data.items() if v.get('action','').upper() == filter_action.upper()}
        emoji    = '📈' if filter_action == 'BUY' else '📉'
        title    = f"{emoji} <b>{filter_action} Stocks ({len(filtered)}):</b>\n\n"
    else:
        filtered = stocks_data
        title    = f"🔥 <b>Active Stocks ({len(filtered)}):</b>\n\n"

    if not filtered:
        send_message(chat_id, f"❌ कोई {filter_action} स्टॉक नहीं मिला।")
        return

    message = title
    count   = 0
    msgs    = []
    for ticker, data in filtered.items():
        action  = data.get('action','N/A').upper()
        price   = data.get('price','N/A')
        rsi     = data.get('rsi','N/A')
        t       = data.get('time','N/A')
        em      = '🟢' if action == 'BUY' else '🔴'
        message += f"{em} <b>{ticker}</b> @ ₹{price} | RSI:{rsi} | {t}\n"
        count   += 1
        if count % 30 == 0:
            msgs.append(message)
            message = "<b>...continued:</b>\n\n"
    if message.strip():
        msgs.append(message)
    for m in msgs:
        send_message(chat_id, m)

def handle_gainers_losers(chat_id, mode='gainers'):
    send_message(chat_id, "📡 डेटा फेच हो रहा है... थोड़ा इंतज़ार करें!")
    try:
        results = []
        check_list = NSE_STOCKS[:30]
        for symbol in check_list:
            try:
                ticker = yf.Ticker(symbol + ".NS")
                hist   = ticker.history(period="2d", interval="1d")
                if len(hist) >= 2:
                    prev  = hist['Close'].iloc[-2]
                    curr  = hist['Close'].iloc[-1]
                    chng  = round(((curr - prev) / prev) * 100, 2) if prev else 0
                    results.append((symbol, round(curr, 2), chng))
                time.sleep(0.1)
            except:
                pass

        results.sort(key=lambda x: x[2], reverse=(mode == 'gainers'))
        top   = results[:10]
        title = "🏆 <b>Top Gainers:</b>\n\n" if mode == 'gainers' else "💀 <b>Top Losers:</b>\n\n"
        msg   = title
        for i, (sym, price, chng) in enumerate(top, 1):
            sign = "+" if chng >= 0 else ""
            em   = "📈" if chng >= 0 else "📉"
            msg += f"{i}. {em} <b>{sym}</b> ₹{price} ({sign}{chng}%)\n"
        send_message(chat_id, msg)
    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

def handle_button(chat_id, text, first_name):
    # स्टेट चेकिंग (ब्रॉडकास्ट के लिए)
    if chat_id in user_states and user_states[chat_id] == 'WAITING_FOR_BROADCAST':
        execute_broadcast(chat_id, text)
        return

    # Normal Buttons
    if text == '📊 Price Check':
        send_message(chat_id, "📊 कौनसे स्टॉक का प्राइस चाहिए?\n\nलिखें: <code>/price RELIANCE</code>")
    elif text in ['🔥 All Active Stocks', '🔥 Active Stocks']:
        handle_allstocks(chat_id)
    elif text == '📈 All BUY Stocks':
        handle_allstocks(chat_id, filter_action='BUY')
    elif text == '📉 All SELL Stocks':
        handle_allstocks(chat_id, filter_action='SELL')
    elif text == '📋 Aaj Ke Alerts':
        if not alerts_today:
            send_message(chat_id, "📋 आज अभी तक कोई अलर्ट नहीं आया।")
        else:
            msg = f"📋 <b>आज के अलर्ट्स ({len(alerts_today)}):</b>\n\n"
            for al in alerts_today[-15:]:
                em = '🟢' if al.get('action') == 'BUY' else '🔴'
                msg += f"{em} <b>{al.get('ticker','?')}</b> — {al.get('action')} @ ₹{al.get('price','?')} | {al.get('time','')}\n"
            send_message(chat_id, msg)
    elif text == '⏮ Last Alert':
        if alerts_today: send_message(chat_id, format_alert_message(alerts_today[-1]))
        else: send_message(chat_id, "📋 कोई अलर्ट नहीं मिला।")
    elif text == '🏆 Top Gainers':
        handle_gainers_losers(chat_id, mode='gainers')
    elif text == '💀 Top Losers':
        handle_gainers_losers(chat_id, mode='losers')
    
    # Super Admin Buttons
    elif text == '🛠 Admin Panel':
        if is_admin(chat_id): handle_admin_panel(chat_id)
    elif text == '🔍 Force Scan':
        if is_admin(chat_id):
            send_message(chat_id, "🔍 Force Scan शुरू हो रहा है... 2-3 मिनट लगेंगे!")
            threading.Thread(target=scan_all_stocks, args=(chat_id,)).start()
    elif text == '👥 All Users':
        if is_admin(chat_id): handle_users_list(chat_id)
    elif text == '📢 Broadcast':
        if is_admin(chat_id): handle_broadcast_init(chat_id)
    elif text == '💾 Backup DB':
        if is_admin(chat_id):
            send_document(chat_id, USERS_DB_FILE, caption="💾 <b>बॉट का डेटाबेस बैकअप</b>")
    elif text == '⏸ Pause Bot':
        if is_admin(chat_id):
            bot_settings['is_paused'] = True
            send_message(chat_id, "⏸ <b>बॉट रोक दिया गया है।</b>\nअब कोई ऑटोमैटिक स्कैनिंग नहीं होगी।")
    elif text == '▶️ Resume Bot':
        if is_admin(chat_id):
            bot_settings['is_paused'] = False
            send_message(chat_id, "▶️ <b>बॉट फिर से चालू कर दिया गया है।</b>\nऑटोमैटिक स्कैनिंग फिर से शुरू हो गई है।")
    elif text == '✅ Bot Status':
        if is_admin(chat_id): handle_admin_panel(chat_id)
    else:
        keyboard = get_admin_keyboard() if is_admin(chat_id) else get_user_keyboard()
        send_message(chat_id, "❓ कमांड समझ नहीं आई। मेनू का उपयोग करें!", reply_markup=keyboard)

# ==========================================
# 🌐 FLASK ROUTES
# ==========================================

@app.route('/')
def home():
    return jsonify({'status': '✅ Black Devil Super Bot Running!', 'users': len(bot_users)})

@app.route('/telegram', methods=['POST'])
def telegram_updates():
    try:
        update = request.get_json()
        if 'message' not in update:
            return jsonify({'status': 'ok'}), 200
        
        msg        = update['message']
        chat_id    = msg['chat']['id']
        text       = msg.get('text', '')
        first_name = msg.get('from', {}).get('first_name', 'Friend')
        username   = msg.get('from', {}).get('username', 'NoUsername')

        # अगर यूजर बैन है, तो उसके सारे मैसेज इग्नोर कर दो
        if is_banned(chat_id):
            return jsonify({'status': 'ok'}), 200

        register_user(chat_id, first_name, username)

        # Admin Commands
        if is_admin(chat_id):
            if text.startswith('/ban '):
                handle_ban_unban(chat_id, text, 'ban')
                return jsonify({'status': 'ok'}), 200
            elif text.startswith('/unban '):
                handle_ban_unban(chat_id, text, 'unban')
                return jsonify({'status': 'ok'}), 200

        # Normal Commands
        if text.startswith('/start'):
            handle_start(chat_id, first_name, username)
        elif text.startswith('/price'):
            handle_price(chat_id, text)
        else:
            handle_button(chat_id, text, first_name)

        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Error in telegram updates: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    render_url = request.args.get('url', '')
    if not render_url:
        return jsonify({'error': 'URL आवश्यक है'}), 400
    webhook_url = f"{render_url}/telegram"
    api_url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}"
    response    = requests.get(api_url)
    result      = response.json()
    if result.get('ok'):
        return jsonify({'status': '✅ Webhook Set!', 'url': webhook_url})
    return jsonify({'status': '❌ Failed', 'error': result})

# ==========================================
# 🚀 INITIALIZATION
# ==========================================
scanner_thread = threading.Thread(target=auto_scan_loop)
scanner_thread.daemon = True
scanner_thread.start()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
