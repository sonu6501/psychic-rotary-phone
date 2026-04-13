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

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
JOIN_LINK = "https://t.me/+vK7WE4K6T3U2ODc1"

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("⚠️ WARNING: Telegram Token या Chat ID set नहीं है!")

alerts_today = []
stocks_data = {}
paper_portfolio = {}

# Stocks List
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
    "BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD","ADA-USD","AVAX-USD",
    "DOGE-USD","DOT-USD","MATIC-USD","LINK-USD","UNI-USD","LTC-USD","BCH-USD",
    "ATOM-USD","XLM-USD","ALGO-USD","VET-USD","FIL-USD","TRX-USD","NEAR-USD",
    "ICP-USD","AAVE-USD","SAND-USD","MANA-USD","AXS-USD","THETA-USD","FTM-USD"
]

# ─────────────────────────────────────────
# NEW KEYBOARD (Option Adjusted)
# ─────────────────────────────────────────
def get_main_keyboard():
    return {
        'keyboard': [
            [{'text': '📊 Price Check'}, {'text': '🧭 Market Trend'}],
            [{'text': '📈 BUY Signals'}, {'text': '📉 SELL Signals'}],
            [{'text': '🏆 Top Gainers'}, {'text': '💀 Top Losers'}],
            [{'text': '📓 My Portfolio'}, {'text': '📢 Join Channel'}],
            [{'text': '🔥 All Stocks'}, {'text': '✅ Bot Status'}],
            [{'text': '❓ Help'}]
        ],
        'resize_keyboard': True,
        'persistent': True
    }

# ─────────────────────────────────────────
# ADMIN CHECK LOGIC
# ─────────────────────────────────────────
def is_admin(chat_id, user_id):
    # Private chat mein user khud admin hota hai
    if str(chat_id).startswith('-'): # Group or Channel
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember?chat_id={chat_id}&user_id={user_id}"
        try:
            res = requests.get(url).json()
            status = res.get('result', {}).get('status', '')
            return status in ['creator', 'administrator']
        except:
            return False
    return True

# ─────────────────────────────────────────
# INDICATORS & MATH
# ─────────────────────────────────────────
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
    if avg_loss == 0: return 100
    rs  = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_atr(df, period=14):
    high, low = df['High'].values, df['Low'].values
    close = df['Close'].shift(1).values
    close[0] = low[0]
    tr = np.maximum(high - low, np.maximum(abs(high - close), abs(low - close)))
    return round(pd.Series(tr).rolling(window=period).mean().iloc[-1], 2)

def check_master_trend():
    try:
        nifty = yf.Ticker("^NSEI").history(period="5d")
        if len(nifty) >= 2:
            return "📈 BULLISH" if nifty['Close'].iloc[-1] > nifty['Close'].iloc[-2] else "📉 BEARISH"
    except: pass
    return "⚖️ NEUTRAL"

# ─────────────────────────────────────────
# SCANNER LOGIC
# ─────────────────────────────────────────
def check_stock_pro(symbol, is_crypto=False):
    try:
        ticker_sym = symbol if is_crypto else symbol + ".NS"
        ticker     = yf.Ticker(ticker_sym)
        hist       = ticker.history(period="3mo", interval="1d")
        if hist.empty or len(hist) < 25: return None
        closes, volumes = hist['Close'].tolist(), hist['Volume'].tolist()
        ema9, ema21 = calculate_ema(closes, 9), calculate_ema(closes, 21)
        rsi, atr = calculate_rsi(closes[-15:]), calculate_atr(hist)
        avg_vol = np.mean(volumes[-11:-1]) if len(volumes) > 10 else 1
        vol_burst = volumes[-1] > (avg_vol * 1.5)
        prev_ema9_gt, curr_ema9_gt = ema9[-2] > ema21[-2], ema9[-1] > ema21[-1]
        current_price = round(closes[-1], 2)
        if (not prev_ema9_gt) and curr_ema9_gt and rsi < 70:
            return {'ticker': symbol, 'price': str(current_price), 'action': 'BUY', 'tgt': round(current_price + (2 * atr), 2), 'sl': round(current_price - (1.5 * atr), 2), 'rsi': str(rsi), 'vol_burst': vol_burst}
        elif prev_ema9_gt and (not curr_ema9_gt) and rsi > 30:
            return {'ticker': symbol, 'price': str(current_price), 'action': 'SELL', 'tgt': round(current_price - (2 * atr), 2), 'sl': round(current_price + (1.5 * atr), 2), 'rsi': str(rsi), 'vol_burst': vol_burst}
        return None
    except: return None

