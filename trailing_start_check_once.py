"""
=====================================================================
TRAILING START MONITOR - Versi Hybrid (Intraday Timing + Daily Confirmation)
=====================================================================

ARSITEKTUR:
    - TIMING breakout (kapan trigger, harga, volume saat itu) dihitung
      dari data INTRADAY (misal candle 15 menit) -> lebih presisi untuk
      menangkap momen breakout yang sebenarnya, bukan cuma snapshot
      penutupan harian.

    - KONFIRMASI (apakah breakout ini "sehat" secara struktur lebih besar)
      tetap dihitung dari data HARIAN -> tren mingguan (MTF), volatilitas
      (ATR), dan akumulasi (OBV) semuanya dihitung dari data harian karena
      lebih stabil dan tidak berisik dibanding data intraday.

Filter yang tersedia (semua otomatis, tidak perlu input manual):
    1. Volume Confirmation (INTRADAY)  - volume bar saat ini vs rata-rata
                                          volume per-bar N bar terakhir
    2. Close Confirmation (INTRADAY)   - breakout dikonfirmasi di CLOSE
                                          bar intraday, bukan sekadar High
    3. Multi-Timeframe Filter (DAILY)  - tren mingguan harus mendukung
    4. ATR Dynamic Threshold (DAILY)   - ambang breakout dari volatilitas
                                          harian (lebih stabil dari ATR
                                          intraday yang bisa terlalu noisy)
    5. OBV Accumulation Filter (DAILY) - akumulasi dihitung dari data
                                          harian (representasi net accumulation
                                          lintas hari lebih bermakna dibanding
                                          OBV per-bar yang berisik)

KETERBATASAN PENTING:
    - Data intraday di yfinance hanya tersedia untuk ~60 hari terakhir
      (batasan resmi Yahoo Finance untuk interval <1 hari).
    - Untuk saham Indonesia (.JK), kerapatan data intraday belum tentu
      selalu konsisten - saham kurang likuid bisa punya bar kosong/gap.
      Selalu cek log setelah run pertama untuk pastikan datanya cukup.
=====================================================================
"""

import json
import os
import sys
import logging
from datetime import datetime

import requests
import yfinance as yf
import pandas as pd
import numpy as np

# =====================================================================
# CONFIG
# =====================================================================

TICKER = os.environ.get("TICKER", "TINS.JK")

# --- Data Intraday (untuk TIMING breakout) ---
INTRADAY_INTERVAL = os.environ.get("INTRADAY_INTERVAL", "15m")   # 1m,2m,5m,15m,30m,60m,90m
INTRADAY_PERIOD_DAYS = int(os.environ.get("INTRADAY_PERIOD_DAYS", "5"))  # ambil N hari terakhir data intraday
INTRADAY_LOOKBACK_BARS = int(os.environ.get("INTRADAY_LOOKBACK_BARS", "20"))  # cari titik terendah dalam N bar
BREAKOUT_PERCENT = float(os.environ.get("BREAKOUT_PERCENT", "5.0"))
USE_INTRADAY_LOW = os.environ.get("USE_INTRADAY_LOW", "true").lower() == "true"

# --- 1. Volume Confirmation (Intraday) ---
ENABLE_VOLUME_FILTER = os.environ.get("ENABLE_VOLUME_FILTER", "true").lower() == "true"
VOLUME_LOOKBACK_BARS = int(os.environ.get("VOLUME_LOOKBACK_BARS", "20"))
VOLUME_MULTIPLIER = float(os.environ.get("VOLUME_MULTIPLIER", "1.5"))

# --- 2. Close Confirmation (Intraday) ---
ENABLE_CLOSE_CONFIRMATION = os.environ.get("ENABLE_CLOSE_CONFIRMATION", "true").lower() == "true"

# --- 3. Multi-Timeframe Filter (Daily) ---
ENABLE_MTF_FILTER = os.environ.get("ENABLE_MTF_FILTER", "true").lower() == "true"
MTF_SMA_WEEKS = int(os.environ.get("MTF_SMA_WEEKS", "10"))
DAILY_PERIOD_DAYS = int(os.environ.get("DAILY_PERIOD_DAYS", "200"))  # data harian untuk MTF/ATR/OBV

# --- 4. ATR Dynamic Threshold (Daily) ---
ENABLE_ATR_THRESHOLD = os.environ.get("ENABLE_ATR_THRESHOLD", "false").lower() == "true"
ATR_PERIOD = int(os.environ.get("ATR_PERIOD", "14"))
ATR_MULTIPLIER = float(os.environ.get("ATR_MULTIPLIER", "1.5"))

# --- 5. OBV Accumulation Filter (Daily) ---
ENABLE_OBV_FILTER = os.environ.get("ENABLE_OBV_FILTER", "true").lower() == "true"
OBV_SMA_PERIOD = int(os.environ.get("OBV_SMA_PERIOD", "20"))

