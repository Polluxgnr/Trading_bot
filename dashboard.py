import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import alpaca_trade_api as tradeapi
import yfinance as yf
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# 1 PAGE CONFIGURATION
st.set_page_config(page_title="Pollux's bot | Command Center", layout="wide", page_icon="🛡️")

# 2 CUSTOM STYLING & DESIGN
st.markdown("""
<style>
    .metric-box { background-color: #151A22; padding: 20px; border-radius: 10px; border-left: 5px solid #00E676; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); }
    .metric-title { color: #8B949E; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;}
    .metric-value { color: #FFFFFF; font-size: 28px; font-weight: bold; margin-top: 5px; }
    .metric-sub { color: #00E676; font-size: 13px; margin-top: 5px; font-weight: 500;}
    .header-links a { color: #00E676; text-decoration: none; margin-right: 15px; font-weight: bold; }
    .header-links a:hover { text-decoration: underline; }
    .mistral-box { background-color: #0E1117; border: 1px solid #30363D; border-radius: 8px; padding: 15px; margin-bottom: 20px; border-left: 3px solid #AF52DE;}
</style>
""", unsafe_allow_html=True)

# 3 SECTOR MAPPING
SECTOR_MAP = {
    'NVDA': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology', 'AMZN': 'Technology', 
    'META': 'Technology', 'AAPL': 'Technology', 'TSLA': 'Technology', 'SMH': 'Technology', 'QQQ': 'Technology',
    'LLY': 'Healthcare', 'UNH': 'Healthcare', 
    'ITA': 'Industrials', 'XLI': 'Industrials', 'RTX': 'Industrials', 
    'XLE': 'Commodities', 'COPX': 'Commodities', 'URA': 'Commodities', 
    'IBIT': 'Alpha (Crypto)', 'BTC-USD': 'Alpha (Crypto)',
    'GLD': 'Defense (Gold)', 'TLT': 'Defense (Bonds)', 'SHV': 'Defense (Cash)', 'SPY': 'Broad Market',
    'CASH (Reserve)': 'Cash Reserve'
}

# 4 HEADER & LINKS
st.markdown("<h1>🛡️ Pollux's trading bot</h1>", unsafe_allow_html=True)
st.markdown("""
<div class="header-links">
    <a href="https://github.com/Polluxgnr/Trading_bot" target="_blank">🔗 GitHub Repository</a> | 
    <a href="https://polluxgronier.me" target="_blank">💼 Portfolio</a>
</div><br>
""", unsafe_allow_html=True)

# 5 API INITIALIZATION
load_dotenv()
try:
    api = tradeapi.REST(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), os.getenv("ALPACA_BASE_URL"), 'v2')
    account = api.get_account()
except Exception as e:
    st.error(f"API Connection Failed: {e}. Check your .env credentials.")
    st.stop()

# LANGUAGE TOGGLE
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/000000/shield.png", width=50)
    lang = st.radio("🌐 Interface Language", ['🇬🇧 English', '🇫🇷 Français'])
    is_fr = lang == '🇫🇷 Français'
    st.write("---")

# 6 ROBUST CACHING FUNCTIONS
@st.cache_data(ttl=300) 
def fetch_portfolio_history(period="1M"):
    try:
        hist = api.get_portfolio_history(period=period, timeframe="1D")
        df = pd.DataFrame({'equity': hist.equity}, index=pd.to_datetime(hist.timestamp, unit='s', utc=True))
        df.index = df.index.tz_convert('US/Eastern')
        # Filter out $0 starting points from unfunded Alpaca accounts
        return df[df['equity'] > 0].dropna()
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_radar_data(universe, start_d):
    try:
        df = yf.download(universe, start=start_d, progress=False)['Close']
        return df.ffill().dropna(thresh=10)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_trade_activities():
    try:
        acts = api.get_activities(activity_types='FILL')
        return [{"symbol": a.symbol, "side": a.side, "qty": float(a.qty), "price": float(a.price), "date": str(a.transaction_time)} for a in acts]
    except Exception:
        return []

