"""
=====================================================================
TRAILING START MONITOR - Multi-Ticker Advanced Version
=====================================================================

ARSITEKTUR HYBRID:
    - TIMING: Data INTRADAY (15m/30m/60m) untuk menangkap momen breakout
    - KONFIRMASI: Data HARIAN untuk MTF, ATR, OBV

VOLUME FILTERS (ADVANCED):
    1. Volume Ratio      - Volume per-bar vs rata-rata (basic)
    2. Volume Spike      - Deteksi lonjakan volume dengan Z-Score
    3. Volume Trend      - Volume meningkat bertahap (slope analysis)
    4. VWAP              - Harga di atas volume-weighted average price
    5. CVD               - Cumulative Volume Delta (buy/sell dominance)
    6. MT Volume         - Konfirmasi volume harian juga meningkat
    7. Volume-Price Corr - Korelasi volume & harga (breakout strength)

FILTER KONFIRMASI:
    1. Close Confirmation - Breakout di Close, bukan High
    2. MTF Filter         - Tren mingguan mendukung
    3. ATR Threshold      - Ambang dinamis dari volatilitas
    4. OBV Accumulation   - Akumulasi dari data harian

BREAKOUT STRENGTH SCORE:
    - Skor 0-100 dari kombinasi semua filter
    - Kategori: STRONG (80+), MODERATE (60-79), WEAK (40-59), SIGNAL (<40)
=====================================================================
"""

import json
import os
import sys
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

import requests
import yfinance as yf
import pandas as pd
import numpy as np


# =====================================================================
# HELPER FUNCTIONS - SAFE ENV CONVERSION
# =====================================================================

def safe_int(value: str, default: int) -> int:
    """Safe convert string ke int, handle empty string."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: str, default: float) -> float:
    """Safe convert string ke float, handle empty string."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_str(value: str, default: str) -> str:
    """Safe get string, handle None."""
    if value is None or value == "":
        return default
    return value


def safe_bool(value: str, default: bool) -> bool:
    """Safe convert string ke bool, handle empty string."""
    if value is None or value == "":
        return default
    return value.lower() == "true"


def parse_tickers(tickers_str: str) -> List[str]:
    """
    Parse string ticker menjadi list.
    Format: "TINS.JK,ANTM.JK,TLKM.JK" atau "TINS.JK, ANTM.JK, TLKM.JK"
    """
    if not tickers_str or tickers_str == "":
        return ["TINS.JK"]
    
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
    
    if not tickers:
        return ["TINS.JK"]
    
    return tickers


# =====================================================================
# CONFIGURATION - SEMUA DARI ENVIRONMENT VARIABLES
# =====================================================================

# --- MULTI-TICKER ---
TICKERS_RAW = safe_str(os.environ.get("TICKERS"), "TINS.JK")
TICKERS = parse_tickers(TICKERS_RAW)
MAX_TICKERS = safe_int(os.environ.get("MAX_TICKERS"), 10)

if len(TICKERS) > MAX_TICKERS:
    logging.warning(f"Terlalu banyak ticker ({len(TICKERS)}), dibatasi menjadi {MAX_TICKERS}")
    TICKERS = TICKERS[:MAX_TICKERS]

# --- DATA INTRADAY (TIMING) ---
INTRADAY_INTERVAL = safe_str(os.environ.get("INTRADAY_INTERVAL"), "15m")
INTRADAY_PERIOD_DAYS = safe_int(os.environ.get("INTRADAY_PERIOD_DAYS"), 5)
INTRADAY_LOOKBACK_BARS = safe_int(os.environ.get("INTRADAY_LOOKBACK_BARS"), 20)
BREAKOUT_PERCENT = safe_float(os.environ.get("BREAKOUT_PERCENT"), 5.0)
USE_INTRADAY_LOW = safe_bool(os.environ.get("USE_INTRADAY_LOW"), True)

# --- FILTER 1: VOLUME RATIO ---
ENABLE_VOLUME_FILTER = safe_bool(os.environ.get("ENABLE_VOLUME_FILTER"), True)
VOLUME_LOOKBACK_BARS = safe_int(os.environ.get("VOLUME_LOOKBACK_BARS"), 20)
VOLUME_MULTIPLIER = safe_float(os.environ.get("VOLUME_MULTIPLIER"), 1.5)

# --- FILTER 2: VOLUME SPIKE ---
ENABLE_VOLUME_SPIKE = safe_bool(os.environ.get("ENABLE_VOLUME_SPIKE"), True)
VOLUME_SPIKE_THRESHOLD = safe_float(os.environ.get("VOLUME_SPIKE_THRESHOLD"), 2.0)
VOLUME_SPIKE_LOOKBACK = safe_int(os.environ.get("VOLUME_SPIKE_LOOKBACK"), 20)

# --- FILTER 3: VOLUME TREND ---
ENABLE_VOLUME_TREND = safe_bool(os.environ.get("ENABLE_VOLUME_TREND"), True)
VOLUME_TREND_BARS = safe_int(os.environ.get("VOLUME_TREND_BARS"), 10)

