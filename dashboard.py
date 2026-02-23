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
    .info-text { color: #A3B3BC; font-size: 14px; font-style: italic; margin-bottom: 15px; }
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
        news_data = yf.Ticker(symbol).news[:3]
        parsed_news = []
        for n in news_data:
            # Nouvelle structure Yahoo Finance (imbriquée dans 'content')
            if 'content' in n:
                content = n['content']
                title = content.get('title', 'No Title')
                link = content.get('clickThroughUrl', {}).get('url', '#')
                date_str = content.get('pubDate', '')
                pub_time = date_str[:10] if date_str else "Recent"
            # Ancienne structure Yahoo Finance (plate)
            else:
                title = n.get('title', 'No Title')
                link = n.get('link', '#')
                pub_time_raw = n.get('providerPublishTime')
                try:
                    pub_time = datetime.fromtimestamp(pub_time_raw).strftime('%Y-%m-%d') if pub_time_raw else "Recent"
                except:
                    pub_time = "Recent"
            
            # On ne garde que les articles valides
            if title != 'No Title':
                parsed_news.append({'title': title, 'link': link, 'date': pub_time})
        return parsed_news
    except Exception:
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

# ==========================================
# TAB 1: LIVE PERFORMANCE & DRAWDOWN
# ==========================================
with tab1:
    st.subheader("Account Evolution Tracker (Percentage Growth)" if not is_fr else "Évolution du Compte (Croissance en %)")
    
    desc_tab1 = "Track the live equity curve and risk metrics of your portfolio. The Drawdown chart below highlights the distance from the all-time high, allowing you to monitor the algorithm's resilience during market corrections." if not is_fr else "Suivez la courbe de performance et les métriques de risque de votre portefeuille. Le graphique de Drawdown ci-dessous met en évidence la chute depuis le dernier sommet historique, permettant d'évaluer la résilience de l'algorithme."
    st.markdown(f"<div class='info-text'>{desc_tab1}</div>", unsafe_allow_html=True)

    timeframes = {"1 Week": "1W", "1 Month": "1M", "3 Months": "3M", "1 Year": "1A", "All Time": "all"} if not is_fr else {"1 Semaine": "1W", "1 Mois": "1M", "3 Mois": "3M", "1 An": "1A", "Tout l'historique": "all"}
    tf_sel = st.radio("Select Period:" if not is_fr else "Sélectionner la Période :", list(timeframes.keys()), horizontal=True, index=4)
    
    df_hist = fetch_portfolio_history(period=timeframes[tf_sel])
    if not df_hist.empty and len(df_hist) > 1:
        df_hist['pct_growth'] = (df_hist['equity'] / df_hist['equity'].iloc[0] - 1) * 100
        
        peak = df_hist['equity'].cummax()
        drawdown = (df_hist['equity'] / peak - 1) * 100
        max_dd = drawdown.min()
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_hist.index, y=df_hist['pct_growth'], 
            mode='lines', line=dict(color='#00E676', width=3), 
            fill='tozeroy', fillcolor='rgba(0, 230, 118, 0.1)',
            hovertemplate='%{x|%Y-%m-%d %H:%M}<br>Growth: %{y:.2f}%<extra></extra>' if not is_fr else '%{x|%d/%m/%Y %H:%M}<br>Croissance: %{y:.2f}%<extra></extra>'
        ))
        fig.update_layout(template='plotly_dark', plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis_title="", yaxis_title="Growth (%)" if not is_fr else "Croissance (%)", height=400, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)
        
        c1, c2, c3, c4 = st.columns(4)
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
        
        c4.metric("Max Drawdown", f"{max_dd:.2f}%")

        st.markdown("#### Stress Test: Historical Drawdown" if not is_fr else "#### Test de Résistance : Drawdown Historique")
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=drawdown.index, y=drawdown, 
            mode='lines', fill='tozeroy', 
            line=dict(color='#FF3B30', width=2), fillcolor='rgba(255, 59, 48, 0.2)',
            hovertemplate='DD: %{y:.2f}%<extra></extra>'
        ))
        fig_dd.update_layout(template='plotly_dark', height=200, margin=dict(t=10, b=10, l=0, r=0), yaxis=dict(title="Drawdown (%)", range=[min(-5.0, max_dd * 1.2), 0]))
        st.plotly_chart(fig_dd, use_container_width=True)
        
    else:
        st.info("Awaiting sufficient trading data to map the equity curve. If you just funded the account, the chart will appear tomorrow." if not is_fr else "En attente de données suffisantes pour tracer la courbe. Si le compte vient d'être financé, le graphique apparaîtra demain.")


