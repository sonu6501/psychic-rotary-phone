from flask import Flask, request, jsonify
import requests
import os
import json
from datetime import datetime

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

alerts_today = []
stocks_data = {}

# ─────────────────────────────────────────
# HELPER FUNCTIONS
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

def get_main_keyboard():
    return {
        'keyboard': [
            [{'text': '📊 Price Check'},     {'text': '🔥 All Active Stocks'}],
            [{'text': '📈 All BUY Stocks'},  {'text': '📉 All SELL Stocks'}],
            [{'text': '📋 Aaj Ke Alerts'},   {'text': '⏮ Last Alert'}],
            [{'text': '🏆 Top Gainers'},      {'text': '💀 Top Losers'}],
            [{'text': '✅ Bot Status'},        {'text': '❓ Help'}]
        ],
        'resize_keyboard': True,
        'persistent': True
    }

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
        prev_close    = meta.get('chartPreviousClose', 0)
        day_high      = meta.get('regularMarketDayHigh', 0)
        day_low       = meta.get('regularMarketDayLow', 0)
        volume        = meta.get('regularMarketVolume', 0)
        company_name  = meta.get('shortName', symbol)
        change        = current_price - prev_close
        change_pct    = (change / prev_close * 100) if prev_close else 0
        trend         = "📈" if change >= 0 else "📉"
        sign          = "+" if change >= 0 else ""
        message = (
            f"{trend} <b>{company_name}</b> ({symbol})\n\n"
            f"💰 <b>Price:</b>  ₹{current_price:.2f}\n"
            f"📊 <b>Change:</b> {sign}{change:.2f} ({sign}{change_pct:.2f}%)\n"
            f"🔺 <b>High:</b>   ₹{day_high:.2f}\n"
            f"🔻 <b>Low:</b>    ₹{day_low:.2f}\n"
            f"📦 <b>Volume:</b> {volume:,}\n"
            f"🕐 <b>Time:</b>   {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        )
        return message, current_price, change_pct
    except Exception as e:
        return f"❌ <b>{symbol}</b> ka data nahi mila!\nExample: <code>/price RELIANCE</code>", 0, 0

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
    return (
        f"{emoji} <b>{action_text}</b> {emoji}\n\n"
        f"📊 <b>Stock:</b>     {data.get('ticker', 'N/A')}\n"
        f"💰 <b>Price:</b>     ₹{data.get('price', 'N/A')}\n"
        f"⚡ <b>Action:</b>    {action}\n"
        f"⏰ <b>Timeframe:</b> {data.get('timeframe', 'N/A')}\n"
        f"📝 <b>Strategy:</b>  {data.get('strategy', 'N/A')}\n"
        f"🕐 <b>Time:</b>      {now}"
    )

# ─────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────

def handle_start(chat_id, first_name):
    message = (
        f"🤖 <b>Namaste {first_name}! Black Devil Trading Bot</b>\n\n"
        f"Main tumhare liye TradingView ke stock alerts track karta hoon!\n\n"
        f"<b>📌 Commands:</b>\n"
        f"/price RELIANCE — Live price\n"
        f"/allstocks — Saare active stocks\n"
        f"/buy — Sirf BUY signals\n"
        f"/sell — Sirf SELL signals\n"
        f"/alerts — Aaj ke alerts\n"
        f"/gainers — Top gainers\n"
        f"/losers — Top losers\n"
        f"/status — Bot status\n"
        f"/help — Sabhi commands\n\n"
        f"<i>👇 Neeche buttons se bhi use karo!</i>"
    )
    send_message(chat_id, message, reply_markup=get_main_keyboard())

def handle_help(chat_id):
    message = (
        "❓ <b>Sabhi Commands:</b>\n\n"
        "📊 <b>Price:</b>\n"
        "/price RELIANCE — Live price check\n"
        "/price TCS\n"
        "/price HDFCBANK\n\n"
        "🔥 <b>Stock Lists:</b>\n"
        "/allstocks — Saare active stocks\n"
        "/buy — Sirf BUY signals\n"
        "/sell — Sirf SELL signals\n"
        "/gainers — Top gainers aaj\n"
        "/losers — Top losers aaj\n\n"
        "📋 <b>Alerts:</b>\n"
        "/alerts — Aaj ke saare alerts\n"
        "/last — Sabse aakhri alert\n\n"
        "✅ <b>Other:</b>\n"
        "/status — Bot stats\n"
        "/start — Main menu\n\n"
        "💡 <i>NSE ka exact symbol use karo</i>"
    )
    send_message(chat_id, message, reply_markup=get_main_keyboard())

def handle_status(chat_id):
    now        = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
    buy_count  = sum(1 for s in stocks_data.values() if s.get('action','').upper() == 'BUY')
    sell_count = sum(1 for s in stocks_data.values() if s.get('action','').upper() == 'SELL')
    message = (
        f"✅ <b>Bot Status: ACTIVE</b>\n\n"
        f"🟢 Server:   Running\n"
        f"🟢 Webhook:  Connected\n"
        f"🟢 Telegram: Connected\n\n"
        f"📊 <b>Aaj Ki Stats:</b>\n"
        f"🔔 Total Alerts:   {len(alerts_today)}\n"
        f"📈 BUY Stocks:     {buy_count}\n"
        f"📉 SELL Stocks:    {sell_count}\n"
        f"🔥 Active Stocks:  {len(stocks_data)}\n\n"
        f"🕐 Server Time: {now}"
    )
    send_message(chat_id, message, reply_markup=get_main_keyboard())

def handle_price(chat_id, text):
    parts = text.strip().split()
    if len(parts) < 2:
        send_message(chat_id, "⚠️ Symbol batao!\n\nExample: <code>/price RELIANCE</code>")
        return
    symbol = parts[1].upper()
    send_message(chat_id, f"🔍 <b>{symbol}</b> ka price fetch ho raha hai...")
    price_message, _, _ = get_live_price(symbol)
    send_message(chat_id, price_message)

def handle_alerts(chat_id):
    if not alerts_today:
        send_message(chat_id, "📋 Aaj abhi tak koi alert nahi aaya.\n\n<i>TradingView se alert aane par yahan dikhega.</i>")
        return
    message = f"📋 <b>Aaj Ke Alerts ({len(alerts_today)}):</b>\n\n"
    for alert in alerts_today[-15:]:
        action = alert.get('action', 'N/A').upper()
        emoji  = '🟢' if action == 'BUY' else '🔴' if action == 'SELL' else '🔔'
        message += f"{emoji} <b>{alert.get('ticker','?')}</b> — {action} @ ₹{alert.get('price','?')} | {alert.get('time','')}\n"
    send_message(chat_id, message)

def handle_last(chat_id):
    if not alerts_today:
        send_message(chat_id, "📋 Abhi tak koi alert nahi aaya.")
        return
    send_message(chat_id, format_alert_message(alerts_today[-1]))

def handle_allstocks(chat_id, filter_action=None):
    if not stocks_data:
        send_message(chat_id, "🔥 Abhi tak koi stock active nahi hai.\n\n<i>TradingView alert aane par yahan dikhega.</i>")
        return

    if filter_action:
        filtered    = {k: v for k, v in stocks_data.items() if v.get('action','').upper() == filter_action.upper()}
        title_emoji = '📈' if filter_action.upper() == 'BUY' else '📉'
        title       = f"{title_emoji} <b>{filter_action.upper()} Stocks ({len(filtered)}):</b>\n\n"
    else:
        filtered = stocks_data
        title    = f"🔥 <b>Saare Active Stocks ({len(filtered)}):</b>\n\n"

    if not filtered:
        send_message(chat_id, f"❌ Koi {filter_action} stock nahi mila abhi.")
        return

    # Multiple messages (30 stocks per message)
    message       = title
    count         = 0
    messages_list = []

    for ticker, data in filtered.items():
        action    = data.get('action', 'N/A').upper()
        price     = data.get('price', 'N/A')
        timeframe = data.get('timeframe', 'N/A')
        time      = data.get('time', 'N/A')
        emoji     = '🟢' if action == 'BUY' else '🔴' if action == 'SELL' else '🔔'
        message  += f"{emoji} <b>{ticker}</b> — {action} @ ₹{price} | {timeframe} | {time}\n"
        count    += 1
        if count % 30 == 0:
            messages_list.append(message)
            message = f"<b>...continued:</b>\n\n"

    if message.strip():
        messages_list.append(message)

    for msg in messages_list:
        send_message(chat_id, msg)

def handle_gainers_losers(chat_id, mode='gainers'):
    if not stocks_data:
        send_message(chat_id, "📊 Abhi tak koi stock data nahi hai.")
        return

    send_message(chat_id, "📡 Live prices fetch ho rahi hain... thoda wait karo!")

    results = []
    for ticker in list(stocks_data.keys())[:20]:  # Top 20 check karo
        _, price, change_pct = get_live_price(ticker)
        if price > 0:
            results.append((ticker, price, change_pct))

    if not results:
        send_message(chat_id, "❌ Data fetch nahi hua. Dobara try karo.")
        return

    results.sort(key=lambda x: x[2], reverse=(mode == 'gainers'))
    top = results[:10]

    if mode == 'gainers':
        title = "🏆 <b>Top 10 Gainers (Aaj):</b>\n\n"
        emoji = '📈'
    else:
        title = "💀 <b>Top 10 Losers (Aaj):</b>\n\n"
        emoji = '📉'

    message = title
    for i, (ticker, price, change_pct) in enumerate(top, 1):
        sign     = "+" if change_pct >= 0 else ""
        message += f"{i}. {emoji} <b>{ticker}</b> — ₹{price:.2f} ({sign}{change_pct:.2f}%)\n"

    send_message(chat_id, message)

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
        send_message(chat_id, "❓ Samjha nahi! /help likho ya neeche buttons use karo.", reply_markup=get_main_keyboard())

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@app.route('/')
def home():
    return jsonify({'status': '✅ Black Devil Trading Bot is Running!'})

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
    result  = send_message(TELEGRAM_CHAT_ID, message)
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

        ticker = data.get('ticker', 'UNKNOWN')
        stocks_data[ticker] = data

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
    try:
        update = request.get_json()
        print(f"Telegram update: {update}")

        if 'message' not in update:
            return jsonify({'status': 'ok'}), 200

        msg        = update['message']
        chat_id    = msg['chat']['id']
        text       = msg.get('text', '')
        first_name = msg.get('from', {}).get('first_name', 'Friend')

        if text.startswith('/start'):
            handle_start(chat_id, first_name)
        elif text.startswith('/help') or text == '❓ Help':
            handle_help(chat_id)
        elif text.startswith('/price'):
            handle_price(chat_id, text)
        elif text.startswith('/alerts') or text == '📋 Aaj Ke Alerts':
            handle_alerts(chat_id)
        elif text.startswith('/last') or text == '⏮ Last Alert':
            handle_last(chat_id)
        elif text.startswith('/status') or text == '✅ Bot Status':
            handle_status(chat_id)
        elif text.startswith('/allstocks') or text == '🔥 All Active Stocks':
            handle_allstocks(chat_id)
        elif text.startswith('/buy') or text == '📈 All BUY Stocks':
            handle_allstocks(chat_id, filter_action='BUY')
        elif text.startswith('/sell') or text == '📉 All SELL Stocks':
            handle_allstocks(chat_id, filter_action='SELL')
        elif text.startswith('/gainers') or text == '🏆 Top Gainers':
            handle_gainers_losers(chat_id, mode='gainers')
        elif text.startswith('/losers') or text == '💀 Top Losers':
            handle_gainers_losers(chat_id, mode='losers')
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
    api_url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}"
    response    = requests.get(api_url)
    result      = response.json()
    if result.get('ok'):
        return jsonify({'status': '✅ Webhook set ho gaya!', 'webhook_url': webhook_url})
    else:
        return jsonify({'status': '❌ Failed', 'error': result})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