# --- FILTER 4: VWAP ---
ENABLE_VWAP_FILTER = safe_bool(os.environ.get("ENABLE_VWAP_FILTER"), True)
VWAP_LOOKBACK_BARS = safe_int(os.environ.get("VWAP_LOOKBACK_BARS"), 20)

# --- FILTER 5: CVD ---
ENABLE_CVD_FILTER = safe_bool(os.environ.get("ENABLE_CVD_FILTER"), True)
CVD_LOOKBACK_BARS = safe_int(os.environ.get("CVD_LOOKBACK_BARS"), 10)
CVD_BUY_THRESHOLD = safe_float(os.environ.get("CVD_BUY_THRESHOLD"), 0.55)

# --- FILTER 6: MT VOLUME ---
ENABLE_MT_VOLUME = safe_bool(os.environ.get("ENABLE_MT_VOLUME"), True)
MT_VOLUME_DAILY_LOOKBACK = safe_int(os.environ.get("MT_VOLUME_DAILY_LOOKBACK"), 20)
MT_VOLUME_DAILY_MULTIPLIER = safe_float(os.environ.get("MT_VOLUME_DAILY_MULTIPLIER"), 1.2)

# --- FILTER 7: VOLUME-PRICE CORRELATION ---
ENABLE_VOLUME_PRICE_CORRELATION = safe_bool(os.environ.get("ENABLE_VOLUME_PRICE_CORRELATION"), True)
VOLUME_PRICE_CORR_BARS = safe_int(os.environ.get("VOLUME_PRICE_CORR_BARS"), 10)

# --- CLOSE CONFIRMATION ---
ENABLE_CLOSE_CONFIRMATION = safe_bool(os.environ.get("ENABLE_CLOSE_CONFIRMATION"), True)

# --- MTF FILTER ---
ENABLE_MTF_FILTER = safe_bool(os.environ.get("ENABLE_MTF_FILTER"), True)
MTF_SMA_WEEKS = safe_int(os.environ.get("MTF_SMA_WEEKS"), 10)

# --- ATR THRESHOLD ---
ENABLE_ATR_THRESHOLD = safe_bool(os.environ.get("ENABLE_ATR_THRESHOLD"), False)
ATR_PERIOD = safe_int(os.environ.get("ATR_PERIOD"), 14)
ATR_MULTIPLIER = safe_float(os.environ.get("ATR_MULTIPLIER"), 1.5)

# --- OBV FILTER ---
ENABLE_OBV_FILTER = safe_bool(os.environ.get("ENABLE_OBV_FILTER"), True)
OBV_SMA_PERIOD = safe_int(os.environ.get("OBV_SMA_PERIOD"), 20)

# --- LIQUIDITY CHECK ---
ENABLE_LIQUIDITY_CHECK = safe_bool(os.environ.get("ENABLE_LIQUIDITY_CHECK"), True)
MIN_INTRADAY_BARS = safe_int(os.environ.get("MIN_INTRADAY_BARS"), 30)
MAX_ZERO_VOLUME_BAR_RATIO = safe_float(os.environ.get("MAX_ZERO_VOLUME_BAR_RATIO"), 0.3)
MIN_AVG_DAILY_VALUE_RP = safe_float(os.environ.get("MIN_AVG_DAILY_VALUE_RP"), 1000000000)
LIQUIDITY_LOOKBACK_DAYS = safe_int(os.environ.get("LIQUIDITY_LOOKBACK_DAYS"), 20)

# --- STRENGTH SCORE ---
ENABLE_STRENGTH_SCORE = safe_bool(os.environ.get("ENABLE_STRENGTH_SCORE"), True)
STRONG_SCORE_THRESHOLD = safe_int(os.environ.get("STRONG_SCORE_THRESHOLD"), 80)
MODERATE_SCORE_THRESHOLD = safe_int(os.environ.get("MODERATE_SCORE_THRESHOLD"), 60)

# --- TELEGRAM ---
TELEGRAM_BOT_TOKEN = safe_str(os.environ.get("TELEGRAM_BOT_TOKEN"), "")
TELEGRAM_CHAT_ID = safe_str(os.environ.get("TELEGRAM_CHAT_ID"), "")

# --- STATE ---
STATE_DIR = "state"
STATE_FILE_PREFIX = "trailing_start_state"

# --- DAILY PERIOD ---
DAILY_PERIOD_DAYS = safe_int(os.environ.get("DAILY_PERIOD_DAYS"), 200)

# --- BATCH ---
BATCH_DELAY_SECONDS = safe_int(os.environ.get("BATCH_DELAY_SECONDS"), 2)


# =====================================================================
# LOGGING SETUP
# =====================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# =====================================================================
# STATE MANAGEMENT - PER TICKER
# =====================================================================

def get_state_file(ticker: str) -> str:
    """Dapatkan path state file untuk ticker tertentu."""
    safe_ticker = ticker.replace(".", "_")
    return os.path.join(STATE_DIR, f"{STATE_FILE_PREFIX}_{safe_ticker}.json")


