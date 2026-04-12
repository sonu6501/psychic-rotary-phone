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

# Environment Variables
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Global Data Stores
alerts_today = []
stocks_data = {}

# Stocks List (Expanded for better coverage)
NSE_STOCKS = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","SBIN",
    "BHARTIARTL","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI","SUNPHARMA",
    "TITAN","BAJFINANCE","WIPRO","ONGC","NTPC","POWERGRID","ULTRACEMCO","HCLTECH",
    "NESTLEIND","TATAMOTORS","ADANIENT","ADANIPORTS","BAJAJFINSV","JSWSTEEL",
    "TATASTEEL","TECHM","DRREDDY","CIPLA","DIVISLAB","COALINDIA","GRASIM",
    "BPCL","EICHERMOT","HINDALCO","INDUSINDBK","SBILIFE","HDFCLIFE","APOLLOHOSP",
    "BAJAJ-AUTO","TATACONSUM","BRITANNIA","HEROMOTOCO","UPL","DMART","ADANIGREEN",
    "ADANITRANS","SIEMENS","PIDILITIND","HAVELLS","MARICO","BERGEPAINT","COLPAL"
]

CRYPTO_PAIRS = ["BTC-USD","ETH-USD","SOL-USD","BNB-USD","XRP-USD","ADA-USD","DOGE-USD"]

# ---------------------------------------------------------
# TECHNICAL INDICATORS CALCULATIONS
# ---------------------------------------------------------

def calculate_indicators(df):
    """Sari calculations ek sath dataframe me calculate karega"""
    # EMA Calculation
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()

    # RSI Calculation
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['STD20'] = df['Close'].rolling(window=20).std()
    df['Upper_Band'] = df['MA20'] + (df['STD20'] * 2)
    df['Lower_Band'] = df['MA20'] - (df['STD20'] * 2)

    # Volume Average
    df['Vol_Avg'] = df['Volume'].rolling(window=10).mean()
    
    return df

# ---------------------------------------------------------
# CORE LOGIC: SIGNAL GENERATION
# ---------------------------------------------------------

def check_signal(symbol, is_crypto=False):
    try:
        ticker_sym = symbol if is_crypto else symbol + ".NS"
        df = yf.download(ticker_sym, period="60d", interval="1d", progress=False)

        if df.empty or len(df) < 30:
            return None

        df = calculate_indicators(df)
        
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        curr_price = round(last_row['Close'], 2)
        curr_rsi = round(last_row['RSI'], 2)
        curr_vol = last_row['Volume']
        avg_vol = last_row['Vol_Avg']
        
        # BUY Logic: EMA Crossover + RSI + Volume Confirmation
        buy_cond = (prev_row['EMA9'] <= prev_row['EMA21']) and (last_row['EMA9'] > last_row['EMA21'])
        buy_cond = buy_cond and curr_rsi > 45 and curr_rsi < 70
        buy_cond = buy_cond and curr_vol > (avg_vol * 0.8) # Volume check

        # SELL Logic: EMA Crossover + RSI + Price near Upper BB
        sell_cond = (prev_row['EMA9'] >= prev_row['EMA21']) and (last_row['EMA9'] < last_row['EMA21'])
        sell_cond = sell_cond or (curr_rsi > 75)
        
        # Risk Management (SL/TP)
        atr = (df['High'] - df['Low']).rolling(window=14).mean().iloc[-1]
        
        if buy_cond:
            return {
                'ticker': symbol,
                'price': curr_price,
                'action': 'BUY',
                'rsi': curr_rsi,
                'target': round(curr_price + (atr * 2), 2),
                'sl': round(curr_price - (atr * 1.5), 2),
                'strength': 'High' if curr_vol > avg_vol else 'Medium'
            }
        elif sell_cond:
            return {
                'ticker': symbol,
                'price': curr_price,
                'action': 'SELL',
                'rsi': curr_rsi,
                'target': round(curr_price - (atr * 2), 2),
                'sl': round(curr_price + (atr * 1.5), 2),
                'strength': 'High' if curr_vol > avg_vol else 'Medium'
            }
        return None
    except Exception as e:
        print(f"Error scanning {symbol}: {e}")
        return None

# ---------------------------------------------------------
# TELEGRAM FORMATTING & SENDING
# ---------------------------------------------------------

def send_message(chat_id, message, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
    if reply_markup: payload['reply_markup'] = json.dumps(reply_markup)
    try:
        return requests.post(url, json=payload, timeout=10).json()
    except:
        return None

def format_alert_message(data):
    now = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%I:%M %p")
    action = data['action']
    emoji = '🚀' if action == 'BUY' else '📉'
    color = '🟢' if action == 'BUY' else '🔴'
    
    msg = (
        f"{emoji} <b>PRO SIGNAL: {action}</b> {emoji}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 <b>Stock:</b> <code>{data['ticker']}</code>\n"
        f"💰 <b>Entry:</b> ₹{data['price']}\n"
        f"🎯 <b>Target:</b> ₹{data['target']}\n"
        f"🛡️ <b>StopLoss:</b> ₹{data['sl']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>RSI:</b> {data['rsi']} | ⚡ <b>Conf:</b> {data['strength']}\n"
        f"🕒 <b>Time:</b> {now} (IST)\n"
        f"✅ <i>Analysis by Black Devil Bot</i>"
    )
    return msg

# ---------------------------------------------------------
# BOT FUNCTIONALITY & ROUTES
# ---------------------------------------------------------

def scan_all_stocks():
    IST = pytz.timezone('Asia/Kolkata')
    send_message(TELEGRAM_CHAT_ID, "🔎 <b>Advanced Scanning Shuru...</b>")
    
    current_signals = []
    for symbol in NSE_STOCKS + CRYPTO_PAIRS:
        is_crypto = "-" in symbol
        res = check_signal(symbol, is_crypto)
        if res:
            res['time'] = datetime.now(IST).strftime('%H:%M')
            current_signals.append(res)
            alerts_today.append(res)
            stocks_data[symbol] = res
            # Instant alert for high strength signals
            if res['strength'] == 'High':
                send_message(TELEGRAM_CHAT_ID, format_alert_message(res))
        time.sleep(0.1) # Small delay for API stability

    if not current_signals:
        send_message(TELEGRAM_CHAT_ID, "😴 Market me abhi koi clear signal nahi hai.")
    else:
        send_message(TELEGRAM_CHAT_ID, f"✅ <b>Scan Done!</b> Total {len(current_signals)} signals mile.")

def auto_scan_loop():
    while True:
        try:
            now = datetime.now(pytz.timezone('Asia/Kolkata'))
            # Scan only in Market Hours for NSE, or 24/7 for Crypto if you prefer
            if now.weekday() < 5 and (9 <= now.hour <= 15):
                scan_all_stocks()
            else:
                # Late night crypto check
                print("Market closed, skipping NSE scan...")
            
            time.sleep(1800) # Every 30 minutes
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(60)

# Flask Routes (Keeping your existing structure)
@app.route('/')
def home(): return "Black Devil V2 is Active!"

@app.route('/telegram', methods=['POST'])
def telegram_updates():
    update = request.get_json()
    if 'message' in update:
        chat_id = update['message']['chat']['id']
        text = update['message'].get('text', '')
        if text == '/scan':
            threading.Thread(target=scan_all_stocks).start()
            send_message(chat_id, "Wait... main poora market analyze kar raha hoon.")
    return jsonify({'status': 'ok'})

# Start Threads
threading.Thread(target=auto_scan_loop, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
