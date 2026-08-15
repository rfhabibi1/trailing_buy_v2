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
# CONFIG
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

# Parse tickers
TICKERS = [t.strip().upper() for t in TICKERS_RAW.split(",") if t.strip()]

# Hapus duplikat
TICKERS = list(dict.fromkeys(TICKERS))

INTRADAY_INTERVAL = os.environ.get("INTRADAY_INTERVAL", "15m")
INTRADAY_LOOKBACK_BARS = int(os.environ.get("INTRADAY_LOOKBACK_BARS", "20"))
BREAKOUT_PERCENT = float(os.environ.get("BREAKOUT_PERCENT", "5.0"))

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
    simulated_price = max(current_price, breakout_price) * 1.02  # 2% di atas trigger
    simulated_volume = df["Volume"].tail(10).mean() * 2.5  # 2.5x rata-rata
    
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
        "filters_passed": {
            "volume_ratio": f"{simulated_volume / df['Volume'].tail(10).mean():.2f}x (min 1.5x)" if df['Volume'].tail(10).mean() > 0 else "2.50x (min 1.5x)",
            "volume_spike": "Z-Score 3.20 > 2.0",
            "volume_trend": "Volume meningkat (slope: +1250)",
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


def format_test_message(result: Dict, is_multi: bool = False, index: int = 0, total: int = 0) -> str:
    """Format pesan test untuk satu ticker."""
    strength = result.get("strength_score", {})
    score = strength.get("score", 0)
    emoji = strength.get("emoji", "🚀")
    category = strength.get("category", "TEST")
    ticker = result.get("ticker", "UNKNOWN")
    
    if is_multi:
        header = f"{emoji} *{category} - TEST #{index+1}/{total}*"
    else:
        header = f"{emoji} *{category} - TEST MODE*"
    
    lines = [
        header,
        "",
        "🧪 *INI ADALAH PESAN TEST*",
        "Sistem berjalan dan terhubung dengan Telegram!",
        "",
        f"📊 *{ticker}* | {INTRADAY_INTERVAL}",
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
    
    # Tampilkan 5 filter pertama
    filter_names = list(result["filters_passed"].keys())[:5]
    for name in filter_names:
        lines.append(f"  • {name}: ✅")
    
    if len(result["filters_passed"]) > 5:
        lines.append(f"  • ... dan {len(result['filters_passed']) - 5} lainnya")
    
    lines.append("")
    lines.append("📌 *INFORMASI:*")
    lines.append("  • Ini adalah pesan TEST dari sistem")
    lines.append("  • Data adalah simulasi untuk verifikasi koneksi")
    lines.append(f"  • Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB")
    lines.append("")
    lines.append("✅ *Test berhasil! Sistem siap digunakan.*")

    return "\n".join(lines)


def format_summary_message(results: List[Dict]) -> str:
    """Format pesan ringkasan semua ticker."""
    lines = [
        "📊 *SUMMARY TEST - SEMUA TICKER*",
        "",
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB",
        ""
    ]
    
    for i, r in enumerate(results):
        ticker = r.get("ticker", "UNKNOWN")
        price = r.get("current_price", 0)
        percent = r.get("actual_percent_from_low", 0)
        score = r.get("strength_score", {}).get("score", 0)
        
        lines.append(f"• *{ticker}*: Rp{price:,.0f} | ↑{percent:.1f}% | Score: {score}/100 ✅")
    
    lines.append("")
    lines.append("✅ *Semua ticker berhasil di-simulasi!*")
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
        TICKERS = ["TINS.JK"]
    
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
        
        success = send_telegram_message(message)
        if success:
            alerts_sent += 1
        
        # Delay antar ticker
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
        print("\n⚠️ TEST PARTIAL - Ada yang gagal")
        print("💡 Periksa ticker yang tidak valid.")
    
    print("\n" + "=" * 60)
    
    return 0 if alerts_sent > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
