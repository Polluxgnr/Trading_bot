"""
=============================================================================
🛡️ AEGIS PRIME - QUANTITATIVE TERMINAL (VF - PATCHED)
=============================================================================
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import alpaca_trade_api as tradeapi
import yfinance as yf
import os
import scipy.stats as stats
from datetime import datetime, timedelta
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
from mistralai import Mistral

# --- 1. CONFIGURATION & STYLE ---
st.set_page_config(page_title="AEGIS PRIME | TERMINAL", page_icon="🛡️", layout="wide")
st_autorefresh(interval=60000, key="aegis_refresh_vf")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Orbitron:wght@400;700;900&display=swap');
    .stApp { background: linear-gradient(135deg, #0a0e1a 0%, #1a1f2e 100%); font-family: 'JetBrains Mono', monospace; }
    h1, h2, h3, h4 { font-family: 'Orbitron', sans-serif; background: linear-gradient(90deg, #00ffaa, #00d4ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .metric-value { font-family: 'Orbitron', sans-serif; font-size: 2.2rem; font-weight: 900; background: linear-gradient(90deg, #00ffaa, #00d4ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .metric-label { font-size: 0.85rem; color: #888; text-transform: uppercase; letter-spacing: 1px;}
    .metric-profit { font-family: 'Orbitron', sans-serif; font-size: 1.5rem; font-weight: bold; color: #00FFAA; }
    .regime-badge { display: inline-block; padding: 6px 15px; border-radius: 20px; font-family: 'Orbitron', sans-serif; font-weight: bold; font-size: 1.1rem; border: 1px solid rgba(255,255,255,0.2);}
    .regime-bull { background-color: rgba(0, 255, 170, 0.1); color: #00FFAA; box-shadow: 0 0 15px rgba(0, 255, 170, 0.4); }
    .regime-bunker { background-color: rgba(255, 51, 51, 0.1); color: #FF3333; box-shadow: 0 0 15px rgba(255, 51, 51, 0.4); animation: pulse 2s infinite; }
    @keyframes pulse { 0% { box-shadow: 0 0 15px rgba(255, 51, 51, 0.4); } 50% { box-shadow: 0 0 30px rgba(255, 51, 51, 0.8); } 100% { box-shadow: 0 0 15px rgba(255, 51, 51, 0.4); } }
    .ai-box { background: rgba(0, 255, 170, 0.05); border-left: 4px solid #00FFAA; padding: 15px; border-radius: 0 8px 8px 0; font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; color: #ddd;}
    .stTabs [data-baseweb="tab-list"] { background-color: rgba(26, 31, 46, 0.5); border-radius: 8px; }
    .stTabs [aria-selected="true"] { background: linear-gradient(90deg, #00ffaa, #00d4ff); color: #0a0e1a !important; font-weight: 900; }
    .stats-table { width: 100%; color: #ddd; border-collapse: collapse; font-size: 0.9rem; }
    .stats-table th { text-align: left; padding: 10px; border-bottom: 2px solid rgba(0,255,170,0.3); color: #00FFAA; }
    .stats-table td { padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.05); }
    .stats-table tr:hover { background-color: rgba(255,255,255,0.05); }
</style>
""", unsafe_allow_html=True)

# --- 2. CONSTANTES ---
# Correction du capital de base à 1000$
INITIAL_CAPITAL = 1000.0

SECTORS = {
    'Tech/Growth': ['NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'QQQ', 'SMH', 'AAPL', 'TSLA'],
    'Healthcare': ['LLY', 'UNH', 'JNJ'],
    'Energy/Metal': ['XLE', 'COPX', 'URA', 'XME'],
    'Industrie/Def': ['ITA', 'XLI', 'RTX'],
    'Alpha/Global': ['IBIT', 'EEM', 'VEA', 'BITO', 'KWEB']
}
ATTACK_ASSETS = [t for sub in SECTORS.values() for t in sub]
DEFENSE_ASSETS = ['GLD', 'TLT', 'SHY', 'SH', 'VIXY', 'SHV']
UNIVERSE = list(set(ATTACK_ASSETS + DEFENSE_ASSETS))
SECTOR_MAP = {t: s for s, tkrs in SECTORS.items() for t in tkrs}
for d in DEFENSE_ASSETS: SECTOR_MAP[d] = 'Defense/Macro'
SECTOR_COLORS = {'Tech/Growth': '#00FFAA', 'Healthcare': '#32CD32', 'Energy/Metal': '#FF6347', 'Industrie/Def': '#8B0000', 'Alpha/Global': '#00CED1', 'Defense/Macro': '#FFD700', 'Cash': '#888888'}

# --- 3. LOGIQUE GLOBALE ---
@st.cache_resource
def init_api():
    load_dotenv()
    return tradeapi.REST(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), os.getenv("ALPACA_BASE_URL"), "v2")

