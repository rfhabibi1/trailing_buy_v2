#!/usr/bin/env python3
"""
=====================================================================
TEST KONEKSI TELEGRAM
=====================================================================
Script ini digunakan untuk menguji koneksi Telegram sebelum 
menjalankan monitor utama. Pastikan TELEGRAM_BOT_TOKEN dan 
TELEGRAM_CHAT_ID sudah diset dengan benar.

Cara menjalankan:
    python test_telegram.py

Atau dengan environment variables:
    TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy python test_telegram.py
=====================================================================
"""

import os
import sys
import json
import requests
import logging
from datetime import datetime

# =====================================================================
# LOGGING SETUP
# =====================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# =====================================================================
# CONFIG
# =====================================================================

# Bisa dari environment variables atau input manual
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# File untuk menyimpan config (optional)
CONFIG_FILE = "telegram_config.json"


# =====================================================================
# FUNCTIONS
# =====================================================================

def load_config():
    """Load config dari file jika ada."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                return config.get("bot_token", ""), config.get("chat_id", "")
        except Exception:
            pass
    return "", ""


def save_config(bot_token: str, chat_id: str):
    """Save config ke file."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump({"bot_token": bot_token, "chat_id": chat_id}, f, indent=2)
        logger.info(f"✅ Config saved to {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Failed to save config: {e}")


def get_user_input():
    """Minta input dari user jika environment variables kosong."""
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    
    # Coba load dari file dulu
    saved_token, saved_chat_id = load_config()
    if saved_token and saved_chat_id:
        logger.info("📁 Found saved config in telegram_config.json")
        use_saved = input("Use saved config? (y/n): ").strip().lower()
        if use_saved == "y":
            TELEGRAM_BOT_TOKEN = saved_token
            TELEGRAM_CHAT_ID = saved_chat_id
            return
    
    if not TELEGRAM_BOT_TOKEN:
        TELEGRAM_BOT_TOKEN = input("Enter your TELEGRAM_BOT_TOKEN: ").strip()
    
    if not TELEGRAM_CHAT_ID:
        TELEGRAM_CHAT_ID = input("Enter your TELEGRAM_CHAT_ID: ").strip()
    
    # Tanya apakah mau simpan
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        save_choice = input("Save config for future use? (y/n): ").strip().lower()
        if save_choice == "y":
            save_config(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)


def test_bot_info(bot_token: str) -> dict:
    """
    Test get bot info menggunakan getMe API.
    Returns: dict dengan info bot
    """
    url = f"https://api.telegram.org/bot{bot_token}/getMe"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ok"):
            return {
                "success": True,
                "bot_id": data["result"]["id"],
                "bot_name": data["result"]["first_name"],
                "username": data["result"].get("username", "N/A"),
                "is_bot": data["result"].get("is_bot", True)
            }
        else:
            return {
                "success": False,
                "error": data.get("description", "Unknown error")
            }
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Connection timeout"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Connection error - check internet"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def test_send_message(bot_token: str, chat_id: str, message: str) -> dict:
    """
    Test kirim pesan ke Telegram.
    Returns: dict dengan hasil
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, data=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ok"):
            return {
                "success": True,
                "message_id": data["result"]["message_id"],
                "date": data["result"]["date"]
            }
        else:
            return {
                "success": False,
                "error": data.get("description", "Unknown error")
            }
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Connection timeout"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Connection error - check internet"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def test_get_updates(bot_token: str, chat_id: str) -> dict:
    """
    Test get updates untuk verifikasi chat_id.
    Returns: dict dengan hasil
    """
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {"limit": 1, "timeout": 5}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ok"):
            updates = data.get("result", [])
            if updates:
                last_update = updates[-1]
                chat = last_update.get("message", {}).get("chat", {})
                return {
                    "success": True,
                    "has_updates": True,
                    "chat_id_from_update": chat.get("id"),
                    "chat_type": chat.get("type", "unknown"),
                    "chat_title": chat.get("title") or chat.get("first_name", "N/A")
                }
            else:
                return {
                    "success": True,
                    "has_updates": False,
                    "message": "No recent messages found. Send a message to your bot first."
                }
        else:
            return {
                "success": False,
                "error": data.get("description", "Unknown error")
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def test_delete_webhook(bot_token: str) -> dict:
    """
    Test delete webhook (optional).
    """
    url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return {"success": data.get("ok", False), "result": data.get("result", False)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("\n" + "=" * 60)
    print("📱 TELEGRAM CONNECTION TEST")
    print("=" * 60 + "\n")
    
    # --- GET CONFIG ---
    get_user_input()
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID harus diisi!")
        logger.info("\n💡 Cara mendapatkan:")
        logger.info("   1. Token: Chat dengan @BotFather di Telegram → /newbot")
        logger.info("   2. Chat ID: Chat dengan @userinfobot → /start")
        sys.exit(1)
    
    # Mask token untuk log
    masked_token = TELEGRAM_BOT_TOKEN[:10] + "..." + TELEGRAM_BOT_TOKEN[-5:] if len(TELEGRAM_BOT_TOKEN) > 15 else "***"
    logger.info(f"📌 Bot Token: {masked_token}")
    logger.info(f"📌 Chat ID: {TELEGRAM_CHAT_ID}")
    
    print("\n" + "-" * 60)
    print("🧪 TEST 1: Cek Informasi Bot (getMe)")
    print("-" * 60)
    
    bot_info = test_bot_info(TELEGRAM_BOT_TOKEN)
    if bot_info.get("success"):
        logger.info("✅ Bot Info:")
        logger.info(f"   ID: {bot_info['bot_id']}")
        logger.info(f"   Nama: {bot_info['bot_name']}")
        logger.info(f"   Username: @{bot_info['username']}")
    else:
        logger.error(f"❌ Gagal get bot info: {bot_info.get('error')}")
        logger.info("\n💡 Kemungkinan penyebab:")
        logger.info("   - Token salah atau expired")
        logger.info("   - Internet tidak stabil")
        logger.info("   - Server Telegram bermasalah")
        sys.exit(1)
    
    print("\n" + "-" * 60)
    print("🧪 TEST 2: Kirim Pesan Test")
    print("-" * 60)
    
    test_message = f"""