@st.cache_data(ttl=3600)
def generate_mistral_insight(top_holdings_str):
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key: return "Mistral API Key missing. Analysis disabled."
    try:
        from mistralai import Mistral
        client = Mistral(api_key=api_key)
        prompt = f"Act as a quantitative hedge fund manager. My current top holdings are: {top_holdings_str}. Write exactly 2 concise sentences explaining this specific allocation and market stance. Professional and institutional tone only."
        response = client.chat.complete(model="mistral-tiny", messages=[{"role":"user","content":prompt}])
        return response.choices[0].message.content
    except Exception:
        return f"Mistral Analysis unavailable at this time."
    
@st.cache_data(ttl=3600)
def get_recent_news(symbol):
    try:
        return yf.Ticker(symbol).news[:3]
    except:
        return []

def get_system_logs(lines=15):
    try:
        with open("aegis_production.log", "r") as f:
            return "".join(f.readlines()[-lines:])
    except FileNotFoundError:
        return "Log file not found." if not is_fr else "Fichier journal introuvable."

# 7 TOP METRICS & MISTRAL AI
equity = float(account.equity)
cash = float(account.cash)

# Calculate All-Time Net Profit securely
df_all = fetch_portfolio_history(period="all")
if not df_all.empty and len(df_all) > 0:
    base_equity = df_all['equity'].iloc[0]
    net_profit_dol = equity - base_equity
    net_profit_pct = (net_profit_dol / base_equity) * 100
else:
    net_profit_dol, net_profit_pct = 0.0, 0.0

c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(f'<div class="metric-box"><div class="metric-title">Net Liquidity</div><div class="metric-value">${equity:,.2f}</div></div>', unsafe_allow_html=True)
with c2: st.markdown(f'<div class="metric-box"><div class="metric-title">Cash Reserve</div><div class="metric-value">${cash:,.2f}</div></div>', unsafe_allow_html=True)
with c3: st.markdown(f'<div class="metric-box"><div class="metric-title">All-Time Net Profit</div><div class="metric-value">${net_profit_dol:,.2f}</div><div class="metric-sub" style="color:{"#00E676" if net_profit_pct>=0 else "#FF3B30"}">{net_profit_pct:+.2f}%</div></div>', unsafe_allow_html=True)
with c4:
    mode = "🔴 LIVE" if "paper" not in os.getenv("ALPACA_BASE_URL", "paper") else "🧪 PAPER"
    st.markdown(f'<div class="metric-box" style="border-left-color: #007AFF;"><div class="metric-title">System Status</div><div class="metric-value">{mode}</div><div class="metric-sub">Zero Leverage Enforced</div></div>', unsafe_allow_html=True)

st.write("")

# Mistral AI Block
positions = api.list_positions()
top_symbols = ", ".join([p.symbol for p in sorted(positions, key=lambda x: float(x.market_value), reverse=True)[:5]]) if positions else "100% Cash"
mistral_text = generate_mistral_insight(top_symbols)

st.markdown(f"""
<div class="mistral-box">
    <div style="color: #AF52DE; font-weight: bold; font-size: 14px; margin-bottom: 5px;">🤖 MISTRAL AI • LIVE PORTFOLIO INSIGHT</div>
    <div style="color: #C9D1D9; font-size: 15px; font-style: italic;">"{mistral_text}"</div>
</div>
""", unsafe_allow_html=True)

# 8 NAVIGATION TABS
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📈 Live Performance" if not is_fr else "📈 Performance en Direct", 
    "🎯 Portfolio & Allocation" if not is_fr else "🎯 Portefeuille & Allocation", 
    "🏆 Extremes & Alpha",
    "🧾 Execution & News" if not is_fr else "🧾 Exécution & Actualités",
    "🔮 Monte Carlo", 
    "📡 Global Radar" if not is_fr else "📡 Radar Global",
    "🧠 Strategy Deep Dive" if not is_fr else "🧠 Stratégie Détaillée"
])


# TAB 1: LIVE PERFORMANCE & DRAWDOWN

