import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import linregress
from datetime import datetime, timedelta
import alpaca_trade_api as tradeapi
import os
import sys
import schedule
import time
import pytz
from dotenv import load_dotenv
import warnings

warnings.filterwarnings("ignore")

# ─────────────────────────── 1. CONFIGURATION ────────────────────────────── #

load_dotenv()

# Institutional Limits
MAX_SINGLE_WEIGHT = 0.12        # 12% max per asset
MAX_SECTOR_WEIGHT = 0.28        # 28% max per sector
CASH_BUFFER       = 0.02        # 98% MAX EXPOSURE (ZERO LEVERAGE)
DRIFT_THRESHOLD   = 0.04        # 4% friction tolerance (used to avoid overtrading)

SECTORS = {
    "Tech"       : ["QQQ", "SMH", "XLK", "NVDA", "MSFT", "AAPL"],
    "Healthcare" : ["XLV", "LLY", "UNH"],
    "Industrials": ["XLI", "ITA", "RTX"],
    "Energy"     : ["XLE", "URA", "COPX"],
    "EM/Intl"    : ["EEM", "VEA"],
    "Alpha"      : ["IBIT", "MTUM"], 
    "Defensives" : ["XLP", "XLU"],
    "RealAssets" : ["VNQ", "DBC"],
}

OFFENSIVE_ASSETS = [t for sub in SECTORS.values() for t in sub]
DEFENSIVE_ASSETS = ["GLD", "TLT", "IEF", "SHY"]
ALL_TICKERS      = list(set(OFFENSIVE_ASSETS + DEFENSIVE_ASSETS + ["SPY", "BTC-USD"]))

# ─────────────────────────── 2. LOGGING & ALERTS ─────────────────────────── #

def log_msg(msg):
    """Log to console and file simultaneously for Docker and Dashboard sync"""
    ts = datetime.now(pytz.timezone('America/New_York')).strftime('%Y-%m-%d %H:%M:%S %Z')
    formatted_msg = f"[{ts}] {msg}"
    print(formatted_msg)
    sys.stdout.flush() # Force Docker to write log immediately
    try:
        with open("aegis_production.log", "a") as f:
            f.write(formatted_msg + "\n")
    except Exception as e:
        print(f"File log error: {e}")

# ─────────────────────────── 3. DATA PIPELINE ────────────────────────────── #

def fetch_live_data() -> pd.DataFrame:
    log_msg(f"📥 Fetching Global Matrix ({len(ALL_TICKERS)} tickers)...")
    start_d = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
    
    df = yf.download(ALL_TICKERS, start=start_d, progress=False)["Close"]

    if "IBIT" in df.columns and "BTC-USD" in df.columns:
        btc = df["BTC-USD"].reindex(df.index).ffill()
        first_ibit = df["IBIT"].dropna().index[0] if not df["IBIT"].dropna().empty else df.index[0]
        try:
            ratio = df["IBIT"].loc[first_ibit] / btc.loc[first_ibit]
            df["IBIT"] = df["IBIT"].fillna(btc * ratio)
        except Exception:
            pass # Failsafe if IBIT has no data yet

    df = df.drop(columns=["BTC-USD"], errors="ignore").ffill().bfill()
    
    if "SPY" in df.columns:
        df = df.loc[df["SPY"].dropna().index] 
        
    log_msg(f"✅ Data fetched successfully. Evaluating context for {df.index[-1].strftime('%Y-%m-%d')}.")
    return df

# ─────────────────────────── 4. ALPHA ENGINE ─────────────────────────────── #

def trend_quality_score(prices: pd.Series, window: int = 90) -> float:
    if len(prices) < window: return 0.0
    y = prices.tail(window).values
    if y[0] == 0 or np.isnan(y[0]): return 0.0
    y = y / y[0]
    x = np.arange(len(y))
    slope, _, r, _, _ = linregress(x, y)
    return float((slope * 252) * (r ** 2))

def compute_alpha_scores(data: pd.DataFrame) -> pd.Series:
    scores = {}
    for t in OFFENSIVE_ASSETS:
        if t not in data.columns: continue
        p = data[t].dropna()
        if len(p) < 252: continue

        tq    = trend_quality_score(p, window=90)
        mom6  = float((p.iloc[-1] / p.iloc[-126]) - 1)
        vol3m = float(p.pct_change().tail(63).std() * np.sqrt(252))
        sharp = mom6 / vol3m if vol3m > 1e-6 else 0.0
        mom12 = float((p.iloc[-1] / p.iloc[-252]) - 1)

        # Dual Momentum Filter
        if mom6 <= 0 or mom12 <= 0:
            scores[t] = -999.0
            continue

        scores[t] = 0.4 * tq + 0.4 * sharp + 0.2 * mom12
    return pd.Series(scores)

# ─────────────────────────── 5. RISK ENGINE ─────────────────────────── #