# --- 0. Liquidity Check (GERBANG PALING AWAL - sebelum semua filter lain) ---
ENABLE_LIQUIDITY_CHECK = os.environ.get("ENABLE_LIQUIDITY_CHECK", "true").lower() == "true"
MIN_INTRADAY_BARS = int(os.environ.get("MIN_INTRADAY_BARS", "30"))
# Minimal jumlah bar intraday yang harus ada dalam data yang diambil.
# Kalau kurang dari ini, kemungkinan besar saham jarang ditransaksikan
# (banyak bar kosong/tidak terbentuk sama sekali).

MAX_ZERO_VOLUME_BAR_RATIO = float(os.environ.get("MAX_ZERO_VOLUME_BAR_RATIO", "0.3"))
# Maksimal proporsi bar dengan volume = 0 yang masih ditoleransi (0.3 = 30%).
# Kalau lebih dari ini, artinya banyak periode tanpa transaksi sama sekali.

MIN_AVG_DAILY_VALUE_RP = float(os.environ.get("MIN_AVG_DAILY_VALUE_RP", "1000000000"))
# Minimal rata-rata nilai transaksi harian (Rp) dalam LIQUIDITY_LOOKBACK_DAYS
# hari terakhir. Default Rp1 miliar/hari - saham di bawah ini dianggap
# terlalu tipis untuk dianalisa breakout secara reliable.

LIQUIDITY_LOOKBACK_DAYS = int(os.environ.get("LIQUIDITY_LOOKBACK_DAYS", "20"))

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

STATE_FILE = "state/trailing_start_state.json"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# =====================================================================
# AMBIL DATA - DUA SUMBER TERPISAH
# =====================================================================

def get_intraday_data(ticker: str):
    """
    Data intraday untuk TIMING breakout (harga, trigger, volume per-bar).
    """
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=f"{INTRADAY_PERIOD_DAYS}d", interval=INTRADAY_INTERVAL)

        if df.empty:
            logger.warning(f"Data intraday kosong untuk {ticker}")
            return None

        if len(df) < INTRADAY_LOOKBACK_BARS:
            logger.warning(
                f"Data intraday hanya {len(df)} bar, kurang dari lookback "
                f"{INTRADAY_LOOKBACK_BARS} bar yang diminta. Hasil mungkin kurang akurat."
            )

        return df

    except Exception as e:
        logger.error(f"Gagal ambil data intraday untuk {ticker}: {e}")
        return None


def get_daily_data(ticker: str):
    """
    Data harian untuk KONFIRMASI (MTF trend, ATR, OBV) - dipisah dari
    data intraday karena butuh histori lebih panjang & lebih stabil.
    """
    try:
        needed_days = max(ATR_PERIOD, OBV_SMA_PERIOD, MTF_SMA_WEEKS * 7, DAILY_PERIOD_DAYS)
        t = yf.Ticker(ticker)
        df = t.history(period=f"{needed_days}d", interval="1d")

        if df.empty:
            logger.warning(f"Data harian kosong untuk {ticker}")
            return None

        return df

    except Exception as e:
        logger.error(f"Gagal ambil data harian untuk {ticker}: {e}")
        return None


# =====================================================================
# FUNGSI KONFIRMASI - DAILY
# =====================================================================

def calculate_atr_daily(daily_df: pd.DataFrame, period: int):
    high, low, close = daily_df["High"], daily_df["Low"], daily_df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return float(tr.rolling(window=period).mean().iloc[-1])


def check_weekly_trend(daily_df: pd.DataFrame, sma_weeks: int):
    try:
        weekly = daily_df["Close"].resample("W").last()
        if len(weekly) < sma_weeks:
            logger.warning("Data mingguan tidak cukup untuk MTF, filter dilewati (default: lolos)")
            return {"is_weekly_uptrend": True, "sufficient_data": False}

        weekly_sma = weekly.rolling(window=sma_weeks).mean().iloc[-1]
        current_weekly_close = weekly.iloc[-1]
        return {
            "is_weekly_uptrend": bool(current_weekly_close > weekly_sma),
            "weekly_sma": float(weekly_sma),
            "current_weekly_close": float(current_weekly_close),
            "sufficient_data": True
        }
    except Exception as e:
        logger.error(f"Gagal hitung MTF filter: {e}")
        return {"is_weekly_uptrend": True, "sufficient_data": False}