# ==========================================
# TAB 2: PORTFOLIO MAP & ALLOCATION
# ==========================================
with tab2:
    st.subheader("Interactive Allocation Map" if not is_fr else "Carte d'Allocation Interactive")
    
    desc_tab2 = "Explore your portfolio's structure. The Sunburst and Treemap charts provide a multi-layered view, breaking down your exposure from Sector level down to specific Assets." if not is_fr else "Explorez la structure de votre portefeuille. Les graphiques Sunburst et Treemap offrent une vue multicouche, décomposant votre exposition du Secteur global jusqu'à l'Actif spécifique."
    st.markdown(f"<div class='info-text'>{desc_tab2}</div>", unsafe_allow_html=True)
    
    pos_data = [{"Symbol": "CASH", "Market Value ($)": cash, "Weight (%)": (cash/equity)*100, "Unrealized P&L ($)": 0.0, "Unrealized P&L (%)": 0.0, "Current Price": 1.0, "Avg Entry": 1.0, "Sector": "Cash Reserve"}]
    
    if positions:
        pos_data += [{"Symbol": p.symbol, "Market Value ($)": float(p.market_value), "Weight (%)": (float(p.market_value) / equity) * 100, "Unrealized P&L ($)": float(p.unrealized_pl), "Unrealized P&L (%)": float(p.unrealized_plpc) * 100, "Current Price": float(p.current_price), "Avg Entry": float(p.avg_entry_price), "Sector": SECTOR_MAP.get(p.symbol, 'Other')} for p in positions]
    
    df_pos = pd.DataFrame(pos_data)
    df_pos = df_pos.sort_values(by="Market Value ($)", ascending=False).reset_index(drop=True)
    
    active_pos_count = len(positions)
    top_sector = df_pos.groupby('Sector')['Market Value ($)'].sum().idxmax()
    top_asset = df_pos.iloc[0]['Symbol'] if active_pos_count > 0 else "CASH"
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Active Assets" if not is_fr else "Actifs en cours", f"{active_pos_count}")
    m2.metric("Dominant Sector" if not is_fr else "Secteur Dominant", top_sector)
    m3.metric("Largest Holding" if not is_fr else "Plus Grosse Position", top_asset)
    st.write("---")

    view_type = st.radio("Visualization Mode:" if not is_fr else "Mode de Visualisation :", ["Sunburst Chart (Multi-Layer)", "Nested Treemap (Heatmap)"], horizontal=True)
    
    hover_temp = '<b>%{label}</b><br>Value: $%{value:,.2f}<br>P&L: %{color:.2f}%<extra></extra>' if not is_fr else '<b>%{label}</b><br>Valeur: $%{value:,.2f}<br>P&L: %{color:.2f}%<extra></extra>'

    if view_type == "Sunburst Chart (Multi-Layer)":
        fig_map = px.sunburst(df_pos, path=['Sector', 'Symbol'], values='Market Value ($)', color='Unrealized P&L (%)', color_continuous_scale='RdYlGn', color_continuous_midpoint=0, hover_data=['Weight (%)'])
        fig_map.update_traces(hovertemplate=hover_temp)
    else:
        fig_map = px.treemap(df_pos, path=['Sector', 'Symbol'], values='Market Value ($)', color='Unrealized P&L (%)', color_continuous_scale='RdYlGn', color_continuous_midpoint=0, hover_data=['Weight (%)'])
        fig_map.update_traces(hovertemplate=hover_temp)
        
    fig_map.update_layout(template='plotly_dark', margin=dict(t=10, l=0, r=0, b=0), height=500)
    st.plotly_chart(fig_map, use_container_width=True)
    
    st.markdown("### Full Holdings Ledger" if not is_fr else "### Grand Livre des Positions")
    
    df_display = df_pos.copy()
    if is_fr:
        df_display = df_display.rename(columns={
            "Symbol": "Symbole", 
            "Market Value ($)": "Valeur ($)", 
            "Weight (%)": "Poids (%)", 
            "Unrealized P&L ($)": "P&L Latent ($)", 
            "Unrealized P&L (%)": "P&L Latent (%)", 
            "Current Price": "Prix Actuel", 
            "Avg Entry": "Prix d'Entrée", 
            "Sector": "Secteur"
        })
        st.dataframe(df_display.style.format({"Valeur ($)": "${:,.2f}", "Poids (%)": "{:.2f}%", "P&L Latent ($)": "${:,.2f}", "P&L Latent (%)": "{:.2f}%", "Prix Actuel": "${:,.2f}", "Prix d'Entrée": "${:,.2f}"}).background_gradient(subset=['P&L Latent (%)'], cmap='RdYlGn'), use_container_width=True)
    else:
        st.dataframe(df_display.style.format({"Market Value ($)": "${:,.2f}", "Weight (%)": "{:.2f}%", "Unrealized P&L ($)": "${:,.2f}", "Unrealized P&L (%)": "{:.2f}%", "Current Price": "${:,.2f}", "Avg Entry": "${:,.2f}"}).background_gradient(subset=['Unrealized P&L (%)'], cmap='RdYlGn'), use_container_width=True)


