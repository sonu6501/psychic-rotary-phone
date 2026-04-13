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

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("⚠️ WARNING: Telegram Token या Chat ID set नहीं है!")

alerts_today = []
stocks_data = {}
paper_portfolio = {} # Shadow Paper Trading के लिए

# पुराने पूरे 200 NSE Stocks
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

# 30+ Crypto Pairs
CRYPTO_PAIRS = [
    "BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD","ADA-USD","AVAX-USD",
    "DOGE-USD","DOT-USD","MATIC-USD","LINK-USD","UNI-USD","LTC-USD","BCH-USD",
    "ATOM-USD","XLM-USD","ALGO-USD","VET-USD","FIL-USD","TRX-USD","NEAR-USD",
    "ICP-USD","AAVE-USD","SAND-USD","MANA-USD","AXS-USD","THETA-USD","FTM-USD"
]

# ─────────────────────────────────────────
# NEW UPGRADED KEYBOARD (आसान Buttons)
# ─────────────────────────────────────────
def get_main_keyboard():
    return {
        'keyboard': [
            [{'text': '🔍 Pro Scan'}, {'text': '📊 Price Check'}],
            [{'text': '📈 BUY Signals'}, {'text': '📉 SELL Signals'}],
            [{'text': '🏆 Top Gainers'}, {'text': '💀 Top Losers'}],
            [{'text': '📓 My Portfolio'}, {'text': '🧭 Market Trend'}],
            [{'text': '🔥 All Stocks'}, {'text': '✅ Bot Status'}],
            [{'text': '❓ Help'}]
        ],
        'resize_keyboard': True,
        'persistent': True
    }

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
    high = df['High'].values
    low = df['Low'].values
    close = df['Close'].shift(1).values
    close[0] = low[0]
    tr = np.maximum(high - low, np.maximum(abs(high - close), abs(low - close)))
    atr = pd.Series(tr).rolling(window=period).mean().iloc[-1]
    return round(atr, 2)

def check_master_trend():
    try:
        nifty = yf.Ticker("^NSEI").history(period="5d")
        if len(nifty) >= 2:
            return "📈 BULLISH" if nifty['Close'].iloc[-1] > nifty['Close'].iloc[-2] else "📉 BEARISH"
    except:
        pass
    return "⚖️ NEUTRAL"

# ─────────────────────────────────────────
# CORE SCANNER FUNCTION
# ─────────────────────────────────────────
def check_stock_pro(symbol, is_crypto=False):
    try:
        ticker_sym = symbol if is_crypto else symbol + ".NS"
        ticker     = yf.Ticker(ticker_sym)
        hist       = ticker.history(period="3mo", interval="1d")

        if hist.empty or len(hist) < 25:
            return None

        closes = hist['Close'].tolist()
        volumes = hist['Volume'].tolist()

        ema9  = calculate_ema(closes, 9)
        ema21 = calculate_ema(closes, 21)
        rsi   = calculate_rsi(closes[-15:])
        atr   = calculate_atr(hist)

        # Volume Burst (अगर आज का volume पिछले 10 दिन के average से दोगुना है)
        avg_vol = np.mean(volumes[-11:-1]) if len(volumes) > 10 else 1
        vol_burst = volumes[-1] > (avg_vol * 1.5)

        prev_ema9_gt  = ema9[-2]  > ema21[-2]
        curr_ema9_gt  = ema9[-1]  > ema21[-1]
        current_price = round(closes[-1], 2)

        buy_signal  = (not prev_ema9_gt) and curr_ema9_gt  and rsi < 70
        sell_signal = prev_ema9_gt       and (not curr_ema9_gt) and rsi > 30

        if buy_signal:
            sl = round(current_price - (1.5 * atr), 2)
            tgt = round(current_price + (2 * atr), 2)
            return {'ticker': symbol, 'price': str(current_price), 'action': 'BUY', 'tgt': tgt, 'sl': sl, 'rsi': str(rsi), 'vol_burst': vol_burst}
        elif sell_signal:
            sl = round(current_price + (1.5 * atr), 2)
            tgt = round(current_price - (2 * atr), 2)
            return {'ticker': symbol, 'price': str(current_price), 'action': 'SELL', 'tgt': tgt, 'sl': sl, 'rsi': str(rsi), 'vol_burst': vol_burst}

        return None
    except Exception as e:
        return None