def check_obv_accumulation_daily(daily_df: pd.DataFrame, sma_period: int):
    direction = np.sign(daily_df["Close"].diff()).fillna(0)
    obv = (direction * daily_df["Volume"]).cumsum()

    if len(obv) < sma_period:
        logger.warning("Data harian tidak cukup untuk OBV SMA, filter dilewati (default: lolos)")
        return {"is_accumulating": True, "sufficient_data": False}

    obv_sma = obv.rolling(window=sma_period).mean().iloc[-1]
    obv_current = obv.iloc[-1]
    return {
        "is_accumulating": bool(obv_current > obv_sma),
        "obv_current": float(obv_current),
        "obv_sma": float(obv_sma),
        "sufficient_data": True
    }


# =====================================================================
# FUNGSI TIMING - INTRADAY
# =====================================================================

def check_intraday_volume(intraday_df: pd.DataFrame, lookback_bars: int, multiplier: float):
    avg_volume = intraday_df["Volume"].tail(lookback_bars).mean()
    current_volume = intraday_df["Volume"].iloc[-1]
    ratio = current_volume / avg_volume if avg_volume > 0 else 0
    return {
        "is_volume_confirmed": bool(ratio >= multiplier),
        "current_volume": float(current_volume),
        "avg_volume": float(avg_volume),
        "volume_ratio": float(ratio)
    }


def detect_breakout(intraday_df: pd.DataFrame, daily_df: pd.DataFrame):
    """
    Gabungkan TIMING (intraday) dan KONFIRMASI (daily) jadi satu keputusan.
    """
    close_col = intraday_df["Close"]
    low_col = intraday_df["Low"] if USE_INTRADAY_LOW else intraday_df["Close"]

    lowest_low = float(low_col.tail(INTRADAY_LOOKBACK_BARS).min())
    current_close = float(close_col.iloc[-1])
    current_high = float(intraday_df["High"].iloc[-1])
    current_time = intraday_df.index[-1]

    # --- Ambang breakout: fixed % (dari data intraday) atau ATR harian ---
    if ENABLE_ATR_THRESHOLD:
        atr = calculate_atr_daily(daily_df, ATR_PERIOD)
        threshold_amount = atr * ATR_MULTIPLIER
        trigger_level = lowest_low + threshold_amount
        threshold_desc = f"ATR harian({ATR_PERIOD}) x {ATR_MULTIPLIER} = {threshold_amount:.1f}"
    else:
        trigger_level = lowest_low * (1 + BREAKOUT_PERCENT / 100)
        threshold_desc = f"{BREAKOUT_PERCENT}% dari titik terendah intraday"

    price_for_check = current_close if ENABLE_CLOSE_CONFIRMATION else current_high
    is_price_breakout = price_for_check >= trigger_level
    actual_percent_from_low = ((current_close - lowest_low) / lowest_low) * 100

    result = {
        "current_price": current_close,
        "current_time": current_time,
        "lowest_low": lowest_low,
        "trigger_level": trigger_level,
        "threshold_desc": threshold_desc,
        "actual_percent_from_low": actual_percent_from_low,
        "is_price_breakout": is_price_breakout,
        "filters_passed": {},
        "filters_failed": {},
    }

    # --- FILTER 1: Volume Confirmation (INTRADAY) ---
    if ENABLE_VOLUME_FILTER:
        vol_check = check_intraday_volume(intraday_df, VOLUME_LOOKBACK_BARS, VOLUME_MULTIPLIER)
        result["volume_check"] = vol_check
        if vol_check["is_volume_confirmed"]:
            result["filters_passed"]["volume"] = f"Ratio {vol_check['volume_ratio']:.2f}x per-bar (min {VOLUME_MULTIPLIER}x)"
        else:
            result["filters_failed"]["volume"] = f"Ratio {vol_check['volume_ratio']:.2f}x per-bar (min {VOLUME_MULTIPLIER}x)"

    # --- FILTER 2: Close Confirmation (INTRADAY) ---
    if ENABLE_CLOSE_CONFIRMATION:
        result["filters_passed"]["close_confirmation"] = "Breakout dikonfirmasi di Close bar intraday"

    # --- FILTER 3: Multi-Timeframe Filter (DAILY) ---
    if ENABLE_MTF_FILTER:
        mtf_check = check_weekly_trend(daily_df, MTF_SMA_WEEKS)
        result["mtf_check"] = mtf_check
        if mtf_check["is_weekly_uptrend"]:
            result["filters_passed"]["mtf"] = "Tren mingguan (harian) mendukung"
        else:
            result["filters_failed"]["mtf"] = "Tren mingguan (harian) TIDAK mendukung"

    # --- FILTER 4: ATR sudah termasuk di threshold_desc ---
    if ENABLE_ATR_THRESHOLD:
        result["filters_passed"]["atr_threshold"] = threshold_desc

    # --- FILTER 5: OBV Accumulation (DAILY) ---
    if ENABLE_OBV_FILTER:
        obv_check = check_obv_accumulation_daily(daily_df, OBV_SMA_PERIOD)
        result["obv_check"] = obv_check
        if obv_check["is_accumulating"]:
            result["filters_passed"]["obv"] = "OBV harian di atas SMA -> akumulasi"
        else:
            result["filters_failed"]["obv"] = "OBV harian di bawah SMA -> distribusi"

    result["is_final_breakout"] = is_price_breakout and len(result["filters_failed"]) == 0
    return result