# ==========================================
# TAB 3: EXTREMES & ALPHA ATTRIBUTION
# ==========================================
with tab3:
    st.subheader("Performance Extremes & True Edge Discovery" if not is_fr else "Extrêmes de Performance & Découverte de l'Alpha")
    
    desc_tab3 = "This tab separates your <b>Active Trades</b> (Sprint) from your <b>Historical Edge</b> (Marathon). It helps identify which assets generate consistent returns over time versus short-term momentum." if not is_fr else "Cet onglet sépare vos <b>Trades Actifs</b> (Sprint) de votre <b>Avantage Historique</b> (Marathon). Il aide à identifier les actifs générant de la performance sur le long terme par rapport aux fluctuations à court terme."
    st.markdown(f"<div class='info-text'>{desc_tab3}</div>", unsafe_allow_html=True)
    
    if positions:
        df_real = df_pos[df_pos['Symbol'] != "CASH"].sort_values(by="Unrealized P&L (%)", ascending=False)
        if not df_real.empty:
            top_perf, worst_perf = df_real.iloc[0], df_real.iloc[-1]
            
            col_w, col_l = st.columns(2)
            with col_w:
                st.success("🟢 **BEST ACTIVE POSITION (Sprint)**" if not is_fr else "🟢 **MEILLEURE POSITION ACTIVE (Sprint)**")
                st.metric(label=top_perf['Symbol'], value=f"${top_perf['Market Value ($)']:,.2f}", delta=f"{top_perf['Unrealized P&L (%)']:.2f}% (${top_perf['Unrealized P&L ($)']:,.2f})")
                st.markdown(f"- **Sector:** {top_perf['Sector']} | **Weight:** {top_perf['Weight (%)']:.1f}%" if not is_fr else f"- **Secteur:** {top_perf['Sector']} | **Poids:** {top_perf['Weight (%)']:.1f}%")
            with col_l:
                st.error("🔴 **WORST ACTIVE POSITION (Sprint)**" if not is_fr else "🔴 **PIRE POSITION ACTIVE (Sprint)**")
                st.metric(label=worst_perf['Symbol'], value=f"${worst_perf['Market Value ($)']:,.2f}", delta=f"{worst_perf['Unrealized P&L (%)']:.2f}% (${worst_perf['Unrealized P&L ($)']:,.2f})")
                st.markdown(f"- **Sector:** {worst_perf['Sector']} | **Weight:** {worst_perf['Weight (%)']:.1f}%" if not is_fr else f"- **Secteur:** {worst_perf['Sector']} | **Poids:** {worst_perf['Weight (%)']:.1f}%")
            
    st.write("---")
    st.markdown("#### All-Time Profit by Asset (Marathon)" if not is_fr else "#### Profit Total par Actif (Marathon)")
    st.caption("Combines realized and unrealized gains. Identifies the real drivers of your edge." if not is_fr else "Combine les gains réalisés et non réalisés. Identifie les vrais moteurs de votre performance.")
    
    activities = fetch_trade_activities()
    if activities:
        df_act = pd.DataFrame(activities)
        df_act['cash_flow'] = df_act.apply(lambda x: x['qty'] * x['price'] * (-1 if x['side'] == 'buy' else 1), axis=1)
        pnl_tracker = df_act.groupby('symbol')['cash_flow'].sum()
        
        for p in positions:
            pnl_tracker[p.symbol] = pnl_tracker.get(p.symbol, 0) + float(p.market_value)
            
        pnl_tracker = pnl_tracker.sort_values(ascending=True)
        
        fig_attr = px.bar(pnl_tracker, x=pnl_tracker.values, y=pnl_tracker.index, orientation='h', color=pnl_tracker.values, color_continuous_scale='RdYlGn', color_continuous_midpoint=0)
        
        hover_temp_bar = '<b>%{y}</b><br>Net P&L: $%{x:,.2f}<extra></extra>' if not is_fr else '<b>%{y}</b><br>P&L Net: $%{x:,.2f}<extra></extra>'
        fig_attr.update_traces(hovertemplate=hover_temp_bar)
        
        fig_attr.update_layout(template='plotly_dark', height=400, xaxis_title="Net Profit/Loss ($)" if not is_fr else "Profit/Perte Net ($)", yaxis_title="", margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_attr, use_container_width=True)
    else:
        st.info("Not enough history to compute alpha attribution." if not is_fr else "Pas assez d'historique pour calculer l'attribution d'alpha.")