def load_state(ticker: str) -> Dict:
    """Load state dari file per ticker."""
    state_file = get_state_file(ticker)
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_alert_time": None, "last_lowest_low": None, "last_price": None}


def save_state(ticker: str, state: Dict) -> None:
    """Save state ke file per ticker."""
    os.makedirs(STATE_DIR, exist_ok=True)
    state_file = get_state_file(ticker)
    with open(state_file, "w") as f:
        json.dump(state, f, default=str, indent=2)


# =====================================================================
# DATA FETCHING
# =====================================================================

def get_intraday_data(ticker: str) -> Optional[pd.DataFrame]:
    """Ambil data intraday untuk TIMING breakout."""
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=f"{INTRADAY_PERIOD_DAYS}d", interval=INTRADAY_INTERVAL)

        if df.empty:
            logger.warning(f"[{ticker}] Data intraday kosong")
            return None

        if len(df) < INTRADAY_LOOKBACK_BARS:
            logger.warning(
                f"[{ticker}] Data intraday hanya {len(df)} bar, "
                f"kurang dari lookback {INTRADAY_LOOKBACK_BARS} bar"
            )

        return df

    except Exception as e:
        logger.error(f"[{ticker}] Gagal ambil data intraday: {e}")
        return None


def get_daily_data(ticker: str) -> Optional[pd.DataFrame]:
    """Ambil data harian untuk KONFIRMASI (MTF, ATR, OBV)."""
    try:
        needed_days = max(ATR_PERIOD, OBV_SMA_PERIOD, MTF_SMA_WEEKS * 7, DAILY_PERIOD_DAYS)
        t = yf.Ticker(ticker)
        df = t.history(period=f"{needed_days}d", interval="1d")

        if df.empty:
            logger.warning(f"[{ticker}] Data harian kosong")
            return None

        return df

    except Exception as e:
        logger.error(f"[{ticker}] Gagal ambil data harian: {e}")
        return None


# =====================================================================
# LIQUIDITY CHECK
# =====================================================================

def check_liquidity(ticker: str, intraday_df: pd.DataFrame, daily_df: pd.DataFrame) -> Tuple[bool, Dict]:
    """Cek likuiditas saham sebelum analisis lebih lanjut."""
    if not ENABLE_LIQUIDITY_CHECK:
        return True, {"enabled": False}

    details = {"enabled": True}
    is_liquid = True

    n_bars = len(intraday_df)
    if n_bars < MIN_INTRADAY_BARS:
        is_liquid = False
        details["bar_check"] = f"❌ Hanya {n_bars} bar (min {MIN_INTRADAY_BARS})"
    else:
        details["bar_check"] = f"✅ {n_bars} bar"

    zero_volume_ratio = (intraday_df["Volume"] == 0).sum() / len(intraday_df)
    if zero_volume_ratio > MAX_ZERO_VOLUME_BAR_RATIO:
        is_liquid = False
        details["zero_volume"] = f"❌ {zero_volume_ratio*100:.1f}% bar volume 0 (max {MAX_ZERO_VOLUME_BAR_RATIO*100:.0f}%)"
    else:
        details["zero_volume"] = f"✅ {zero_volume_ratio*100:.1f}% bar volume 0"

    if len(daily_df) >= LIQUIDITY_LOOKBACK_DAYS:
        avg_value = (daily_df["Close"].tail(LIQUIDITY_LOOKBACK_DAYS) * 
                     daily_df["Volume"].tail(LIQUIDITY_LOOKBACK_DAYS)).mean()
        if avg_value < MIN_AVG_DAILY_VALUE_RP:
            is_liquid = False
            details["avg_daily_value"] = f"❌ Rp{avg_value:,.0f} (min Rp{MIN_AVG_DAILY_VALUE_RP:,.0f})"
        else:
            details["avg_daily_value"] = f"✅ Rp{avg_value:,.0f}"
    else:
        details["avg_daily_value"] = "⚠️ Data harian tidak cukup"

    details["is_liquid"] = is_liquid
    return is_liquid, details


# =====================================================================
# VOLUME FILTERS - ADVANCED
# =====================================================================

def check_volume_ratio(intraday_df: pd.DataFrame) -> Dict:
    """Filter 1: Volume ratio vs rata-rata."""
    avg_volume = intraday_df["Volume"].tail(VOLUME_LOOKBACK_BARS).mean()
    current_volume = intraday_df["Volume"].iloc[-1]
    ratio = current_volume / avg_volume if avg_volume > 0 else 0
    
    return {
        "passed": bool(ratio >= VOLUME_MULTIPLIER),
        "current_volume": float(current_volume),
        "avg_volume": float(avg_volume),
        "ratio": float(ratio),
        "threshold": VOLUME_MULTIPLIER
    }


