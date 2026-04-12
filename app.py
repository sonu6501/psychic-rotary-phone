from flask import Flask, request, jsonify
import requests
import os
import json
from datetime import datetime, timedelta
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
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '-1003926102512') # Default Channel ID

# Force Subscribe Config
FORCE_CHANNEL_ID = "-1003926102512" 
FORCE_CHANNEL_LINK = "https://t.me/+vK7WE4K6T3U2ODc1" 

if not TELEGRAM_TOKEN:
    print("⚠️ WARNING: Telegram Token set nahi hai!")

# ==========================================
# 📊 GLOBAL DATA & STATE
# ==========================================
alerts_today = []
stocks_data = {}
user_states = {}  
bot_settings = {'is_paused': False}
USERS_DB_FILE = 'users_db.json'

def load_users():
    if os.path.exists(USERS_DB_FILE):
        try:
            with open(USERS_DB_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading users: {e}")
            return {}
    return {}

def save_users(users_data):
    try:
        with open(USERS_DB_FILE, 'w') as f:
            json.dump(users_data, f, indent=4)
    except Exception as e:
        print(f"Error saving users: {e}")

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
    "IDFCFIRSTB","BANDHANBNK","MUTHOOTFIN","CHOLAFIN","BAJAJHLDNG","SBICARD"
]

CRYPTO_PAIRS = ["BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD","ADA-USD","DOGE-USD"]

