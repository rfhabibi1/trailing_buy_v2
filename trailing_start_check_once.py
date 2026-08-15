"""
=====================================================================
TRAILING START MONITOR - Versi Advanced (Volume-Confirmed Breakout)
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

FILTER KONFIRMASI (tetap):
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
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

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


# =====================================================================
# CONFIGURATION - SEMUA DARI ENVIRONMENT VARIABLES
# =====================================================================

# --- SAHAM ---
TICKER = safe_str(os.environ.get("TICKER"), "TINS.JK")

# --- DATA INTRADAY (TIMING) ---
INTRADAY_INTERVAL = safe_str(os.environ.get("INTRADAY_INTERVAL"), "15m")
INTRADAY_PERIOD_DAYS = safe_int(os.environ.get("INTRADAY_PERIOD_DAYS"), 5)
INTRADAY_LOOKBACK_BARS = safe_int(os.environ.get("INTRADAY_LOOKBACK_BARS"), 20)
BREAKOUT_PERCENT = safe_float(os.environ.get("BREAKOUT_PERCENT"), 5.0)
USE_INTRADAY_LOW = safe_bool(os.environ.get("USE_INTRADAY_LOW"), True)

# --- FILTER 1: VOLUME RATIO (Basic) ---
ENABLE_VOLUME_FILTER = safe_bool(os.environ.get("ENABLE_VOLUME_FILTER"), True)
VOLUME_LOOKBACK_BARS = safe_int(os.environ.get("VOLUME_LOOKBACK_BARS"), 20)
VOLUME_MULTIPLIER = safe_float(os.environ.get("VOLUME_MULTIPLIER"), 1.5)

# --- FILTER 2: VOLUME SPIKE (Z-Score) ---
ENABLE_VOLUME_SPIKE = safe_bool(os.environ.get("ENABLE_VOLUME_SPIKE"), True)
VOLUME_SPIKE_THRESHOLD = safe_float(os.environ.get("VOLUME_SPIKE_THRESHOLD"), 2.0)
VOLUME_SPIKE_LOOKBACK = safe_int(os.environ.get("VOLUME_SPIKE_LOOKBACK"), 20)

# --- FILTER 3: VOLUME TREND (Slope) ---
ENABLE_VOLUME_TREND = safe_bool(os.environ.get("ENABLE_VOLUME_TREND"), True)
VOLUME_TREND_BARS = safe_int(os.environ.get("VOLUME_TREND_BARS"), 10)

# --- FILTER 4: VWAP ---
ENABLE_VWAP_FILTER = safe_bool(os.environ.get("ENABLE_VWAP_FILTER"), True)
VWAP_LOOKBACK_BARS = safe_int(os.environ.get("VWAP_LOOKBACK_BARS"), 20)

# --- FILTER 5: CVD (Cumulative Volume Delta) ---
ENABLE_CVD_FILTER = safe_bool(os.environ.get("ENABLE_CVD_FILTER"), True)
CVD_LOOKBACK_BARS = safe_int(os.environ.get("CVD_LOOKBACK_BARS"), 10)
CVD_BUY_THRESHOLD = safe_float(os.environ.get("CVD_BUY_THRESHOLD"), 0.55)

# --- FILTER 6: MULTI-TIMEFRAME VOLUME ---
ENABLE_MT_VOLUME = safe_bool(os.environ.get("ENABLE_MT_VOLUME"), True)
MT_VOLUME_DAILY_LOOKBACK = safe_int(os.environ.get("MT_VOLUME_DAILY_LOOKBACK"), 20)
MT_VOLUME_DAILY_MULTIPLIER = safe_float(os.environ.get("MT_VOLUME_DAILY_MULTIPLIER"), 1.2)

# --- FILTER 7: VOLUME-PRICE CORRELATION ---
ENABLE_VOLUME_PRICE_CORRELATION = safe_bool(os.environ.get("ENABLE_VOLUME_PRICE_CORRELATION"), True)
VOLUME_PRICE_CORR_BARS = safe_int(os.environ.get("VOLUME_PRICE_CORR_BARS"), 10)

# --- CLOSE CONFIRMATION ---
ENABLE_CLOSE_CONFIRMATION = safe_bool(os.environ.get("ENABLE_CLOSE_CONFIRMATION"), True)

# --- MTF FILTER (Daily) ---
ENABLE_MTF_FILTER = safe_bool(os.environ.get("ENABLE_MTF_FILTER"), True)
MTF_SMA_WEEKS = safe_int(os.environ.get("MTF_SMA_WEEKS"), 10)

# --- ATR THRESHOLD (Daily) ---
ENABLE_ATR_THRESHOLD = safe_bool(os.environ.get("ENABLE_ATR_THRESHOLD"), False)
ATR_PERIOD = safe_int(os.environ.get("ATR_PERIOD"), 14)
ATR_MULTIPLIER = safe_float(os.environ.get("ATR_MULTIPLIER"), 1.5)

# --- OBV FILTER (Daily) ---
ENABLE_OBV_FILTER = safe_bool(os.environ.get("ENABLE_OBV_FILTER"), True)
OBV_SMA_PERIOD = safe_int(os.environ.get("OBV_SMA_PERIOD"), 20)

# --- LIQUIDITY CHECK ---
ENABLE_LIQUIDITY_CHECK = safe_bool(os.environ.get("ENABLE_LIQUIDITY_CHECK"), True)
MIN_INTRADAY_BARS = safe_int(os.environ.get("MIN_INTRADAY_BARS"), 30)
MAX_ZERO_VOLUME_BAR_RATIO = safe_float(os.environ.get("MAX_ZERO_VOLUME_BAR_RATIO"), 0.3)
MIN_AVG_DAILY_VALUE_RP = safe_float(os.environ.get("MIN_AVG_DAILY_VALUE_RP"), 1000000000)
LIQUIDITY_LOOKBACK_DAYS = safe_int(os.environ.get("LIQUIDITY_LOOKBACK_DAYS"), 20)

# --- BREAKOUT STRENGTH SCORE ---
ENABLE_STRENGTH_SCORE = safe_bool(os.environ.get("ENABLE_STRENGTH_SCORE"), True)
STRONG_SCORE_THRESHOLD = safe_int(os.environ.get("STRONG_SCORE_THRESHOLD"), 80)
MODERATE_SCORE_THRESHOLD = safe_int(os.environ.get("MODERATE_SCORE_THRESHOLD"), 60)

# --- TELEGRAM ---
TELEGRAM_BOT_TOKEN = safe_str(os.environ.get("TELEGRAM_BOT_TOKEN"), "")
TELEGRAM_CHAT_ID = safe_str(os.environ.get("TELEGRAM_CHAT_ID"), "")

# --- STATE ---
STATE_FILE = "state/trailing_start_state.json"

# --- DATA HARIAN (untuk konfirmasi) ---
DAILY_PERIOD_DAYS = safe_int(os.environ.get("DAILY_PERIOD_DAYS"), 200)


# =====================================================================
# LOGGING SETUP
# =====================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# =====================================================================
# DATA FETCHING
# =====================================================================

def get_intraday_data(ticker: str) -> Optional[pd.DataFrame]:
    """Ambil data intraday untuk TIMING breakout."""
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=f"{INTRADAY_PERIOD_DAYS}d", interval=INTRADAY_INTERVAL)

        if df.empty:
            logger.warning(f"Data intraday kosong untuk {ticker}")
            return None

        if len(df) < INTRADAY_LOOKBACK_BARS:
            logger.warning(
                f"Data intraday hanya {len(df)} bar, kurang dari lookback "
                f"{INTRADAY_LOOKBACK_BARS} bar yang diminta."
            )

        return df

    except Exception as e:
        logger.error(f"Gagal ambil data intraday untuk {ticker}: {e}")
        return None


def get_daily_data(ticker: str) -> Optional[pd.DataFrame]:
    """Ambil data harian untuk KONFIRMASI (MTF, ATR, OBV)."""
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
# LIQUIDITY CHECK
# =====================================================================

def check_liquidity(intraday_df: pd.DataFrame, daily_df: pd.DataFrame) -> Tuple[bool, Dict]:
    """
    Cek likuiditas saham sebelum analisis lebih lanjut.
    Returns: (is_liquid, details)
    """
    if not ENABLE_LIQUIDITY_CHECK:
        return True, {"enabled": False}

    details = {"enabled": True}
    is_liquid = True

    # 1. Cek jumlah bar intraday
    n_bars = len(intraday_df)
    if n_bars < MIN_INTRADAY_BARS:
        is_liquid = False
        details["bar_check"] = f"❌ Hanya {n_bars} bar (min {MIN_INTRADAY_BARS})"
    else:
        details["bar_check"] = f"✅ {n_bars} bar"

    # 2. Cek proporsi volume = 0
    zero_volume_ratio = (intraday_df["Volume"] == 0).sum() / len(intraday_df)
    if zero_volume_ratio > MAX_ZERO_VOLUME_BAR_RATIO:
        is_liquid = False
        details["zero_volume"] = f"❌ {zero_volume_ratio*100:.1f}% bar volume 0 (max {MAX_ZERO_VOLUME_BAR_RATIO*100:.0f}%)"
    else:
        details["zero_volume"] = f"✅ {zero_volume_ratio*100:.1f}% bar volume 0"

    # 3. Cek rata-rata nilai transaksi harian
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
    
    # Metode: berdasarkan posisi close dalam range high-low
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    volume = df["Volume"]
    
    # Buy volume = proporsi dari close ke low
    range_price = high - low
    range_price = range_price.replace(0, 1)  # Hindari division by zero
    
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
            logger.warning("Data mingguan tidak cukup untuk MTF, default: lolos")
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
            logger.warning("Data harian tidak cukup untuk OBV SMA, default: lolos")
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

def detect_breakout(intraday_df: pd.DataFrame, daily_df: pd.DataFrame) -> Dict:
    """
    Gabungkan TIMING (intraday) dan semua KONFIRMASI.
    """
    close_col = intraday_df["Close"]
    low_col = intraday_df["Low"] if USE_INTRADAY_LOW else intraday_df["Close"]

    lowest_low = float(low_col.tail(INTRADAY_LOOKBACK_BARS).min())
    current_close = float(close_col.iloc[-1])
    current_high = float(intraday_df["High"].iloc[-1])
    current_open = float(intraday_df["Open"].iloc[-1])
    current_time = intraday_df.index[-1]

    # --- AMBANG BREAKOUT ---
    if ENABLE_ATR_THRESHOLD:
        atr = calculate_atr_daily(daily_df, ATR_PERIOD)
        threshold_amount = atr * ATR_MULTIPLIER
        trigger_level = lowest_low + threshold_amount
        threshold_desc = f"ATR({ATR_PERIOD}) x {ATR_MULTIPLIER} = {threshold_amount:.1f}"
    else:
        trigger_level = lowest_low * (1 + BREAKOUT_PERCENT / 100)
        threshold_desc = f"{BREAKOUT_PERCENT}% dari titik terendah"

    # --- CEK HARGA ---
    price_for_check = current_close if ENABLE_CLOSE_CONFIRMATION else current_high
    is_price_breakout = price_for_check >= trigger_level
    actual_percent_from_low = ((current_close - lowest_low) / lowest_low) * 100

    # --- RESULT ---
    result = {
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

    # --- FILTER 6: Multi-Timeframe Volume ---
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

    # --- FINAL DECISION ---
    result["is_final_breakout"] = is_price_breakout and len(result["filters_failed"]) == 0
    
    # --- STRENGTH SCORE ---
    if ENABLE_STRENGTH_SCORE:
        result["strength_score"] = calculate_breakout_strength(result)
    
    return result


# =====================================================================
# BREAKOUT STRENGTH SCORE
# =====================================================================

def calculate_breakout_strength(result: Dict) -> Dict:
    """
    Hitung skor kekuatan breakout dari semua filter (0-100).
    """
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
    
    # Normalisasi
    final_score = (score / max_score) * 100 if max_score > 0 else 0
    
    # Kategori
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
# STATE MANAGEMENT
# =====================================================================

def load_state() -> Dict:
    """Load state dari file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_alert_time": None, "last_lowest_low": None}