# ==========================================
# TAB 4: EXECUTION TAPE & NEWS
# ==========================================
with tab4:
    st.subheader("🧾 " + ("Journal d'Exécution, Logs & Actualités" if is_fr else "Execution Ledger, Logs & News"))
    
    desc_tab4 = "Monitor the algorithm's pulse. This tab provides a transparent audit trail of raw market orders, live system logs for technical health, and real-time news for your top holdings to understand the macro context." if not is_fr else "Surveillez le pouls de l'algorithme. Cet onglet fournit une piste d'audit transparente des ordres de marché, les logs du système en direct pour surveiller sa santé technique, et les actualités en temps réel de vos principales positions."
    st.markdown(f"<div class='info-text'>{desc_tab4}</div>", unsafe_allow_html=True)
    
    col_tape, col_news = st.columns([1.2, 1])
    
    with col_tape:
        # EXECUTION LEDGER
        st.markdown("### 📝 " + ("Dernières Transactions" if is_fr else "Recent Market Orders"))
        activities = fetch_trade_activities()
        if activities:
            logs = []
            for a in activities[:15]:
                logs.append({
                    "Date": pd.to_datetime(a['date']).strftime('%Y-%m-%d %H:%M'), 
                    "Action": "🟢 ACHAT" if a['side'] == 'buy' and is_fr else "🟢 BUY" if a['side'] == 'buy' else ("🔴 VENTE" if is_fr else "🔴 SELL"), 
                    "Symbole" if is_fr else "Ticker": a['symbol'], 
                    "Prix" if is_fr else "Price": f"${a['price']:.2f}", 
                    "Qté" if is_fr else "Qty": a['qty']
                })
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
        st.markdown("### 📡 " + ("Contexte Macro (Top 3 Actifs)" if is_fr else "Market Context (Top 3 Holdings)"))
        if positions:
            top_3 = sorted(positions, key=lambda x: float(x.market_value), reverse=True)[:3]
            for p in top_3:
                st.markdown(f"**{'Actualités pour' if is_fr else 'News for'} {p.symbol}**")
                news_items = get_recent_news(p.symbol)
                if news_items:
                    for n in news_items:
                        st.markdown(f"- [{n['title']}]({n['link']}) *(Yahoo Finance, {n['date']})*")
                else:
                    st.caption("Aucune actualité récente." if is_fr else "No recent news found.")
                st.write("---")
        else:
            st.info("Portefeuille en Cash. Aucune actualité spécifique." if is_fr else "Portfolio in Cash. No specific news.")

