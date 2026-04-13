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
PORTFOLIO_FILE = "portfolio.json"

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

CRYPTO_PAIRS = [
    "BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD",
    "ADA-USD","AVAX-USD","DOGE-USD","DOT-USD","MATIC-USD"
]

# ─────────────────────────────────────────
# PAPER TRADING DATABASE FUNCTIONS
# ─────────────────────────────────────────

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_portfolio(data):
    try:
        with open(PORTFOLIO_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"File save error: {e}")

def get_user_portfolio(user_id):
    data = load_portfolio()
    if str(user_id) not in data:
        # Naye user ko ₹1,00,000 ka virtual balance do
        data[str(user_id)] = {"balance": 100000.0, "holdings": {}}
        save_portfolio(data)
    return data[str(user_id)], data

def get_live_price(symbol, is_crypto=False):
    try:
        ticker_sym = symbol if is_crypto else symbol + ".NS"
        ticker = yf.Ticker(ticker_sym)
        info = ticker.history(period="1d", interval="1m")
        if info.empty and not is_crypto:
            ticker = yf.Ticker(symbol)
            info = ticker.history(period="1d", interval="1m")
        if not info.empty:
            return round(info['Close'].iloc[-1], 2)
    except:
        pass
    return None

# ─────────────────────────────────────────
# CORE BOT FUNCTIONS
# ─────────────────────────────────────────

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

def send_long_message(chat_id, text):
    lines = text.split('\n')
    msg = ""
    for line in lines:
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
            [{'text': '💼 My Portfolio'},   {'text': '📋 Aaj Ke Alerts'}],
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

        if buy_signal: action = 'BUY'
        elif sell_signal: action = 'SELL'
        else: action = 'NEUTRAL'

        return {'ticker': symbol, 'price': str(current_price), 'action': action,  'timeframe': '1D', 'rsi': str(rsi), 'strategy': 'EMA9x21+RSI'}
    except Exception as e:
        return None

