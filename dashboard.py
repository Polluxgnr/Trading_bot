import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import alpaca_trade_api as tradeapi
import yfinance as yf
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components
from mistralai import Mistral

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Pollux Quant | Terminal", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, key="auto_refresh")

# --- 2. INSTITUTIONAL THEME ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');
    
    :root {
        --bg-deep: #0B0E14; --bg-card: #151A22; --text-main: #C9D1D9; 
        --accent-blue: #2A7BDE; --accent-green: #00E676; --accent-red: #FF3B30;
    }

    .stApp { background-color: var(--bg-deep); font-family: 'Inter', sans-serif; color: var(--text-main); }
    
    .hud-header {
        background: var(--bg-card); border-bottom: 1px solid rgba(255,255,255,0.05);
        padding: 20px 30px; margin: -3rem -3rem 30px -3rem; 
        display: flex; justify-content: space-between; align-items: center;
    }
    .hud-title { font-weight: 800; font-size: 26px; color: #FFFFFF; letter-spacing: 1px; margin: 0; }
    .hud-subtitle { font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #8B949E; margin-top: 5px;}
    .hud-links a { color: var(--accent-blue); text-decoration: none; margin-right: 15px; font-weight: 600; font-size: 14px;}
    .hud-links a:hover { text-decoration: underline; }
    .hud-status-box { text-align: right; }
    .hud-status-label { font-size: 11px; color: #8B949E; letter-spacing: 1px; text-transform: uppercase;}
    .hud-status-val { font-family: 'JetBrains Mono', monospace; color: var(--accent-green); font-weight: 700; font-size: 15px;}

    .metric-card {
        background: var(--bg-card); border: 1px solid rgba(255,255,255,0.05);
        border-radius: 8px; padding: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-bottom: 20px;
    }
    .metric-label { font-size: 12px; color: #8B949E; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px;}
    .metric-val { font-family: 'JetBrains Mono', monospace; font-size: 28px; font-weight: 700; color: #FFFFFF; margin-top: 8px;}
    .val-up { color: var(--accent-green) !important; }
    .val-down { color: var(--accent-red) !important; }
    
    .insight-box {
        background: rgba(42, 123, 222, 0.05); padding: 15px 20px; border-radius: 8px; border-left: 4px solid var(--accent-blue); margin: 0 0 25px 0;
        font-family: 'Inter', sans-serif; font-size: 14px; color: #E6EDF3; line-height: 1.5;
    }

    .stTabs [data-baseweb="tab-list"] { background-color: transparent; border-bottom: 1px solid rgba(255,255,255,0.1); gap: 10px;}
    .stTabs [data-baseweb="tab"] { color: #8B949E; font-family: 'Inter', sans-serif; font-weight: 600; font-size: 13px; }
    .stTabs [aria-selected="true"] { color: #FFFFFF !important; border-bottom: 2px solid var(--accent-blue) !important; background: transparent !important; }
</style>
""", unsafe_allow_html=True)

# --- 3. CONSTANTS ---
INITIAL_CAPITAL = 1000.0  
SECTORS = {
    'Technology': ['NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'AAPL', 'TSLA', 'SMH'],
    'Healthcare': ['LLY', 'UNH'],
    'Industrials': ['ITA', 'XLI', 'RTX'],
    'Commodities': ['GLD', 'XLE', 'COPX', 'URA'],
    'Bonds/Macro': ['IBIT', 'TLT', 'SHV']
}
ALL_ASSETS = [t for sub in SECTORS.values() for t in sub]
SECTOR_MAP = {t: s for s, tkrs in SECTORS.items() for t in tkrs}
COLOR_MAP = {'Technology': '#2A7BDE', 'Healthcare': '#00E676', 'Industrials': '#FFB703', 'Commodities': '#FF3B30', 'Bonds/Macro': '#9D4EDD', 'Cash': '#495057'}

# --- DATA FETCHING ---
@st.cache_resource
def init_clients():
    load_dotenv()
    try:
        api = tradeapi.REST(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), os.getenv("ALPACA_BASE_URL"), "v2")
    except: api = None
    ai = Mistral(api_key=os.getenv("MISTRAL_API_KEY")) if os.getenv("MISTRAL_API_KEY") else None
    return api, ai

@st.cache_data(ttl=3600)
def fetch_market_data():
    try:
        start = (datetime.now() - timedelta(days=365*3)).strftime('%Y-%m-%d')
        df = yf.download(list(set(ALL_ASSETS + ['SPY'])), start=start, progress=False, auto_adjust=True)['Close']
        if 'IBIT' in df.columns: df['IBIT'] = df['IBIT'].bfill()
        return df.ffill().dropna(thresh=10)
    except: return pd.DataFrame()

# --- TRADINGVIEW WIDGET ---
def render_tradingview_widget(symbol):
    if symbol == "CASH": return
    html = f"""
    <div class="tradingview-widget-container" style="height: 100%; width: 100%;">
      <div id="tradingview_{symbol}" style="height: 450px;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true,
        "symbol": "{symbol}",
        "interval": "D",
        "timezone": "Etc/UTC",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "enable_publishing": false,
        "backgroundColor": "#151A22",
        "gridColor": "rgba(255, 255, 255, 0.05)",
        "hide_top_toolbar": false,
        "hide_legend": false,
        "save_image": false,
        "container_id": "tradingview_{symbol}"
      }});
      </script>
    </div>
    """
    components.html(html, height=450)

def monte_carlo_forecast(current_equity):
    mu, vol, dt, sims, days = 0.3343, 0.2437, 1/252, 100, 252
    paths = np.zeros((days, sims))
    paths[0] = current_equity
    for t in range(1, days):
        paths[t] = paths[t-1] * np.exp((mu - 0.5 * vol**2) * dt + vol * np.sqrt(dt) * np.random.standard_normal(sims))
    return paths

# --- MAIN ---
def main():
    api, ai = init_clients()
    df_market = fetch_market_data()

    equity, cash, profit_usd, profit_pct = INITIAL_CAPITAL, 0.0, 0.0, 0.0
    positions = []
    if api:
        try:
            acc = api.get_account()
            equity = float(acc.equity)
            cash = float(acc.cash)
            profit_usd = equity - INITIAL_CAPITAL
            profit_pct = profit_usd / INITIAL_CAPITAL if INITIAL_CAPITAL > 0 else 0
            positions = api.list_positions()
        except Exception as e:
            st.error(f"Broker API Error: {e}")

    regime = "DEFENSIVE (BEAR)"
    regime_color = "#FF3B30"
    if not df_market.empty and 'SPY' in df_market.columns:
        spy = df_market['SPY'].dropna()
        if len(spy) > 200 and spy.iloc[-1] > spy.rolling(200).mean().iloc[-1]:
            regime = "GROWTH (BULL)"
            regime_color = "#00E676"

    # HEADER
    st.markdown(f"""
    <div class="hud-header">
        <div>
            <h1 class="hud-title">POLLUX QUANTITATIVE MACRO</h1>
            <div class="hud-subtitle">Autonomous Fund Management System</div>
            <div class="hud-links" style="margin-top: 10px;">
                <a href="https://polluxgronier.me" target="_blank">🌐 polluxgronier.me</a>
                <a href="https://github.com/Polluxgnr" target="_blank">💻 GitHub</a>
            </div>
        </div>
        <div class="hud-status-box">
            <div class="hud-status-label">BROKER STATUS</div><div class="hud-status-val" style="color: {'#00E676' if api else '#FF3B30'};">{'CONNECTED' if api else 'OFFLINE'}</div>
            <div class="hud-status-label" style="margin-top: 5px;">MARKET REGIME</div><div class="hud-status-val" style="color: {regime_color};">{regime}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Total Equity</div><div class="metric-val">${equity:,.2f}</div></div>', unsafe_allow_html=True)
    with c2: 
        p_class = "val-up" if profit_usd >= 0 else "val-down"
        p_sign = "+" if profit_usd >= 0 else ""
        st.markdown(f'<div class="metric-card"><div class="metric-label">All-Time Return</div><div class="metric-val {p_class}">{p_sign}${profit_usd:,.2f} ({p_sign}{profit_pct:.2%})</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Available Cash</div><div class="metric-val" style="color:#8B949E;">${cash:,.2f}</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">Risk Control</div><div class="metric-val" style="font-size:22px; color:#2A7BDE; margin-top:12px;">NO LEVERAGE</div></div>', unsafe_allow_html=True)

    # AI INSIGHT
    ai_text = "Waiting for market data to generate insights..."
    if ai and not df_market.empty and 'SPY' in df_market.columns:
        try:
            spy = df_market['SPY'].dropna()
            vol = spy.pct_change().tail(21).std() * np.sqrt(252)
            trend = "Bullish" if spy.iloc[-1] > spy.rolling(200).mean().iloc[-1] else "Bearish"
            prompt = f"SPY Trend: {trend}, SPY Volatility: {vol:.1%}. Write a concise, 2-sentence market analysis for a quantitative portfolio manager."
            ai_text = ai.chat.complete(model="mistral-tiny", messages=[{"role":"user", "content": prompt}]).choices[0].message.content
        except: ai_text = "AI Engine temporarily unavailable."
    st.markdown(f"<div class='insight-box'><b>AI MARKET ANALYSIS:</b> {ai_text}</div>", unsafe_allow_html=True)

    # TABS
    t1, t2, t3, t4, t5 = st.tabs(["🎯 PORTFOLIO ALLOCATION", "🎲 FORECAST & SIMULATION", "📡 MARKET RADAR", "🧠 STRATEGY OVERVIEW", "⚡ EXECUTION LOGS"])

    # --- TAB 1: ALLOCATION ---
    with t1:
        col_pie, col_pos = st.columns([1, 1.5])
        with col_pie:
            st.markdown("#### Sector Distribution")
            pos_data = [{'Asset': p.symbol, 'Value': float(p.market_value), 'Sector': SECTOR_MAP.get(p.symbol, 'Bonds/Macro')} for p in positions]
            if cash > 10: pos_data.append({'Asset': 'CASH', 'Value': cash, 'Sector': 'Cash'})
            
            if pos_data:
                fig_pie = px.sunburst(pd.DataFrame(pos_data), path=['Sector', 'Asset'], values='Value', color='Sector', color_discrete_map=COLOR_MAP)
                fig_pie.update_layout(template="plotly_dark", height=400, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_pie, use_container_width=True)
            else: st.info("No active exposure.")

        with col_pos:
            st.markdown("#### Active Positions")
            if positions:
                df_pnl = pd.DataFrame([{
                    'Asset': p.symbol, 
                    'Value': float(p.market_value), 
                    'PnL $': float(p.unrealized_pl), 
                    'PnL %': float(p.unrealized_plpc)
                } for p in positions])
                
                st.dataframe(
                    df_pnl.sort_values('Value', ascending=False).style.format({
                        'Value': '${:,.2f}', 'PnL $': '{:+.2f}', 'PnL %': '{:+.2%}'
                    }).map(lambda x: "color: #00E676;" if x > 0 else "color: #FF3B30;", subset=['PnL $', 'PnL %']), 
                    use_container_width=True, hide_index=True, height=200
                )
                
                st.markdown("<br>", unsafe_allow_html=True)
                c_best, c_worst = st.columns(2)
                with c_best:
                    st.markdown("**Top Performer 🟢**")
                    best = df_pnl.loc[df_pnl['PnL $'].idxmax()] if df_pnl['PnL $'].max() > 0 else None
                    if best is not None: st.success(f"{best['Asset']}: +${best['PnL $']:.2f} (+{best['PnL %']:.2%})")
                    else: st.write("N/A")
                with c_worst:
                    st.markdown("**Worst Performer 🔴**")
                    worst = df_pnl.loc[df_pnl['PnL $'].idxmin()] if df_pnl['PnL $'].min() < 0 else None
                    if worst is not None: st.error(f"{worst['Asset']}: -${abs(worst['PnL $']):.2f} ({worst['PnL %']:.2%})")
                    else: st.write("N/A")
            else: st.info("No open positions.")

    # --- TAB 2: FORECAST ---
    with t2:
        st.markdown("#### Monte Carlo Portfolio Projection (1 Year)")
        st.write("Stochastic simulation generating 100 possible future paths based on the strategy's historical risk/return profile (CAGR ~33%, Volatility ~24%).")
        paths = monte_carlo_forecast(equity)
        p5, p50, p95 = np.percentile(paths, 5, axis=1), np.percentile(paths, 50, axis=1), np.percentile(paths, 95, axis=1)
        
        fig_mc = go.Figure()
        fig_mc.add_trace(go.Scatter(y=p95, line=dict(color='rgba(42, 123, 222, 0.5)', dash='dot'), name='Optimistic (Top 5%)'))
        fig_mc.add_trace(go.Scatter(y=p50, line=dict(color='#00E676', width=2), name='Median Expected'))
        fig_mc.add_trace(go.Scatter(y=p5, fill='tonexty', fillcolor='rgba(255, 59, 48, 0.05)', line=dict(color='rgba(255, 59, 48, 0.5)', dash='dot'), name='Pessimistic (Bottom 5%)'))
        fig_mc.update_layout(template="plotly_dark", height=400, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_mc, use_container_width=True)
        
        c_min, c_med, c_max = st.columns(3)
        c_min.metric("Pessimistic Forecast", f"${p5[-1]:,.0f}")
        c_med.metric("Median Forecast", f"${p50[-1]:,.0f}")
        c_max.metric("Optimistic Forecast", f"${p95[-1]:,.0f}")

    # --- TAB 3: RADAR ---
    with t3:
        c_radar, c_deep = st.columns([1, 1.2])
        with c_radar:
            st.markdown("#### Quantitative Factor Scoring")
            scores = []
            if not df_market.empty:
                for sym in ALL_ASSETS:
                    if sym in df_market.columns:
                        series = df_market[sym].dropna()
                        if len(series) > 126:
                            mom = (series.iloc[-1] / series.iloc[-60]) - 1
                            vol = series.pct_change().tail(60).std() * np.sqrt(252)
                            if vol > 0:
                                scores.append({
                                    'Asset': sym, 'Risk-Adj Score': round(mom/vol, 2), 
                                    'Momentum': mom, 'Volatility': vol
                                })
                if scores:
                    df_scores = pd.DataFrame(scores).sort_values('Risk-Adj Score', ascending=False)
                    st.dataframe(
                        df_scores.style.format({'Momentum': '{:+.1%}', 'Volatility': '{:.1%}'}), 
                        use_container_width=True, hide_index=True, height=450
                    )
        with c_deep:
            st.markdown("#### Interactive Deep Dive")
            active_symbols = [p.symbol for p in positions] if positions else []
            dropdown_list = list(set(active_symbols + ['SPY'] + ALL_ASSETS))
            selected_asset = st.selectbox("Select Asset to Analyze:", dropdown_list, index=0, label_visibility="collapsed")
            if selected_asset:
                render_tradingview_widget(selected_asset)

    # --- TAB 4: STRATEGY OVERVIEW ---
    with t4:
        st.markdown("#### Strategy & Architecture Overview")
        st.markdown("""
        **System Core:**
        This autonomous trading system operates a "Global Macro" quantitative strategy. It makes decisions based strictly on mathematical models, eliminating human emotion and bias.
        
        **Three-Pillar Logic:**
        1. **Macro Filter (The Shield):** The algorithm continuously monitors the S&P 500 against its 200-day moving average. If the broader market is collapsing, it liquidates high-risk assets and rotates into safe havens (Gold, US Treasuries) to protect capital.
        2. **Adaptive Volatility:** It measures market nervousness. In calm markets, it plays aggressively. If volatility spikes, it automatically reduces exposure to equities and increases defensive assets.
        3. **Risk-Adjusted Momentum:** When selecting assets, it doesn't just chase what's going up. It looks for "smooth" momentum—assets that rise steadily with low volatility, penalizing erratic price swings.
        
        **Risk Management:**
        - **Zero Leverage:** The system is hard-coded to never borrow money.
        - **Decoupled Risk:** Growth assets are strictly capped (e.g., max 8% per stock, max 25% per sector) to prevent catastrophic losses from a single stock crashing. Defensive assets are uncapped to absorb market shocks.
        """)

    # --- TAB 5: LOGS ---
    with t5:
        c_tape, c_logs = st.columns(2)
        with c_tape:
            st.markdown("#### Execution Tape")
            if api:
                try:
                    activities = api.get_activities(activity_types='FILL')
                    if activities:
                        trades = [{'Time': pd.to_datetime(a.transaction_time).strftime('%Y-%m-%d %H:%M'), 
                                   'Action': 'BUY' if a.side == 'buy' else 'SELL', 
                                   'Asset': a.symbol, 'Notional': f"${float(a.qty) * float(a.price):.2f}"} for a in activities[:50]]
                        st.dataframe(pd.DataFrame(trades), use_container_width=True, hide_index=True, height=400)
                    else: st.info("No recent executions found.")
                except: st.warning("Could not retrieve execution tape.")
            else: st.info("Broker offline.")

        with c_logs:
            st.markdown("#### System Diagnostics")
            log_path = "aegis_production.log"
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    lines = f.readlines()[-30:]
                    st.code("".join(lines), language="log")
            else:
                st.info("System logs will appear here once the background kernel executes its first loop.")

if __name__ == "__main__":
    main()