# ==========================================
# 📡 TELEGRAM UTILS
# ==========================================
def send_message(chat_id, message, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
    if reply_markup: payload['reply_markup'] = reply_markup
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.json()
    except Exception as e:
        print(f"TG Error: {e}")
        return None

def send_document(chat_id, document_path, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    try:
        with open(document_path, 'rb') as doc:
            files = {'document': doc}
            data = {'chat_id': chat_id, 'caption': caption}
            res = requests.post(url, data=data, files=files, timeout=20)
            return res.json()
    except Exception as e:
        print(f"TG Doc Error: {e}")
        return None

# ==========================================
# 🔐 AUTH & PAGINATED KEYBOARDS
# ==========================================
def is_admin(chat_id):
    user = bot_users.get(str(chat_id), {})
    return user.get('is_admin', False)

def is_vip(chat_id):
    user = bot_users.get(str(chat_id), {})
    if is_admin(chat_id): return True # Admin is always VIP
    if not user.get('is_vip', False): return False
    # Check expiry
    expiry_str = user.get('vip_expiry')
    if not expiry_str: return True # Lifetime VIP
    try:
        expiry = datetime.strptime(expiry_str, "%d-%m-%Y %H:%M")
        return datetime.now() < expiry
    except: return False

def check_channel_membership(user_id):
    if is_admin(user_id): return True
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember"
    try:
        res = requests.get(url, params={'chat_id': FORCE_CHANNEL_ID, 'user_id': user_id}, timeout=10).json()
        if res.get('ok') and res['result']['status'] in ['member', 'administrator', 'creator']: return True
    except: return True 
    return False

def register_user(chat_id, first_name, username):
    chat_id_str = str(chat_id)
    if chat_id_str not in bot_users:
        now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%d-%m-%Y %H:%M:%S")
        bot_users[chat_id_str] = {
            'first_name': first_name,
            'username': username,
            'join_date': now,
            'interactions': 1,
            'is_banned': False,
            'is_admin': False,
            'is_vip': False,
            'watchlist': []
        }
        save_users(bot_users)
        # Notify admins about new user
        for uid, data in bot_users.items():
            if data.get('is_admin'):
                send_message(uid, f"🚨 <b>New User!</b>\n👤 {first_name}\n🆔 <code>{chat_id}</code>")
    else:
        bot_users[chat_id_str]['interactions'] = bot_users[chat_id_str].get('interactions', 0) + 1
        save_users(bot_users)

# --- KEYBOARDS ---
def get_main_keyboard(chat_id):
    """Main clean keyboard"""
    kb = [
        [{'text': '📊 Price Check'}, {'text': '🔥 Active Stocks'}],
        [{'text': '📈 BUY Stocks'}, {'text': '📉 SELL Stocks'}],
        [{'text': '⭐ My Watchlist'}],
    ]
    # Admin gets Admin Menu, Normal gets More Options
    if is_admin(chat_id):
        kb.append([{'text': '➡️ More Options'}, {'text': '👑 Admin Menu'}])
    else:
        kb.append([{'text': '➡️ More Options'}])
    return {'keyboard': kb, 'resize_keyboard': True, 'persistent': True}

def get_more_options_keyboard():
    """Page 2 for normal users"""
    return {
        'keyboard': [
            [{'text': '📋 Aaj Ke Alerts'}, {'text': '⏮ Last Alert'}],
            [{'text': '🏆 Top Gainers'}, {'text': '💀 Top Losers'}],
            [{'text': '💎 Upgrade VIP'}, {'text': '⬅️ Back to Main'}]
        ], 'resize_keyboard': True
    }

def get_admin_menu_keyboard():
    """Admin specific tools"""
    return {
        'keyboard': [
            [{'text': '🛠 Admin Panel'}, {'text': '🔍 Force Scan'}],
            [{'text': '📢 Broadcast'}, {'text': '💾 Excel Backup'}],
            [{'text': '👥 All Users'}, {'text': '⏸ Pause / ▶️ Resume'}],
            [{'text': '⬅️ Back to Main'}]
        ], 'resize_keyboard': True
    }

def get_force_join_keyboard():
    return {"inline_keyboard": [[{"text": "📢 Join Our Channel First", "url": FORCE_CHANNEL_LINK}], [{"text": "✅ I Have Joined", "callback_data": "check_join"}]]}

# ==========================================
# 🧮 MARKET ANALYSIS
# ==========================================
def calculate_ema(prices, period):
    prices = np.array(prices, dtype=float)
    k = 2.0 / (period + 1)
    ema = [prices[0]]
    for p in prices[1:]: ema.append(p * k + ema[-1] * (1 - k))
    return ema

def calculate_rsi(prices, period=14):
    prices = np.array(prices, dtype=float)
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0: return 100
    return round(100 - (100 / (1 + (avg_gain / avg_loss))), 2)

def check_stock(symbol, is_crypto=False):
    try:
        ticker_sym = symbol if is_crypto else symbol + ".NS"
        hist = yf.Ticker(ticker_sym).history(period="3mo", interval="1d")
        if hist.empty or len(hist) < 25: return None
        closes = hist['Close'].tolist()
        ema9, ema21, rsi = calculate_ema(closes, 9), calculate_ema(closes, 21), calculate_rsi(closes[-15:])
        
        buy_sig = (not ema9[-2] > ema21[-2]) and (ema9[-1] > ema21[-1]) and rsi < 70
        sell_sig = (ema9[-2] > ema21[-2]) and (not ema9[-1] > ema21[-1]) and rsi > 30
        price = round(closes[-1], 2)

        if buy_sig: return {'ticker': symbol, 'price': str(price), 'action': 'BUY', 'rsi': str(rsi)}
        elif sell_sig: return {'ticker': symbol, 'price': str(price), 'action': 'SELL', 'rsi': str(rsi)}
        return None
    except: return None

def scan_all_stocks(triggered_by=None):
    if bot_settings['is_paused'] and not triggered_by: return
    notify_chat = triggered_by if triggered_by else TELEGRAM_CHAT_ID
    
    if triggered_by: send_message(notify_chat, "🔍 <b>Scanning started...</b>")
    
    buys, sells = [], []
    for sym in NSE_STOCKS + CRYPTO_PAIRS:
        is_cr = sym in CRYPTO_PAIRS
        res = check_stock(sym, is_cr)
        if res:
            res['time'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')
            alerts_today.append(res)
            stocks_data[sym] = res
            if res['action'] == 'BUY': buys.append(res)
            else: sells.append(res)
        time.sleep(0.1)

    summary = f"✅ <b>Scan Complete!</b>\n\n📈 BUY: {len(buys)}\n📉 SELL: {len(sells)}\n🕐 Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')}\n\n"
    for s in buys: summary += f"🟢 <b>{s['ticker']}</b> @ ₹{s['price']} | RSI: {s['rsi']}\n"
    for s in sells: summary += f"🔴 <b>{s['ticker']}</b> @ ₹{s['price']} | RSI: {s['rsi']}\n"

    if len(summary) > 4000:
        for chunk in [summary[i:i+4000] for i in range(0, len(summary), 4000)]: send_message(notify_chat, chunk)
    else: send_message(notify_chat, summary)

def auto_scan_loop():
    while True:
        try:
            if not bot_settings['is_paused']:
                now = datetime.now(pytz.timezone('Asia/Kolkata'))
                if now.weekday() < 5 and 9 <= now.hour <= 16: scan_all_stocks()
                else: scan_all_stocks()
            time.sleep(3600)  
        except: time.sleep(60)

# ==========================================
# 👑 ADMIN COMMANDS
# ==========================================
def export_excel_backup(chat_id):
    try:
        # Save JSON
        send_document(chat_id, USERS_DB_FILE, caption="📁 <b>JSON Database Backup</b>")
        
        # Convert to Excel (CSV)
        df = pd.DataFrame.from_dict(bot_users, orient='index')
        csv_file = 'users_backup.csv'
        df.to_csv(csv_file)
        send_document(chat_id, csv_file, caption="📊 <b>Excel/CSV Database Backup</b>")
    except Exception as e:
        send_message(chat_id, f"❌ Backup Failed: {e}")

def handle_broadcast(chat_id, text):
    if text.lower() == 'cancel':
        user_states.pop(chat_id, None)
        send_message(chat_id, "✅ Broadcast cancelled.")
        return
    send_message(chat_id, "⏳ Sending broadcast...")
    success, failed = 0, 0
    msg = f"🔔 <b>Important Update:</b>\n\n{text}"
    for uid, data in bot_users.items():
        if not data.get('is_banned'):
            if send_message(uid, msg): success += 1
            else: failed += 1
            time.sleep(0.05)
    user_states.pop(chat_id, None)
    send_message(chat_id, f"✅ <b>Broadcast Complete!</b>\nSent: {success} | Failed: {failed}")

# ==========================================
# 👤 USER COMMANDS & BUTTONS
# ==========================================
def handle_price(chat_id, text):
    parts = text.strip().split()
    if len(parts) < 2: return send_message(chat_id, "⚠️ Format: <code>/price RELIANCE</code>")
    sym = parts[1].upper()
    try:
        hist = yf.Ticker(sym + ".NS").history(period="2d", interval="1d")
        if hist.empty: hist = yf.Ticker(sym).history(period="2d", interval="1d")
        if not hist.empty and len(hist) >= 2:
            pr = round(hist['Close'].iloc[-1], 2)
            pc = round(hist['Close'].iloc[-2], 2)
            ch = round(pr - pc, 2)
            cp = round((ch / pc) * 100, 2)
            tr, sg = ("📈", "+") if ch >= 0 else ("📉", "")
            send_message(chat_id, f"{tr} <b>{sym}</b>\n💰 Price: ₹{pr}\n📊 Change: {sg}{ch} ({sg}{cp}%)")
        else: send_message(chat_id, f"❌ Data not found for {sym}")
    except: send_message(chat_id, f"❌ Error fetching {sym}")

def handle_allstocks(chat_id, filter_act=None):
    if not stocks_data: return send_message(chat_id, "🔥 Koi active stock nahi hai.")
    filtered = {k: v for k, v in stocks_data.items() if (v['action'] == filter_act if filter_act else True)}
    
    # --- VIP SYSTEM LOGIC ---
    vip_status = is_vip(chat_id)
    items = list(filtered.items())
    
    if not vip_status and len(items) > 3:
        display_items = items[:3]
        vip_msg = "\n\n🔒 <i>Remaining signals are hidden. Get VIP to see all!</i>"
    else:
        display_items = items
        vip_msg = ""

    if not display_items: return send_message(chat_id, "❌ Koi stock nahi mila.")
    
    msg = f"🔥 <b>{filter_act or 'Active'} Stocks:</b>\n\n"
    for t, d in display_items:
        em = '🟢' if d['action'] == 'BUY' else '🔴'
        msg += f"{em} <b>{t}</b> @ ₹{d['price']} | RSI:{d['rsi']}\n"
    
    send_message(chat_id, msg + vip_msg)

def handle_watchlist(chat_id, text):
    parts = text.split()
    uid = str(chat_id)
    wl = bot_users[uid].get('watchlist', [])
    
    if text == '⭐ My Watchlist' or text == '/watchlist':
        if not wl: return send_message(chat_id, "⭐ Aapki watchlist khali hai.\nAdd karein: <code>/add RELIANCE</code>")
        msg = "⭐ <b>Your Watchlist Live Status:</b>\n\n"
        for sym in wl:
            data = stocks_data.get(sym)
            if data:
                em = '🟢' if data['action'] == 'BUY' else '🔴'
                msg += f"{em} <b>{sym}</b>: {data['action']} @ ₹{data['price']}\n"
            else:
                msg += f"⚪ <b>{sym}</b>: Neutral (No Signal)\n"
        msg += "\n<i>Remove karne ke liye: /remove SYMBOL</i>"
        send_message(chat_id, msg)
        
    elif text.startswith('/add '):
        if len(parts) < 2: return
        sym = parts[1].upper()
        if sym not in wl: 
            wl.append(sym)
            bot_users[uid]['watchlist'] = wl
            save_users(bot_users)
            send_message(chat_id, f"✅ <b>{sym}</b> added to watchlist!")
        else: send_message(chat_id, "⚠️ Pehle se added hai.")
        
    elif text.startswith('/remove '):
        if len(parts) < 2: return
        sym = parts[1].upper()
        if sym in wl:
            wl.remove(sym)
            bot_users[uid]['watchlist'] = wl
            save_users(bot_users)
            send_message(chat_id, f"🗑 <b>{sym}</b> removed.")

def handle_button(chat_id, text):
    if chat_id in user_states and user_states[chat_id] == 'WAITING_FOR_BROADCAST':
        return handle_broadcast(chat_id, text)

    # --- Pagination & Navigation ---
    if text == '⬅️ Back to Main':
        send_message(chat_id, "🏠 Main Menu", reply_markup=get_main_keyboard(chat_id))
    elif text == '➡️ More Options':
        send_message(chat_id, "📂 More Options", reply_markup=get_more_options_keyboard())
    elif text == '👑 Admin Menu':
        if is_admin(chat_id): send_message(chat_id, "👑 Super Admin Tools", reply_markup=get_admin_menu_keyboard())

    # --- Core Features ---
    elif text == '📊 Price Check': send_message(chat_id, "📊 Kaunse stock ka price chahiye?\nLikho: <code>/price RELIANCE</code>")
    elif text == '🔥 Active Stocks': handle_allstocks(chat_id)
    elif text == '📈 BUY Stocks': handle_allstocks(chat_id, 'BUY')
    elif text == '📉 SELL Stocks': handle_allstocks(chat_id, 'SELL')
    elif text == '⭐ My Watchlist': handle_watchlist(chat_id, text)
    
    # --- Page 2 Features ---
    elif text == '📋 Aaj Ke Alerts':
        if not alerts_today: return send_message(chat_id, "📋 Aaj koi alert nahi aaya.")
        msg = "📋 <b>Aaj Ke Alerts:</b>\n\n"
        for al in alerts_today[-10:]:
            em = '🟢' if al['action'] == 'BUY' else '🔴'
            msg += f"{em} <b>{al.get('ticker')}</b> — {al['action']} @ ₹{al['price']}\n"
        send_message(chat_id, msg)
    elif text == '💎 Upgrade VIP':
        send_message(chat_id, "💎 <b>VIP Membership</b>\n\nVIP lene ke liye Admin ko contact karein. Isme aapko milenge:\n✅ Unlimited Live Signals\n✅ Full Active Stocks List\n✅ Zero Delay")
    
    # --- Admin Features ---
    elif text == '🛠 Admin Panel':
        if is_admin(chat_id): send_message(chat_id, f"👑 <b>Panel</b>\nUsers: {len(bot_users)}\nActive Stocks: {len(stocks_data)}\nVIPs: {sum(1 for u in bot_users.values() if u.get('is_vip'))}")
    elif text == '🔍 Force Scan':
        if is_admin(chat_id): threading.Thread(target=scan_all_stocks, args=(chat_id,)).start()
    elif text == '📢 Broadcast':
        if is_admin(chat_id):
            user_states[chat_id] = 'WAITING_FOR_BROADCAST'
            send_message(chat_id, "📢 Message type karein (cancel ke liye 'cancel' likhein):")
    elif text == '💾 Excel Backup':
        if is_admin(chat_id): export_excel_backup(chat_id)
    elif text == '⏸ Pause / ▶️ Resume':
        if is_admin(chat_id):
            bot_settings['is_paused'] = not bot_settings['is_paused']
            st = "PAUSED ⏸" if bot_settings['is_paused'] else "RUNNING ▶️"
            send_message(chat_id, f"Bot is now {st}")
    elif text == '👥 All Users':
        if is_admin(chat_id): send_message(chat_id, f"Total Registered: {len(bot_users)}\n<i>(Full detail ke liye Excel Backup lein)</i>")

# ==========================================
# 🌐 FLASK ROUTES
# ==========================================
@app.route('/')
def home(): return jsonify({'status': 'Running', 'users': len(bot_users)})

@app.route('/telegram', methods=['POST'])
def telegram_updates():
    try:
        update = request.get_json()
        
        # Callbacks (Join Check)
        if 'callback_query' in update:
            cb = update['callback_query']
            cid = cb['message']['chat']['id']
            if cb['data'] == "check_join":
                if check_channel_membership(cid):
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage", json={'chat_id': cid, 'message_id': cb['message']['message_id']})
                    send_message(cid, "🎉 <b>Verified!</b> Bot is unlocked.", reply_markup=get_main_keyboard(cid))
                else: send_message(cid, "❌ Abhi tak join nahi kiya.")
            return jsonify({'status': 'ok'}), 200

        if 'message' not in update: return jsonify({'status': 'ok'}), 200
        
        msg = update['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        fname = msg.get('from', {}).get('first_name', 'User')
        uname = msg.get('from', {}).get('username', 'None')

        if str(chat_id) in bot_users and bot_users[str(chat_id)].get('is_banned'): return jsonify({'status': 'ok'})
        register_user(chat_id, fname, uname)

        # 🛑 SECRET ADMIN SWITCH 🛑
        if text == "sonu@123":
            bot_users[str(chat_id)]['is_admin'] = True
            save_users(bot_users)
            send_message(chat_id, "🔐 <b>Secret Password Accepted!</b>\n\nAap ab Super Admin hain. Niche <b>👑 Admin Menu</b> check karein.", reply_markup=get_main_keyboard(chat_id))
            return jsonify({'status': 'ok'}), 200

        # Force Subscribe Check (Skipped for Admins)
        if not check_channel_membership(chat_id):
            send_message(chat_id, "⚠️ <b>Bot use karne ke liye channel join karein!</b>", reply_markup=get_force_join_keyboard())
            return jsonify({'status': 'ok'}), 200

        # Admin specific text commands
        if is_admin(chat_id):
            if text.startswith('/addvip '):
                parts = text.split()
                if len(parts) == 3:
                    target, days = parts[1], int(parts[2])
                    if target in bot_users:
                        exp = datetime.now() + timedelta(days=days)
                        bot_users[target]['is_vip'] = True
                        bot_users[target]['vip_expiry'] = exp.strftime("%d-%m-%Y %H:%M")
                        save_users(bot_users)
                        send_message(chat_id, f"✅ VIP given to {target} for {days} days.")
                        send_message(target, f"💎 <b>Congratulations!</b> You are now VIP for {days} days.")
                return jsonify({'status': 'ok'})

        # Global text commands
        if text.startswith('/start'): send_message(chat_id, f"🤖 Namaste {fname}!", reply_markup=get_main_keyboard(chat_id))
        elif text.startswith('/price '): handle_price(chat_id, text)
        elif text.startswith('/add ') or text.startswith('/remove ') or text == '/watchlist': handle_watchlist(chat_id, text)
        else: handle_button(chat_id, text)

        return jsonify({'status': 'ok'})
    except Exception as e:
        print(f"Update error: {e}")
        return jsonify({'status': 'error'})

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    url = request.args.get('url', '')
    res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={url}/telegram")
    return jsonify(res.json())

threading.Thread(target=auto_scan_loop, daemon=True).start()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
