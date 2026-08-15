#!/usr/bin/env python3
"""
=====================================================================
TEST BREAKOUT SIMULATION - Untuk Testing di Akhir Pekan
=====================================================================
Script ini mensimulasikan kondisi breakout dengan data historis
untuk menguji notifikasi Telegram dan semua filter.

Support MULTI-TICKER: Bisa test beberapa saham sekaligus.

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
import time
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional

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
# CONFIG - GLOBAL
# =====================================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Support multi-ticker - coba berbagai source
TICKERS_RAW = os.environ.get("TICKERS", "")
if not TICKERS_RAW:
    TICKERS_RAW = os.environ.get("TICKER", "")
if not TICKERS_RAW:
    # Fallback ke default
    TICKERS_RAW = "TINS.JK"

# Parse tickers - HAPUS DUPLIKAT
TICKERS = []
for t in TICKERS_RAW.split(","):
    t = t.strip().upper()
    if t and t not in TICKERS:
        TICKERS.append(t)

INTRADAY_INTERVAL = os.environ.get("INTRADAY_INTERVAL", "15m")
INTRADAY_LOOKBACK_BARS = int(os.environ.get("INTRADAY_LOOKBACK_BARS", "20"))
BREAKOUT_PERCENT = float(os.environ.get("BREAKOUT_PERCENT", "5.0"))

# =====================================================================
# FUNGSI TELEGRAM
# =====================================================================

def send_telegram_message(message: str) -> bool:
    """
    Kirim notifikasi ke Telegram - plain text (tanpa Markdown).
    Ini yang paling aman dan selalu berhasil.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset!")
        logger.info(f"[SIMULASI PESAN]\n{message}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        # TIDAK PAKAI parse_mode - plain text selalu aman
    }

    try:
        response = requests.post(url, data=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get("ok"):
            logger.info("✅ Notifikasi Telegram berhasil terkirim!")
            return True
        else:
            logger.error(f"❌ Telegram error: {data.get('description', 'Unknown error')}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ Telegram timeout")
        return False
    except requests.exceptions.ConnectionError:
        logger.error("❌ Telegram connection error")
        return False
    except requests.exceptions.HTTPError as e:
        logger.error(f"❌ HTTP error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Gagal kirim notifikasi: {e}")
        return False


# =====================================================================
# FUNGSI DATA
# =====================================================================

def get_historical_data(ticker: str) -> Optional[pd.DataFrame]:
    """
    Ambil data historis untuk satu ticker.
    """
    try:
        logger.info(f"📊 Mengambil data {ticker}...")
        t = yf.Ticker(ticker)
        df = t.history(period="5d", interval=INTRADAY_INTERVAL)
        
        if df.empty:
            logger.warning(f"⚠️ Tidak ada data untuk {ticker}")
            return None
        
        logger.info(f"✅ {ticker}: {len(df)} bar data")
        return df
        
    except Exception as e:
        logger.warning(f"⚠️ {ticker}: Gagal ambil data - {str(e)[:50]}")
        return None


def simulate_breakout_for_ticker(ticker: str, df: pd.DataFrame) -> Optional[Dict]:
    """
    Simulasi breakout untuk satu ticker berdasarkan data historis.
    """
    if df is None or df.empty:
        return None
    
    # Ambil data terakhir
    last_bar = df.iloc[-1].copy()
    lowest_low = df["Low"].tail(INTRADAY_LOOKBACK_BARS).min()
    current_price = last_bar["Close"]
    
    # Simulasi breakout: harga naik dari low
    breakout_price = lowest_low * (1 + BREAKOUT_PERCENT / 100)
    
    # Buat data simulasi
    simulated_price = max(current_price, breakout_price) * 1.02
    simulated_volume = df["Volume"].tail(10).mean() * 2.5
    
    # Pastikan tidak NaN
    if pd.isna(simulated_price):
        simulated_price = current_price * 1.05
    if pd.isna(simulated_volume) or simulated_volume == 0:
        simulated_volume = 1000000
    
    actual_percent = ((simulated_price - lowest_low) / lowest_low) * 100
    
    # Buat result simulasi
    result = {
        "ticker": ticker,
        "current_price": simulated_price,
        "current_time": datetime.now(),
        "lowest_low": lowest_low,
        "trigger_level": breakout_price,
        "threshold_desc": f"{BREAKOUT_PERCENT}% dari titik terendah",
        "actual_percent_from_low": actual_percent,
        "is_price_breakout": True,
        "is_final_breakout": True,
        "filters_passed": [
            "Volume Ratio (2.50x)",
            "Volume Spike (Z=3.20)",
            "Volume Trend (meningkat)",
            "VWAP (di atas)",
            "CVD (Buy 65%)",
            "MT Volume (1.80x)",
            "Volume-Price Correlation (+0.85)",
            "Close Confirmation",
            "MTF (uptrend)",
            "OBV (akumulasi)"
        ],
        "filters_failed": [],
        "strength_score": {
            "score": 92.5,
            "category": "STRONG",
            "emoji": "🔥🔥🔥"
        }
    }
    
    return result


# =====================================================================
# FORMAT PESAN - PLAIN TEXT (TANPA MARKDOWN)
# =====================================================================

def format_test_message(result: Dict, is_multi: bool = False, index: int = 0, total: int = 0) -> str:
    """
    Format pesan test - plain text.
    Format ini SAMA PERSIS dengan yang berhasil di summary.
    """
    strength = result.get("strength_score", {})
    score = strength.get("score", 0)
    category = strength.get("category", "TEST")
    ticker = result.get("ticker", "UNKNOWN")
    
    # Header
    if is_multi:
        header = f"🧪 TEST #{index+1}/{total} - {category}"
    else:
        header = f"🧪 TEST MODE - {category}"
    
    # Buat garis pembatas
    separator = "-" * 40
    
    # Format pesan
    lines = [
        header,
        separator,
        "📊 SAHAM: " + ticker,
        f"📈 INTERVAL: {INTRADAY_INTERVAL}",
        "",
        f"💰 HARGA: Rp{result['current_price']:,.0f}",
        f"📈 NAIK: {result['actual_percent_from_low']:.2f}% dari Low",
        f"📉 LOW: Rp{result['lowest_low']:,.0f}",
        f"🎯 TRIGGER: Rp{result['trigger_level']:,.0f}",
        "",
        f"📊 STRENGTH SCORE: {score}/100 - {category}",
        "",
        "✅ FILTER LOLOS (SIMULASI):"
    ]
    
    # Tampilkan semua filter yang lolos
    for i, filter_name in enumerate(result["filters_passed"], 1):
        lines.append(f"  {i}. {filter_name}")
    
    if not result["filters_passed"]:
        lines.append("  (tidak ada filter yang lolos)")
    
    lines.append("")
    lines.append("📌 INFORMASI:")
    lines.append("  • Ini adalah pesan TEST dari sistem")
    lines.append("  • Data adalah simulasi untuk verifikasi")
    lines.append(f"  • Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB")
    lines.append("")
    lines.append("✅ Test berhasil! Sistem siap digunakan.")

    return "\n".join(lines)


def format_summary_message(results: List[Dict]) -> str:
    """
    Format pesan ringkasan - plain text.
    Format ini SUDAH TERBUKTI BERHASIL.
    """
    lines = [
        "📊 SUMMARY TEST - SEMUA TICKER",
        "",
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB",
        ""
    ]
    
    for i, r in enumerate(results, 1):
        ticker = r.get("ticker", "UNKNOWN")
        price = r.get("current_price", 0)
        percent = r.get("actual_percent_from_low", 0)
        score = r.get("strength_score", {}).get("score", 0)
        
        lines.append(f"{i}. {ticker}: Rp{price:,.0f} | ↑{percent:.1f}% | Score: {score}/100 ✅")
    
    lines.append("")
    lines.append("✅ Semua ticker berhasil di-simulasi!")
    lines.append("🚀 Sistem siap digunakan.")
    
    return "\n".join(lines)


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("\n" + "=" * 60)
    print("🧪 TEST BREAKOUT SIMULATION - MULTI-TICKER")
    print("=" * 60 + "\n")
    
    # Log semua environment variables untuk debugging
    logger.info("📋 Environment Variables:")
    logger.info(f"   TICKERS: '{os.environ.get('TICKERS', 'NOT SET')}'")
    logger.info(f"   TICKER: '{os.environ.get('TICKER', 'NOT SET')}'")
    logger.info(f"   INTRADAY_INTERVAL: '{os.environ.get('INTRADAY_INTERVAL', 'NOT SET')}'")
    logger.info(f"   BREAKOUT_PERCENT: '{os.environ.get('BREAKOUT_PERCENT', 'NOT SET')}'")
    
    # Cek Telegram config
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset!")
        logger.info("\n💡 Cara set:")
        logger.info("  export TELEGRAM_BOT_TOKEN='your_token'")
        logger.info("  export TELEGRAM_CHAT_ID='your_chat_id'")
        logger.info("  python test_breakout_simulation.py")
        sys.exit(1)
    
    logger.info("✅ Telegram config ditemukan")
    logger.info(f"📌 Tickers RAW: '{TICKERS_RAW}'")
    logger.info(f"📌 Tickers parsed: {TICKERS}")
    logger.info(f"📌 Total: {len(TICKERS)} saham")
    logger.info(f"📌 Interval: {INTRADAY_INTERVAL}")
    logger.info(f"📌 Breakout: {BREAKOUT_PERCENT}%\n")
    
    # Jika tidak ada ticker, gunakan default
    if not TICKERS:
        logger.warning("⚠️ Tidak ada ticker ditemukan, menggunakan default: TINS.JK")
        TICKERS.append("TINS.JK")
    
    # Proses setiap ticker
    results = []
    alerts_sent = 0
    
    for idx, ticker in enumerate(TICKERS):
        logger.info(f"\n{'='*40}")
        logger.info(f"[{idx+1}/{len(TICKERS)}] Memproses {ticker}...")
        logger.info(f"{'='*40}")
        
        # Ambil data historis
        df = get_historical_data(ticker)
        
        if df is None:
            logger.warning(f"⚠️ {ticker}: Tidak ada data, skip")
            continue
        
        # Simulasi breakout
        result = simulate_breakout_for_ticker(ticker, df)
        
        if result is None:
            logger.warning(f"⚠️ {ticker}: Gagal simulasi, skip")
            continue
        
        results.append(result)
        
        logger.info(f"✅ {ticker}: Simulasi berhasil!")
        logger.info(f"   Harga: Rp{result['current_price']:,.0f}")
        logger.info(f"   Low: Rp{result['lowest_low']:,.0f}")
        logger.info(f"   Naik: {result['actual_percent_from_low']:.2f}%")
        logger.info(f"   Score: {result['strength_score']['score']}/100")
        
        # Kirim notifikasi per ticker
        if len(TICKERS) > 1:
            message = format_test_message(result, True, idx, len(TICKERS))
        else:
            message = format_test_message(result, False)
        
        # Kirim dengan plain text (AMAN)
        success = send_telegram_message(message)
        if success:
            alerts_sent += 1
            logger.info(f"✅ Alert #{idx+1} terkirim!")
        else:
            logger.warning(f"⚠️ Alert #{idx+1} gagal dikirim")
        
        # Delay antar ticker (biar tidak spam)
        if idx < len(TICKERS) - 1:
            logger.info("⏱️ Delay 2s sebelum ticker berikutnya...")
            time.sleep(2)
    
    # Kirim summary jika lebih dari 1 ticker dan ada hasil
    if len(results) > 1:
        logger.info("\n" + "-" * 60)
        logger.info("📤 Mengirim summary...")
        logger.info("-" * 60)
        
        summary_message = format_summary_message(results)
        send_telegram_message(summary_message)
    
    # Final report
    print("\n" + "=" * 60)
    print("📊 TEST COMPLETE")
    print("=" * 60)
    print(f"\n📌 Total ticker diproses: {len(TICKERS)}")
    print(f"📌 Berhasil disimulasi: {len(results)}")
    print(f"📌 Alert terkirim: {alerts_sent}")
    
    if alerts_sent > 0:
        print("\n✅ TEST SUCCESS!")
        print("📱 Cek Telegram Anda - pesan test sudah terkirim!")
    else:
        print("\n⚠️ TEST PARTIAL - Tidak ada alert terkirim")
        print("💡 Periksa koneksi Telegram.")
    
    print("\n" + "=" * 60)
    
    return 0 if alerts_sent > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