def check_volume_spike(intraday_df: pd.DataFrame) -> Dict:
    """Filter 2: Deteksi volume spike dengan Z-Score."""
    volumes = intraday_df["Volume"].tail(VOLUME_SPIKE_LOOKBACK)
    current_volume = volumes.iloc[-1]
    
    if len(volumes) < 5:
        return {"passed": False, "z_score": 0, "reason": "Data tidak cukup"}
    
    mean = volumes.mean()
    std = volumes.std()
    
    if std == 0:
        return {"passed": False, "z_score": 0, "reason": "Tidak ada variasi volume"}
    
    z_score = (current_volume - mean) / std
    passed = z_score > VOLUME_SPIKE_THRESHOLD
    
    return {
        "passed": passed,
        "z_score": float(z_score),
        "threshold": VOLUME_SPIKE_THRESHOLD,
        "mean_volume": float(mean),
        "current_volume": float(current_volume)
    }


def check_volume_trend(intraday_df: pd.DataFrame) -> Dict:
    """Filter 3: Cek apakah volume dalam N bar terakhir meningkat."""
    volumes = intraday_df["Volume"].tail(VOLUME_TREND_BARS)
    
    if len(volumes) < 3:
        return {"passed": False, "slope": 0, "reason": "Data tidak cukup"}
    
    x = np.arange(len(volumes))
    slope = np.polyfit(x, volumes, 1)[0]
    passed = slope > 0
    
    return {
        "passed": passed,
        "slope": float(slope),
        "is_uptrend": passed
    }


def calculate_vwap(intraday_df: pd.DataFrame) -> Dict:
    """Filter 4: Hitung VWAP dan cek harga di atasnya."""
    df = intraday_df.tail(VWAP_LOOKBACK_BARS)
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    total_volume = df["Volume"].sum()
    vwap = (typical_price * df["Volume"]).sum() / total_volume if total_volume > 0 else 0
    current_close = float(intraday_df["Close"].iloc[-1])
    
    return {
        "passed": bool(current_close > vwap),
        "vwap": float(vwap),
        "current_close": current_close,
        "diff_percent": ((current_close - vwap) / vwap * 100) if vwap > 0 else 0
    }


def calculate_cvd(intraday_df: pd.DataFrame) -> Dict:
    """Filter 5: Cumulative Volume Delta - estimasi buy vs sell volume."""
    df = intraday_df.tail(CVD_LOOKBACK_BARS)
    
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    volume = df["Volume"]
    
    range_price = high - low
    range_price = range_price.replace(0, 1)
    
    buy_volume = ((close - low) / range_price * volume).sum()
    sell_volume = ((high - close) / range_price * volume).sum()
    
    total = buy_volume + sell_volume
    buy_ratio = buy_volume / total if total > 0 else 0.5
    cvd = buy_volume - sell_volume
    
    passed = buy_ratio > CVD_BUY_THRESHOLD
    
    return {
        "passed": passed,
        "cvd": float(cvd),
        "buy_ratio": float(buy_ratio),
        "buy_volume": float(buy_volume),
        "sell_volume": float(sell_volume),
        "threshold": CVD_BUY_THRESHOLD
    }


def check_daily_volume_spike(daily_df: pd.DataFrame) -> Dict:
    """Filter 6: Cek volume harian terakhir vs rata-rata."""
    lookback = MT_VOLUME_DAILY_LOOKBACK
    avg_volume = daily_df["Volume"].tail(lookback).mean()
    current_volume = daily_df["Volume"].iloc[-1]
    ratio = current_volume / avg_volume if avg_volume > 0 else 0
    
    passed = ratio >= MT_VOLUME_DAILY_MULTIPLIER
    
    return {
        "passed": passed,
        "ratio": float(ratio),
        "current_volume": float(current_volume),
        "avg_volume": float(avg_volume),
        "threshold": MT_VOLUME_DAILY_MULTIPLIER
    }


def check_volume_price_correlation(intraday_df: pd.DataFrame) -> Dict:
    """Filter 7: Korelasi antara volume dan harga."""
    df = intraday_df.tail(VOLUME_PRICE_CORR_BARS)
    
    if len(df) < 5:
        return {"passed": False, "correlation": 0, "reason": "Data tidak cukup"}
    
    prices = df["Close"].values
    volumes = df["Volume"].values
    
    corr = np.corrcoef(prices, volumes)[0, 1] if len(prices) > 1 else 0
    passed = corr > 0
    
    return {
        "passed": passed,
        "correlation": float(corr),
        "is_positive": passed
    }


# =====================================================================
# KONFIRMASI FILTERS - DAILY
# =====================================================================

def calculate_atr_daily(daily_df: pd.DataFrame, period: int) -> float:
    """Hitung ATR dari data harian."""
    high, low, close = daily_df["High"], daily_df["Low"], daily_df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(window=period).mean().iloc[-1])


def check_weekly_trend(daily_df: pd.DataFrame, sma_weeks: int) -> Dict:
    """Cek tren mingguan (MTF filter)."""
    try:
        weekly = daily_df["Close"].resample("W").last()
        if len(weekly) < sma_weeks:
            return {"passed": True, "sufficient_data": False}

        weekly_sma = weekly.rolling(window=sma_weeks).mean().iloc[-1]
        current_weekly_close = weekly.iloc[-1]
        passed = current_weekly_close > weekly_sma
        
        return {
            "passed": passed,
            "weekly_sma": float(weekly_sma),
            "current_weekly_close": float(current_weekly_close),
            "sufficient_data": True
        }
    except Exception as e:
        logger.error(f"Gagal hitung MTF filter: {e}")
        return {"passed": True, "sufficient_data": False}


