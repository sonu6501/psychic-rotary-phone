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
CHANNEL_LINK = "https://t.me/+vK7WE4K6T3U2ODc1"

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("⚠️ WARNING: Telegram Token ya Chat ID set nahi hai!")

alerts_today = []
stocks_data = {}

# NSE Top 200 Stocks
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

# Crypto Pairs
CRYPTO_PAIRS = [
    "BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD",
    "ADA-USD","AVAX-USD","DOGE-USD","DOT-USD","MATIC-USD"
]

def send_message(chat_id, message, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Telegram error: {e}")
        return None

# HTML-safe message chunker 4-5 page support ke liye
def send_long_message(chat_id, text):
    lines = text.split('\n')
    msg = ""
    for line in lines:
        # Check if adding this line exceeds the 4000 char limit
        if len(msg) + len(line) + 1 > 3900:
            send_message(chat_id, msg)
            msg = line + "\n"
        else:
            msg += line + "\n"
    if msg.strip():
        send_message(chat_id, msg)

def get_main_keyboard():
    return {
        'keyboard': [
            [{'text': '📊 Price Check'},    {'text': '🔥 All Active Stocks'}],
            [{'text': '📈 All BUY Stocks'}, {'text': '📉 All SELL Stocks'}],
            [{'text': '📋 Aaj Ke Alerts'},  {'text': '⏮ Last Alert'}],
            [{'text': '🏆 Top Gainers'},     {'text': '💀 Top Losers'}],
            [{'text': '✅ Bot Status'},      {'text': '❓ Help'}]
        ],
        'resize_keyboard': True,
        'persistent': True
    }

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

        # Ab koi stock skip nahi hoga, sabhi ka data return hoga
        if buy_signal:
            action = 'BUY'
        elif sell_signal:
            action = 'SELL'
        else:
            action = 'NEUTRAL'

        return {'ticker': symbol, 'price': str(current_price), 'action': action,  'timeframe': '1D', 'rsi': str(rsi), 'strategy': 'EMA9x21+RSI'}

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
        emoji       = '🔸'
        action_text = '📊 STOCK UPDATE'
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

def scan_all_stocks():
    print("🔍 Scanning started...")
    send_message(TELEGRAM_CHAT_ID, "🔍 <b>Scanning shuru hua...</b>\nSaare NSE + Crypto stocks check ho rahe hain!")

    buy_signals  = []
    sell_signals = []
    total        = len(NSE_STOCKS) + len(CRYPTO_PAIRS)
    done         = 0

    # NSE Stocks scan
    for symbol in NSE_STOCKS:
        result = check_stock(symbol, is_crypto=False)
        if result:
            result['time'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')
            stocks_data[symbol] = result # Sabhi stocks ko list me add karo
            if result['action'] == 'BUY':
                buy_signals.append(result)
                alerts_today.append(result)
            elif result['action'] == 'SELL':
                sell_signals.append(result)
                alerts_today.append(result)
        done += 1
        time.sleep(0.2)  # Rate limit avoid karo

    # Crypto scan
    for symbol in CRYPTO_PAIRS:
        result = check_stock(symbol, is_crypto=True)
        if result:
            result['time'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')
            stocks_data[symbol] = result # Sabhi stocks ko list me add karo
            if result['action'] == 'BUY':
                buy_signals.append(result)
                alerts_today.append(result)
            elif result['action'] == 'SELL':
                sell_signals.append(result)
                alerts_today.append(result)
        done += 1
        time.sleep(0.2)

    # Summary bhejo
    summary = (
        f"✅ <b>Scan Complete!</b>\n\n"
        f"📊 Total Checked: {total}\n"
        f"📈 BUY Signals:  {len(buy_signals)}\n"
        f"📉 SELL Signals: {len(sell_signals)}\n"
        f"🕐 Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M')}\n"
        f"🔗 <b>Join Our Channel:</b> <a href='{CHANNEL_LINK}'>Click Here To Join</a>\n\n"
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
        summary += "\n"

    # Yaha saare stocks ki price list hogi taaki aap 4-5 pages me sab dekh sakein
    summary += "📋 <b>Sare Scanned Stocks Ki Price List:</b>\n\n"
    for ticker, data in stocks_data.items():
        em = '🟢' if data['action'] == 'BUY' else '🔴' if data['action'] == 'SELL' else '🔸'
        summary += f"{em} <b>{ticker}</b> : ₹{data['price']} | RSI: {data['rsi']}\n"

    if not buy_signals and not sell_signals:
        summary += "\n😴 Koi naya BUY/SELL signal nahi mila abhi."

    # Send using long message helper function (ye HTML tags ko nahi todega)
    send_long_message(TELEGRAM_CHAT_ID, summary)
    print("✅ Scan complete!")

def auto_scan_loop():
    IST = pytz.timezone('Asia/Kolkata')
    while True:
        try:
            now = datetime.now(IST)
            # Weekdays 9am-4pm (9:00 to 16:59) scan karo har 15 minute
            if now.weekday() < 5 and 9 <= now.hour <= 16:
                scan_all_stocks()
            else:
                # Crypto 24/7 scan ke liye abhi yahi call rakha hai
                scan_all_stocks()
            time.sleep(900)  # 15 ghanta (900 Seconds = 15 Minutes)
        except Exception as e:
            print(f"Auto scan error: {e}")
            time.sleep(60)

# ─────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────

def handle_start(chat_id, first_name):
    message = (
        f"🤖 <b>Namaste {first_name}! Black Devil Trading Bot</b>\n\n"
        f"Main har 15 minute NSE + Crypto scan karta hoon!\n\n"
        f"<b>Commands:</b>\n"
        f"/scan — Abhi scan karo\n"
        f"/price RELIANCE — Live price\n"
        f"/allstocks — Active stocks\n"
        f"/buy — BUY signals\n"
        f"/sell — SELL signals\n"
        f"/gainers — Top gainers\n"
        f"/losers — Top losers\n"
        f"/alerts — Aaj ke alerts\n"
        f"/status — Bot status\n\n"
        f"🔗 <b>Join Our Channel:</b> <a href='{CHANNEL_LINK}'>Click Here</a>\n\n"
        f"<i>👇 Buttons se bhi use karo!</i>"
    )
    send_message(chat_id, message, reply_markup=get_main_keyboard())

def handle_help(chat_id):
    message = (
        "❓ <b>Sabhi Commands:</b>\n\n"
        "🔍 /scan — Abhi saare stocks scan karo\n"
        "📊 /price RELIANCE — Live price\n"
        "🔥 /allstocks — Active stocks\n"
        "📈 /buy — BUY signals\n"
        "📉 /sell — SELL signals\n"
        "🏆 /gainers — Top gainers\n"
        "💀 /losers — Top losers\n"
        "📋 /alerts — Aaj ke alerts\n"
        "⏮ /last — Last alert\n"
        "✅ /status — Bot stats\n"
        f"🔗 <b>Join Channel:</b> <a href='{CHANNEL_LINK}'>Click Here</a>\n"
    )
    send_message(chat_id, message, reply_markup=get_main_keyboard())

def handle_status(chat_id):
    now        = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M:%S')
    buy_count  = sum(1 for s in stocks_data.values() if s.get('action','').upper() == 'BUY')
    sell_count = sum(1 for s in stocks_data.values() if s.get('action','').upper() == 'SELL')
    message = (
        f"✅ <b>Bot Status: ACTIVE</b>\n\n"
        f"🟢 Server:  Running\n"
        f"🟢 Scanner: Active (har 15 minute)\n"
        f"🟢 Telegram: Connected\n\n"
        f"📊 <b>Aaj Ki Stats:</b>\n"
        f"🔔 Total Alerts:  {len(alerts_today)}\n"
        f"📈 BUY Signals:   {buy_count}\n"
        f"📉 SELL Signals:  {sell_count}\n"
        f"🔥 Scanned Stocks: {len(stocks_data)}\n\n"
        f"🕐 Time: {now}"
    )
    send_message(chat_id, message, reply_markup=get_main_keyboard())

def handle_price(chat_id, text):
    parts = text.strip().split()
    if len(parts) < 2:
        send_message(chat_id, "⚠️ Symbol batao!\n\nExample: <code>/price RELIANCE</code>")
        return
    symbol = parts[1].upper()
    send_message(chat_id, f"🔍 <b>{symbol}</b> ka price fetch ho raha hai...")
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
            send_message(chat_id, f"❌ <b>{symbol}</b> ka data nahi mila!")
    except Exception as e:
        send_message(chat_id, f"❌ Error: {str(e)}")

def handle_alerts(chat_id):
    if not alerts_today:
        send_message(chat_id, "📋 Aaj abhi tak koi BUY/SELL alert nahi aaya.\n\n/scan karo!")
        return
    message = f"📋 <b>Aaj Ke Alerts ({len(alerts_today)}):</b>\n\n"
    for alert in alerts_today[-15:]:
        action  = alert.get('action', 'N/A').upper()
        emoji   = '🟢' if action == 'BUY' else '🔴'
        message += f"{emoji} <b>{alert.get('ticker','?')}</b> — {action} @ ₹{alert.get('price','?')} | {alert.get('time','')}\n"
    send_message(chat_id, message)

def handle_last(chat_id):
    if not alerts_today:
        send_message(chat_id, "📋 Abhi tak koi alert nahi aaya.\n\n/scan karo!")
        return
    send_message(chat_id, format_alert_message(alerts_today[-1]))

def handle_allstocks(chat_id, filter_action=None):
    if not stocks_data:
        send_message(chat_id, "🔥 Koi active stock nahi hai.\n\n/scan likho — abhi scan karunga!")
        return
    if filter_action:
        filtered = {k: v for k, v in stocks_data.items() if v.get('action','').upper() == filter_action.upper()}
        emoji    = '📈' if filter_action == 'BUY' else '📉'
        title    = f"{emoji} <b>{filter_action} Stocks ({len(filtered)}):</b>\n\n"
    else:
        filtered = stocks_data
        title    = f"🔥 <b>All Scanned Stocks ({len(filtered)}):</b>\n\n"

    if not filtered:
        send_message(chat_id, f"❌ Koi {filter_action} stock nahi mila.\n\n/scan karo!")
        return

    message = title
    for ticker, data in filtered.items():
        action  = data.get('action','N/A').upper()
        price   = data.get('price','N/A')
        rsi     = data.get('rsi','N/A')
        t       = data.get('time','N/A')
        em      = '🟢' if action == 'BUY' else '🔴' if action == 'SELL' else '🔸'
        message += f"{em} <b>{ticker}</b> @ ₹{price} | RSI:{rsi} | {t}\n"
    
    # Ye helper HTML format me lambi lists ko safely 4-5 pages me bhej dega
    send_long_message(chat_id, message)

def handle_gainers_losers(chat_id, mode='gainers'):
    send_message(chat_id, "📡 Data fetch ho raha hai... thoda wait karo!")
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
    if text == '📊 Price Check':
        send_message(chat_id, "📊 Kaunse stock ka price chahiye?\n\nLikho: <code>/price RELIANCE</code>")
    elif text == '🔥 All Active Stocks':
        handle_allstocks(chat_id)
    elif text == '📈 All BUY Stocks':
        handle_allstocks(chat_id, filter_action='BUY')
    elif text == '📉 All SELL Stocks':
        handle_allstocks(chat_id, filter_action='SELL')
    elif text == '📋 Aaj Ke Alerts':
        handle_alerts(chat_id)
    elif text == '⏮ Last Alert':
        handle_last(chat_id)
    elif text == '🏆 Top Gainers':
        handle_gainers_losers(chat_id, mode='gainers')
    elif text == '💀 Top Losers':
        handle_gainers_losers(chat_id, mode='losers')
    elif text == '✅ Bot Status':
        handle_status(chat_id)
    elif text == '❓ Help':
        handle_help(chat_id)
    else:
        send_message(chat_id, "❓ /help likho!", reply_markup=get_main_keyboard())

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@app.route('/')
def home():
    return jsonify({'status': '✅ Black Devil Bot Running!'})

@app.route('/test', methods=['GET'])
def test():
    result = send_message(TELEGRAM_CHAT_ID, "✅ <b>Bot Test Successful!</b>\n\nBlack Devil Trading Bot active hai!")
    if result and result.get('ok'):
        return jsonify({'status': 'Test sent ✅'})
    return jsonify({'status': 'Failed ❌'})

@app.route('/scan_now', methods=['GET'])
def scan_now():
    thread = threading.Thread(target=scan_all_stocks)
    thread.daemon = True
    thread.start()
    return jsonify({'status': '✅ Scan shuru ho gaya! Telegram check karo.'})

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        if request.is_json:
            data = request.get_json()
        else:
            raw = request.data.decode('utf-8')
            try:
                data = json.loads(raw)
            except:
                data = {'ticker': 'UNKNOWN', 'action': 'ALERT'}
        data['time'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')
        
        # Only alert me daalein agar BUY/SELL ho, taaki spam na ho
        if data.get('action', '').upper() in ['BUY', 'SELL']:
            alerts_today.append(data)
            
        ticker = data.get('ticker', 'UNKNOWN')
        stocks_data[ticker] = data
        message = format_alert_message(data)
        result  = send_message(TELEGRAM_CHAT_ID, message)
        if result and result.get('ok'):
            return jsonify({'status': 'success'}), 200
        return jsonify({'status': 'error'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

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

        if text.startswith('/start'):
            handle_start(chat_id, first_name)
        elif text.startswith('/help'):
            handle_help(chat_id)
        elif text.startswith('/price'):
            handle_price(chat_id, text)
        elif text.startswith('/scan'):
            send_message(chat_id, "🔍 Scan shuru ho raha hai... isme 2-3 minute lagenge!")
            thread = threading.Thread(target=scan_all_stocks)
            thread.daemon = True
            thread.start()
        elif text.startswith('/alerts'):
            handle_alerts(chat_id)
        elif text.startswith('/last'):
            handle_last(chat_id)
        elif text.startswith('/status'):
            handle_status(chat_id)
        elif text.startswith('/allstocks'):
            handle_allstocks(chat_id)
        elif text.startswith('/buy'):
            handle_allstocks(chat_id, filter_action='BUY')
        elif text.startswith('/sell'):
            handle_allstocks(chat_id, filter_action='SELL')
        elif text.startswith('/gainers'):
            handle_gainers_losers(chat_id, mode='gainers')
        elif text.startswith('/losers'):
            handle_gainers_losers(chat_id, mode='losers')
        else:
            handle_button(chat_id, text, first_name)

        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    render_url = request.args.get('url', '')
    if not render_url:
        return jsonify({'error': 'URL chahiye'}), 400
    webhook_url = f"{render_url}/telegram"
    api_url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}"
    response    = requests.get(api_url)
    result      = response.json()
    if result.get('ok'):
        return jsonify({'status': '✅ Webhook set!', 'url': webhook_url})
    return jsonify({'status': '❌ Failed', 'error': result})

# Auto scan start karo
scanner_thread = threading.Thread(target=auto_scan_loop)
scanner_thread.daemon = True
scanner_thread.start()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
