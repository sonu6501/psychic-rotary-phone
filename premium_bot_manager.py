import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import sqlite3
from datetime import datetime, timedelta
import os

# ---------------------------------------------------------
# BOT CONFIGURATION & SETUP
# ---------------------------------------------------------
# अपना टोकन यहाँ डालें या Environment Variable से लें
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', 'YOUR_BOT_TOKEN_HERE')
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# चैनल की डिटेल्स (फोर्स ज्वाइन के लिए)
# ध्यान दें: बॉट को इस चैनल में एडमिन होना बहुत ज़रूरी है तभी वो चेक कर पायेगा।
CHANNEL_LINK = "https://t.me/+vK7WE4K6T3U2ODc1"
# यहाँ आपको अपने चैनल का Username या ID (-100... वाला) डालना होगा
CHANNEL_ID = "@your_channel_username" # इसे अपने चैनल आईडी से बदलें

# ---------------------------------------------------------
# DATABASE MANAGEMENT (SQLite)
# ---------------------------------------------------------
def init_db():
    """डेटाबेस और टेबल्स को इनिशियलाइज़ करने के लिए"""
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            is_admin INTEGER DEFAULT 0,
            is_vip INTEGER DEFAULT 0,
            vip_expiry TEXT,
            join_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_user(chat_id, username, first_name):
    """नए यूज़र को डेटाबेस में ऐड करने के लिए"""
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM users WHERE chat_id=?", (chat_id,))
    if not cursor.fetchone():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO users (chat_id, username, first_name, join_date)
            VALUES (?, ?, ?, ?)
        ''', (chat_id, username, first_name, now))
        conn.commit()
    conn.close()

def make_user_admin(chat_id):
    """यूज़र को एडमिन बनाने के लिए"""
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_admin=1 WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

def is_admin(chat_id):
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] == 1 if result else False

def get_all_users():
    """VIP देने के लिए सभी यूज़र्स की लिस्ट मंगाने के लिए"""
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, first_name, username, is_vip FROM users")
    users = cursor.fetchall()
    conn.close()
    return users

def update_vip_status(chat_id, days):
    """यूज़र को VIP प्लान देने के लिए"""
    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_vip=1, vip_expiry=? WHERE chat_id=?", (expiry_date, chat_id))
    conn.commit()
    conn.close()

def check_vip(chat_id):
    """यूज़र का VIP स्टेटस और एक्सपायरी चेक करने के लिए"""
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_vip, vip_expiry FROM users WHERE chat_id=?", (chat_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0] == 1:
        expiry = datetime.strptime(result[1], "%Y-%m-%d %H:%M:%S")
        if datetime.now() < expiry:
            return True, result[1]
        else:
            # VIP Expire हो गया है, अपडेट करें
            conn = sqlite3.connect('bot_users.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_vip=0, vip_expiry=NULL WHERE chat_id=?", (chat_id,))
            conn.commit()
            conn.close()
            return False, None
    return False, None

# ---------------------------------------------------------
# FORCE JOIN CHECKER
# ---------------------------------------------------------
def check_channel_member(user_id):
    """चेक करता है कि यूज़र ने चैनल ज्वाइन किया है या नहीं"""
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        print(f"Error checking channel membership: {e}")
        # अगर चैनल आईडी गलत है या बॉट एडमिन नहीं है, तो अभी के लिए True रिटर्न कर देते हैं 
        # ताकि बॉट ब्लॉक न हो (आप इसे अपने हिसाब से बदल सकते हैं)
        return False

def force_join_markup():
    """फोर्स ज्वाइन के लिए बटन्स"""
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton("📢 Join Our Channel", url=CHANNEL_LINK)
    btn2 = InlineKeyboardButton("✅ I Have Joined", callback_data="check_joined")
    markup.add(btn1)
    markup.add(btn2)
    return markup

# ---------------------------------------------------------
# BOT COMMANDS & HANDLERS
# ---------------------------------------------------------

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # यूज़र को डेटाबेस में सेव करें
    add_user(chat_id, username, first_name)
    
    # चैनल ज्वाइन चेक करें
    if not check_channel_member(chat_id):
        text = (f"👋 हैलो <b>{first_name}</b>!\n\n"
                f"बॉट का इस्तेमाल करने के लिए आपको हमारा प्रीमियम चैनल ज्वाइन करना होगा। "
                f"नीचे दिए गए बटन पर क्लिक करके चैनल ज्वाइन करें और फिर 'I Have Joined' पर क्लिक करें।")
        bot.send_message(chat_id, text, reply_markup=force_join_markup(), parse_mode="HTML")
        return

    welcome_text = (f"🚀 <b>Welcome to Black Devil V2!</b>\n\n"
                    f"आपका स्वागत है {first_name}। मार्केट सिग्नल्स और VIP फीचर्स का आनंद लें।\n"
                    f"अगर आप एडमिन हैं तो सीक्रेट कोड टाइप करें।")
    bot.send_message(chat_id, welcome_text, parse_mode="HTML")

# ---------------------------------------------------------
# ADMIN PANEL LOGIC (SECRET TRIGGER)
# ---------------------------------------------------------

@bot.message_handler(func=lambda message: message.text == 'sonu@123')
def secret_admin_login(message):
    chat_id = message.chat.id
    make_user_admin(chat_id) # डेटाबेस में एडमिन बना दिया
    
    bot.delete_message(chat_id, message.message_id) # सीक्रेट कोड वाला मैसेज डिलीट कर दें ताकि कोई और न देखे
    
    show_admin_panel(chat_id)

def show_admin_panel(chat_id):
    """एकदम प्रीमियम लुक वाला एडमिन पैनल"""
    if not is_admin(chat_id):
        return

    markup = InlineKeyboardMarkup(row_width=2)
    btn_vip = InlineKeyboardButton("👑 Give VIP (1-Click)", callback_data="admin_give_vip")
    btn_users = InlineKeyboardButton("👥 User List", callback_data="admin_user_list")
    btn_broadcast = InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
    btn_stats = InlineKeyboardButton("📊 Bot Stats", callback_data="admin_stats")
    
    markup.add(btn_vip, btn_users)
    markup.add(btn_broadcast, btn_stats)
    
    text = ("👑 <b>Premium Admin Panel</b> 👑\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "नमस्कार एडमिन बॉस! यहाँ से आप पूरे बॉट को कण्ट्रोल कर सकते हैं। "
            "सब कुछ आसान और फ़ास्ट बनाया गया है। कोई भी ऑप्शन चुनें:")
    
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")

# ---------------------------------------------------------
# CALLBACK QUERIES (BUTTON CLICKS)
# ---------------------------------------------------------

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    # 1. Force Join Check Verification
    if call.data == "check_joined":
        if check_channel_member(chat_id):
            bot.answer_callback_query(call.id, "✅ वेरिफिकेशन सफल! बॉट अनलॉक हो गया है।")
            bot.edit_message_text("✅ <b>धन्यवाद!</b> अब आप बॉट का इस्तेमाल कर सकते हैं।", 
                                  chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML")
        else:
            bot.answer_callback_query(call.id, "❌ आपने अभी तक चैनल ज्वाइन नहीं किया है!", show_alert=True)
            
    # 2. Admin: Show Users List for VIP
    elif call.data == "admin_give_vip":
        if not is_admin(chat_id): return
        
        users = get_all_users()
        if not users:
            bot.answer_callback_query(call.id, "अभी तक कोई यूज़र नहीं है।", show_alert=True)
            return
            
        markup = InlineKeyboardMarkup(row_width=1)
        for u in users:
            uid, name, uname, vip_status = u
            status_emoji = "👑" if vip_status else "👤"
            btn_text = f"{status_emoji} {name} (@{uname if uname else 'No_User'})"
            # बटन के डेटा में यूज़र की ID पास कर रहे हैं
            markup.add(InlineKeyboardButton(btn_text, callback_data=f"setvip_{uid}"))
            
        markup.add(InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="back_to_admin"))
        
        bot.edit_message_text("👇 <b>उस यूज़र पर क्लिक करें जिसे VIP देना है:</b>", 
                              chat_id=chat_id, message_id=call.message.message_id, 
                              reply_markup=markup, parse_mode="HTML")

    # 3. Admin: Selected a user, now ask for Days
    elif call.data.startswith("setvip_"):
        if not is_admin(chat_id): return
        target_user_id = call.data.split("_")[1]
        
        msg = bot.edit_message_text(f"⏳ आपने User ID: <code>{target_user_id}</code> को सेलेक्ट किया है।\n\n"
                                    f"<b>कृपया रिप्लाई में दिन (Days) टाइप करें</b> (जैसे 30, 60, 90):", 
                                    chat_id=chat_id, message_id=call.message.message_id, parse_mode="HTML")
        
        # Next step handler का इस्तेमाल ताकि एडमिन जो भी लिखे वो दिन के रूप में सेव हो
        bot.register_next_step_handler(msg, process_vip_days, target_user_id)

    # 4. Admin: Back Button
    elif call.data == "back_to_admin":
        bot.delete_message(chat_id, call.message.message_id)
        show_admin_panel(chat_id)

    # 5. Admin: Stats
    elif call.data == "admin_stats":
        users = get_all_users()
        vip_count = sum(1 for u in users if u[3] == 1)
        text = (f"📊 <b>Bot Statistics</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"👥 Total Users: {len(users)}\n"
                f"👑 Active VIPs: {vip_count}\n"
                f"⚙️ Status: Running 100% OK")
        bot.answer_callback_query(call.id, "Stats Updated!")
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="back_to_admin"))
        bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="HTML")

# ---------------------------------------------------------
# NEXT STEP HANDLERS (Waiting for inputs)
# ---------------------------------------------------------

def process_vip_days(message, target_user_id):
    """एडमिन द्वारा टाइप किये गए दिनों को प्रोसेस करता है"""
    chat_id = message.chat.id
    try:
        days = int(message.text.strip())
        update_vip_status(target_user_id, days)
        
        bot.send_message(chat_id, f"✅ <b>सफलतापूर्वक!</b> User {target_user_id} का VIP {days} दिनों के लिए एक्टिव कर दिया गया है।", parse_mode="HTML")
        
        # यूज़र को भी नोटिफिकेशन भेज देते हैं कि उसका VIP एक्टिव हो गया है
        try:
            bot.send_message(target_user_id, f"🎉 <b>बधाई हो!</b>\n\nएडमिन ने आपका <b>Premium VIP Plan</b> {days} दिनों के लिए एक्टिवेट कर दिया है! अब आप सभी प्रीमियम सिग्नल्स का फायदा उठा सकते हैं।", parse_mode="HTML")
        except:
            pass # अगर यूज़र ने बॉट ब्लॉक कर दिया हो तो एरर न आये
            
        show_admin_panel(chat_id)
        
    except ValueError:
        bot.send_message(chat_id, "❌ <b>गलती!</b> कृपया सिर्फ नंबर लिखें (जैसे 30)। फिर से प्रयास करने के लिए एडमिन पैनल खोलें।", parse_mode="HTML")
        show_admin_panel(chat_id)

# ---------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print("Database Initialized...")
    print("Premium Admin Manager Started Successfully...")
    # Infinity polling इस्तेमाल कर रहे हैं ताकि बॉट लगातार बैकग्राउंड में चलता रहे
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