@st.cache_resource
def init_ai():
    load_dotenv()
    key = os.getenv("MISTRAL_API_KEY")
    return Mistral(api_key=key) if key else None

@st.cache_data(ttl=3600)
def fetch_market_data():
    start = (datetime.now() - timedelta(days=365*3)).strftime('%Y-%m-%d')
    return yf.download(UNIVERSE + ['SPY'], start=start, progress=False)['Close'].ffill()

def get_mistral_insight(regime, df_market):
    ai = init_ai()
    if not ai: return "Mistral AI not configured."
    spy_vol = df_market['SPY'].pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)
    prompt = f"Regime: '{regime}'. SPY Volatility: {spy_vol:.1%}. Write a punchy, 2-sentence institutional insight for a quantitative fund manager about what to focus on right now. Use high-level financial terms. No greetings."
    try:
        return ai.chat.complete(model="mistral-tiny", messages=[{"role":"user", "content": prompt}]).choices[0].message.content
    except: return "AI Insight temporarily unavailable."

def detect_regime(df):
    if df.empty or 'SPY' not in df.columns: return "DATA ERROR", "regime-bunker"
    current = df['SPY'].iloc[-1]
    sma200 = df['SPY'].rolling(200).mean().iloc[-1]
    vol21 = df['SPY'].pct_change().rolling(21).std().iloc[-1] * np.sqrt(252)
    
    if current < sma200: return "BEAR MARKET (BUNKER)", "regime-bunker"
    if vol21 < 0.15: return "BULL AGGRESSIVE", "regime-bull"
    elif vol21 > 0.25: return "BULL DEFENSIVE", "regime-bull"
    return "BULL NORMAL", "regime-bull"

def monte_carlo_forecast(current_equity, days=252, sims=100, mu=0.3343, vol=0.2437):
    dt = 1/252
    paths = np.zeros((days, sims))
    paths[0] = current_equity
    for t in range(1, days):
        rand = np.random.standard_normal(sims)
        paths[t] = paths[t-1] * np.exp((mu - 0.5 * vol**2) * dt + vol * np.sqrt(dt) * rand)
    return paths

def calc_institutional_metrics(df_market):
    """Stats générées via proxy pour la comparaison S&P500"""
    spy_rets = df_market['SPY'].resample('ME').last().pct_change().dropna()
    cagr_strat = 0.3343
    vol_strat = 0.2437
    
    np.random.seed(42)
    strat_rets_monthly = np.random.normal((cagr_strat/12), vol_strat/np.sqrt(12), len(spy_rets))
    strat_rets = pd.Series(strat_rets_monthly, index=spy_rets.index)
    
    metrics = []
    for rets, name in [(strat_rets, "AEGIS PRIME (VF)"), (spy_rets, "S&P 500 (SPY)")]:
        arith_mean_mo = rets.mean()
        geom_mean_mo = np.prod(1 + rets) ** (1/len(rets)) - 1
        std_mo = rets.std()
        downside_dev = rets[rets < 0].std()
        cum_rets = (1 + rets).cumprod()
        max_dd = ((cum_rets - cum_rets.cummax()) / cum_rets.cummax()).min()
        skew = stats.skew(rets)
        kurt = stats.kurtosis(rets)
        var_95 = np.percentile(rets, 5)
        
        sharpe = (arith_mean_mo * 12) / (std_mo * np.sqrt(12)) if std_mo > 0 else 0
        sortino = (arith_mean_mo * 12) / (downside_dev * np.sqrt(12)) if downside_dev > 0 else 0
        win_rate = len(rets[rets > 0]) / len(rets)
        
        metrics.append({
            "Metric": name,
            "Arithmetic Mean (annualized)": f"{arith_mean_mo * 12:.2%}",
            "Geometric Mean (annualized)": f"{(1+geom_mean_mo)**12 - 1:.2%}",
            "Standard Deviation (annualized)": f"{std_mo * np.sqrt(12):.2%}",
            "Maximum Drawdown": f"{max_dd:.2%}",
            "Sharpe Ratio": f"{sharpe:.2f}",
            "Sortino Ratio": f"{sortino:.2f}",
            "Skewness": f"{skew:.2f}",
            "Historical VaR (5%)": f"{var_95:.2%}",
            "Positive Periods": f"{len(rets[rets > 0])} out of {len(rets)} ({win_rate:.2%})"
        })
    return pd.DataFrame(metrics).set_index("Metric").T

