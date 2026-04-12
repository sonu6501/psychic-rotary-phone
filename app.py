from flask import Flask, request, jsonify
import requests
import os
import json
from datetime import datetime

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

alerts_today = []

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
    try:
        symbol_yf = symbol + ".NS"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol_yf}?interval=1m&range=1d"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        result = data['chart']['result'][0]
        meta = result['meta']
        current_price = meta.get('regularMarketPrice', 0)
        prev_close = meta.get('chartPreviousClose', 0)
        day_high = meta.get('regularMarketDayHigh', 0)
        day_low = meta.get('regularMarketDayLow', 0)
        volume = meta.get('regularMarketVolume', 0)
        company_name = meta.get('shortName', symbol)
        change = current_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0
        trend = "📈" if change >= 0 else "📉"
        sign = "+" if change >= 0 else ""
        message = f"{trend} <b>{company_name}</b> ({symbol})\n\n💰 <b>Price:</b> ₹{current_price:.2f}\n📊 <b>Change:</b> {sign}{change:.2f} ({sign}{change_pct:.2f}%)\n🔺 <b>High:</b> ₹{day_high:.2f}\n🔻 <b>Low:</b> ₹{day_low:.2f}\n📦 <b>Volume:</b> {volume:,}\n🕐 <b>Time:</b> {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        return message
    except Exception as e:
        return f"❌ <b>{symbol}</b> ka data nahi mila!\nSahi NSE symbol likho\nExample: <code>/price RELIANCE</code>"

def format_alert_message(data):
    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    action = data.get('action', '').upper()
    if action == 'BUY':
        emoji = '🟢'
        action_text = '📈 BUY SIGNAL'
    elif action == 'SELL':
        emoji = '🔴'
        action_text = '📉 SELL SIGNAL'
    else:
        emoji = '🔔'
        action_text = '⚡ ALERT'
    message = f"{emoji} <b>{action_text}</b> {emoji}\n\n📊 <b>Stock:</b> {data.get('ticker', 'N/A')}\n💰 <b>Price:</b> ₹{data.get('price', 'N/A')}\n⚡ <b>Action:</b> {action}\n⏰ <b>Timeframe:</b> {data.get('timeframe', 'N/A')}\n📝 <b>Strategy:</b> {data.get('strategy', 'N/A')}\n🕐 <b>Time:</b> {now}"
    return message

def handle_start(chat_id, first_name):
    keyboard = {
        'keyboard': [
            [{'text': '📊 Price Check'}, {'text': '📋 Aaj Ke Alerts'}],
            [{'text': '✅ Bot Status'}, {'text': '❓ Help'}]
        ],
        'resize_keyboard': True,
        'persistent': True
    }
    message = f"🤖 <b>Namaste {first_name}!</b>\n\nYe bot TradingView ke stock alerts tumhare paas bhejta hai.\n\n<b>Quick Commands:</b>\n/price RELIANCE — Live price\n/alerts — Aaj ke alerts\n/status — Bot status\n/help — Sabhi commands\n\n<i>Neeche buttons se bhi use kar sakte ho! 👇</i>"
    send_message(chat_id, message, reply_markup=keyboard)

def handle_help(chat_id):
    message = "❓ <b>Sabhi Commands:</b>\n\n📊 <b>Price:</b>\n/price RELIANCE\n/price TCS\n/price HDFCBANK\n\n📋 <b>Alerts:</b>\n/alerts — Aaj ke saare alerts\n/last — Aakhri alert\n\n✅ <b>Other:</b>\n/status — Bot check\n/start — Main menu\n/help — Ye message\n\n💡 <i>NSE ka exact symbol use karo</i>"
    send_message(chat_id, message)

def handle_status(chat_id):
    now = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
    message = f"✅ <b>Bot Status: ACTIVE</b>\n\n🟢 Server: Running\n🟢 Webhook: Ready\n🟢 Telegram: Connected\n📊 Aaj ke Alerts: {len(alerts_today)}\n🕐 Time: {now}"
    send_message(chat_id, message)

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
        send_message(chat_id, "📋 Aaj abhi tak koi alert nahi aaya.")
        return
    message = f"📋 <b>Aaj Ke Alerts ({len(alerts_today)}):</b>\n\n"
    for alert in alerts_today[-10:]:
        action = alert.get('action', 'N/A').upper()
        emoji = '🟢' if action == 'BUY' else '🔴' if action == 'SELL' else '🔔'
        message += f"{emoji} <b>{alert.get('ticker','?')}</b> — {action} @ ₹{alert.get('price','?')} | {alert.get('time','')}\n"
    send_message(chat_id, message)

def handle_last(chat_id):
    if not alerts_today:
        send_message(chat_id, "📋 Abhi tak koi alert nahi aaya.")
        return
    send_message(chat_id, format_alert_message(alerts_today[-1]))

def handle_button(chat_id, text, first_name):
    if text == '📊 Price Check':
        send_message(chat_id, "📊 Kaunse stock ka price chahiye?\n\nLikho: <code>/price RELIANCE</code>")
    elif text == '📋 Aaj Ke Alerts':
        handle_alerts(chat_id)
    elif text == '✅ Bot Status':
        handle_status(chat_id)
    elif text == '❓ Help':
        handle_help(chat_id)

@app.route('/')
def home():
    return jsonify({'status': '✅ Bot is Running!'})

@app.route('/test', methods=['GET'])
def test():
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
                data = {'message': raw, 'ticker': 'UNKNOWN', 'action': 'ALERT'}
        data['time'] = datetime.now().strftime('%H:%M')
        alerts_today.append(data)
        print(f"Alert received: {data}")
        message = format_alert_message(data)
        result = send_message(TELEGRAM_CHAT_ID, message)
        if result and result.get('ok'):
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'status': 'error'}), 500
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/telegram', methods=['POST'])
def telegram_updates():
    try:
        update = request.get_json()
        print(f"Telegram update: {update}")
        if 'message' not in update:
            return jsonify({'status': 'ok'}), 200
        msg = update['message']
        chat_id = msg['chat']['id']
        text = msg.get('text', '')
        first_name = msg.get('from', {}).get('first_name', 'Friend')
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
    render_url = request.args.get('url', '')
    if not render_url:
        return jsonify({'error': 'URL parameter chahiye'}), 400
    webhook_url = f"{render_url}/telegram"
    api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}"
    response = requests.get(api_url)
    result = response.json()
    if result.get('ok'):
        return jsonify({'status': '✅ Webhook set ho gaya!', 'webhook_url': webhook_url})
    else:
        return jsonify({'status': '❌ Failed', 'error': result})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
