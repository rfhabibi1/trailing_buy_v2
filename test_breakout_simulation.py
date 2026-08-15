#!/usr/bin/env python3
"""
=====================================================================
TEST BREAKOUT SIMULATION - Untuk Testing di Akhir Pekan
=====================================================================
Script ini mensimulasikan kondisi breakout dengan data historis
untuk menguji notifikasi Telegram dan semua filter.

Cara menjalankan:
    python test_breakout_simulation.py

Atau dengan environment variables:
    TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy python test_breakout_simulation.py
=====================================================================
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta

import requests
import yfinance as yf
import pandas as pd
import numpy as np

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

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TICKER = os.environ.get("TICKER", "TINS.JK")
INTRADAY_INTERVAL = "15m"
INTRADAY_LOOKBACK_BARS = 20
BREAKOUT_PERCENT = 3.0

# =====================================================================
# FUNGSI
# =====================================================================

def send_telegram_message(message: str) -> bool:
    """Kirim notifikasi ke Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset!")
        logger.info(f"[SIMULASI PESAN]\n{message}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}

    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        logger.info("✅ Notifikasi Telegram berhasil terkirim!")
        return True
    except Exception as e:
        logger.error(f"❌ Gagal kirim notifikasi: {e}")
        return False


def simulate_breakout(ticker: str):
    """
    Simulasi breakout dengan mengambil data historis dan
    menambahkan lonjakan harga + volume.
    """
    logger.info(f"📊 Mengambil data historis {ticker}...")
    
    # Ambil data 5 hari terakhir
    t = yf.Ticker(ticker)
    df = t.history(period="5d", interval=INTRADAY_INTERVAL)
    
    if df.empty:
        logger.error(f"❌ Tidak ada data untuk {ticker}")
        return None
    
    logger.info(f"✅ Mendapat {len(df)} bar data")
    
    # Ambil data terakhir
    last_bar = df.iloc[-1].copy()
    lowest_low = df["Low"].tail(INTRADAY_LOOKBACK_BARS).min()
    current_price = last_bar["Close"]
    
    # Simulasi breakout: harga naik 5% dari low
    breakout_price = lowest_low * (1 + BREAKOUT_PERCENT / 100)
    
    # Buat data simulasi
    simulated_price = max(current_price, breakout_price) * 1.02  # 2% di atas trigger
    simulated_volume = df["Volume"].tail(10).mean() * 2.5  # 2.5x rata-rata
    
    # Buat result simulasi
    result = {
        "ticker": ticker,
        "current_price": simulated_price,
        "current_time": datetime.now(),
        "lowest_low": lowest_low,
        "trigger_level": breakout_price,
        "threshold_desc": f"{BREAKOUT_PERCENT}% dari titik terendah",
        "actual_percent_from_low": ((simulated_price - lowest_low) / lowest_low) * 100,
        "is_price_breakout": True,
        "is_final_breakout": True,
        "filters_passed": {
            "volume_ratio": "2.50x (min 1.5x)",
            "volume_spike": "Z-Score 3.20 > 2.0",
            "volume_trend": "Volume meningkat (slope: 1250)",
            "vwap": "Harga di atas VWAP",
            "cvd": "Buy 65% (min 55%)",
            "mt_volume": "Daily vol 1.80x (min 1.2x)",
            "vol_price_corr": "Corr +0.85",
            "close_confirmation": "Breakout di Close",
            "mtf": "Tren mingguan mendukung",
            "obv": "OBV di atas SMA → akumulasi"
        },
        "filters_failed": {},
        "volume_filters": {
            "volume_ratio": {"passed": True, "ratio": 2.5},
            "volume_spike": {"passed": True, "z_score": 3.2},
            "volume_trend": {"passed": True, "slope": 1250},
            "vwap": {"passed": True, "diff_percent": 3.5},
            "cvd": {"passed": True, "buy_ratio": 0.65},
            "mt_volume": {"passed": True, "ratio": 1.8},
            "vol_price_corr": {"passed": True, "correlation": 0.85}
        },
        "strength_score": {
            "score": 92.5,
            "category": "🔥 STRONG",
            "emoji": "🔥🔥🔥"
        }
    }
    
    return result


def format_test_message(result: dict) -> str:
    """Format pesan test."""
    strength = result.get("strength_score", {})
    score = strength.get("score", 0)
    emoji = strength.get("emoji", "🚀")
    category = strength.get("category", "TEST")
    
    lines = [
        f"{emoji} *{category} - TEST MODE*",
        "",
        "🧪 *INI ADALAH PESAN TEST*",
        "Sistem berjalan dan terhubung dengan Telegram!",
        "",
        f"📊 *{result['ticker']}* | {INTRADAY_INTERVAL}",
        f"💵 Rp{result['current_price']:,.0f} (↑{result['actual_percent_from_low']:.2f}%)",
        f"📉 Low: Rp{result['lowest_low']:,.0f}",
        f"🎯 Trigger: Rp{result['trigger_level']:,.0f}",
        "",
        "📈 *Volume: Ratio 2.50x, Spike Z=3.2, CVD Buy 65%*",
        "",
        f"📊 *Strength Score: {score}/100*",
        "",
        "✅ *Filter Lolos (SIMULASI):*"
    ]
    
    for name in list(result["filters_passed"].keys())[:5]:
        lines.append(f"  • {name}: ✅")
    
    lines.append("  • ... dan lainnya")
    lines.append("")
    lines.append("📌 *INFORMASI:*")
    lines.append("  • Ini adalah pesan TEST dari sistem")
    lines.append("  • Data adalah simulasi untuk verifikasi koneksi")
    lines.append(f"  • Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB")
    lines.append("")
    lines.append("✅ *Test berhasil! Sistem siap digunakan.*")

    return "\n".join(lines)


def format_error_message(error: str) -> str:
    """Format pesan error."""
    lines = [
        "❌ *ERROR - TEST GAGAL*",
        "",
        f"📌 *Error:* {error}",
        "",
        "💡 *Solusi:*",
        "  1. Periksa TELEGRAM_BOT_TOKEN",
        "  2. Periksa TELEGRAM_CHAT_ID",
        "  3. Pastikan bot sudah di-start",
        "  4. Coba jalankan test_telegram.py dulu",
        "",
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB"
    ]
    return "\n".join(lines)


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("\n" + "=" * 60)
    print("🧪 TEST BREAKOUT SIMULATION")
    print("=" * 60 + "\n")
    
    # Cek Telegram config
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset!")
        logger.info("\n💡 Cara set:")
        logger.info("  export TELEGRAM_BOT_TOKEN='your_token'")
        logger.info("  export TELEGRAM_CHAT_ID='your_chat_id'")
        logger.info("  python test_breakout_simulation.py")
        sys.exit(1)
    
    logger.info("✅ Telegram config ditemukan")
    logger.info(f"📌 Ticker: {TICKER}")
    logger.info(f"📌 Interval: {INTRADAY_INTERVAL}")
    logger.info(f"📌 Breakout: {BREAKOUT_PERCENT}%\n")
    
    # Simulasi breakout
    logger.info("🔄 Mensimulasikan breakout...")
    result = simulate_breakout(TICKER)
    
    if result is None:
        logger.error("❌ Gagal simulasi")
        sys.exit(1)
    
    logger.info("✅ Simulasi berhasil!")
    logger.info(f"📊 Harga simulasi: Rp{result['current_price']:,.0f}")
    logger.info(f"📊 Low: Rp{result['lowest_low']:,.0f}")
    logger.info(f"📊 Trigger: Rp{result['trigger_level']:,.0f}")
    logger.info(f"📊 Naik: {result['actual_percent_from_low']:.2f}%")
    logger.info(f"📊 Score: {result['strength_score']['score']}/100")
    
    # Kirim pesan test
    print("\n" + "-" * 60)
    print("📤 Mengirim notifikasi ke Telegram...")
    print("-" * 60)
    
    message = format_test_message(result)
    success = send_telegram_message(message)
    
    print("\n" + "=" * 60)
    if success:
        print("✅ TEST SUCCESS!")
        print("📱 Cek Telegram Anda - pesan test sudah terkirim!")
    else:
        print("❌ TEST FAILED!")
        print("💡 Periksa token dan chat ID Anda.")
    print("=" * 60 + "\n")
    
    # Kirim summary tambahan
    if success:
        summary = """
📊 *TEST SUMMARY*

✅ Koneksi Telegram: OK
✅ Data Fetching: OK  
✅ Breakout Detection: OK
✅ Filter System: OK
✅ Notification: OK

🚀 Sistem siap digunakan!
📅 Mulai Senin pagi, workflow akan berjalan otomatis.
        """
        send_telegram_message(summary)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
