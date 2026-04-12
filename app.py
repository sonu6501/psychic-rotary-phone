from flask import Flask, request, jsonify
import requests
import os
import json
from datetime import datetime

app = Flask(__name__)

# Environment variables se lenge (Render me set karenge)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

def send_telegram_message(message):
    """Telegram par message bhejne ka function"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Telegram error: {e}")
        return None

def format_alert_message(data):
    """TradingView se aaye data ko sundar message me convert karo"""
    
    # Current time
    now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    
    # Alert type ke hisaab se emoji
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
    
    # Message format karo
    message = f"""
{emoji} <b>{action_text}</b> {emoji}

📊 <b>Stock:</b> {data.get('ticker', 'N/A')}
💰 <b>Price:</b> ₹{data.get('price', 'N/A')}
📈 <b>Action:</b> {action}
⏰ <b>Timeframe:</b> {data.get('timeframe', 'N/A')}
📝 <b>Strategy:</b> {data.get('strategy', 'N/A')}

🕐 <b>Time:</b> {now}
"""
    return message.strip()

@app.route('/')
def home():
    """Home route - server check karne ke liye"""
    return jsonify({
        'status': 'Bot is Running! ✅',
        'message': 'TradingView to Telegram Bot Active'
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingView se alert receive karne ka main route"""
    try:
        # TradingView se data lo
        if request.is_json:
            data = request.get_json()
        else:
            # Plain text me aaye to parse karo
            raw_data = request.data.decode('utf-8')
            try:
                data = json.loads(raw_data)
            except:
                # Simple text alert
                data = {'message': raw_data, 'ticker': 'UNKNOWN', 'action': 'ALERT'}
        
        print(f"Alert received: {data}")  # Log ke liye
        
        # Message format karo
        message = format_alert_message(data)
        
        # Telegram par bhejo
        result = send_telegram_message(message)
        
        if result and result.get('ok'):
            return jsonify({'status': 'success', 'message': 'Alert sent to Telegram!'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Telegram send failed'}), 500
            
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
    result = send_telegram_message(message)
    
    if result and result.get('ok'):
        return jsonify({'status': 'Test message sent! Check Telegram ✅'})
    else:
        return jsonify({'status': 'Failed ❌', 'error': result})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