def apply_risk_limits(weights: dict) -> pd.Series:
    off_w = {k: v for k, v in weights.items() if k in OFFENSIVE_ASSETS}
    def_w = {k: v for k, v in weights.items() if k in DEFENSIVE_ASSETS}

    # Strict Cap on individual assets
    off_w = {k: min(v, MAX_SINGLE_WEIGHT) for k, v in off_w.items()}

    # Sector Caps
    for sector, tickers in SECTORS.items():
        sector_exp = sum(off_w.get(t, 0) for t in tickers)
        if sector_exp > MAX_SECTOR_WEIGHT:
            scale = MAX_SECTOR_WEIGHT / sector_exp
            for t in tickers:
                if t in off_w: off_w[t] *= scale

    # Re-assemble and apply Cash Buffer (Zero Leverage)
    final = {**off_w, **def_w}
    total = sum(final.values())
    if total > 0:
        final = {k: (v / total) * (1.0 - CASH_BUFFER) for k, v in final.items()}

    # Prune micro-positions
    return pd.Series({k: v for k, v in final.items() if v >= 0.005})

# ─────────────────────────── 6. THE CHIMERA KERNEL ───────────────────────── #

def compute_target_weights(data: pd.DataFrame, api: tradeapi.REST) -> dict:
    spy = data["SPY"]
    if len(spy) < 252:
        log_msg("⚠️ Insufficient SPY data. Defaulting to Cash/SHY.")
        return {"SHY": 1.0 - CASH_BUFFER}

    # --- A. REGIME SENTINEL (Two-Speed Hysteresis) ---
    sma200   = float(spy.rolling(200).mean().iloc[-1])
    sma50    = float(spy.rolling(50).mean().iloc[-1])
    spy_60h  = float(spy.tail(60).max())
    dd_60h   = float((spy.iloc[-1] / spy_60h) - 1)

    bearish = (spy.iloc[-1] < sma200) and (spy.iloc[-1] < sma50) and (dd_60h < -0.05)
    bull_trend = not bearish

    # --- B. INFLATION SENTINEL ---
    dbc = data["DBC"].dropna() if "DBC" in data.columns else None
    inflation = False
    if dbc is not None and len(dbc) > 120:
        inflation = float(dbc.iloc[-1]) > float(dbc.rolling(120).mean().iloc[-1])

    # --- C. VOLATILITY & KINETIC BRAKE ---
    hist_vols = spy.pct_change().rolling(21).std() * np.sqrt(252)
    vol_pct   = float(hist_vols.tail(252).rank(pct=True).iloc[-1])

    if   vol_pct < 0.35: atk_split = 0.97
    elif vol_pct < 0.55: atk_split = 0.82
    elif vol_pct < 0.70: atk_split = 0.72
    else:                atk_split = 0.30

    # Kinetic Brake (Live Drawdown Amputation) via Alpaca
    try:
        hist = api.get_portfolio_history(period="1A", timeframe="1D")
        equity_curve = pd.Series(hist.equity)
        live_dd = float((equity_curve.iloc[-1] / equity_curve.max()) - 1)
        if live_dd < -0.10: 
            atk_split *= 0.50 
            log_msg(f"⚠️ KINETIC BRAKE: Drawdown {live_dd:.2%} -> Offense slashed by 50%")
        if live_dd < -0.15: 
            atk_split *= 0.20 
            log_msg(f"🚨 KINETIC BRAKE: Drawdown {live_dd:.2%} -> Offense slashed by 80%")
    except Exception:
        log_msg("ℹ️ Kinetic Brake skipped (No Alpaca history found).")

    target = {}

    # --- D. BUNKER MODE ---
    if not bull_trend:
        log_msg("🛡️ BUNKER MODE ENGAGED (SPY below constraints)")
        if inflation: 
            target = {"GLD": 0.42, "DBC": 0.20, "SHY": 0.36}
            log_msg("🔥 Inflation context detected -> Heavy Real Assets")
        else:         
            target = {"TLT": 0.48, "IEF": 0.12, "GLD": 0.22, "SHY": 0.16}
            log_msg("❄️ Deflationary context -> Heavy Long Bonds")

    # --- E. ALPHA SELECTION & CONVEX WEIGHTING ---
    else:
        log_msg(f"🟢 BULL REGIME (Vol Rank: {vol_pct:.0%} | Offense Cap: {atk_split:.0%})")
        scores = compute_alpha_scores(data)
        scores = scores[scores > 0].sort_values(ascending=False)
        top7   = scores.head(7).index.tolist()

        if len(top7) >= 3:
            mom3 = [(data[t].iloc[-1] / data[t].iloc[-63]) - 1 for t in top7[:3]]
            if all(m > 0.08 for m in mom3):
                atk_split = min(atk_split + 0.05, 0.97) # Momentum premium boost

        if not top7:
            target = {"SHY": 0.60, "GLD": 0.20, "IEF": 0.18}
            log_msg("⚠️ No offensive asset passed filters. Reverting to safe yield.")
        else:
            vols   = data[top7].pct_change().tail(63).std()
            inv_v  = 1.0 / vols.replace(0, np.nan).fillna(1.0)
            n      = len(top7)
            rank_w = pd.Series({t: float(n - i) for i, t in enumerate(top7)})

            # 60% Rank conviction, 40% Inverse Volatility smoothing
            combined = (0.60 * rank_w / rank_w.sum() + 0.40 * inv_v / inv_v.sum())
            atk_w    = (combined / combined.sum()) * atk_split

            for t in top7: target[t] = float(atk_w[t])

            def_split = 1.0 - atk_split
            if def_split <= 0.20:
                if inflation:
                    target["GLD"], target["SHY"] = def_split * 0.70, def_split * 0.30
                else:
                    target["GLD"], target["SHY"] = def_split * 0.50, def_split * 0.50
            else:
                if inflation:
                    target["GLD"], target["DBC"], target["IEF"] = def_split * 0.55, def_split * 0.25, def_split * 0.20
                else:
                    target["TLT"], target["GLD"], target["IEF"], target["SHY"] = def_split * 0.45, def_split * 0.30, def_split * 0.15, def_split * 0.10

    # --- F. APPLY CAPS ---
    final_weights = apply_risk_limits(target)
    return final_weights.to_dict()