def check_obv_accumulation(daily_df: pd.DataFrame, sma_period: int) -> Dict:
    """Cek OBV accumulation (harus di atas SMA)."""
    try:
        direction = np.sign(daily_df["Close"].diff()).fillna(0)
        obv = (direction * daily_df["Volume"]).cumsum()

        if len(obv) < sma_period:
            return {"passed": True, "sufficient_data": False}

        obv_sma = obv.rolling(window=sma_period).mean().iloc[-1]
        obv_current = obv.iloc[-1]
        passed = obv_current > obv_sma
        
        return {
            "passed": passed,
            "obv_current": float(obv_current),
            "obv_sma": float(obv_sma),
            "sufficient_data": True
        }
    except Exception as e:
        logger.error(f"Gagal hitung OBV: {e}")
        return {"passed": True, "sufficient_data": False}


# =====================================================================
# BREAKOUT DETECTION - MAIN
# =====================================================================

def detect_breakout(ticker: str, intraday_df: pd.DataFrame, daily_df: pd.DataFrame) -> Dict:
    """Gabungkan TIMING (intraday) dan semua KONFIRMASI."""
    close_col = intraday_df["Close"]
    low_col = intraday_df["Low"] if USE_INTRADAY_LOW else intraday_df["Close"]

    lowest_low = float(low_col.tail(INTRADAY_LOOKBACK_BARS).min())
    current_close = float(close_col.iloc[-1])
    current_high = float(intraday_df["High"].iloc[-1])
    current_open = float(intraday_df["Open"].iloc[-1])
    current_time = intraday_df.index[-1]

    if ENABLE_ATR_THRESHOLD:
        atr = calculate_atr_daily(daily_df, ATR_PERIOD)
        threshold_amount = atr * ATR_MULTIPLIER
        trigger_level = lowest_low + threshold_amount
        threshold_desc = f"ATR({ATR_PERIOD}) x {ATR_MULTIPLIER} = {threshold_amount:.1f}"
    else:
        trigger_level = lowest_low * (1 + BREAKOUT_PERCENT / 100)
        threshold_desc = f"{BREAKOUT_PERCENT}% dari titik terendah"

    price_for_check = current_close if ENABLE_CLOSE_CONFIRMATION else current_high
    is_price_breakout = price_for_check >= trigger_level
    actual_percent_from_low = ((current_close - lowest_low) / lowest_low) * 100

    result = {
        "ticker": ticker,
        "current_price": current_close,
        "current_open": current_open,
        "current_high": current_high,
        "current_time": current_time,
        "lowest_low": lowest_low,
        "trigger_level": trigger_level,
        "threshold_desc": threshold_desc,
        "actual_percent_from_low": actual_percent_from_low,
        "is_price_breakout": is_price_breakout,
        "filters_passed": {},
        "filters_failed": {},
        "volume_filters": {},
    }

    # --- FILTER 1: Volume Ratio ---
    if ENABLE_VOLUME_FILTER:
        vol_check = check_volume_ratio(intraday_df)
        result["volume_filters"]["volume_ratio"] = vol_check
        if vol_check["passed"]:
            result["filters_passed"]["volume_ratio"] = f"{vol_check['ratio']:.2f}x (min {VOLUME_MULTIPLIER}x)"
        else:
            result["filters_failed"]["volume_ratio"] = f"{vol_check['ratio']:.2f}x (min {VOLUME_MULTIPLIER}x)"

    # --- FILTER 2: Volume Spike ---
    if ENABLE_VOLUME_SPIKE:
        spike_check = check_volume_spike(intraday_df)
        result["volume_filters"]["volume_spike"] = spike_check
        if spike_check["passed"]:
            result["filters_passed"]["volume_spike"] = f"Z-Score {spike_check['z_score']:.2f} > {VOLUME_SPIKE_THRESHOLD}"
        else:
            result["filters_failed"]["volume_spike"] = f"Z-Score {spike_check['z_score']:.2f} ≤ {VOLUME_SPIKE_THRESHOLD}"

    # --- FILTER 3: Volume Trend ---
    if ENABLE_VOLUME_TREND:
        trend_check = check_volume_trend(intraday_df)
        result["volume_filters"]["volume_trend"] = trend_check
        if trend_check["passed"]:
            result["filters_passed"]["volume_trend"] = f"Volume meningkat (slope: {trend_check['slope']:.0f})"
        else:
            result["filters_failed"]["volume_trend"] = f"Volume menurun (slope: {trend_check['slope']:.0f})"

    # --- FILTER 4: VWAP ---
    if ENABLE_VWAP_FILTER:
        vwap_check = calculate_vwap(intraday_df)
        result["volume_filters"]["vwap"] = vwap_check
        if vwap_check["passed"]:
            result["filters_passed"]["vwap"] = f"Harga di atas VWAP ({vwap_check['vwap']:.0f})"
        else:
            result["filters_failed"]["vwap"] = f"Harga di bawah VWAP ({vwap_check['vwap']:.0f})"

    # --- FILTER 5: CVD ---
    if ENABLE_CVD_FILTER:
        cvd_check = calculate_cvd(intraday_df)
        result["volume_filters"]["cvd"] = cvd_check
        if cvd_check["passed"]:
            result["filters_passed"]["cvd"] = f"Buy {cvd_check['buy_ratio']*100:.0f}% (min {CVD_BUY_THRESHOLD*100:.0f}%)"
        else:
            result["filters_failed"]["cvd"] = f"Buy {cvd_check['buy_ratio']*100:.0f}% (min {CVD_BUY_THRESHOLD*100:.0f}%)"

    # --- FILTER 6: MT Volume ---
    if ENABLE_MT_VOLUME:
        mt_vol_check = check_daily_volume_spike(daily_df)
        result["volume_filters"]["mt_volume"] = mt_vol_check
        if mt_vol_check["passed"]:
            result["filters_passed"]["mt_volume"] = f"Daily vol {mt_vol_check['ratio']:.2f}x (min {MT_VOLUME_DAILY_MULTIPLIER}x)"
        else:
            result["filters_failed"]["mt_volume"] = f"Daily vol {mt_vol_check['ratio']:.2f}x (min {MT_VOLUME_DAILY_MULTIPLIER}x)"

    # --- FILTER 7: Volume-Price Correlation ---
    if ENABLE_VOLUME_PRICE_CORRELATION:
        corr_check = check_volume_price_correlation(intraday_df)
        result["volume_filters"]["vol_price_corr"] = corr_check
        if corr_check["passed"]:
            result["filters_passed"]["vol_price_corr"] = f"Corr +{corr_check['correlation']:.2f}"
        else:
            result["filters_failed"]["vol_price_corr"] = f"Corr {corr_check['correlation']:.2f} (negatif)"

    # --- CLOSE CONFIRMATION ---
    if ENABLE_CLOSE_CONFIRMATION:
        result["filters_passed"]["close_confirmation"] = "Breakout di Close"

    # --- MTF FILTER ---
    if ENABLE_MTF_FILTER:
        mtf_check = check_weekly_trend(daily_df, MTF_SMA_WEEKS)
        result["mtf_check"] = mtf_check
        if mtf_check["passed"]:
            result["filters_passed"]["mtf"] = "Tren mingguan mendukung"
        else:
            result["filters_failed"]["mtf"] = "Tren mingguan TIDAK mendukung"

    # --- ATR ---
    if ENABLE_ATR_THRESHOLD:
        result["filters_passed"]["atr"] = threshold_desc

    # --- OBV ---
    if ENABLE_OBV_FILTER:
        obv_check = check_obv_accumulation(daily_df, OBV_SMA_PERIOD)
        result["obv_check"] = obv_check
        if obv_check["passed"]:
            result["filters_passed"]["obv"] = "OBV di atas SMA → akumulasi"
        else:
            result["filters_failed"]["obv"] = "OBV di bawah SMA → distribusi"

    result["is_final_breakout"] = is_price_breakout and len(result["filters_failed"]) == 0
    
    if ENABLE_STRENGTH_SCORE:
        result["strength_score"] = calculate_breakout_strength(result)
    
    return result