# ─────────────────────────────────────────
# TELEGRAM HELPERS
# ─────────────────────────────────────────
def send_message(chat_id, message, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
    if reply_markup: payload['reply_markup'] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except:
        return None

def format_alert_message(data):
    now    = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%d-%m-%Y %H:%M:%S")
    action = data.get('action', '').upper()
    emoji  = '🟢' if action == 'BUY' else '🔴'
    burst  = '🔥 <b>VOLUME BURST DETECTED!</b>' if data.get('vol_burst') else ''
    
    return (
        f"{emoji} <b>PRO {action} SIGNAL</b> {emoji}\n\n"
        f"📊 <b>Stock:</b>     {data.get('ticker', 'N/A')}\n"
        f"💰 <b>Entry:</b>     ₹{data.get('price', 'N/A')}\n"
        f"🎯 <b>Target:</b>    ₹{data.get('tgt', 'N/A')}\n"
        f"🛑 <b>Stop-Loss:</b> ₹{data.get('sl', 'N/A')}\n"
        f"📊 <b>RSI:</b>       {data.get('rsi', 'N/A')}\n"
        f"{burst}\n"
        f"🕐 {now}\n\n"
        f"💡 <i>Virtual Trade के लिए type करें:</i>\n<code>/vbuy {data.get('ticker')} {data.get('price')}</code>"
    )

def scan_all_stocks():
    send_message(TELEGRAM_CHAT_ID, "🔍 <b>Pro Scan शुरू...</b>\nइसमें थोड़ा समय लगेगा (Market Trend & 230+ Stocks Check हो रहे हैं).")
    
    buy_signals, sell_signals = [], []
    done = 0

    # NSE Scan
    for symbol in NSE_STOCKS:
        res = check_stock_pro(symbol, is_crypto=False)
        if res:
            res['time'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')
            alerts_today.append(res)
            stocks_data[symbol] = res
            if res['action'] == 'BUY': buy_signals.append(res)
            else: sell_signals.append(res)
            send_message(TELEGRAM_CHAT_ID, format_alert_message(res))
        time.sleep(0.2) 

    # Crypto Scan
    for symbol in CRYPTO_PAIRS:
        res = check_stock_pro(symbol, is_crypto=True)
        if res:
            res['time'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')
            alerts_today.append(res)
            stocks_data[symbol] = res
            if res['action'] == 'BUY': buy_signals.append(res)
            else: sell_signals.append(res)
            send_message(TELEGRAM_CHAT_ID, format_alert_message(res))
        time.sleep(0.2)

    summary = (
        f"✅ <b>Scan Complete!</b>\n\n"
        f"📈 BUY Signals:  {len(buy_signals)}\n"
        f"📉 SELL Signals: {len(sell_signals)}\n"
    )
    send_message(TELEGRAM_CHAT_ID, summary)

def auto_scan_loop():
    IST = pytz.timezone('Asia/Kolkata')
    while True:
        try:
            now = datetime.now(IST)
            if now.weekday() < 5 and 9 <= now.hour <= 15:
                scan_all_stocks()
            else:
                scan_all_stocks() # Off-market crypto check
            time.sleep(3600)
        except Exception as e:
            time.sleep(60)

# ─────────────────────────────────────────
# OLD FEATURES + NEW BUTTON HANDLERS
# ─────────────────────────────────────────
def handle_allstocks(chat_id, filter_action=None):
    if not stocks_data:
        send_message(chat_id, "🔥 कोई active stock नहीं है। Pro Scan करें!")
        return
    filtered = {k: v for k, v in stocks_data.items() if (v.get('action','').upper() == filter_action.upper() if filter_action else True)}
    title = f"🔥 <b>Active Stocks ({len(filtered)}):</b>\n\n"
    if filter_action: title = f"<b>{filter_action} Stocks ({len(filtered)}):</b>\n\n"

    if not filtered:
        send_message(chat_id, f"❌ कोई {filter_action} stock नहीं मिला।")
        return

    message, count, msgs = title, 0, []
    for ticker, data in filtered.items():
        em = '🟢' if data.get('action') == 'BUY' else '🔴'
        message += f"{em} <b>{ticker}</b> @ ₹{data.get('price')} | Tgt: {data.get('tgt')}\n"
        count += 1
        if count % 30 == 0:
            msgs.append(message)
            message = "<b>...continued:</b>\n\n"
    msgs.append(message)
    for m in msgs: send_message(chat_id, m)

def handle_gainers_losers(chat_id, mode='gainers'):
    send_message(chat_id, "📡 Data आ रहा है... थोड़ा wait करो!")
    try:
        results = []
        for symbol in NSE_STOCKS[:30]: # Fast check on top 30
            try:
                hist = yf.Ticker(symbol + ".NS").history(period="2d", interval="1d")
                if len(hist) >= 2:
                    prev, curr = hist['Close'].iloc[-2], hist['Close'].iloc[-1]
                    chng = round(((curr - prev) / prev) * 100, 2) if prev else 0
                    results.append((symbol, round(curr, 2), chng))
            except: pass
            time.sleep(0.1)
        results.sort(key=lambda x: x[2], reverse=(mode == 'gainers'))
        msg = ("🏆 <b>Top Gainers:</b>\n\n" if mode == 'gainers' else "💀 <b>Top Losers:</b>\n\n")
        for i, (sym, price, chng) in enumerate(results[:10], 1):
            sign, em = ("+" if chng >= 0 else ""), ("📈" if chng >= 0 else "📉")
            msg += f"{i}. {em} <b>{sym}</b> ₹{price} ({sign}{chng}%)\n"
        send_message(chat_id, msg)
    except:
        send_message(chat_id, "❌ Error fetching gainers/losers.")

def handle_price(chat_id, text):
    parts = text.strip().split()
    if len(parts) < 2:
        send_message(chat_id, "⚠️ Symbol बताओ!\n\nExample: <code>/price RELIANCE</code>")
        return
    symbol = parts[1].upper()
    try:
        info = yf.Ticker(symbol + ".NS").history(period="5d", interval="1m")
        if info.empty: info = yf.Ticker(symbol).history(period="5d", interval="1m")
        if not info.empty and len(info) >= 2:
            price, prev_close = round(info['Close'].iloc[-1], 2), round(info['Close'].iloc[-2], 2)
            change = round(price - prev_close, 2)
            pct = round((change / prev_close) * 100, 2)
            send_message(chat_id, f"💰 <b>{symbol} Price:</b> ₹{price}\n📊 <b>Change:</b> {change} ({pct}%)")
        else: send_message(chat_id, f"❌ <b>{symbol}</b> नहीं मिला!")
    except: send_message(chat_id, "❌ Error.")

# ─────────────────────────────────────────
# ROUTES & WEBHOOKS
# ─────────────────────────────────────────
@app.route('/telegram', methods=['POST'])
def telegram_updates():
    try:
        update = request.get_json()
        if 'message' not in update: return jsonify({'status': 'ok'}), 200
        msg        = update['message']
        chat_id    = msg['chat']['id']
        text       = msg.get('text', '')
        first_name = msg.get('from', {}).get('first_name', 'Boss')

        # Command & Button Logic
        if text.startswith('/start'):
            send_message(chat_id, f"🤖 <b>Welcome {first_name}! Black Devil Pro Max Active.</b>\nनीचे दिए गए Menu Buttons का यूज़ करें👇", reply_markup=get_main_keyboard())
        elif text == '🔍 Pro Scan' or text == '/scan':
            threading.Thread(target=scan_all_stocks).start()
        elif text == '📊 Price Check':
            send_message(chat_id, "📊 किस stock का price चाहिए?\n\nलिखें: <code>/price RELIANCE</code>")
        elif text.startswith('/price'):
            handle_price(chat_id, text)
        elif text == '📈 BUY Signals' or text == '/buy':
            handle_allstocks(chat_id, 'BUY')
        elif text == '📉 SELL Signals' or text == '/sell':
            handle_allstocks(chat_id, 'SELL')
        elif text == '🔥 All Stocks' or text == '/allstocks':
            handle_allstocks(chat_id)
        elif text == '🏆 Top Gainers' or text == '/gainers':
            handle_gainers_losers(chat_id, 'gainers')
        elif text == '💀 Top Losers' or text == '/losers':
            handle_gainers_losers(chat_id, 'losers')
        elif text == '🧭 Market Trend':
            send_message(chat_id, f"🧭 <b>Nifty 50 Master Trend:</b>\n\n{check_master_trend()}")
        elif text == '📓 My Portfolio' or text == '/portfolio':
            if not paper_portfolio:
                send_message(chat_id, "📓 Portfolio अभी खाली है!\n\nनया Trade add करने के लिए लिखें:\n<code>/vbuy TATASTEEL 150</code>")
            else:
                p_msg = "📓 <b>Your Virtual Portfolio:</b>\n\n"
                for s, d in paper_portfolio.items():
                    p_msg += f"🔹 <b>{s}</b> | Buy Price: ₹{d['entry']} | Time: {d['time']}\n"
                send_message(chat_id, p_msg)
        elif text.startswith('/vbuy'):
            parts = text.split()
            if len(parts) >= 3:
                sym, price = parts[1].upper(), parts[2]
                paper_portfolio[sym] = {'entry': float(price), 'time': datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')}
                send_message(chat_id, f"✅ <b>Virtual Trade Saved!</b>\nBought {sym} at ₹{price}")
            else: send_message(chat_id, "सही तरीका: <code>/vbuy RELIANCE 2500</code>")
        elif text == '✅ Bot Status' or text == '/status':
            now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M:%S')
            send_message(chat_id, f"✅ <b>Status: PRO MAX ACTIVE</b>\n\n🟢 Total Alerts: {len(alerts_today)}\n🕐 Time: {now}")
        elif text == '❓ Help' or text == '/help':
            send_message(chat_id, "💡 <b>Help Menu:</b>\nनीचे दिए गए Buttons पर click करें या / commands का यूज़ करें।")
            
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'status': 'error'}), 500

@app.route('/')
def home():
    return jsonify({'status': 'Black Devil Pro Max is Live!'})

# Start Scanner Thread
scanner_thread = threading.Thread(target=auto_scan_loop)
scanner_thread.daemon = True
scanner_thread.start()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
