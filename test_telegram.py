#!/usr/bin/env python3
"""
=====================================================================
TEST KONEKSI TELEGRAM
=====================================================================
Script untuk menguji koneksi Telegram sebelum menjalankan monitor utama.
Cara menjalankan:
    python test_telegram.py --ci
=====================================================================
"""

import os
import sys
import json
import requests
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

IS_CI = os.environ.get("CI", "false").lower() == "true" or "--ci" in sys.argv
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def test_bot_info(bot_token: str) -> dict:
    """Test get bot info menggunakan getMe API."""
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
                "username": data["result"].get("username", "N/A")
            }
        return {"success": False, "error": data.get("description", "Unknown error")}
    except Exception as e:
        return {"success": False, "error": str(e)}


def test_send_message(bot_token: str, chat_id: str, message: str) -> dict:
    """Test kirim pesan ke Telegram."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, data=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("ok"):
            return {"success": True, "message_id": data["result"]["message_id"]}
        return {"success": False, "error": data.get("description", "Unknown error")}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    print("\n" + "=" * 60)
    print("📱 TELEGRAM CONNECTION TEST")
    print("=" * 60 + "\n")
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID harus diset!")
        sys.exit(1)
    
    masked_token = TELEGRAM_BOT_TOKEN[:10] + "..." + TELEGRAM_BOT_TOKEN[-5:]
    logger.info(f"📌 Bot Token: {masked_token}")
    logger.info(f"📌 Chat ID: {TELEGRAM_CHAT_ID}")
    logger.info(f"📌 Mode: {'CI' if IS_CI else 'Local'}")
    
    print("\n" + "-" * 60)
    print("🧪 TEST 1: Cek Informasi Bot")
    print("-" * 60)
    
    bot_info = test_bot_info(TELEGRAM_BOT_TOKEN)
    if bot_info.get("success"):
        logger.info("✅ Bot Info:")
        logger.info(f"   ID: {bot_info['bot_id']}")
        logger.info(f"   Nama: {bot_info['bot_name']}")
        logger.info(f"   Username: @{bot_info['username']}")
    else:
        logger.error(f"❌ Gagal: {bot_info.get('error')}")
        sys.exit(1)
    
    print("\n" + "-" * 60)
    print("🧪 TEST 2: Kirim Pesan Test")
    print("-" * 60)
    
    test_message = f"""
✅ *TELEGRAM CONNECTION TEST SUCCESS*

📊 *Status:* Connected
🕐 *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB
📱 *Bot:* @{bot_info.get('username', 'unknown')}
📌 *Chat ID:* {TELEGRAM_CHAT_ID}

🚀 *Ready to monitor!*
    """
    
    send_result = test_send_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, test_message)
    if send_result.get("success"):
        logger.info("✅ Pesan test berhasil terkirim!")
        print("\n📱 *CEK TELEGRAM ANDA!*")
    else:
        logger.error(f"❌ Gagal kirim pesan: {send_result.get('error')}")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
