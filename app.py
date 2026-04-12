from flask import Flask, request, jsonify
import requests
import os
import json
from datetime import datetime

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Aaj ke alerts store karne ke liye
alerts_today = []

# ─────────────────────────────────────────
# TELEGRAM FUNCTIONS
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

def get_live_price(symbol):
    """NSE se live price fetch karo"""
    try:
        # Yahoo Finance API use karenge
        symbol_yf = symbol + ".NS"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol_yf}?interval=1m&range=1d"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()

        result = data['chart']['result'][0]
        meta = result['meta']

        current_price = meta.get('regularMarketPrice', 0)
        prev_close    = meta.get('chartPreviousClose', 0)
        day_high      = meta.get('regularMarketDayHigh', 0)
        day_low       = meta.get('regularMarketDayLow', 0)
        volume        = meta.get('regularMarketVolume', 0)
        company_name  = meta.get('shortName', symbol)

        change     = current_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0
        trend      = "📈" if change >= 0 else "📉"
        sign       = "+" if change >= 0 else ""

        message = f"""
{trend} <b>{company_name}</b> ({symbol})

💰 <b>Price:</b>  ₹{current_price:.2f}
📊 <b>Change:</b> {sign}{change:.2f} ({sign}{change_pct:.2f}%)
🔺 <b>High:</b>   ₹{day_high:.2f}
🔻 <b>Low:</b>    ₹{day_low:.2f}
📦 <b>Volume:</b> {volume:,}
🕐 <b>Time:</b>   {datetime.now().strftime('%d-%m-%Y %H:%M')}
"""
        return message.strip()

    except Exception as e:
        return f"❌ <b>{symbol}</b> ka data nahi mila!\n\nSahi NSE symbol likho\nExample: <code>/price RELIANCE</code>"

def format_alert_message(data):
    now    = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
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

    message = f"""
{emoji} <b>{action_text}</b> {emoji}

📊 <b>Stock:</b>    {data.get('ticker', 'N/A')}
💰 <b>Price:</b>    ₹{data.get('price', 'N/A')}
⚡ <b>Action:</b>   {action}
⏰ <b>Timeframe:</b> {data.get('timeframe', 'N/A')}
📝 <b>Strategy:</b> {data.get('strategy', 'N/A')}
🕐 <b>Time:</b>     {now}
"""
    return message.strip()

# ─────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────

def handle_start(chat_id, first_name):
    keyboard = {
        'keyboard': [
            [{'text': '📊 Price Check'}, {'text': '📋 Aaj Ke Alerts'}],
            [{'text': '✅ Bot Status'},  {'text': '❓ Help'}]
        ],
        'resize_keyboard': True,
        'persistent': True
    }
    message = f"""
🤖 <b>Namaste {first_name}!</b>

Ye bot TradingView ke stock alerts tumhare paas bhejta hai.

<b>Kya kar sakte ho:</b>
📊 Live price check karo
📋 Aaj ke alerts dekho
🔔 Auto alerts milte rahenge

<b>Quick Commands:</b>
/price RELIANCE — Live price
/alerts — Aaj ke alerts
/status — Bot status
/help — Sabhi commands

<i>Neeche buttons se bhi use kar sakte ho! 👇</i>
"""
    send_message(chat_id, message.strip(), reply_markup=keyboard)

def handle_help(chat_id):
    message = """
❓ <b>Sabhi Commands:</b>

📊 <b>Price Commands:</b>
/price RELIANCE — Reliance ka price
/price TCS — TCS ka price
/price NIFTY50 — Nifty 50 index

📋 <b>Alert Commands:</b>
/alerts — Aaj ke saare alerts
/last — Sabse aakhri alert

✅ <b>Other Commands:</b>
/status — Bot alive check
/start — Main menu
/help — Ye message

<b>Example:</b>
<code>/price HDFCBANK</code>
<code>/price INFY</code>
<code>/price TATAMOTORS</code>

💡 <i>NSE ka exact symbol use karo</i>
"""
    send_message(chat_id, message.strip())

def handle_status(chat_id):
    now = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
    message = f"""
✅ <b>Bot Status: ACTIVE</b>

🟢 Server: Running
🟢 Webhook: Ready
🟢 Telegram: Connected
📊 Aaj ke Alerts: {len(alerts_today)}
🕐 Server Time: {now}
"""
    send_message(chat_id, message.strip())

def handle_price(chat_id, text):
    parts = text.strip().split()
    if len(parts) < 2:
        send_message(chat_id, "⚠️ Symbol batao!\n\nExample: <code>/price RELIANCE</code>")
        return
    symbol = parts[1].upper()
    send_message(chat_id, f"🔍 <b>{symbol}</b> ka price fetch ho raha hai...")
    price_message = get_live_price(symbol)
    send_message(chat_id, price_message)