def format_alert_message(data):
    now    = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%d-%m-%Y %H:%M:%S")
    action = data.get('action', '').upper()
    if action == 'BUY':
        emoji = '🟢'
        action_text = '📈 BUY SIGNAL'
    elif action == 'SELL':
        emoji = '🔴'
        action_text = '📉 SELL SIGNAL'
    else:
        emoji = '🔸'
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

    for symbol in NSE_STOCKS:
        result = check_stock(symbol, is_crypto=False)
        if result:
            result['time'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')
            stocks_data[symbol] = result
            if result['action'] == 'BUY':
                buy_signals.append(result)
                alerts_today.append(result)
            elif result['action'] == 'SELL':
                sell_signals.append(result)
                alerts_today.append(result)
        time.sleep(0.2)

    for symbol in CRYPTO_PAIRS:
        result = check_stock(symbol, is_crypto=True)
        if result:
            result['time'] = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M')
            stocks_data[symbol] = result
            if result['action'] == 'BUY':
                buy_signals.append(result)
                alerts_today.append(result)
            elif result['action'] == 'SELL':
                sell_signals.append(result)
                alerts_today.append(result)
        time.sleep(0.2)

    summary = (
        f"✅ <b>Scan Complete!</b>\n\n"
        f"📊 Total Checked: {total}\n"
        f"📈 BUY Signals:  {len(buy_signals)}\n"
        f"📉 SELL Signals: {len(sell_signals)}\n"
        f"🕐 Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M')}\n"
        f"🔗 <b>Join Our Channel:</b> <a href='{CHANNEL_LINK}'>Click Here</a>\n\n"
    )

    if buy_signals:
        summary += "🟢 <b>BUY Stocks:</b>\n"
        for s in buy_signals: summary += f"📈 <b>{s['ticker']}</b> @ ₹{s['price']} | RSI: {s['rsi']}\n"
        summary += "\n"

    if sell_signals:
        summary += "🔴 <b>SELL Stocks:</b>\n"
        for s in sell_signals: summary += f"📉 <b>{s['ticker']}</b> @ ₹{s['price']} | RSI: {s['rsi']}\n"
        summary += "\n"

    summary += "📋 <b>Sare Scanned Stocks Ki Price List:</b>\n\n"
    for ticker, data in stocks_data.items():
        em = '🟢' if data['action'] == 'BUY' else '🔴' if data['action'] == 'SELL' else '🔸'
        summary += f"{em} <b>{ticker}</b> : ₹{data['price']} | RSI: {data['rsi']}\n"

    send_long_message(TELEGRAM_CHAT_ID, summary)

def auto_scan_loop():
    IST = pytz.timezone('Asia/Kolkata')
    while True:
        try:
            now = datetime.now(IST)
            if now.weekday() < 5 and 9 <= now.hour <= 16:
                scan_all_stocks()
            else:
                scan_all_stocks()
            time.sleep(900)  # Har 15 minute me
        except Exception as e:
            time.sleep(60)

# ─────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────

def handle_start(chat_id, first_name):
    message = (
        f"🤖 <b>Namaste {first_name}! Black Devil Trading Bot</b>\n\n"
        f"Main har 15 minute NSE + Crypto scan karta hoon! Ab isme <b>Paper Trading</b> bhi add ho gaya hai.\n\n"
        f"<b>Trading Commands:</b>\n"
        f"💵 /paperbuy RELIANCE 10 — Stock kharido\n"
        f"💴 /papersell RELIANCE 10 — Stock becho\n"
        f"💼 /portfolio — Apna P&L aur holdings dekho\n\n"
        f"<b>Scanner Commands:</b>\n"
        f"/scan — Abhi scan karo\n"
        f"/price RELIANCE — Live price\n"
        f"/allstocks — Active stocks\n"
        f"/buy — BUY signals\n"
        f"/sell — SELL signals\n\n"
        f"🔗 <b>Join Our Channel:</b> <a href='{CHANNEL_LINK}'>Click Here</a>"
    )
    send_message(chat_id, message, reply_markup=get_main_keyboard())

def handle_help(chat_id):
    handle_start(chat_id, "Friend")

# ----- PAPER TRADING HANDLERS -----

def handle_paperbuy(chat_id, text):
    parts = text.strip().split()
    if len(parts) != 3:
        send_message(chat_id, "⚠️ <b>Sahi format use karo!</b>\nExample: <code>/paperbuy RELIANCE 10</code>")
        return
    
    symbol = parts[1].upper()
    try:
        qty = int(parts[2])
        if qty <= 0: raise ValueError
    except:
        send_message(chat_id, "⚠️ Quantity hamesha number me likho (jaise 10, 50).")
        return

    send_message(chat_id, f"🔍 <b>{symbol}</b> ka live price check kar raha hu...")
    price = get_live_price(symbol, is_crypto=("-USD" in symbol))
    
    if not price:
        send_message(chat_id, f"❌ <b>{symbol}</b> ka data nahi mila! Spelling check karo.")
        return

    total_cost = round(price * qty, 2)
    user_pf, all_data = get_user_portfolio(chat_id)

    if user_pf["balance"] < total_cost:
        send_message(chat_id, f"❌ <b>Balance Kam Hai!</b>\n\n💰 Available: ₹{round(user_pf['balance'], 2)}\n📉 Required: ₹{total_cost}")
        return

    # Deduct Balance
    user_pf["balance"] -= total_cost

    # Add to Holdings
    if symbol in user_pf["holdings"]:
        old_qty = user_pf["holdings"][symbol]["qty"]
        old_avg = user_pf["holdings"][symbol]["avg_price"]
        new_qty = old_qty + qty
        new_avg = ((old_qty * old_avg) + (qty * price)) / new_qty
        user_pf["holdings"][symbol] = {"qty": new_qty, "avg_price": round(new_avg, 2)}
    else:
        user_pf["holdings"][symbol] = {"qty": qty, "avg_price": price}

    all_data[str(chat_id)] = user_pf
    save_portfolio(all_data)

    msg = (
        f"✅ <b>PAPER BUY SUCCESSFUL</b>\n\n"
        f"📊 Stock: <b>{symbol}</b>\n"
        f"📦 Qty: {qty}\n"
        f"💰 Buy Price: ₹{price}\n"
        f"💸 Total Investment: ₹{total_cost}\n\n"
        f"💳 Remaining Balance: ₹{round(user_pf['balance'], 2)}\n\n"
        f"<i>Check: /portfolio</i>"
    )
    send_message(chat_id, msg)

def handle_papersell(chat_id, text):
    parts = text.strip().split()
    if len(parts) != 3:
        send_message(chat_id, "⚠️ <b>Sahi format use karo!</b>\nExample: <code>/papersell RELIANCE 10</code>")
        return
    
    symbol = parts[1].upper()
    try:
        qty = int(parts[2])
        if qty <= 0: raise ValueError
    except:
        send_message(chat_id, "⚠️ Quantity hamesha number me likho (jaise 10, 50).")
        return

    user_pf, all_data = get_user_portfolio(chat_id)

    if symbol not in user_pf["holdings"] or user_pf["holdings"][symbol]["qty"] < qty:
        send_message(chat_id, f"❌ Aapke paas <b>{symbol}</b> ke itne shares nahi hain!\nCheck: /portfolio")
        return

    send_message(chat_id, f"🔍 <b>{symbol}</b> ka live market price fetch ho raha hai...")
    price = get_live_price(symbol, is_crypto=("-USD" in symbol))
    
    if not price:
        send_message(chat_id, f"❌ Live price fetch karne me error aayi. Thodi der baad try karo.")
        return

    total_earn = round(price * qty, 2)
    buy_avg = user_pf["holdings"][symbol]["avg_price"]
    profit_loss = round(total_earn - (buy_avg * qty), 2)
    
    em = "🟢 PROFIT" if profit_loss >= 0 else "🔴 LOSS"
    sign = "+" if profit_loss >= 0 else ""

    # Update Balance & Holdings
    user_pf["balance"] += total_earn
    user_pf["holdings"][symbol]["qty"] -= qty
    
    if user_pf["holdings"][symbol]["qty"] == 0:
        del user_pf["holdings"][symbol]

    all_data[str(chat_id)] = user_pf
    save_portfolio(all_data)

    msg = (
        f"✅ <b>PAPER SELL SUCCESSFUL</b>\n\n"
        f"📊 Stock: <b>{symbol}</b>\n"
        f"📦 Qty Sold: {qty}\n"
        f"💰 Sell Price: ₹{price}\n\n"
        f"📝 <b>Trade Result:</b>\n"
        f"{em}: ₹{sign}{profit_loss}\n\n"
        f"💳 New Balance: ₹{round(user_pf['balance'], 2)}"
    )
    send_message(chat_id, msg)

def handle_portfolio(chat_id):
    user_pf, _ = get_user_portfolio(chat_id)
    holdings = user_pf.get("holdings", {})
    
    if not holdings:
        send_message(chat_id, f"💼 <b>My Portfolio:</b>\n\n💳 Cash Balance: ₹{round(user_pf['balance'], 2)}\n\nAapne abhi tak koi stock nahi kharida hai.\nKharidne ke liye likhein: <code>/paperbuy RELIANCE 10</code>")
        return

    send_message(chat_id, "⏳ <b>Portfolio Calculate ho raha hai...</b>\nLive market prices check kiye jaa rahe hain, please wait!")
    
    msg = f"💼 <b>LIVE PORTFOLIO</b>\n\n💳 Cash Balance: ₹{round(user_pf['balance'], 2)}\n\n"
    total_invested = 0
    total_current = 0

    for symbol, data in holdings.items():
        qty = data["qty"]
        avg_price = data["avg_price"]
        invested = qty * avg_price
        total_invested += invested
        
        live_price = get_live_price(symbol, is_crypto=("-USD" in symbol))
        if live_price:
            current_val = live_price * qty
            total_current += current_val
            pnl = round(current_val - invested, 2)
            pnl_pct = round((pnl / invested) * 100, 2)
            em = "🟢" if pnl >= 0 else "🔴"
            sign = "+" if pnl >= 0 else ""
            msg += f"<b>{symbol}</b> ({qty} Qty)\n"
            msg += f"🔹 Avg: ₹{avg_price} | Live: ₹{live_price}\n"
            msg += f"🔹 {em} P&L: {sign}₹{pnl} ({sign}{pnl_pct}%)\n\n"
        else:
            total_current += invested # Agar live price nahi mila toh error na aaye
            msg += f"<b>{symbol}</b> ({qty} Qty)\n🔹 Avg: ₹{avg_price} | Live: N/A\n\n"

    overall_pnl = round(total_current - total_invested, 2)
    overall_pnl_pct = round((overall_pnl / total_invested) * 100, 2) if total_invested > 0 else 0
    over_em = "🟢" if overall_pnl >= 0 else "🔴"
    over_sign = "+" if overall_pnl >= 0 else ""

    msg += f"───────────────\n"
    msg += f"💵 Total Invested: ₹{round(total_invested, 2)}\n"
    msg += f"💴 Current Value: ₹{round(total_current, 2)}\n"
    msg += f"📊 <b>Total P&L:</b> {over_em} {over_sign}₹{overall_pnl} ({over_sign}{overall_pnl_pct}%)"
    
    send_long_message(chat_id, msg)

# ----- OTHERS -----

def handle_status(chat_id):
    now        = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M:%S')
    message = (
        f"✅ <b>Bot Status: ACTIVE</b>\n\n"
        f"🟢 Server:  Running\n"
        f"🟢 Scanner: Active (har 15 minute)\n"
        f"🟢 Paper Trade: Active\n\n"
        f"🕐 Time: {now}"
    )
    send_message(chat_id, message, reply_markup=get_main_keyboard())

def handle_price(chat_id, text):
    parts = text.strip().split()
    if len(parts) < 2:
        send_message(chat_id, "⚠️ Symbol batao!\n\nExample: <code>/price RELIANCE</code>")
        return
    symbol = parts[1].upper()
    price = get_live_price(symbol, is_crypto=("-USD" in symbol))
    if price:
        send_message(chat_id, f"📈 <b>{symbol}</b>\n💰 <b>Live Price:</b> ₹{price}")
    else:
        send_message(chat_id, f"❌ <b>{symbol}</b> ka data nahi mila!")

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

    message = title
    for ticker, data in filtered.items():
        action  = data.get('action','N/A').upper()
        price   = data.get('price','N/A')
        rsi     = data.get('rsi','N/A')
        em      = '🟢' if action == 'BUY' else '🔴' if action == 'SELL' else '🔸'
        message += f"{em} <b>{ticker}</b> @ ₹{price} | RSI:{rsi}\n"
    
    send_long_message(chat_id, message)

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
    elif text == '💼 My Portfolio':
        handle_portfolio(chat_id)
    elif text == '✅ Bot Status':
        handle_status(chat_id)
    elif text == '❓ Help':
        handle_help(chat_id)
    else:
        send_message(chat_id, "❓ Samajh nahi aaya. /help likho!", reply_markup=get_main_keyboard())

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@app.route('/')
def home():
    return jsonify({'status': '✅ Black Devil Bot with Paper Trading Running!'})

@app.route('/scan_now', methods=['GET'])
def scan_now():
    thread = threading.Thread(target=scan_all_stocks)
    thread.daemon = True
    thread.start()
    return jsonify({'status': '✅ Scan shuru ho gaya!'})

@app.route('/telegram', methods=['POST'])
def telegram_updates():
    try:
        update = request.get_json()
        if 'message' not in update: return jsonify({'status': 'ok'}), 200
        msg        = update['message']
        chat_id    = msg['chat']['id']
        text       = msg.get('text', '')
        first_name = msg.get('from', {}).get('first_name', 'Friend')

        if text.startswith('/start'): handle_start(chat_id, first_name)
        elif text.startswith('/help'): handle_help(chat_id)
        elif text.startswith('/price'): handle_price(chat_id, text)
        elif text.startswith('/scan'):
            send_message(chat_id, "🔍 Scan shuru ho raha hai... wait karo!")
            threading.Thread(target=scan_all_stocks, daemon=True).start()
        elif text.startswith('/alerts'): handle_alerts(chat_id)
        elif text.startswith('/status'): handle_status(chat_id)
        elif text.startswith('/allstocks'): handle_allstocks(chat_id)
        elif text.startswith('/buy'): handle_allstocks(chat_id, filter_action='BUY')
        elif text.startswith('/sell'): handle_allstocks(chat_id, filter_action='SELL')
        elif text.startswith('/paperbuy'): handle_paperbuy(chat_id, text)
        elif text.startswith('/papersell'): handle_papersell(chat_id, text)
        elif text.startswith('/portfolio'): handle_portfolio(chat_id)
        else: handle_button(chat_id, text, first_name)

        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    render_url = request.args.get('url', '')
    if not render_url: return jsonify({'error': 'URL chahiye'}), 400
    webhook_url = f"{render_url}/telegram"
    api_url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}"
    response    = requests.get(api_url)
    if response.json().get('ok'): return jsonify({'status': '✅ Webhook set!', 'url': webhook_url})
    return jsonify({'status': '❌ Failed', 'error': response.json()})

scanner_thread = threading.Thread(target=auto_scan_loop)
scanner_thread.daemon = True
scanner_thread.start()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