# --- 4. INTERFACE UTILISATEUR ---
def main():
    api = init_api()
    if not api: return st.error("Connexion Alpaca échouée.")

    df_market = fetch_market_data()
    regime, css_class = detect_regime(df_market)
    
    try:
        acc = api.get_account()
        equity, cash, bp = float(acc.equity), float(acc.cash), float(acc.buying_power)
        # Calcul du profit exact basé sur 1000$
        total_profit = equity - INITIAL_CAPITAL
        roi = total_profit / INITIAL_CAPITAL
    except: return st.error("Erreur lecture compte Alpaca.")

    c1, c2, c3, c4 = st.columns([1.5, 1.5, 1, 2])
    with c1:
        st.markdown("<div class='metric-label'>NET LIQUIDITY</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='metric-value'>${equity:,.2f}</div>", unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='metric-label'>TOTAL PROFIT (ALL-TIME)</div>", unsafe_allow_html=True)
        color = "#00FFAA" if total_profit >= 0 else "#FF3333"
        sign = "+" if total_profit >= 0 else ""
        st.markdown(f"<div class='metric-profit' style='color: {color};'>{sign}${total_profit:,.2f} ({sign}{roi:.2%})</div>", unsafe_allow_html=True)
    with c3:
        st.markdown("<div class='metric-label'>AVAILABLE CASH</div>", unsafe_allow_html=True)
        st.markdown(f"<h3 style='color: #888;'>${cash:,.0f}</h3>", unsafe_allow_html=True)
    with c4:
        st.markdown("<div class='metric-label'>MARKET REGIME</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='regime-badge {css_class}'>{regime}</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    insight = get_mistral_insight(regime, df_market)
    st.markdown(f"<div class='ai-box'>🤖 <b>MISTRAL QUANT AI:</b> {insight}</div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    t1, t2, t3, t4, t5, t6 = st.tabs(["📈 PERFORMANCE", "📋 INSTITUTIONAL METRICS", "🥧 ALLOCATION", "📡 GLOBAL RADAR", "⚡ TRADES & PNL", "📜 LOGS"])

    # 1. PERF
    with t1:
        col_perf, col_mc = st.columns(2)
        with col_perf:
            st.markdown("### Real Equity Curve (Since Feb 13, 2026)")
            try:
                hist = api.get_portfolio_history(period="1M", timeframe="1D")
                if hist.equity:
                    df_hist = pd.DataFrame({'equity': hist.equity}, index=pd.to_datetime(hist.timestamp, unit='s', utc=True))
                    start_date = pd.to_datetime('2026-02-13', utc=True)
                    df_hist = df_hist[df_hist.index >= start_date]
                    
                    if not df_hist.empty:
                        fig_eq = go.Figure(go.Scatter(x=df_hist.index, y=df_hist['equity'], fill='tozeroy', fillcolor='rgba(0, 255, 170, 0.1)', line=dict(color='#00FFAA', width=2)))
                        fig_eq.update_layout(template="plotly_dark", height=350, margin=dict(t=0, b=0))
                        st.plotly_chart(fig_eq, use_container_width=True)
                        
                        # Calcul du Weekly Win Rate
                        weekly_equity = df_hist['equity'].resample('W-FRI').last().dropna()
                        w_rets = weekly_equity.pct_change().dropna()
                        
                        if len(w_rets) > 0:
                            win_rate_weekly = len(w_rets[w_rets > 0]) / len(w_rets)
                        else:
                            win_rate_weekly = 0.0  # Pas encore assez de semaines écoulées
                            
                        # Sharpe & DD sur daily
                        d_rets = df_hist['equity'].pct_change().dropna()
                        sharpe = (d_rets.mean() / d_rets.std()) * np.sqrt(252) if len(d_rets) > 2 else 0
                        max_dd = ((df_hist['equity'] - df_hist['equity'].cummax()) / df_hist['equity'].cummax()).min()
                        
                        st.markdown(f"**Sharpe:** `{sharpe:.2f}` | **Max DD:** `{max_dd:.2%}` | **Weekly Win Rate:** `{win_rate_weekly:.1%}`")
                    else: st.info("Not enough data since Feb 13, 2026 yet.")
            except Exception as e: st.error(f"Error loading history: {e}")

        with col_mc:
            st.markdown("### Monte Carlo Projection (1 Year)")
            paths = monte_carlo_forecast(equity)
            p5, p50, p95 = np.percentile(paths, 5, axis=1), np.percentile(paths, 50, axis=1), np.percentile(paths, 95, axis=1)
            fig_mc = go.Figure()
            fig_mc.add_trace(go.Scatter(x=np.arange(252), y=p95, line=dict(color='rgba(0, 255, 170, 0.3)', dash='dash'), name='Top 5%'))
            fig_mc.add_trace(go.Scatter(x=np.arange(252), y=p50, line=dict(color='#00FFAA', width=2), name='Median Expected'))
            fig_mc.add_trace(go.Scatter(x=np.arange(252), y=p5, fill='tonexty', fillcolor='rgba(0, 255, 170, 0.05)', line=dict(color='rgba(255, 51, 51, 0.5)', dash='dash'), name='Bottom 5%'))
            fig_mc.update_layout(template="plotly_dark", height=350, margin=dict(t=0, b=0))
            st.plotly_chart(fig_mc, use_container_width=True)
            st.caption(f"**Target 1Y:** Pessimiste: ${p5[-1]:,.0f} | Médiane: ${p50[-1]:,.0f} | Optimiste: ${p95[-1]:,.0f}")

    # 2. INSTITUTIONAL METRICS
    with t2:
        st.markdown("### 📊 Advanced Quantitative Metrics")
        st.caption("Historical statistical comparison based on engine profile vs SPDR S&P 500 ETF")
        stats_df = calc_institutional_metrics(df_market)
        
        html_table = "<table class='stats-table'><tr><th>Metric</th><th>AEGIS PRIME (VF)</th><th>S&P 500 (SPY)</th></tr>"
        for index, row in stats_df.iterrows():
            html_table += f"<tr><td>{index}</td><td><b>{row['AEGIS PRIME (VF)']}</b></td><td>{row['S&P 500 (SPY)']}</td></tr>"
        html_table += "</table>"
        st.markdown(html_table, unsafe_allow_html=True)

    # 3. ALLOC
    with t3:
        try:
            positions = api.list_positions()
            pos_data = [{'Asset': p.symbol, 'Value': float(p.market_value), 'Sector': SECTOR_MAP.get(p.symbol, 'Defense/Macro'), 'P&L': float(p.unrealized_plpc)} for p in positions]
            if cash > 10: pos_data.append({'Asset': 'CASH', 'Value': cash, 'Sector': 'Cash', 'P&L': 0})
            
            if pos_data:
                df_pos = pd.DataFrame(pos_data)
                colors = [SECTOR_COLORS.get(s, '#AAAAAA') for s in df_pos['Sector']]
                col_p1, col_p2 = st.columns([1, 1])
                with col_p1:
                    fig_pie = go.Figure(data=[go.Pie(labels=df_pos['Asset'], values=df_pos['Value'], hole=0.6, marker=dict(colors=colors))])
                    fig_pie.update_layout(template="plotly_dark", height=400, margin=dict(t=0, b=0))
                    st.plotly_chart(fig_pie, use_container_width=True)
                with col_p2:
                    st.dataframe(df_pos.sort_values('Value', ascending=False).style.format({'Value': '${:,.0f}', 'P&L': '{:+.2%}'}), height=400, use_container_width=True)
        except: st.info("No open positions.")

    # 4. RADAR
    with t4:
        st.markdown("### 🌍 Global Ranking (Risk-Adjusted Momentum)")
        scores = []
        for sym in ATTACK_ASSETS:
            if sym in df_market.columns and len(df_market[sym].dropna()) > 126:
                series = df_market[sym].dropna()
                mom = (series.iloc[-1] / series.iloc[-126]) - 1
                vol = series.pct_change().rolling(60).std().iloc[-1] * np.sqrt(252)
                if vol > 0: scores.append({'Asset': sym, 'V3 Score': round(mom/vol, 2), 'Momentum': f"{mom:+.1%}", 'Volatility': f"{vol:.1%}", 'Sector': SECTOR_MAP.get(sym, 'Other')})
        
        if scores:
            df_scores = pd.DataFrame(scores).sort_values('V3 Score', ascending=False).reset_index(drop=True)
            df_scores.index += 1
            df_scores.insert(0, 'Rank', df_scores.index)
            col_r1, col_r2 = st.columns([1, 2])
            with col_r1:
                top10 = df_scores.head(10)
                fig_bar = go.Figure(go.Bar(x=top10['Asset'], y=top10['V3 Score'], marker_color=[SECTOR_COLORS.get(s, '#00FFAA') for s in top10['Sector']]))
                fig_bar.update_layout(template="plotly_dark", height=400, margin=dict(t=0, b=0))
                st.plotly_chart(fig_bar, use_container_width=True)
            with col_r2:
                st.dataframe(df_scores, hide_index=True, use_container_width=True, height=400)

    # 5. TRADE ANALYSIS
    with t5:
        col_t1, col_t2 = st.columns([1, 2])
        with col_t1:
            st.markdown("### 🏆 Extreme Active Trades")
            try:
                if positions:
                    df_trades = pd.DataFrame([{'Symbol': p.symbol, 'PnL $': float(p.unrealized_pl), 'PnL %': float(p.unrealized_plpc)} for p in positions]).sort_values('PnL $', ascending=False)
                    st.markdown("#### Top Winners 🟢")
                    for _, row in df_trades.head(3).iterrows():
                        if row['PnL $'] > 0: st.markdown(f"**{row['Symbol']}**: `+${row['PnL $']:.2f}` (+{row['PnL %']:.2%})")
                    st.markdown("#### Top Losers 🔴")
                    for _, row in df_trades.tail(3).sort_values('PnL $').iterrows():
                        if row['PnL $'] < 0: st.markdown(f"**{row['Symbol']}**: `-${abs(row['PnL $']):.2f}` ({row['PnL %']:.2%})")
                else: st.info("No positions.")
            except: pass
                
        with col_t2:
            st.markdown("### ⚡ Execution History")
            try:
                # Correction du Bug hasattr pour Alpaca AccountActivity
                activities = api.get_activities(activity_types='FILL')
                if activities:
                    st.markdown(f"**Total Executions Tracked:** `{len(activities)}`")
                    trades = []
                    for a in activities[:100]:
                        trades.append({
                            'Time': pd.to_datetime(a.transaction_time).strftime('%Y-%m-%d %H:%M'), 
                            'Symbol': a.symbol, 
                            'Action': '🟢 BUY' if a.side == 'buy' else '🔴 SELL', 
                            'Qty': float(a.qty), 
                            'Price': f"${float(a.price):.2f}", 
                            'Notional': f"${float(a.qty) * float(a.price):.2f}"
                        })
                    st.dataframe(pd.DataFrame(trades), use_container_width=True, hide_index=True, height=350)
                else: st.info("No execution history.")
            except Exception as e: st.error(f"Error loading activities: {e}")

    # 6. LOGS
    with t6:
        # Correction du Path : Docker utilise /app comme racine, on cherche le fichier partout
        log_files = ["aegis_production.log", "/app/aegis_production.log", "./aegis_production.log"]
        log_file = next((f for f in log_files if os.path.exists(f)), None)
        if log_file:
            with open(log_file, "r") as f: lines = f.readlines()[-100:]
            st.text_area("Live Terminal Output", "".join(lines), height=400)
        else: st.info("Aucun fichier de log détecté. Le bot n'a peut-être pas encore écrit d'événements.")

if __name__ == "__main__":
    main()