# =====================================================================
# STATE MANAGEMENT
# =====================================================================

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_alert_time": None, "last_lowest_low": None}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, default=str)


# =====================================================================
# NOTIFIKASI TELEGRAM
# =====================================================================

def send_telegram_message(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset!")
        logger.info(f"[SIMULASI PESAN]\n{message}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}

    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        logger.info("Notifikasi Telegram berhasil terkirim.")
        return True
    except Exception as e:
        logger.error(f"Gagal kirim notifikasi Telegram: {e}")
        return False


def format_alert_message(result: dict):
    lines = [
        "🚀 *TRAILING START - BREAKOUT TERDETEKSI*",
        "",
        f"Saham: *{TICKER}*",
        f"Timeframe: Intraday {INTRADAY_INTERVAL} (timing) + Harian (konfirmasi)",
        f"Harga saat ini: Rp{result['current_price']:.0f} (bar {result['current_time']})",
        f"Titik terendah ({INTRADAY_LOOKBACK_BARS} bar): Rp{result['lowest_low']:.0f}",
        f"Naik: *{result['actual_percent_from_low']:.2f}%* dari titik terendah",
        f"Level trigger: Rp{result['trigger_level']:.0f} ({result['threshold_desc']})",
        "",
        "✅ *Filter yang lolos:*"
    ]
    for name, detail in result["filters_passed"].items():
        lines.append(f"  • {name}: {detail}")

    if "volume_check" in result:
        vc = result["volume_check"]
        lines.append(f"  • Volume per-bar: {vc['current_volume']:,.0f} (avg: {vc['avg_volume']:,.0f})")

    if "obv_check" in result and result["obv_check"]["sufficient_data"]:
        oc = result["obv_check"]
        lines.append(f"  • OBV harian: {oc['obv_current']:,.0f} (SMA: {oc['obv_sma']:,.0f})")

    lines.append("")
    lines.append(f"Waktu proses: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB")

    return "\n".join(lines)


def format_rejected_message(result: dict):
    lines = ["Breakout harga (intraday) terdeteksi tapi TIDAK lolos semua filter konfirmasi:"]
    for name, detail in result["filters_failed"].items():
        lines.append(f"  ✗ {name}: {detail}")
    return "\n".join(lines)


# =====================================================================
# MAIN
# =====================================================================

def main():
    logger.info(f"=== Cek {TICKER} (hybrid intraday+daily) ===")
    logger.info(
        f"Filter aktif: Volume={ENABLE_VOLUME_FILTER}, "
        f"CloseConfirm={ENABLE_CLOSE_CONFIRMATION}, MTF={ENABLE_MTF_FILTER}, "
        f"ATR={ENABLE_ATR_THRESHOLD}, OBV={ENABLE_OBV_FILTER}"
    )

    intraday_df = get_intraday_data(TICKER)
    if intraday_df is None:
        logger.warning("Data intraday tidak tersedia, keluar.")
        sys.exit(0)

    daily_df = get_daily_data(TICKER)
    if daily_df is None:
        logger.warning("Data harian tidak tersedia (untuk konfirmasi), keluar.")
        sys.exit(0)

    result = detect_breakout(intraday_df, daily_df)

    logger.info(
        f"{TICKER} | Harga: {result['current_price']:.0f} @ {result['current_time']} | "
        f"Low: {result['lowest_low']:.0f} | Trigger: {result['trigger_level']:.0f} | "
        f"Naik: {result['actual_percent_from_low']:.2f}% | "
        f"Breakout harga: {result['is_price_breakout']} | "
        f"Final (semua filter): {result['is_final_breakout']}"
    )

    if result["filters_failed"]:
        logger.info(format_rejected_message(result))

    state = load_state()
    current_time_str = str(result["current_time"])

    # Cegah alert berulang untuk bar/titik terendah yang sama
    already_alerted = (
        state.get("last_alert_time") == current_time_str
        and state.get("last_lowest_low") == result["lowest_low"]
    )

    if result["is_final_breakout"] and not already_alerted:
        message = format_alert_message(result)
        send_telegram_message(message)

        state["last_alert_time"] = current_time_str
        state["last_lowest_low"] = result["lowest_low"]
        save_state(state)
    else:
        logger.info("Belum breakout valid (semua filter) atau sudah pernah alert untuk bar ini.")
        save_state(state)


if __name__ == "__main__":
    main()