# ─────────────────────────── 7. LIVE EXECUTION ────────────────────────────── #

def execute_rebalance():
    log_msg("="*60)
    log_msg("🚀 V-CHIMERA KERNEL — INITIATING REBALANCE SEQUENCE")
    log_msg("="*60)

    try:
        # 1. Init API
        api = tradeapi.REST(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), os.getenv("ALPACA_BASE_URL"), 'v2')
        account = api.get_account()
        equity = float(account.equity)
        log_msg(f"💰 Account Equity: ${equity:,.2f}")
        
        # 2. Get Data & Calculate Target
        df = fetch_live_data()
        target_weights = compute_target_weights(df, api)
        
        log_msg("🎯 TARGET ALLOCATION COMPUTED:")
        for t, w in target_weights.items():
            log_msg(f"   -> {t}: {w:.2%}")
            
        # 3. Clean up non-target positions
        log_msg("🧹 PURGING OBSOLETE POSITIONS...")
        current_positions = api.list_positions()
        for pos in current_positions:
            if pos.symbol not in target_weights:
                log_msg(f"   [LIQUIDATE] Selling 100% of {pos.symbol}")
                api.close_position(pos.symbol)
                
        # 4. Rebalance target positions
        log_msg("⚖️ ROUTING CAPITAL TO TARGETS...")
        for ticker, target_w in target_weights.items():
            target_value = equity * target_w
            
            try:
                current_pos = api.get_position(ticker)
                current_value = float(current_pos.market_value)
            except Exception:
                current_value = 0.0
                
            diff = target_value - current_value
            
            # Application of Drift Threshold (Tolerance to avoid friction costs)
            # Only trade if difference is greater than 4% of total equity
            if abs(diff) > (equity * DRIFT_THRESHOLD):
                side = 'buy' if diff > 0 else 'sell'
                log_msg(f"   [ORDER] {side.upper()} {ticker} | Notional: ${abs(diff):,.2f} | Aiming: {target_w:.2%}")
                
                try:
                    api.submit_order(
                        symbol=ticker, 
                        notional=abs(diff), 
                        side=side, 
                        type='market', 
                        time_in_force='day'
                    )
                except Exception as e:
                    log_msg(f"   ❌ FATAL API ERROR for {ticker}: {e}")
            else:
                log_msg(f"   [HOLD] {ticker} within {DRIFT_THRESHOLD:.0%} drift tolerance. No action taken.")

        log_msg("✅ REBALANCE SEQUENCE COMPLETED SUCCESSFULLY")
        log_msg("="*60)
        
    except Exception as e:
        log_msg(f"💀 CRITICAL KERNEL FAILURE: {e}")

# ─────────────────────────── 8. DAEMON SCHEDULER ────────────────────────── #

def is_market_open():
    """Vérifie si le marché est ouvert avant d'agir."""
    try:
        api = tradeapi.REST(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), os.getenv("ALPACA_BASE_URL"), 'v2')
        clock = api.get_clock()
        return clock.is_open
    except Exception:
        return False

def job():
    if is_market_open():
        execute_rebalance()
    else:
        log_msg("💤 Market is closed. Rebalance skipped.")

if __name__ == "__main__":
    # If run directly manually, execute once
    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        execute_rebalance()
        sys.exit(0)
        
    # Standard Docker Execution: Daemon mode
    log_msg("🛡️ AEGIS KERNEL DAEMON STARTED")
    log_msg("⏳ Waiting for scheduled triggers...")
    
    # Planification : Exécute le vendredi à 15:45 (Heure de NY) pour rebalancer avant la fermeture du weekend
    # Note: Le Docker compose force la TZ (Timezone) à America/New_York
    schedule.every().friday.at("15:45").do(job)
    
    # Boucle infinie du Daemon
    while True:
        schedule.run_pending()
        time.sleep(60)