def save_state(state: Dict) -> None:
    """Save state ke file."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, default=str, indent=2)


# =====================================================================
# TELEGRAM NOTIFICATION
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
        logger.info("Notifikasi Telegram berhasil terkirim.")
        return True
    except Exception as e:
        logger.error(f"Gagal kirim notifikasi Telegram: {e}")
        return False


def format_alert_message(result: Dict) -> str:
    """Format pesan notifikasi Telegram."""
    strength = result.get("strength_score", {})
    score = strength.get("score", 0)
    emoji = strength.get("emoji", "🚀")
    category = strength.get("category", "BREAKOUT")
    
    # Volume summary
    vol_details = []
    if "volume_filters" in result:
        for key, check in result["volume_filters"].items():
            if key == "volume_ratio" and check.get("passed"):
                vol_details.append(f"Ratio {check['ratio']:.2f}x")
            elif key == "volume_spike" and check.get("passed"):
                vol_details.append(f"Spike Z={check['z_score']:.1f}")
            elif key == "vwap" and check.get("passed"):
                vol_details.append(f"VWAP+ {check['diff_percent']:.1f}%")
            elif key == "cvd" and check.get("passed"):
                vol_details.append(f"CVD Buy {check['buy_ratio']*100:.0f}%")
    
    vol_text = ", ".join(vol_details) if vol_details else "Standard"

    lines = [
        f"{emoji} *{category}*",
        "",
        f"📊 *{TICKER}* | {INTRADAY_INTERVAL}",
        f"💵 Rp{result['current_price']:,.0f} (↑{result['actual_percent_from_low']:.2f}%)",
        f"📉 Low: Rp{result['lowest_low']:,.0f}",
        f"🎯 Trigger: Rp{result['trigger_level']:,.0f}",
        "",
        f"📈 *Volume: {vol_text}*",
        "",
        f"📊 *Strength Score: {score}/100*",
        "",
        "✅ *Filter Lolos:*"
    ]
    
    for name, detail in result["filters_passed"].items():
        if name not in ["close_confirmation", "atr"]:
            lines.append(f"  • {name}: {detail}")
    
    if result["filters_failed"]:
        lines.append("")
        lines.append("❌ *Filter Gagal:*")
        for name, detail in result["filters_failed"].items():
            lines.append(f"  • {name}: {detail}")
    
    lines.append("")
    lines.append(f"🕐 {result['current_time'].strftime('%Y-%m-%d %H:%M')} WIB")
    lines.append(f"⏱️ {datetime.now().strftime('%H:%M:%S')} - Monitor")

    return "\n".join(lines)


def format_rejected_message(result: Dict) -> str:
    """Format pesan untuk breakout yang ditolak."""
    lines = ["⚠️ *Breakout harga terdeteksi tapi TIDAK lolos filter:*"]
    for name, detail in result["filters_failed"].items():
        lines.append(f"  ✗ {name}: {detail}")
    
    if "strength_score" in result:
        score = result["strength_score"].get("score", 0)
        lines.append(f"\n📊 Strength Score: {score}/100")
    
    return "\n".join(lines)


# =====================================================================
# MAIN
# =====================================================================

def main():
    logger.info(f"=== Trailing Start Monitor - {TICKER} ===")
    logger.info(f"Interval: {INTRADAY_INTERVAL} | Lookback: {INTRADAY_LOOKBACK_BARS} bars")
    
    # --- AMBIL DATA ---
    intraday_df = get_intraday_data(TICKER)
    if intraday_df is None:
        logger.warning("Data intraday tidak tersedia, keluar.")
        sys.exit(0)

    daily_df = get_daily_data(TICKER)
    if daily_df is None:
        logger.warning("Data harian tidak tersedia, keluar.")
        sys.exit(0)

    # --- LIQUIDITY CHECK ---
    is_liquid, liquidity_details = check_liquidity(intraday_df, daily_df)
    if not is_liquid:
        logger.warning(f"Saham {TICKER} tidak likuid:")
        for key, value in liquidity_details.items():
            if key != "is_liquid":
                logger.warning(f"  {key}: {value}")
        sys.exit(0)
    
    logger.info("✅ Likuiditas OK")
    for key, value in liquidity_details.items():
        if key != "is_liquid" and "✅" in str(value):
            logger.info(f"  {key}: {value}")

    # --- DETEKSI BREAKOUT ---
    result = detect_breakout(intraday_df, daily_df)

    # --- LOG DETAIL ---
    logger.info(
        f"{TICKER} | Rp{result['current_price']:,.0f} @ {result['current_time']} | "
        f"Low: Rp{result['lowest_low']:,.0f} | Trigger: Rp{result['trigger_level']:,.0f} | "
        f"↑{result['actual_percent_from_low']:.2f}% | "
        f"Breakout: {result['is_price_breakout']} | Final: {result['is_final_breakout']}"
    )
    
    if "strength_score" in result:
        score = result["strength_score"]
        logger.info(f"Strength Score: {score['score']}/100 - {score['category']}")

    # --- LOG FILTER ---
    if result["filters_failed"]:
        logger.info("❌ Filter Gagal:")
        for name, detail in result["filters_failed"].items():
            logger.info(f"  ✗ {name}: {detail}")

    if result["filters_passed"]:
        logger.info("✅ Filter Lolos:")
        for name, detail in result["filters_passed"].items():
            logger.info(f"  ✓ {name}: {detail}")

    # --- STATE CHECK ---
    state = load_state()
    current_time_str = str(result["current_time"])

    already_alerted = (
        state.get("last_alert_time") == current_time_str
        and state.get("last_lowest_low") == result["lowest_low"]
    )

    # --- SEND NOTIFICATION ---
    if result["is_final_breakout"] and not already_alerted:
        message = format_alert_message(result)
        send_telegram_message(message)

        state["last_alert_time"] = current_time_str
        state["last_lowest_low"] = result["lowest_low"]
        save_state(state)
        logger.info("✅ Alert terkirim!")
    else:
        if result["is_price_breakout"] and not result["is_final_breakout"]:
            logger.info(format_rejected_message(result))
        else:
            logger.info("ℹ️ Belum breakout atau sudah pernah alert.")
        save_state(state)


if __name__ == "__main__":
    main()