# =====================================================================
# BREAKOUT STRENGTH SCORE
# =====================================================================

def calculate_breakout_strength(result: Dict) -> Dict:
    """Hitung skor kekuatan breakout dari semua filter (0-100)."""
    score = 0
    max_score = 0
    
    # 1. Persentase kenaikan (0-25)
    max_score += 25
    percent = result["actual_percent_from_low"]
    if percent >= 10:
        score += 25
    elif percent >= 7:
        score += 20
    elif percent >= 5:
        score += 15
    elif percent >= 3:
        score += 10
    else:
        score += 5
    
    # 2. Volume Ratio (0-20)
    if "volume_filters" in result and "volume_ratio" in result["volume_filters"]:
        max_score += 20
        ratio = result["volume_filters"]["volume_ratio"].get("ratio", 0)
        if ratio >= 3.0:
            score += 20
        elif ratio >= 2.0:
            score += 15
        elif ratio >= 1.5:
            score += 10
        elif ratio >= 1.2:
            score += 5
    
    # 3. Volume Spike (0-15)
    if "volume_filters" in result and "volume_spike" in result["volume_filters"]:
        max_score += 15
        if result["volume_filters"]["volume_spike"].get("passed", False):
            score += 15
        else:
            z_score = result["volume_filters"]["volume_spike"].get("z_score", 0)
            if z_score > 1.5:
                score += 8
            elif z_score > 1.0:
                score += 5
    
    # 4. VWAP (0-10)
    if "volume_filters" in result and "vwap" in result["volume_filters"]:
        max_score += 10
        if result["volume_filters"]["vwap"].get("passed", False):
            score += 10
    
    # 5. CVD (0-10)
    if "volume_filters" in result and "cvd" in result["volume_filters"]:
        max_score += 10
        if result["volume_filters"]["cvd"].get("passed", False):
            buy_ratio = result["volume_filters"]["cvd"].get("buy_ratio", 0.5)
            score += int((buy_ratio - 0.5) * 100) if buy_ratio > 0.5 else 0
            score = min(score, 10)
    
    # 6. MTF Trend (0-10)
    if "mtf_check" in result:
        max_score += 10
        if result["mtf_check"].get("passed", False):
            score += 10
    
    # 7. OBV (0-10)
    if "obv_check" in result:
        max_score += 10
        if result["obv_check"].get("passed", False):
            score += 10
    
    final_score = (score / max_score) * 100 if max_score > 0 else 0
    
    if final_score >= STRONG_SCORE_THRESHOLD:
        category = "🔥 STRONG"
        emoji = "🔥🔥🔥"
    elif final_score >= MODERATE_SCORE_THRESHOLD:
        category = "✅ MODERATE"
        emoji = "🔥"
    elif final_score >= 40:
        category = "⚠️ WEAK"
        emoji = "📊"
    else:
        category = "📉 SIGNAL"
        emoji = "ℹ️"
    
    return {
        "score": round(final_score, 1),
        "category": category,
        "emoji": emoji,
        "max_score": max_score,
        "achieved_score": score
    }