def send_message(chat_id, message, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
    if reply_markup: payload['reply_markup'] = json.dumps(reply_markup)
    requests.post(url, json=payload, timeout=10)

def format_alert_message(data):
    now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%H:%M:%S")
    action = data.get('action', '').upper()
    emoji = '🟢' if action == 'BUY' else '🔴'
    burst = '🔥 <b>VOL BURST!</b>' if data.get('vol_burst') else ''
    return (
        f"{emoji} <b>PRO {action}</b> {emoji}\n\n"
        f"📊 <b>Stock:</b> {data.get('ticker')}\n💰 <b>Price:</b> ₹{data.get('price')}\n"
        f"🎯 <b>Tgt:</b> ₹{data.get('tgt')}\n🛑 <b>SL:</b> ₹{data.get('sl')}\n"
        f"📊 <b>RSI:</b> {data.get('rsi')}\n{burst}\n"
        f"🕐 {now} | <a href='{JOIN_LINK}'>Join Channel</a>"
    )

def scan_all_stocks():
    buy_sigs, sell_sigs = [], []
    for s in NSE_STOCKS:
        res = check_stock_pro(s)
        if res:
            res['time'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')
            stocks_data[s] = res
            send_message(TELEGRAM_CHAT_ID, format_alert_message(res))
        time.sleep(0.2)
    for s in CRYPTO_PAIRS:
        res = check_stock_pro(s, True)
        if res:
            stocks_data[s] = res
            send_message(TELEGRAM_CHAT_ID, format_alert_message(res))
        time.sleep(0.2)

def auto_scan_loop():
    IST = pytz.timezone('Asia/Kolkata')
    while True:
        try:
            now = datetime.now(IST)
            if (now.weekday() < 5 and 9 <= now.hour <= 15) or True: # Market + Crypto
                scan_all_stocks()
            time.sleep(1800) # 30 Minutes Automation
        except: time.sleep(60)

# ─────────────────────────────────────────
# UPDATED WEBHOOK HANDLER
# ─────────────────────────────────────────
@app.route('/telegram', methods=['POST'])
def telegram_updates():
    try:
        update = request.get_json()
        if 'message' not in update: return jsonify({'status': 'ok'}), 200
        msg = update['message']
        chat_id, user_id, text = msg['chat']['id'], msg['from']['id'], msg.get('text', '')

        # ADMIN RESTRICTION CHECK
        if not is_admin(chat_id, user_id):
            return jsonify({'status': 'not_admin'}), 200

        if text == '/start':
            send_message(chat_id, f"🤖 <b>Black Devil Pro Max Active!</b>\nHar 30 min me auto-scan ho raha hai.\n\n📢 Join: {JOIN_LINK}", reply_markup=get_main_keyboard())
        elif text == '🧭 Market Trend':
            send_message(chat_id, f"🧭 <b>Market Trend:</b> {check_master_trend()}")
        elif text == '📢 Join Channel':
            send_message(chat_id, f"🚀 <b>Hamaare Premium Channel ko join karein:</b>\n\n{JOIN_LINK}")
        elif text == '📈 BUY Signals':
            # Purana Logic calls
            pass 
        elif text.startswith('/price'):
            # Price Logic calls
            pass
        elif text == '✅ Bot Status':
            send_message(chat_id, "✅ Bot Running: Auto-Scan Every 30 Min.")
        
        return jsonify({'status': 'ok'}), 200
    except: return jsonify({'status': 'error'}), 500

@app.route('/')
def home(): return jsonify({'status': 'Live'})

# Start Thread
threading.Thread(target=auto_scan_loop, daemon=True).start()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