# ==========================================
# TAB 5: MONTE CARLO FORECAST
# ==========================================
with tab5:
    st.subheader("Stochastic Portfolio Projection (1 Year)" if not is_fr else "Projection Stochastique du Portefeuille (1 An)")
    
    desc_tab5 = "This Monte Carlo simulation runs 100 random price paths for the next 252 trading days. It uses the historical volatility (16.29%) and CAGR (25.03%) from the strategy's audited backtest to project potential future equity. The top line represents a highly optimistic scenario (top 5%), the middle is the median expectation, and the bottom is the pessimistic scenario (bottom 5%)." if not is_fr else "Cette simulation Monte Carlo génère 100 trajectoires de prix aléatoires pour les 252 prochains jours de bourse. Elle utilise la volatilité historique (16.29%) et le CAGR (25.03%) audités du backtest pour projeter le capital futur. La ligne supérieure représente le scénario très optimiste (top 5%), la ligne du milieu l'attente médiane, et la ligne inférieure le scénario pessimiste (bottom 5%)."
    st.markdown(f"<div class='info-text'>{desc_tab5}</div>", unsafe_allow_html=True)
    
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

# ==========================================
# TAB 6: GLOBAL RADAR
# ==========================================
with tab6:
    st.subheader("Live Score Radar" if not is_fr else "Radar de Scores en Direct")
    
    # On définit l'univers ici pour éviter le NameError
    radar_universe = ['NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'AAPL', 'TSLA', 'SMH', 'LLY', 'UNH', 'XLE', 'COPX', 'URA', 'ITA', 'XLI', 'RTX', 'BTC-USD', 'SPY']
    
    desc_tab6 = "This radar mathematically ranks assets by dividing their 6-month Momentum by their 3-month Volatility." if not is_fr else "Ce radar classe mathématiquement les actifs en divisant leur Momentum sur 6 mois par leur Volatilité sur 3 mois."
    st.markdown(f"<div class='info-text'>{desc_tab6}</div>", unsafe_allow_html=True)

    col_chart, col_data = st.columns([1.5, 1])

    with col_chart:
        st.markdown("#### 📊 Technical Analysis")
        tv_widget_html = """
        <div class="tradingview-widget-container" style="height:600px;width:100%;">
          <div id="tradingview_chart" style="height:100%;width:100%;"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({
            "autosize": true,
            "symbol": "SPY",
            "interval": "D",
            "timezone": "Etc/UTC",
            "theme": "dark",
            "style": "1",
            "locale": "en",
            "toolbar_bg": "#f1f3f6",
            "enable_publishing": false,
            "withdateranges": true,
            "hide_side_toolbar": false,
            "allow_symbol_change": true,
            "container_id": "tradingview_chart"
          });
          </script>
        </div>
        """
        st.components.v1.html(tv_widget_html, height=620)

    with col_data:
        st.markdown("#### 🎯 Momentum Ranking")
        with st.spinner("Analyzing market matrix..."):
            start_d = (datetime.now() - timedelta(days=200)).strftime('%Y-%m-%d')
            # On utilise radar_universe qu'on vient de définir
            df_mkt = fetch_radar_data(radar_universe, start_d)
            
            if not df_mkt.empty:
                scores = []
                for t in radar_universe:
                    if t in df_mkt.columns:
                        p = df_mkt[t]
                        if len(p) > 60:
                            mom = (p.iloc[-1] / p.iloc[-60]) - 1
                            vol = p.pct_change().std() * np.sqrt(252)
                            scores.append({
                                "Asset" if not is_fr else "Actif": t, 
                                "Score": mom / vol if vol > 0 else 0
                            })
                
                df_scores = pd.DataFrame(scores).sort_values("Score", ascending=False).reset_index(drop=True)
                df_scores.index += 1
                
                st.dataframe(
                    df_scores.style.format({"Score": "{:.2f}"})
                    .background_gradient(subset=['Score'], cmap='RdYlGn'), 
                    use_container_width=True,
                    height=580 
                )

# ==========================================
# TAB 7: STRATEGY DEEP DIVE (THEORY & LOGIC)
# ==========================================
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