# =====================================================================
# TELEGRAM NOTIFICATION
# =====================================================================

def send_telegram_message(message: str) -> bool:
    """Kirim notifikasi ke Telegram - plain text (AMAN)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset!")
        logger.info(f"[SIMULASI PESAN]\n{message}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}

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
            
    except Exception as e:
        logger.error(f"❌ Gagal kirim notifikasi: {e}")
        return False


def format_alert_message(result: Dict) -> str:
    """Format pesan notifikasi Telegram - plain text."""
    ticker = result.get("ticker", "UNKNOWN")
    strength = result.get("strength_score", {})
    score = strength.get("score", 0)
    category = strength.get("category", "BREAKOUT")
    
    # Header
    separator = "=" * 50
    
    lines = [
        f"🚀 {category} - BREAKOUT TERDETEKSI",
        separator,
        "",
        f"📊 SAHAM: {ticker}",
        f"📈 INTERVAL: {INTRADAY_INTERVAL}",
        "",
        f"💰 HARGA: Rp{result['current_price']:,.0f}",
        f"📈 NAIK: {result['actual_percent_from_low']:.2f}% dari Low",
        f"📉 LOW: Rp{result['lowest_low']:,.0f}",
        f"🎯 TRIGGER: Rp{result['trigger_level']:,.0f}",
        f"📋 {result['threshold_desc']}",
        "",
        f"📊 STRENGTH SCORE: {score}/100 - {category}",
        "",
        "✅ FILTER LOLOS:"
    ]
    
    # Filter yang lolos
    if result["filters_passed"]:
        for name, detail in result["filters_passed"].items():
            if name not in ["close_confirmation", "atr"]:
                lines.append(f"  ✅ {name}: {detail}")
    else:
        lines.append("  (tidak ada filter yang lolos)")
    
    # Filter yang gagal (jika ada)
    if result["filters_failed"]:
        lines.append("")
        lines.append("❌ FILTER GAGAL:")
        for name, detail in result["filters_failed"].items():
            lines.append(f"  ❌ {name}: {detail}")
    
    # Volume details
    if "volume_filters" in result:
        lines.append("")
        lines.append("📊 VOLUME DETAILS:")
        for key, check in result["volume_filters"].items():
            if key == "volume_ratio" and check.get("passed"):
                lines.append(f"  📈 Ratio: {check['ratio']:.2f}x (avg: {check['avg_volume']:,.0f})")
            elif key == "volume_spike" and check.get("passed"):
                lines.append(f"  ⚡ Spike: Z={check['z_score']:.2f}")
            elif key == "vwap" and check.get("passed"):
                lines.append(f"  📊 VWAP: {check['diff_percent']:.1f}% di atas")
            elif key == "cvd" and check.get("passed"):
                lines.append(f"  📊 CVD: Buy {check['buy_ratio']*100:.0f}%")
    
    lines.append("")
    lines.append(f"🕐 WAKTU: {result['current_time'].strftime('%Y-%m-%d %H:%M')} WIB")
    lines.append(f"⏱️ PROSES: {datetime.now().strftime('%H:%M:%S')} WIB")
    lines.append(separator)
    lines.append("📌 HANYA EMITEN YANG MEMENUHI SYARAT")

    return "\n".join(lines)


# =====================================================================
# MAIN - MULTI-TICKER
# =====================================================================

def main():
    logger.info("=" * 60)
    logger.info("TRAILING START MONITOR - MULTI-TICKER MODE")
    logger.info(f"Monitor {len(TICKERS)} saham: {', '.join(TICKERS)}")
    logger.info(f"Interval: {INTRADAY_INTERVAL} | Lookback: {INTRADAY_LOOKBACK_BARS} bars")
    logger.info("=" * 60)
    
    all_results = []
    alerts_sent = 0
    alert_messages = []
    
    for idx, ticker in enumerate(TICKERS):
        logger.info(f"\n{'='*40}")
        logger.info(f"[{idx+1}/{len(TICKERS)}] Memproses {ticker}...")
        logger.info(f"{'='*40}")
        
        intraday_df = get_intraday_data(ticker)
        if intraday_df is None:
            logger.warning(f"[{ticker}] Data intraday tidak tersedia, skip.")
            continue

        daily_df = get_daily_data(ticker)
        if daily_df is None:
            logger.warning(f"[{ticker}] Data harian tidak tersedia, skip.")
            continue

        is_liquid, liquidity_details = check_liquidity(ticker, intraday_df, daily_df)
        if not is_liquid:
            logger.warning(f"[{ticker}] Tidak likuid, skip.")
            for key, value in liquidity_details.items():
                if key != "is_liquid" and "❌" in str(value):
                    logger.warning(f"  {key}: {value}")
            continue
        
        logger.info(f"[{ticker}] ✅ Likuiditas OK")
        for key, value in liquidity_details.items():
            if key != "is_liquid" and "✅" in str(value):
                logger.info(f"  {key}: {value}")

        result = detect_breakout(ticker, intraday_df, daily_df)
        all_results.append(result)

        logger.info(
            f"[{ticker}] Rp{result['current_price']:,.0f} @ {result['current_time']} | "
            f"Low: Rp{result['lowest_low']:,.0f} | Trigger: Rp{result['trigger_level']:,.0f} | "
            f"↑{result['actual_percent_from_low']:.2f}% | "
            f"Breakout: {result['is_price_breakout']} | Final: {result['is_final_breakout']}"
        )
        
        if "strength_score" in result:
            score = result["strength_score"]
            logger.info(f"[{ticker}] Strength Score: {score['score']}/100 - {score['category']}")

        # Log filter yang lolos/gagal
        if result["filters_passed"]:
            logger.info(f"[{ticker}] ✅ Filter Lolos:")
            for name, detail in result["filters_passed"].items():
                logger.info(f"  ✓ {name}: {detail}")

        if result["filters_failed"]:
            logger.info(f"[{ticker}] ❌ Filter Gagal:")
            for name, detail in result["filters_failed"].items():
                logger.info(f"  ✗ {name}: {detail}")

        state = load_state(ticker)
        current_time_str = str(result["current_time"])

        already_alerted = (
            state.get("last_alert_time") == current_time_str
            and state.get("last_lowest_low") == result["lowest_low"]
        )

        # --- HANYA KIRIM JIKA BREAKOUT DAN LOLOS SEMUA FILTER ---
        if result["is_final_breakout"] and not already_alerted:
            message = format_alert_message(result)
            alert_messages.append(message)
            
            # Kirim per ticker
            success = send_telegram_message(message)
            if success:
                alerts_sent += 1
                logger.info(f"[{ticker}] ✅ Alert terkirim!")
            else:
                logger.warning(f"[{ticker}] ⚠️ Alert gagal dikirim")

            state["last_alert_time"] = current_time_str
            state["last_lowest_low"] = result["lowest_low"]
            save_state(ticker, state)
        else:
            if result["is_price_breakout"] and not result["is_final_breakout"]:
                logger.info(f"[{ticker}] ⚠️ Breakout harga tapi filter tidak lolos")
            else:
                logger.info(f"[{ticker}] ℹ️ Belum breakout atau sudah pernah alert.")
            save_state(ticker, state)
        
        if idx < len(TICKERS) - 1 and BATCH_DELAY_SECONDS > 0:
            logger.info(f"⏱️ Delay {BATCH_DELAY_SECONDS}s sebelum saham berikutnya...")
            time.sleep(BATCH_DELAY_SECONDS)

    # --- FINAL SUMMARY ---
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ Selesai memproses {len(TICKERS)} saham. Alert terkirim: {alerts_sent}")
    logger.info("=" * 60)
    
    # Kirim summary jika ada alert
    if alerts_sent > 0:
        summary_lines = [
            "📊 SUMMARY BREAKOUT",
            "=" * 30,
            "",
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB",
            f"📊 Total Alert: {alerts_sent} saham",
            ""
        ]
        
        # Tambahkan detail per ticker yang alert
        for msg in alert_messages:
            # Ambil ticker dari pesan
            for line in msg.split('\n'):
                if "SAHAM:" in line:
                    summary_lines.append(line)
                    break
        
        summary_lines.append("")
        summary_lines.append("=" * 30)
        summary_lines.append("📌 HANYA EMITEN YANG MEMENUHI SYARAT")
        
        summary_message = "\n".join(summary_lines)
        send_telegram_message(summary_message)


if __name__ == "__main__":
    main()
