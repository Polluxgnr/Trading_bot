
# COMMAND CENTER  (DASHBOARD)

# Monitoring System
# Built with Streamlit & Plotly


import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import alpaca_trade_api as tradeapi
import yfinance as yf
import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

#1. CONFIGURATION & DESIGN
st.set_page_config(
    page_title="AEGIS PRIME | COMMAND CENTER",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Auto-refresh toutes les 60 secondes pour éviter le rate-limit
st_autorefresh(interval=60000, key="aegis_refresh")

# CSS "Hedge Fund" (Dark Theme)
st.markdown("""
<style>
    /* Fond Général */
    .stApp { background-color: #0E1117; }
    
    /* Métriques */
    div[data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.8rem !important;
        font-weight: 700;
    }
    
    /* Tableaux */
    div[data-testid="stDataFrame"] { border: 1px solid #333; }
    
    /* Status Indicators */
    .status-bull { color: #00FFAA; font-weight: 900; font-size: 1.2rem; }
    .status-bear { color: #FF4444; font-weight: 900; font-size: 1.2rem; }
    .status-neutral { color: #AAAAAA; font-weight: 900; font-size: 1.2rem; }
    
    /* Custom Box */
    .css-card {
        background-color: #1E1E1E;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #333;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

#2. CONNECTIVITÉ & DATA
@st.cache_resource
def init_api():
    load_dotenv()
    return tradeapi.REST(
        os.getenv("ALPACA_API_KEY"),
        os.getenv("ALPACA_SECRET_KEY"),
        os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
        "v2"
    )

api = init_api()

UNIVERSE = [
    'NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'QQQ', 'SMH',
    'LLY', 'COPX', 'ITA', 'EEM', 'VEA', 'JEPQ', 'JEPI',
    'IBIT', 'GLD', 'SLV', 'XLE', 'URA', 'TLT', 'AGG', 'SHV', 'SH'
]

SECTOR_MAP = {
    'NVDA': 'Tech', 'MSFT': 'Tech', 'QQQ': 'Tech', 'IBIT': 'Crypto', 
    'GLD': 'Gold', 'TLT': 'Bonds', 'SHV': 'Cash', 'ITA': 'Defense'
}

#3. FONCTIONS UTILITAIRES (ROBUSTES)
def safe_float(val):
    try:
        return float(val)
    except:
        return 0.0

def calculate_metrics(df_history):
    """Calcule Sharpe, Sortino et Max Drawdown sans crasher."""
    if df_history.empty or len(df_history) < 5:
        return 0.0, 0.0, 0.0
    
    # Nettoyage
    df = df_history.copy()
    df['pct_change'] = df['equity'].pct_change().fillna(0)
    
    # Sharpe (Annualisé)
    mean_ret = df['pct_change'].mean()
    std_dev = df['pct_change'].std()
    
    if std_dev < 1e-6: # Eviter division par zéro
        sharpe = 0.0
    else:
        sharpe = (mean_ret / std_dev) * np.sqrt(252)
        
    # Sortino
    neg_ret = df[df['pct_change'] < 0]['pct_change']
    std_neg = neg_ret.std()
    
    if std_neg < 1e-6:
        sortino = 0.0
    else:
        sortino = (mean_ret / std_neg) * np.sqrt(252)
        
    # Max Drawdown
    roll_max = df['equity'].cummax()
    drawdown = (df['equity'] - roll_max) / roll_max
    max_dd = drawdown.min()
    
    return sharpe, sortino, max_dd

#4. SIDEBAR (KPIs)
st.sidebar.title("🛡️ AEGIS V21")
if st.sidebar.button("🔄 FORCE REFRESH DATA"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")

try:
    account = api.get_account()
    equity = safe_float(account.equity)
    last_equity = safe_float(account.last_equity)
    pnl_amt = equity - last_equity
    pnl_pct = (pnl_amt / last_equity) if last_equity > 0 else 0
    
    # Affichage Net Liquidation
    st.sidebar.metric(
        "NET LIQUIDATION", 
        f"${equity:,.2f}", 
        f"{pnl_amt:+.2f} ({pnl_pct:+.2%})",
        delta_color="normal" # Vert/Rouge auto
    )
    
    # Buying Power
    bp = safe_float(account.buying_power)
    st.sidebar.metric("BUYING POWER", f"${bp:,.2f}")
    
    # Récupération Historique (1 Mois / 1H pour finesse)
    history = api.get_portfolio_history(period="1M", timeframe="1H")
    df_hist = pd.DataFrame({
        'timestamp': pd.to_datetime(history.timestamp, unit='s'),
        'equity': history.equity
    }).set_index('timestamp')
    
    # Calcul Métriques
    sharpe, sortino, max_dd = calculate_metrics(df_hist)
    
    st.sidebar.markdown("### 📊 RISK METRICS")
    col_s1, col_s2 = st.sidebar.columns(2)
    col_s1.metric("SHARPE", f"{sharpe:.2f}")
    col_s2.metric("SORTINO", f"{sortino:.2f}")
    st.sidebar.metric("MAX DRAWDOWN", f"{max_dd:.2%}", delta_color="inverse")
    
    # Status
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Status: {'🟢 CONNECTED' if account.status == 'ACTIVE' else '🔴 ERROR'}")
    st.sidebar.caption(f"Mode: {'🧪 PAPER' if 'paper' in str(api._base_url) else '🚀 LIVE'}")

except Exception as e:
    st.sidebar.error(f"API Error: {e}")
    st.stop()

#5. MAIN DASHBOARD

# A. HEADER & RÉGIME
# On utilise SPY via YFinance pour une estimation live du régime
try:
    spy_data = yf.download('SPY', period='1y', progress=False)['Close']
    if not spy_data.empty:
        curr = spy_data.iloc[-1]
        sma = spy_data.rolling(200).mean().iloc[-1]
        regime = "BULL AGGRESSIVE" if curr > sma else "BEAR DEFENSE"
        r_color = "status-bull" if curr > sma else "status-bear"
    else:
        regime = "NEUTRAL (NO DATA)"
        r_color = "status-neutral"
except:
    regime = "OFFLINE"
    r_color = "status-neutral"

c1, c2 = st.columns([3, 1])
with c1:
    st.title("GLOBAL MACRO MONITOR")
with c2:
    st.markdown(f"**MARKET REGIME**")
    st.markdown(f"<span class='{r_color}'>{regime}</span>", unsafe_allow_html=True)

# B. EQUITY CURVE (Interactive)
st.markdown("### 📈 PERFORMANCE")
if not df_hist.empty:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_hist.index, y=df_hist['equity'],
        mode='lines', name='Equity',
        line=dict(color='#00FFAA', width=3),
        fill='tozeroy', fillcolor='rgba(0, 255, 170, 0.1)'
    ))
    fig.update_layout(
        template="plotly_dark",
        height=350,
        margin=dict(l=0, r=0, t=20, b=20),
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor='#333', title="Value ($)")
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Waiting for data history...")

# C. TABS (RADAR / ALLOC / LOGS)
tab1, tab2, tab3 = st.tabs(["📡 TACTICAL RADAR", "🥧 ALLOCATION", "📜 SYSTEM LOGS"])

with tab1:
    st.caption("Live Momentum/Volatility Analysis (V3 Score)")
    # Scan Rapide (Cache 1h pour éviter lenteur)
    @st.cache_data(ttl=3600)
    def get_radar_data():
        scores = []
        try:
            data = yf.download(UNIVERSE, period="6mo", progress=False)['Close']
            for sym in UNIVERSE:
                if sym not in data: continue
                s = data[sym].dropna()
                if len(s) < 60: continue
                
                mom = (s.iloc[-1] / s.iloc[-20]) - 1
                vol = s.pct_change().std() * np.sqrt(252)
                score = (mom / vol * 10) if vol > 0 else 0
                
                scores.append({
                    'Symbol': sym, 
                    'Score': round(score, 2), 
                    'Sector': SECTOR_MAP.get(sym, 'Other')
                })
        except: pass
        return pd.DataFrame(scores).sort_values('Score', ascending=False)

    df_radar = get_radar_data()
    
    if not df_radar.empty:
        # Bar Chart Coloré
        fig_rad = px.bar(
            df_radar.head(10), 
            x='Symbol', y='Score', color='Sector',
            text='Score', title="Top 10 Assets (V3 Score)",
            color_discrete_map={'Tech': '#00FFAA', 'Crypto': '#F7931A', 'Gold': '#FFD700', 'Cash': '#888'}
        )
        fig_rad.update_traces(textposition='outside')
        fig_rad.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_rad, use_container_width=True)
    else:
        st.warning("Radar initializing... (Market Data Fetching)")

with tab2:
    positions = api.list_positions()
    if positions:
        data = []
        for p in positions:
            data.append({'Asset': p.symbol, 'Value': safe_float(p.market_value)})
        
        # Ajout du Cash
        cash = safe_float(account.cash)
        if cash > 10:
            data.append({'Asset': 'CASH', 'Value': cash})
            
        df_pos = pd.DataFrame(data)
        
        c_p1, c_p2 = st.columns([2, 1])
        with c_p1:
            fig_pie = px.pie(
                df_pos, values='Value', names='Asset', hole=0.6,
                color_discrete_sequence=px.colors.sequential.Tealgrn_r
            )
            fig_pie.update_layout(template="plotly_dark", height=350, showlegend=True)
            st.plotly_chart(fig_pie, use_container_width=True)
        with c_p2:
            st.dataframe(df_pos.set_index('Asset'), use_container_width=True)
    else:
        st.info("Portefeuille 100% Cash ou Vide.")

with tab3:
    st.subheader("Live Execution Logs")
    log_file = "logs/aegis_prime.log" # V21 Log File Name
    # Fallback ancien nom au cas où
    if not os.path.exists(log_file): log_file = "logs/aegis.log"
    
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            lines = f.readlines()[-20:] # Dernières 20 lignes
            for line in reversed(lines): # Plus récent en haut
                if "ERROR" in line: st.markdown(f":red[{line.strip()}]")
                elif "WARNING" in line: st.markdown(f":orange[{line.strip()}]")
                elif "BUY" in line or "BULL" in line: st.markdown(f":green[{line.strip()}]")
                elif "SELL" in line or "BEAR" in line: st.markdown(f":red[{line.strip()}]")
                else: st.text(line.strip())
    else:
        st.warning("Log file not found.")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #555;'>"
    "AEGIS PRIME QUANTITATIVE SYSTEMS • PROPRIETARY TRADING ALGORITHM • V21"
    "</div>", 
    unsafe_allow_html=True
)