✅ *TELEGRAM CONNECTION TEST SUCCESS*

📊 *System Status:* Connected
🕐 *Test Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB
📱 *Bot:* @{bot_info.get('username', 'unknown')}
📌 *Chat ID:* {TELEGRAM_CHAT_ID}

💡 *Selanjutnya:*
- Silakan jalankan monitor utama dengan `python trailing_start_check_once.py`
- Atau setup GitHub Actions untuk otomatisasi

🚀 *Happy Trading!*
    """
    
    send_result = test_send_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, test_message)
    
    if send_result.get("success"):
        logger.info("✅ Pesan test berhasil terkirim!")
        logger.info(f"   Message ID: {send_result['message_id']}")
        logger.info(f"   Time: {datetime.fromtimestamp(send_result['date']).strftime('%Y-%m-%d %H:%M:%S')}")
        print("\n📱 *CEK TELEGRAM ANDA!* Pesan test sudah terkirim.")
    else:
        logger.error(f"❌ Gagal kirim pesan: {send_result.get('error')}")
        logger.info("\n💡 Kemungkinan penyebab:")
        logger.info("   - Chat ID salah atau belum di-start")
        logger.info("   - Bot belum di-start oleh user")
        logger.info("   - User belum mengirim pesan ke bot terlebih dahulu")
        logger.info("\n💡 Cara fix:")
        logger.info("   1. Buka Telegram, cari bot @<username>")
        logger.info("   2. Klik START")
        logger.info("   3. Kirim pesan apapun ke bot (contoh: 'hello')")
        logger.info("   4. Jalankan test ini lagi")
        sys.exit(1)
    
    print("\n" + "-" * 60)
    print("🧪 TEST 3: Cek Recent Updates (Opsional)")
    print("-" * 60)
    
    update_result = test_get_updates(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    if update_result.get("success"):
        if update_result.get("has_updates"):
            logger.info("✅ Recent messages found:")
            logger.info(f"   Chat ID from update: {update_result['chat_id_from_update']}")
            logger.info(f"   Chat Type: {update_result['chat_type']}")
            logger.info(f"   Chat Title: {update_result['chat_title']}")
            
            # Cek apakah chat_id cocok
            if str(update_result['chat_id_from_update']) == str(TELEGRAM_CHAT_ID):
                logger.info("   ✅ Chat ID matched!")
            else:
                logger.warning(f"   ⚠️ Chat ID mismatch! Update shows: {update_result['chat_id_from_update']}")
        else:
            logger.info("ℹ️ No recent updates. This is normal if bot is new.")
            logger.info("   Send a message to @{} first to test.".format(bot_info.get('username', 'your_bot')))
    else:
        logger.warning(f"⚠️ Could not get updates: {update_result.get('error')}")
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE!")
    print("=" * 60)
    print(f"\n📊 Summary:")
    print(f"   Bot Token: {'✅ VALID' if bot_info.get('success') else '❌ INVALID'}")
    print(f"   Send Message: {'✅ SUCCESS' if send_result.get('success') else '❌ FAILED'}")
    
    if send_result.get('success'):
        print("\n🚀 Koneksi Telegram berhasil! Anda siap menggunakan monitor.")
        print("\n📝 Langkah selanjutnya:")
        print("   1. Jalankan monitor: python trailing_start_check_once.py")
        print("   2. Atau setup GitHub Actions dengan config di atas")
    else:
        print("\n❌ Koneksi Telegram gagal. Periksa token dan chat ID Anda.")
        print("   Pastikan Anda sudah START bot dan kirim pesan ke bot terlebih dahulu.")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