with tab1:
    st.subheader("Account Evolution Tracker (Percentage Growth)" if not is_fr else "Évolution du Compte (Croissance en %)")
    timeframes = {"1 Week": "1W", "1 Month": "1M", "3 Months": "3M", "1 Year": "1A", "All Time": "all"} if not is_fr else {"1 Semaine": "1W", "1 Mois": "1M", "3 Mois": "3M", "1 An": "1A", "Tout l'historique": "all"}
    tf_sel = st.radio("Select Period:" if not is_fr else "Sélectionner la Période :", list(timeframes.keys()), horizontal=True, index=4)
    
    df_hist = fetch_portfolio_history(period=timeframes[tf_sel])
    if not df_hist.empty and len(df_hist) > 1:
        # Calculate percentage change from the first valid data point
        df_hist['pct_growth'] = (df_hist['equity'] / df_hist['equity'].iloc[0] - 1) * 100
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_hist.index, y=df_hist['pct_growth'], mode='lines', line=dict(color='#00E676', width=3), fill='tozeroy', fillcolor='rgba(0, 230, 118, 0.1)'))
        fig.update_layout(template='plotly_dark', plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title="", yaxis_title="Growth (%)" if not is_fr else "Croissance (%)", height=450, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
        
        c1, c2, c3 = st.columns(3)
        start_eq = df_hist['equity'].iloc[0]
        pl_dol = df_hist['equity'].iloc[-1] - start_eq
        c1.metric(f"Period P&L" if not is_fr else "P&L de la Période", f"${pl_dol:,.2f}", f"{(pl_dol / start_eq) * 100:.2f}%")
        
        daily_rets = df_hist['equity'].pct_change().dropna()
        if len(daily_rets) > 1 and daily_rets.std() > 0:
            c2.metric("Realized Volatility (Ann.)" if not is_fr else "Volatilité Réalisée (Ann.)", f"{daily_rets.std() * np.sqrt(252) * 100:.2f}%")
            c3.metric("Live Sharpe Ratio" if not is_fr else "Ratio de Sharpe Actuel", f"{(daily_rets.mean() / daily_rets.std()) * np.sqrt(252):.2f}")
        else:
            c2.metric("Realized Volatility (Ann.)" if not is_fr else "Volatilité Réalisée (Ann.)", "Calibrating..." if not is_fr else "Calibration...")
            c3.metric("Live Sharpe Ratio" if not is_fr else "Ratio de Sharpe Actuel", "Calibrating..." if not is_fr else "Calibration...")
        
    else:
        st.info("Awaiting sufficient trading data to map the equity curve. If you just funded the account, the chart will appear tomorrow." if not is_fr else "En attente de données suffisantes pour tracer la courbe. Si le compte vient d'être financé, le graphique apparaîtra demain.")


# TAB 2: PORTFOLIO MAP & ALLOCATION

with tab2:
    st.subheader("Interactive Allocation Map (Including Cash & Sectors)" if not is_fr else "Carte d'Allocation Interactive (Incluant Cash & Secteurs)")
    pos_data = [{"Symbol": "CASH (Reserve)", "Market Value ($)": cash, "Weight (%)": (cash/equity)*100, "Unrealized P&L ($)": 0.0, "Unrealized P&L (%)": 0.0, "Current Price": 1.0, "Avg Entry": 1.0, "Sector": "Cash Reserve"}]
    
    if positions:
        pos_data += [{"Symbol": p.symbol, "Market Value ($)": float(p.market_value), "Weight (%)": (float(p.market_value) / equity) * 100, "Unrealized P&L ($)": float(p.unrealized_pl), "Unrealized P&L (%)": float(p.unrealized_plpc) * 100, "Current Price": float(p.current_price), "Avg Entry": float(p.avg_entry_price), "Sector": SECTOR_MAP.get(p.symbol, 'Other')} for p in positions]
    
    df_pos = pd.DataFrame(pos_data)
    # Sort by Market Value descending for a professional look
    df_pos = df_pos.sort_values(by="Market Value ($)", ascending=False).reset_index(drop=True)
    
    view_type = st.radio("Visualization Mode:" if not is_fr else "Mode de Visualisation :", ["Nested Treemap (Sector > Asset)", "Donut Chart (Weight Distribution)"], horizontal=True)
    
    if view_type == "Nested Treemap (Sector > Asset)":
        fig_map = px.treemap(df_pos, path=['Sector', 'Symbol'], values='Market Value ($)', color='Unrealized P&L (%)', color_continuous_scale='RdYlGn', color_continuous_midpoint=0, hover_data=['Weight (%)'])
    else:
        fig_map = px.pie(df_pos, values='Market Value ($)', names='Sector', hole=0.4, hover_data=['Symbol', 'Unrealized P&L (%)'])
        fig_map.update_traces(textposition='inside', textinfo='percent+label')
        
    fig_map.update_layout(template='plotly_dark', margin=dict(t=10, l=0, r=0, b=0), height=450)
    st.plotly_chart(fig_map, use_container_width=True)
    
    st.markdown("### Full Holdings Ledger (Ranked by Importance)" if not is_fr else "### Grand Livre des Positions (Trié par Importance)")
    st.dataframe(df_pos.style.format({"Market Value ($)": "${:,.2f}", "Weight (%)": "{:.2f}%", "Unrealized P&L ($)": "${:,.2f}", "Unrealized P&L (%)": "{:.2f}%", "Current Price": "${:,.2f}", "Avg Entry": "${:,.2f}"}).background_gradient(subset=['Unrealized P&L (%)'], cmap='RdYlGn'), use_container_width=True)


# TAB 3: EXTREMES & ALPHA ATTRIBUTION

with tab3:
    st.subheader("Performance Extremes & True Edge Discovery" if not is_fr else "Extrêmes de Performance & Découverte de l'Alpha")
    
    if positions:
        df_real = df_pos[df_pos['Symbol'] != "CASH (Reserve)"].sort_values(by="Unrealized P&L (%)", ascending=False)
        top_perf, worst_perf = df_real.iloc[0], df_real.iloc[-1]
        
        col_w, col_l = st.columns(2)
        with col_w:
            st.success("🟢 **BEST ACTIVE POSITION**" if not is_fr else "🟢 **MEILLEURE POSITION ACTIVE**")
            st.metric(label=top_perf['Symbol'], value=f"${top_perf['Market Value ($)']:,.2f}", delta=f"{top_perf['Unrealized P&L (%)']:.2f}% (${top_perf['Unrealized P&L ($)']:,.2f})")
            st.markdown(f"- **Sector:** {top_perf['Sector']} | **Weight:** {top_perf['Weight (%)']:.1f}%" if not is_fr else f"- **Secteur:** {top_perf['Sector']} | **Poids:** {top_perf['Weight (%)']:.1f}%")
        with col_l:
            st.error("🔴 **WORST ACTIVE POSITION**" if not is_fr else "🔴 **PIRE POSITION ACTIVE**")
            st.metric(label=worst_perf['Symbol'], value=f"${worst_perf['Market Value ($)']:,.2f}", delta=f"{worst_perf['Unrealized P&L (%)']:.2f}% (${worst_perf['Unrealized P&L ($)']:,.2f})")
            st.markdown(f"- **Sector:** {worst_perf['Sector']} | **Weight:** {worst_perf['Weight (%)']:.1f}%" if not is_fr else f"- **Secteur:** {worst_perf['Sector']} | **Poids:** {worst_perf['Weight (%)']:.1f}%")
            
    st.write("---")
    st.markdown("#### All-Time Profit by Asset" if not is_fr else "#### Profit Total par Actif")
    st.caption("Identifies the real drivers of your edge. Assets consistently losing money over time should be considered for exclusion from the universe." if not is_fr else "Identifie les vrais moteurs de performance. Les actifs perdant systématiquement de l'argent devraient être exclus de l'univers.")
    activities = fetch_trade_activities()
    if activities:
        df_act = pd.DataFrame(activities)
        df_act['cash_flow'] = df_act.apply(lambda x: x['qty'] * x['price'] * (-1 if x['side'] == 'buy' else 1), axis=1)
        pnl_tracker = df_act.groupby('symbol')['cash_flow'].sum()
        
        for p in positions:
            pnl_tracker[p.symbol] = pnl_tracker.get(p.symbol, 0) + float(p.market_value)
            
        pnl_tracker = pnl_tracker.sort_values(ascending=True)
        fig_attr = px.bar(pnl_tracker, x=pnl_tracker.values, y=pnl_tracker.index, orientation='h', color=pnl_tracker.values, color_continuous_scale='RdYlGn')
        fig_attr.update_layout(template='plotly_dark', height=400, xaxis_title="Net Profit/Loss ($)" if not is_fr else "Profit/Perte Net ($)", yaxis_title="", margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_attr, use_container_width=True)
    else:
        st.info("Not enough history to compute alpha attribution." if not is_fr else "Pas assez d'historique pour calculer l'attribution d'alpha.")


# TAB 4: EXECUTION TAPE & NEWS

with tab4:
    st.subheader("🧾 " + ("Journal d'Exécution, Logs & Actualités" if is_fr else "Execution Ledger, Logs & News"))
    
    col_tape, col_news = st.columns([1.2, 1])
    
    with col_tape:
        # EXECUTION LEDGER
        st.markdown("### 📝 " + ("Dernières Transactions" if is_fr else "Recent Market Orders"))
        activities = fetch_trade_activities()
        if activities:
            logs = [{"Date": pd.to_datetime(a['date']).strftime('%Y-%m-%d %H:%M'), 
                     "Action": "🟢 ACHAT" if a['side'] == 'buy' and is_fr else "🟢 BUY" if a['side'] == 'buy' else ("🔴 VENTE" if is_fr else "🔴 SELL"), 
                     "Ticker": a['symbol'], 
                     "Price": f"${a['price']:.2f}", 
                     "Qty": a['qty']} for a in activities[:15]]
            st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
        else:
            st.write("Aucune transaction exécutée." if is_fr else "No executed trades yet.")
            
        st.write("---")
        
        # SYSTEM LOGS
        st.markdown("### ⚙️ " + ("Logs du Serveur en Direct" if is_fr else "Live System Logs"))
        st.caption("aegis_production.log")
        sys_logs = get_system_logs(15)
        st.code(sys_logs, language="bash")

    with col_news:
        # NEWS FEED
        st.markdown("### 📡 " + ("Contexte Macro (Top 3 Actifs)" if is_fr else "Market Context (Top 3 Holdings)"))
        if positions:
            # On prend les 3 plus grosses positions pour chercher les news
            top_3 = sorted(positions, key=lambda x: float(x.market_value), reverse=True)[:3]
            for p in top_3:
                st.markdown(f"**{'Actualités pour' if is_fr else 'News for'} {p.symbol}**")
                news_items = get_recent_news(p.symbol)
                if news_items:
                    for n in news_items:
                        # Safe extraction of publish time
                        pub_time_raw = n.get('providerPublishTime')
                        pub_time = datetime.fromtimestamp(pub_time_raw).strftime('%Y-%m-%d') if pub_time_raw else "Recent"
                        st.markdown(f"- [{n.get('title', 'No Title')}]({n.get('link', '#')}) *(Yahoo Finance, {pub_time})*")
                else:
                    st.caption("Aucune actualité récente." if is_fr else "No recent news found.")
                st.write("---")
        else:
            st.info("Portefeuille en Cash. Aucune actualité spécifique." if is_fr else "Portfolio in Cash. No specific news.")

# TAB 5: MONTE CARLO FORECAST

with tab5:
    st.subheader("Stochastic Portfolio Projection (1 Year)" if not is_fr else "Projection Stochastique du Portefeuille (1 An)")
    st.write("Simulating 100 future paths based on audited institutional metrics: **25.03% CAGR** and **16.29% Volatility**." if not is_fr else "Simulation de 100 trajectoires futures basées sur les métriques institutionnelles auditées : **CAGR 25.03%** et **Volatilité 16.29%**.")
    
    cagr_exact, vol_exact, days, simulations = 0.2503, 0.1629, 252, 100
    daily_drift = (cagr_exact - 0.5 * vol_exact**2) / days
    daily_vol = vol_exact / np.sqrt(days)
    
    paths = np.zeros((days, simulations))
    paths[0] = equity
    for t in range(1, days):
        shock = np.random.normal(0, 1, simulations)
        paths[t] = paths[t-1] * np.exp(daily_drift + daily_vol * shock)
        
    df_mc = pd.DataFrame(paths)
    fig_mc = go.Figure()
    for col in df_mc.columns:
        fig_mc.add_trace(go.Scatter(x=df_mc.index, y=df_mc[col], mode='lines', line=dict(width=1, color='rgba(0, 230, 118, 0.05)'), showlegend=False))
        
    mean_path = df_mc.mean(axis=1)
    top_path = df_mc.quantile(0.95, axis=1)
    bot_path = df_mc.quantile(0.05, axis=1)
    
    fig_mc.add_trace(go.Scatter(x=df_mc.index, y=mean_path, mode='lines', line=dict(width=3, color='white'), name='Median Expected' if not is_fr else 'Médiane Attendue'))
    fig_mc.add_trace(go.Scatter(x=df_mc.index, y=top_path, mode='lines', line=dict(width=2, color='#00E676', dash='dash'), name='Optimistic (Top 5%)' if not is_fr else 'Optimiste (Top 5%)'))
    fig_mc.add_trace(go.Scatter(x=df_mc.index, y=bot_path, mode='lines', line=dict(width=2, color='#FF3B30', dash='dash'), name='Pessimistic (Bottom 5%)' if not is_fr else 'Pessimiste (Derniers 5%)'))
    
    fig_mc.update_layout(template='plotly_dark', xaxis_title="Trading Days (1 Year)" if not is_fr else "Jours de Bourse (1 An)", yaxis_title="Projected Equity ($)" if not is_fr else "Capital Projeté ($)", height=500)
    st.plotly_chart(fig_mc, use_container_width=True)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Optimistic Target (+1yr)" if not is_fr else "Cible Optimiste (+1an)", f"${top_path.iloc[-1]:,.0f}")
    c2.metric("Median Target (+1yr)" if not is_fr else "Cible Médiane (+1an)", f"${mean_path.iloc[-1]:,.0f}")
    c3.metric("Pessimistic Target (+1yr)" if not is_fr else "Cible Pessimiste (+1an)", f"${bot_path.iloc[-1]:,.0f}")


# TAB 6: GLOBAL RADAR

with tab6:
    st.subheader("Live Score Radar (Momentum / Volatility)" if not is_fr else "Radar de Scores en Direct (Momentum / Volatilité)")
    st.write("Scanning the universe for the most stable uptrends." if not is_fr else "Analyse de l'univers à la recherche des tendances les plus stables.")
    universe = ['NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'AAPL', 'TSLA', 'SMH', 'LLY', 'UNH', 'XLE', 'COPX', 'URA', 'ITA', 'XLI', 'RTX', 'BTC-USD', 'SPY']
    
    with st.spinner("Analyzing market matrix..." if not is_fr else "Analyse de la matrice du marché..."):
        start_d = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')
        df_mkt = fetch_radar_data(universe, start_d)
        if not df_mkt.empty:
            scores = []
            for t in universe:
                if t in df_mkt.columns:
                    p = df_mkt[t]
                    if len(p) > 60:
                        mom = (p.iloc[-1] / p.iloc[-60]) - 1
                        vol = p.pct_change().std() * np.sqrt(252)
                        scores.append({"Asset": t, "Sector": SECTOR_MAP.get(t, 'Other'), "Momentum (3M)": mom, "Volatility": vol, "Score": mom / vol if vol > 0 else 0})
                        
            df_scores = pd.DataFrame(scores).sort_values("Score", ascending=False).reset_index(drop=True)
            df_scores.index += 1
            st.dataframe(df_scores.style.format({"Momentum (3M)": "{:.2%}", "Volatility": "{:.2%}", "Score": "{:.2f}"}).background_gradient(subset=['Score'], cmap='RdYlGn'), use_container_width=True)
        else:
            st.error("Could not load radar data. YFinance API might be rate-limited." if not is_fr else "Impossible de charger les données du radar. L'API YFinance a peut-être atteint sa limite de requêtes.")


# TAB 7: STRATEGY DEEP DIVE (THEORY & LOGIC)

with tab7:
    if not is_fr:
        st.markdown("""
        ## 🧠 Aegis Prime: Institutional Architecture & Theory
        
        This system is a deterministic, emotionless **Global Macro quantitative engine**. It does not predict the future; it adapts mathematically to the present. The architecture is heavily inspired by Ray Dalio's *All-Weather Portfolio* and Harry Browne's *Permanent Portfolio*, enhanced with an active momentum overlay.
        
        ### 🌍 The Macroeconomic "Four Quadrants" Theory
        The foundation of Aegis Prime acknowledges that financial markets are driven by shifts in expectations regarding two fundamental forces: **Economic Growth** and **Inflation**. This creates four distinct environments:
        1. **Rising Growth:** Favorable for Equities (Tech, Industrials).
        2. **Falling Growth (Deflation):** Favorable for Long-Term Treasury Bonds (TLT).
        3. **Rising Inflation:** Favorable for Gold (GLD) and Commodities.
        4. **Falling Inflation:** Favorable for Equities and Bonds.
        
        By dynamically mixing assets that thrive in these specific quadrants, the portfolio achieves "true diversification" based on economic causality, rather than historical correlation.
        
        ### 🛡️ Phase 1: The Macro Filter ("Bunker Mode")
        Capital preservation is the absolute priority. Before seeking yield, the algorithm asks: *Is the structural integrity of the broader market compromised?*
        - **Indicator:** S&P 500 (SPY) vs its 200-day Simple Moving Average (SMA 200).
        - **Action:** If the SPY closes below the SMA 200, the system initiates **Bunker Mode**. All equity/risk-on exposure is instantly liquidated. 
        - **The Bunker Allocation (40% GLD / 40% TLT / 20% Cash):** - If the crash is caused by a deflationary recession (e.g., 2008, 2020), central banks cut rates, causing **TLT (Bonds)** to skyrocket.
            - If the crash is caused by an inflationary shock or systemic crisis (e.g., 2022, geopolitical wars), **GLD (Gold)** acts as the ultimate safe haven.
            - **Cash (20%)** acts as dry powder to buy back into the market at a discount when the storm passes.
        
        ### 🌡️ Phase 2: The Adaptive Volatility Thermometer
        When the market is in a confirmed uptrend (SPY > SMA 200), the system assesses *how nervous* the market is to dictate the balance between Offense and Defense.
        - **Indicator:** 21-day annualized volatility of the S&P 500.
        - **Low Volatility (< 15%):** Calm waters. Maximum attack. **90% Growth / 10% Defense**.
        - **Normal Volatility (15% - 25%):** Standard fluctuations. Balanced stance. **50% Growth / 50% Defense**.
        - **High Volatility (> 25%):** Erratic, potentially topping market. Defensive stance. **20% Growth / 80% Defense**.
        
        ### 🎯 Phase 3: Asset Selection (The Dual Engine)
        - **The Growth Engine:** Scans the offensive universe (Tech, Healthcare, Alpha proxies). Instead of picking the assets that surged the most, it targets the highest **Risk-Adjusted Momentum**. The formula divides 6-month Momentum by 3-month Volatility. Assets that rise steadily in a straight line score highest. Capital is distributed using *Inverse Volatility Risk Parity* (less volatile assets receive higher capital weights).
        - **The Shield Engine:** A permanent defensive anchor split 50/50 between Gold (GLD) and Treasuries (TLT), acting as a counterweight to the Growth engine.
        
        ### ✂️ Phase 4: Decoupled Risk Management
        This is the core innovation of the architecture. The system applies asymmetrical constraints to mathematically prevent catastrophic drawdowns:
        - **Strict Offense Caps:** No single offensive asset can exceed **8%** of the portfolio. No single sector can exceed **25%**. This prevents overexposure to isolated bubbles (e.g., a Tech dot-com crash).
        - **Uncapped Defense:** Defensive assets have no upper limits, allowing them to absorb massive capital flows during panics without constraint.
        - **Zero Leverage Protocol:** The gross exposure is mathematically hard-capped at **98%**, maintaining a permanent 2% cash buffer. The system is physically incapable of borrowing money, completely eliminating the risk of a margin call.
        """)
    else:
        st.markdown("""
        ## 🧠 Aegis Prime : Architecture Institutionnelle & Théorie
        
        Ce système est un **moteur quantitatif Global Macro** déterministe et sans émotion. Il ne prédit pas l'avenir ; il s'adapte mathématiquement au présent. L'architecture est fortement inspirée du *All-Weather Portfolio* de Ray Dalio et du *Permanent Portfolio* de Harry Browne, enrichie d'une surcouche de momentum actif.
        
        ### 🌍 La Théorie Macroéconomique des "Quatre Quadrants"
        La fondation d'Aegis Prime reconnaît que les marchés financiers sont dictés par l'évolution des attentes concernant deux forces fondamentales : **La Croissance Économique** et **L'Inflation**. Cela crée quatre environnements distincts :
        1. **Croissance en hausse :** Favorable aux Actions (Tech, Industrie).
        2. **Croissance en baisse (Déflation) :** Favorable aux Obligations d'État à Long Terme (TLT).
        3. **Inflation en hausse :** Favorable à l'Or (GLD) et aux Matières Premières.
        4. **Inflation en baisse :** Favorable aux Actions et Obligations.
        
        En mélangeant dynamiquement les actifs qui prospèrent dans ces quadrants spécifiques, le portefeuille atteint une "véritable diversification" basée sur la causalité économique, plutôt que sur la corrélation historique.
        
        ### 🛡️ Phase 1 : Le Filtre Macro ("Bunker Mode")
        La préservation du capital est la priorité absolue. Avant de chercher du rendement, l'algorithme se demande : *L'intégrité structurelle du marché global est-elle compromise ?*
        - **Indicateur :** Le S&P 500 (SPY) par rapport à sa Moyenne Mobile à 200 jours (SMA 200).
        - **Action :** Si le SPY clôture sous la SMA 200, le système déclenche le **Bunker Mode**. Toute l'exposition aux actifs risqués est instantanément liquidée.
        - **L'Allocation Bunker (40% GLD / 40% TLT / 20% Cash) :** - Si le krach est causé par une récession déflationniste (ex: 2008, 2020), les banques centrales baissent les taux, faisant exploser **TLT (Obligations)** à la hausse.
            - Si le krach est causé par un choc inflationniste ou une crise systémique (ex: 2022, guerres), **GLD (Or)** agit comme l'ultime valeur refuge.
            - **Le Cash (20%)** sert de réserve ("dry powder") pour racheter le marché à prix cassé lorsque la tempête est passée.
        
        ### 🌡️ Phase 2 : Le Thermomètre de Volatilité Adaptatif
        Quand le marché est dans une tendance haussière confirmée (SPY > SMA 200), le système évalue *le niveau de nervosité* du marché pour dicter l'équilibre entre Attaque et Défense.
        - **Volatilité Basse (< 15%) :** Eaux calmes. Attaque maximale. **90% Croissance / 10% Défense**.
        - **Volatilité Normale (15% - 25%) :** Fluctuations standards. Position équilibrée. **50% Croissance / 50% Défense**.
        - **Volatilité Haute (> 25%) :** Marché erratique, possible sommet. Position défensive. **20% Croissance / 80% Défense**.
        
        ### 🎯 Phase 3 : Sélection des Actifs (Le Moteur Double)
        - **Le Moteur de Croissance :** Scanne l'univers offensif (Tech, Santé, Proxys Alpha). Au lieu de choisir les actifs qui ont le plus monté, il cible le plus haut **Momentum Ajusté au Risque**. La formule divise le Momentum sur 6 mois par la Volatilité sur 3 mois. Les actifs montant régulièrement en ligne droite obtiennent le meilleur score. Le capital est distribué en utilisant la *Parité des Risques par Volatilité Inverse* (les actifs moins volatils reçoivent un poids plus important).
        - **Le Moteur Bouclier :** Une ancre défensive permanente répartie 50/50 entre l'Or (GLD) et les Obligations (TLT), agissant comme contrepoids au moteur de Croissance.
        
        ### ✂️ Phase 4 : Gestion des Risques Découplée
        C'est l'innovation centrale de l'architecture. Le système applique des contraintes asymétriques pour prévenir mathématiquement les baisses catastrophiques :
        - **Plafonds stricts sur l'Offensive :** Aucun actif offensif ne peut dépasser **8%** du portefeuille. Aucun secteur ne peut dépasser **25%**. Cela empêche la surexposition à des bulles isolées (ex: le krach des dot-coms).
        - **Défense Sans Plafond :** Les actifs défensifs n'ont pas de limite supérieure, leur permettant d'absorber des flux massifs de capitaux pendant les paniques sans contrainte.
        - **Protocole Zéro Levier :** L'exposition brute est mathématiquement plafonnée à **98%**, maintenant une réserve permanente de 2% en cash. Le système est physiquement incapable d'emprunter de l'argent, éliminant complètement le risque d'appel de marge.
        """)