def handle_alerts(chat_id):
    if not alerts_today:
        send_message(chat_id, "📋 Aaj abhi tak koi alert nahi aaya.\n\n<i>TradingView alert aane par yahan dikhega.</i>")
        return
    message = f"📋 <b>Aaj Ke Alerts ({len(alerts_today)}):</b>\n\n"
    # Last 10 alerts dikhao
    for alert in alerts_today[-10:]:
        action  = alert.get('action', 'N/A').upper()
        emoji   = '🟢' if action == 'BUY' else '🔴' if action == 'SELL' else '🔔'
        message += f"{emoji} <b>{alert.get('ticker','?')}</b> — {action} @ ₹{alert.get('price','?')} | {alert.get('time','')}\n"
    send_message(chat_id, message.strip())

def handle_last(chat_id):
    if not alerts_today:
        send_message(chat_id, "📋 Abhi tak koi alert nahi aaya.")
        return
    last = alerts_today[-1]
    send_message(chat_id, format_alert_message(last))

def handle_button(chat_id, text, first_name):
    """Keyboard buttons handle karo"""
    if text == '📊 Price Check':
        send_message(chat_id, "📊 Kaunse stock ka price chahiye?\n\nLikho: <code>/price RELIANCE</code>")
    elif text == '📋 Aaj Ke Alerts':
        handle_alerts(chat_id)
    elif text == '✅ Bot Status':
        handle_status(chat_id)
    elif text == '❓ Help':
        handle_help(chat_id)

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@app.route('/')
def home():
    return jsonify({'status': '✅ Bot is Running!'})

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView alerts receive karo"""
    try:
        if request.is_json:
            data = request.get_json()
        else:
            raw = request.data.decode('utf-8')
            try:
                data = json.loads(raw)
            except:
                data = {'message': raw, 'ticker': 'UNKNOWN', 'action': 'ALERT'}

        # Time add karo
        data['time'] = datetime.now().strftime('%H:%M')
        alerts_today.append(data)

        print(f"Alert received: {data}")

        message = format_alert_message(data)
        result  = send_message(TELEGRAM_CHAT_ID, message)

        if result and result.get('ok'):
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'status': 'error'}), 500

    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/telegram', methods=['POST'])
def telegram_updates():
    """Telegram se commands receive karo"""
    try:
        update = request.get_json()
        print(f"Telegram update: {update}")

        if 'message' not in update:
            return jsonify({'status': 'ok'}), 200

        msg        = update['message']
        chat_id    = msg['chat']['id']
        text       = msg.get('text', '')
        first_name = msg.get('from', {}).get('first_name', 'Friend')

        # Commands handle karo
        if text.startswith('/start'):
            handle_start(chat_id, first_name)
        elif text.startswith('/help') or text == '❓ Help':
            handle_help(chat_id)
        elif text.startswith('/price'):
            handle_price(chat_id, text)
        elif text.startswith('/alerts') or text == '📋 Aaj Ke Alerts':
            handle_alerts(chat_id)
        elif text.startswith('/last'):
            handle_last(chat_id)
        elif text.startswith('/status') or text == '✅ Bot Status':
            handle_status(chat_id)
        else:
            handle_button(chat_id, text, first_name)

        return jsonify({'status': 'ok'}), 200

    except Exception as e:
        print(f"Telegram update error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """Telegram webhook set karo"""
    render_url = request.args.get('url', '')
    if not render_url:
        return jsonify({'error': 'URL parameter chahiye: /set_webhook?url=https://tumhara-url.onrender.com'}), 400

    webhook_url = f"{render_url}/telegram"
    api_url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}"
    response    = requests.get(api_url)
    result      = response.json()

    if result.get('ok'):
        return jsonify({'status': '✅ Webhook set ho gaya!', 'webhook_url': webhook_url})
    else:
        return jsonify({'status': '❌ Failed', 'error': result})

 @app.route('/test', methods=['GET'])
def test():
    """Bot test karne ke liye"""
    test_data = {
        'ticker': 'RELIANCE',
        'price': '2450.50',
        'action': 'BUY',
        'timeframe': '15m',
        'strategy': 'Test Alert'
    }
    message = format_alert_message(test_data)
    result = send_message(TELEGRAM_CHAT_ID, message)
    if result and result.get('ok'):
        return jsonify({'status': 'Test message sent! Check Telegram ✅'})
    else:
        return jsonify({'status': 'Failed ❌', 'error': result})
        
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
